# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic credentials are assembled at runtime, never stored verbatim."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pattern_scan

SCRIPT = Path(__file__).with_name('pattern_scan.py').resolve()
OC_NAME = 'O' + 'C'
VALUE = 'aB3dE6gH9jK2' + 'mN5pQ8sT1vW4yZ7'


class PatternTests(unittest.TestCase):
    def rules(self, text):
        return {rule for _, rule in pattern_scan.findings(text)}

    def test_provider_shapes(self):
        for prefix in ('ghp', 'gho', 'ghu', 'ghs', 'ghr', 'github_pat'):
            with self.subTest(prefix=prefix):
                self.assertIn('github-token', self.rules(prefix + '_' + VALUE * 2))
        self.assertIn('huggingface-token', self.rules('hf' + '_' + VALUE * 2))
        self.assertIn('aws-access-key', self.rules('AK' + 'IA' + 'A1B2C3D4' * 2))
        for kind in ('', 'RSA ', 'EC ', 'DSA ', 'OPENSSH ', 'ENCRYPTED '):
            self.assertIn('private-key', self.rules('-----BEGIN ' + kind + 'PRIVATE KEY' + '-----'))

    def test_oc_url_and_assignments(self):
        for text in ('https://law.go.kr/DRF?' + OC_NAME + '=' + VALUE + '&target=law',
                     OC_NAME + '=' + VALUE, '"' + OC_NAME.lower() + '": "' + VALUE + '"', "'" + OC_NAME + "': '" + VALUE + "'"):
            self.assertIn('law-oc', self.rules(text))

    def test_generic_assignments(self):
        for key in ('api_key', 'api-key', 'apikey', 'service_key', 'service-key',
                    'secret', 'token', 'password', 'client_secret', 'access_token'):
            for separator in ('=', ': '):
                self.assertIn('generic-secret', self.rules(key + separator + '"' + VALUE + '"'))
        self.assertFalse(self.rules('password=' + 'a' * 40))
        self.assertFalse(self.rules('token=short'))

    def test_typed_assignments(self):
        for name, rule in (('token', 'generic-secret'), ('apiKey', 'generic-secret'),
                           (OC_NAME, 'law-oc')):
            for annotation in ('str', 'Final[str]', 'Optional[str]', 'string',
                               'typing.Final[Optional[str]]'):
                for quote in ('"', "'"):
                    prefix = name + ': ' + annotation + ' = '
                    self.assertEqual(self.rules(prefix + quote + VALUE + quote), {rule})
                    self.assertFalse(self.rules(prefix + quote + '${LAW_OC}' + quote))
                    self.assertFalse(self.rules(prefix + quote + 'example' + quote))
        self.assertFalse(self.rules('token: Optional[str]'))
        self.assertFalse(self.rules('token: string = "short"'))

    def test_environment_references_are_whole_values(self):
        references = ('$NAME', '${NAME}', '$env:NAME', '%NAME%',
                      '${{ secrets.LAW_OC }}', '${{ env.LAW_OC }}')
        for value in references:
            self.assertTrue(pattern_scan.placeholder(value))
            for quote in ('', '"', "'"):
                self.assertFalse(self.rules(OC_NAME + '=' + quote + value + quote))
        for value in ('$' + VALUE + '!/', '${NAME}' + VALUE, '$env:NAME/' + VALUE,
                      '%NAME%' + VALUE, '${bad reference}' + VALUE):
            self.assertFalse(pattern_scan.placeholder(value))
            for quote in ('', '"', "'"):
                self.assertEqual(self.rules('token=' + quote + value + quote), {'generic-secret'})
                self.assertEqual(self.rules(OC_NAME + '=' + quote + value + quote), {'law-oc'})

    def test_default_inspect_forms(self):
        names = ('clientSecret', 'accessToken', 'ApiKey', 'serviceKey',
                 'X_API_KEY', 'prefix_api_key', 'prefix-api-key',
                 'PrefixApiKey', 'prefix.api.key', 'privateKey', 'passwd')
        for name in names:
            for operator in ('=', ':=', ':', '=>', '->', '?='):
                for prefix in ('', 'b', 'r', 'u', 'f', 'br', 'rb', 'BR', 'rB'):
                    with self.subTest(name=name, operator=operator, prefix=prefix):
                        self.assertEqual(self.rules(name + operator + prefix + repr(VALUE)),
                                         {'generic-secret'})
        for name in (OC_NAME, 'law_' + OC_NAME.lower(), 'law' + OC_NAME.title()):
            for operator in (':-', '-', ':=', ':+', '=', '+'):
                value = '${NAME' + operator + VALUE + '}'
                for quote in ('', '"', "'", '`'):
                    self.assertEqual(self.rules(name + '=' + quote + value + quote), {'law-oc'})
        for operator in (':-', '-', ':=', ':+', '=', '+'):
            self.assertEqual(self.rules('token' + '=${TOKEN' + operator + VALUE + '}'), {'generic-secret'})
        for prefix in ('clientSecret: string = ', 'accessToken = ', 'token: bytes = b',
                       'token = rb', 'token = ', '"token": '):
            self.assertEqual(self.rules(prefix + '"' + VALUE + '"'), {'generic-secret'})
        self.assertEqual(self.rules('token = `' + VALUE + '`'), {'generic-secret'})
        self.assertEqual(self.rules('token = `prefix${variable}' + VALUE + '`'), {'generic-secret'})
        # Inspect all candidates, including literals following calls or placeholders.
        for rhs in ('lookup("***", "' + VALUE + '")', '"***" + "' + VALUE + '"',
                    '"***", other="' + VALUE + '"', 'factory(' + repr(VALUE) + ')'):
            self.assertEqual(self.rules('token = ' + rhs), {'generic-secret'})

    def test_default_inspect_negatives(self):
        for name in ('tokenizer', 'protocol', 'location', 'myTokenizer', 'socket'):
            self.assertFalse(self.rules(name + ' = "' + VALUE + '"'))
        for value in ('${TOKEN}', '${TOKEN:-}', '${TOKEN:-${OTHER}}',
                      '${TOKEN:-***}', '${TOKEN:-<value>}', '${TOKEN:-FAKE}',
                      '${TOKEN:-YOUR_KEY}', '${TOKEN:-example}', ''):
            for name in ('token', OC_NAME):
                for quote in ('', '"', "'", '`'):
                    self.assertFalse(self.rules(name + '=' + quote + value + quote))
        for text in ('An ordinary prose sentence about access tokens.',
                     'The tokenizer: processes words, not credentials.',
                     'A secret is never printed.', 'token: Optional[str]'):
            self.assertFalse(self.rules(text))

    def test_quoted_shell_operands(self):
        for operator in (':-', '-', ':=', ':+', '=', '+'):
            for quote in ('"', "'"):
                for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
                    prefix = name + '=${NAME' + operator + quote
                    for value in ('${OTHER}', '$OTHER', 'example', '<value>', '***'):
                        with self.subTest(operator=operator, quote=quote, value=value):
                            self.assertFalse(self.rules(prefix + value + quote + '}'))
                    self.assertEqual(self.rules(prefix + VALUE + quote + '}'), {rule})

    def test_shell_hash_word_boundaries(self):
        self.assertEqual(list(pattern_scan.candidates('x # comment')), ['x'])
        self.assertEqual(list(pattern_scan.candidates('#' + VALUE, comment_at_start=False)),
                         ['#' + VALUE])
        for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
            for value in ('#' + VALUE, VALUE + '#' + VALUE):
                self.assertEqual(self.rules(name + '=' + value), {rule})
            self.assertFalse(self.rules(name + '=example # ' + VALUE))
            self.assertFalse(self.rules(name + '= # ' + VALUE))
            self.assertEqual(self.rules(name + '="' + '#' + VALUE + '"'), {rule})

    def test_literal_subscript_targets(self):
        for target in ('config', 'os.environ', 'settings.credentials'):
            for quote in ('"', "'"):
                for name, rule in (('token', 'generic-secret'), (OC_NAME, 'law-oc'),
                                   ('API_KEY', 'generic-secret')):
                    prefix = target + '[' + quote + name + quote + '] = '
                    self.assertEqual(self.rules(prefix + repr(VALUE)), {rule})
                    for value in ('example', '${NAME}', '***'):
                        self.assertFalse(self.rules(prefix + repr(value)))
                self.assertFalse(self.rules(target + '[' + quote + 'monkey' + quote
                                            + '] = ' + repr(VALUE)))
        self.assertFalse(self.rules('config[token] = ' + repr(VALUE)))

    def test_escape_aware_quote_boundaries(self):
        slash = chr(92)
        for prelude in ('echo "say ' + slash + '"hi"; ',
                        "echo 'say " + slash + "'hi'; ",
                        'echo "say ""hi"; ', 'echo "say ' + slash * 3 + '"hi"; '):
            with self.subTest(prelude=prelude):
                self.assertEqual(self.rules(prelude + 'token="' + VALUE + '"'),
                                 {'generic-secret'})
                self.assertFalse(self.rules(prelude + 'token="example"'))
        for quote in ('"', "'"):
            escaped = VALUE[:12] + '\\' + quote + VALUE[12:]
            self.assertEqual(self.rules('token=' + quote + escaped + quote),
                             {'generic-secret'})
        # An assignment embedded in a string must not consume the next statement.
        self.assertFalse(self.rules('echo "token=example"; other="' + VALUE + '"'))
        self.assertFalse(self.rules('echo "say \\"hi token=example"; other="' + VALUE + '"'))

    def test_provider_placeholder_wrappers(self):
        providers = ('ghp' + '_' + VALUE * 2, 'hf' + '_' + VALUE * 2,
                     'AK' + 'IA' + 'A1B2C3D4' * 2)
        for value, rule in zip(providers, ('github-token', 'huggingface-token', 'aws-access-key')):
            for wrapper in ('<{}>', '***{}', '{}***', 'FAKE_{}', '{}_FAKE'):
                for quote in ('', '"', "'"):
                    with self.subTest(rule=rule, wrapper=wrapper, quote=quote):
                        self.assertFalse(self.rules('token=' + quote + wrapper.format(value) + quote))
            self.assertIn(rule, self.rules('token=' + value))
            self.assertIn(rule, self.rules('Documentation mentions ' + value))
            self.assertIn(rule, self.rules('print("' + value + '")'))
            self.assertIn(rule, self.rules('token=<example>; print("' + value + '")'))
            self.assertIn(rule, self.rules('token=<example>; print("<' + value + '>")'))
            self.assertIn(rule, self.rules('print("token=example", "<' + value + '>")'))

    def test_conventional_secret_key_names(self):
        for name in ('AWS_SECRET_ACCESS_KEY', 'secretKey', 'SECRET_KEY',
                     'accessKey', 'private_key', 'prefixSecretSigningKey',
                     'secretkey', 'ACCESSKEY'):
            self.assertEqual(self.rules(name + '=' + repr(VALUE)), {'generic-secret'})
            self.assertFalse(self.rules(name + '="example"'))
        for name in ('key', 'monkey', 'keyword', 'secretaryKey', 'privateKeyboard'):
            self.assertFalse(self.rules(name + '=' + repr(VALUE)))

    def test_compound_assignment_operators(self):
        for operator in ('??=', '||=', '&&=', '+='):
            for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
                with self.subTest(operator=operator, name=name):
                    self.assertEqual(self.rules(name + operator + repr(VALUE)), {rule})
                    for value in ('example', '${NAME}', '***'):
                        self.assertFalse(self.rules(name + operator + repr(value)))
            self.assertFalse(self.rules('monkey' + operator + repr(VALUE)))

    def test_bomless_utf16_and_binary(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            for encoding in ('utf-16-le', 'utf-16-be'):
                for text, expected in (
                    ('first\n' + OC_NAME + '=' + VALUE, [("'sample.dat'", 2, 'law-oc')]),
                    ('first\ntoken: str = "' + VALUE + '"', [("'sample.dat'", 2, 'generic-secret')]),
                    ('first\n' + 'ghp' + '_' + VALUE * 2, [("'sample.dat'", 2, 'github-token')]),
                    ('first\n' + OC_NAME + '=${NAME:-}', []),
                    ('ordinary text\nno credentials', []),
                ):
                    (root / 'sample.dat').write_bytes(text.encode(encoding))
                    with patch.object(pattern_scan, 'repository_files', return_value=(root, ['sample.dat'])):
                        self.assertEqual(pattern_scan.scan(root), expected)
            # Image-like bytes, NUL-heavy noise, and malformed UTF-16 must stay safe.
            for data in (b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 4,
                         b'\0' * 200, b'\xff\xfe\0', b'\xfe\xff\0',
                         b'\0\xd8' * 50, b'\xd8\0' * 50):
                (root / 'sample.dat').write_bytes(data)
                with patch.object(pattern_scan, 'repository_files', return_value=(root, ['sample.dat'])):
                    self.assertEqual(pattern_scan.scan(root), [])

    def test_placeholders_and_environment(self):
        for value in ('***', '<value>', 'example', 'FAKE', 'NOT-A-REAL',
                      'YOUR_KEY', '${LAW_OC}', '$LAW_OC', '%LAW_OC%',
                      '${{ secrets.LAW_OC }}', 'os.environ["LAW_OC"]',
                      'os.getenv("LAW_OC")', 'process.env.LAW_OC'):
            with self.subTest(value=value):
                self.assertFalse(self.rules(OC_NAME + '=' + value))
        self.assertFalse(self.rules('protocol=ordinary'))
        self.assertFalse(self.rules('hf' + '_short'))

    def test_tracked_cli_masking_and_utf16(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', temp, 'init', '-q'], check=True, capture_output=True)
            (root / 'tracked.dat').write_text('first\nOC=' + VALUE, encoding='utf-16')
            (root / 'untracked.dat').write_text(OC_NAME + '=' + VALUE, encoding='utf-8')
            subprocess.run(['git', '-C', temp, 'add', '--', 'tracked.dat'], check=True, capture_output=True)
            result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], cwd=temp,
                                    env=dict(os.environ, **{'LAW_O' + 'C': ''}, LAW_OC_FILE='must-not-open'),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("'tracked.dat':2: law-oc [masked]", result.stdout)
            self.assertNotIn(VALUE, result.stdout + result.stderr)
            self.assertNotIn('untracked.dat', result.stdout)

    def test_korean_bomless_utf16_cli(self):
        surrounding = '한글 문서의 일반 설명입니다. ' * 100
        provider = 'ghp' + '_' + VALUE * 2
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', temp, 'init', '-q'], check=True, capture_output=True)
            sample = root / 'tracked.dat'
            sample.write_bytes(b'')
            subprocess.run(['git', '-C', temp, 'add', '--', sample.name],
                           check=True, capture_output=True)
            for encoding in ('utf-16-le', 'utf-16-be'):
                for payload, expected in (
                    (provider, 'github-token'),
                    ('token = "' + VALUE + '"', 'generic-secret'),
                    ('비밀 값이 없는 평범한 문서입니다.', None),
                ):
                    with self.subTest(encoding=encoding, rule=expected):
                        data = (surrounding + '\n' + payload + '\n' + surrounding).encode(encoding)
                        # Both lanes stay below the old ASCII-heavy threshold.
                        for lane in (data[::2], data[1::2]):
                            self.assertLess(lane.count(0) / len(lane), 0.6)
                        sample.write_bytes(data)
                        result = subprocess.run(
                            [sys.executable, '-I', '-B', str(SCRIPT)], cwd=temp,
                            env=dict(os.environ, **{'LAW_O' + 'C': ''}, LAW_OC_FILE='must-not-open'),
                            capture_output=True, text=True)
                        output = result.stdout + result.stderr
                        self.assertNotIn(VALUE, output)
                        self.assertNotIn(provider, output)
                        self.assertEqual(result.returncode, 1 if expected else 0)
                        if expected:
                            self.assertIn("'tracked.dat':2: " + expected + ' [masked]', output)
                            self.assertIn('Pattern scan: 1 finding(s).', output)
                        else:
                            self.assertIn('Pattern scan: 0 finding(s).', output)

    def test_patterns_never_select_credentials(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            with patch.object(pattern_scan, 'repository_files', return_value=(root, [])), \
                    patch('secret_scan.selected_key', side_effect=AssertionError('must not select credentials')):
                self.assertEqual(pattern_scan.scan(root), [])

    def test_safe_diagnostics_and_read_failure(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            name = 'ghp' + '_' + VALUE * 2
            (root / name).mkdir()
            with patch.object(pattern_scan, 'repository_files', return_value=(root, [name])):
                with self.assertRaises(pattern_scan.ScanError) as caught:
                    pattern_scan.scan(root)
            self.assertNotIn(VALUE, str(caught.exception))
            self.assertIn('[redacted path]', str(caught.exception))

    def test_allowlist_is_exact_path_rule_and_line(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            text = OC_NAME + '=' + VALUE
            (root / 'sample').write_text(text, encoding='utf-8')
            entry = ('sample', 'law-oc', hashlib.sha256(text.encode()).hexdigest())
            with patch.object(pattern_scan, 'repository_files', return_value=(root, ['sample'])), \
                    patch.object(pattern_scan, 'ALLOWLIST', {entry}):
                self.assertEqual(pattern_scan.scan(root), [])
                (root / 'sample').write_text(text + 'x', encoding='utf-8')
                self.assertEqual(len(pattern_scan.scan(root)), 1)


if __name__ == '__main__':
    unittest.main()
