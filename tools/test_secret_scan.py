# SPDX-License-Identifier: GPL-3.0-only
"""Value-based credential checks use synthetic values and temporary Git repos."""
import base64
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
import secret_scan
import validate

SCRIPT = Path(__file__).with_name('secret_scan.py').resolve()
KEY = 'Synthetic' + ':Oc /+한?Value9'


class SecretScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.env = dict(os.environ, **{'LAW_O' + 'C': KEY})

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True).stdout

    def write(self, data, name='sample.dat', *, tracked=True):
        path = self.root / name
        path.write_bytes(data)
        if tracked:
            self.git('add', '--', name)
        return path

    def run_scan(self, *args, env=None, cwd=None):
        result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), *args],
                                cwd=cwd or self.root, env=self.env if env is None else env,
                                capture_output=True, text=True)
        # Never include match content in assertion messages or diagnostics.
        with patch.dict(os.environ, self.env if env is None else env, clear=True):
            try:
                needles = secret_scan.environment_needles() or []
            except secret_scan.ScanError:
                needles = []
        output = (result.stdout + result.stderr).encode('utf-8')
        for _, needle in needles:
            self.assertNotIn(needle, output)
        return result

    def assert_encoding(self, data, encoding):
        self.write(data)
        result = self.run_scan('--require')
        self.assertEqual(result.returncode, 1)
        self.assertIn('sample.dat', result.stdout)
        self.assertIn(': ' + encoding, result.stdout)
        self.assertEqual(result.stderr, '')

    def test_raw_utf8(self):
        self.assert_encoding(b'prefix ' + KEY.encode() + b' suffix', 'utf-8')

    def test_url_quote(self):
        self.assert_encoding(quote(KEY, safe='').encode(), 'url-quote')

    def test_url_quote_plus(self):
        self.assert_encoding(quote_plus(KEY, safe='').encode(), 'url-quote-plus')

    def test_utf16_little_endian(self):
        self.assert_encoding(('prefix' + KEY + 'suffix').encode('utf-16-le'), 'utf-16-le')

    def test_utf16_big_endian(self):
        self.assert_encoding(('prefix' + KEY + 'suffix').encode('utf-16-be'), 'utf-16-be')

    def test_hex_lowercase(self):
        self.assert_encoding(KEY.encode().hex().encode(), 'hex-lower')

    def test_hex_uppercase(self):
        self.assert_encoding(KEY.encode().hex().upper().encode(), 'hex-upper')

    def test_base64_standard_all_alignments(self):
        for offset in range(3):
            with self.subTest(offset=offset):
                data = base64.b64encode(b'x' * (6 + offset) + KEY.encode() + b'\xffsuffix')
                self.assert_encoding(data, f'base64-offset-{offset}')

    def test_base64_urlsafe_all_alignments(self):
        for offset in range(3):
            with self.subTest(offset=offset):
                data = base64.urlsafe_b64encode(b'x' * (6 + offset) + KEY.encode() + b'\xffsuffix')
                self.assert_encoding(data, f'base64url-offset-{offset}')

    def test_short_base64_fragments_do_not_reject_unrelated_text(self):
        env = dict(self.env, **{'LAW_O' + 'C': 'abcd'})
        self.write(b'ordinary text FiY2 YWJjZ GJjZA')
        self.assertEqual(self.run_scan('--require', env=env).returncode, 0)
        with patch.dict(os.environ, env):
            needles = secret_scan.environment_needles()
        self.assertEqual(secret_scan.redact_diagnostic('ordinary FiY2 token', needles), 'ordinary FiY2 token')
        self.assertFalse(any('-offset-' in name for name, _ in needles))

    def test_short_keys_keep_full_base64_and_only_meaningful_fragments(self):
        for length in range(4, 9):
            key = ('Q7+xY/' * 2)[:length]
            env = dict(self.env, **{'LAW_O' + 'C': key})
            with patch.dict(os.environ, env):
                needles = secret_scan.environment_needles()
            self.assertTrue(all(len(needle) >= 8 for name, needle in needles if '-offset-' in name))
            for encode in (base64.b64encode, base64.urlsafe_b64encode):
                for data in (encode(key.encode()), encode(key.encode()).rstrip(b'=')):
                    with self.subTest(length=length):
                        self.write(data)
                        self.assertEqual(self.run_scan('--require', env=env).returncode, 1)
                        self.assertEqual(secret_scan.redact_diagnostic(data.decode(), needles), '[redacted]')

    def test_base64_boundaries_for_different_key_lengths(self):
        # Exercise every ending remainder and neighbours that change both
        # boundary sextets; verify unpadded and standalone forms as well.
        for length in range(7, 13):
            key = ('Q7+xY/' * 3)[:length]
            with patch.dict(os.environ, {('LAW_O' + 'C' + ''): key}):
                needles = secret_scan.environment_needles()
            for offset in range(3):
                for encode in (base64.b64encode, base64.urlsafe_b64encode):
                    for suffix in (b'', b'\x00', b'\xffmore'):
                        blob = encode(b'\xff' * offset + key.encode() + suffix).rstrip(b'=')
                        self.assertTrue(any(needle in blob for name, needle in needles
                                            if name.startswith('base64')))

    def test_mime_base64_long_key_and_all_alignments(self):
        key = 'SyntheticLongOc7' * 8 + ':end'
        env = dict(self.env, **{'LAW_O' + 'C': key})
        for offset in range(3):
            with self.subTest(offset=offset):
                data = base64.encodebytes(b'x' * (51 + offset) + key.encode() + b'suffix')
                self.assertIn(b'\n', data[:-1])
                self.write(data)
                result = self.run_scan('--require', env=env)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'base64-offset-{offset}', result.stdout)

    def test_wrapped_urlsafe_base64_with_ascii_whitespace(self):
        for offset in range(3):
            with self.subTest(offset=offset):
                blob = base64.urlsafe_b64encode(b'\xff' * (51 + offset) + KEY.encode() + b'suffix')
                wrapped = b'\r\n \t'.join(blob[i:i + 76] for i in range(0, len(blob), 76))
                self.assert_encoding(wrapped, f'base64url-offset-{offset}')

    def test_base64_normalization_does_not_change_raw_matching(self):
        with patch.dict(os.environ, self.env):
            needles = secret_scan.environment_needles()
        raw = KEY.encode()
        split_raw = raw[:5] + b'\r\n \t' + raw[5:]
        self.assertNotIn('utf-8', list(secret_scan.matching_encodings(split_raw, needles)))

    def test_lowercase_and_mixed_case_url_escapes(self):
        for encode, label in ((quote, 'url-quote'), (quote_plus, 'url-quote-plus')):
            encoded = encode(KEY, safe='').encode()
            for form in ('lower', 'mixed'):
                with self.subTest(encoding=label, form=form):
                    transform = (lambda match: match[0].lower()) if form == 'lower' else (
                        lambda match: match[0][:2].lower() + match[0][2:].upper())
                    data = re.sub(rb'%[0-9A-F]{2}', transform, encoded)
                    self.assertNotEqual(data, encoded)
                    self.assert_encoding(data, label)

    def test_url_escape_normalization_preserves_credential_case(self):
        self.write(quote(KEY.swapcase(), safe='').encode())
        self.assertEqual(self.run_scan().returncode, 0)

    def test_empty_tracked_pathnames_are_scanned_without_echo(self):
        safe_key = 'PathOnly' + 'SyntheticOc7'
        cases = [(safe_key, safe_key),
                 (safe_key, safe_key.encode().hex()),
                 (safe_key, safe_key.encode().hex().upper()),
                 (safe_key, base64.b64encode(safe_key.encode()).decode()),
                 (safe_key, base64.urlsafe_b64encode(safe_key.encode()).decode()),
                 (KEY, re.sub(r'%[0-9A-F]{2}', lambda match: match[0].lower(), quote(KEY, safe='')))]
        for key, encoded in cases:
            with self.subTest(encoding_index=cases.index((key, encoded))):
                name = encoded + '.dat'
                path = self.write(b'', name)
                result = self.run_scan(env=dict(self.env, **{'LAW_O' + 'C': key}))
                self.assertEqual(result.returncode, 1)
                self.assertIn('[redacted path]', result.stdout)
                self.assertIn('(pathname)', result.stdout)
                self.assertNotIn(encoded, result.stdout + result.stderr)
                self.git('rm', '--cached', '--', name)
                path.unlink()

    def test_parent_directory_name_is_scanned(self):
        key = 'Directory' + 'SyntheticOc7'
        (self.root / key).mkdir()
        self.write(b'', key + '/empty.dat')
        result = self.run_scan(env=dict(self.env, **{'LAW_O' + 'C': key}))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(key, result.stdout + result.stderr)
        self.assertIn('(pathname)', result.stdout)

    def test_validator_aborts_before_parsing_detected_duplicate_keys(self):
        quoted = json.dumps(KEY, ensure_ascii=False)
        data = ('{' + quoted + ': 1, ' + quoted + ': 2}').encode()
        for name in ('duplicate.json', 'deps.lock'):
            with self.subTest(name=name):
                path = self.write(data, name)
                with patch.dict(os.environ, self.env), patch.object(validate, 'load_index') as load_index:
                    errors, warnings, count = validate.validate(self.root)
                load_index.assert_not_called()
                self.assertTrue(errors)
                self.assertTrue(all('LAW_OC exposure' in error for error in errors))
                self.assertTrue(all(KEY not in error for error in errors))
                self.assertEqual((warnings, count), ([], 0))
                result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT.with_name('validate.py'))],
                                        cwd=self.root, env=dict(self.env, KK_ROOT=str(self.root)),
                                        capture_output=True, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(KEY, result.stdout + result.stderr)
                self.assertNotIn('중복 JSON 키', result.stdout + result.stderr)
                self.assertIn('LAW_OC exposure', result.stdout)
                self.assertEqual(result.stderr, '')
                self.git('rm', '--cached', '--', name)
                path.unlink()

    def test_validator_redacts_diagnostics_outside_preflight(self):
        from tools.test_tools import fixture
        encoded = KEY.encode().hex()
        with fixture() as root, patch.dict(os.environ, self.env):
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            with patch.object(validate, 'load_index', side_effect=ValueError('duplicate key: ' + encoded)):
                errors, warnings, _ = validate.validate(root)
            self.assertIn('[redacted]', errors)
            self.assertTrue(all(encoded not in message and KEY not in message for message in errors + warnings))

    def test_untracked_encoded_duplicate_keys_abort_before_parsing(self):
        with patch.dict(os.environ, self.env):
            needles = secret_scan.environment_needles()
        forms = [KEY, quote(KEY, safe=''), quote_plus(KEY, safe=''), KEY.encode().hex(),
                 KEY.encode().hex().upper(), base64.b64encode(KEY.encode()).decode(),
                 base64.urlsafe_b64encode(KEY.encode()).decode()]
        forms += [re.sub(r'%[0-9A-F]{2}', lambda match: match[0].lower(), forms[1]),
                  ''.join(char.upper() if i % 2 else char for i, char in enumerate(forms[3]))]
        for number, value in enumerate(forms):
            with self.subTest(form=number):
                quoted = json.dumps(value, ensure_ascii=False)
                path = self.write(('{' + quoted + ': 1, ' + quoted + ': 2}').encode(), tracked=False)
                with patch.dict(os.environ, self.env), patch.object(validate, 'load_index') as load_index:
                    errors, warnings, count = validate.validate(self.root)
                load_index.assert_not_called()
                self.assertTrue(errors)
                self.assertTrue(all('LAW_OC exposure' in error for error in errors))
                self.assertEqual((warnings, count), ([], 0))
                result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT.with_name('validate.py'))],
                                        cwd=self.root, env=dict(self.env, KK_ROOT=str(self.root)),
                                        capture_output=True, encoding='utf-8')
                self.assertEqual(result.returncode, 1)
                output = (result.stdout + result.stderr).encode()
                for _, needle in needles:
                    self.assertNotIn(needle, output)
                self.assertNotIn(value, result.stdout + result.stderr)
                self.assertNotIn('중복 JSON 키', result.stdout)
                path.unlink()

    def test_diagnostic_redaction_covers_all_documented_needles_and_variants(self):
        key = 'Diagnostic' + 'Synthetic9:/ +X'
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): key}):
            needles = secret_scan.environment_needles()
        for number, (encoding, needle) in enumerate(needles):
            forms = [needle]
            if encoding.startswith('url-'):
                forms += [re.sub(rb'%[0-9A-F]{2}', lambda match: match[0].lower(), needle),
                          re.sub(rb'%[0-9A-F]{2}', lambda match: match[0][:2].lower() + match[0][2:].upper(), needle)]
            elif encoding.startswith('hex-'):
                forms += [bytes(char + 32 if i % 2 and 65 <= char <= 70 else char
                                for i, char in enumerate(needle.upper()))]
            elif encoding.startswith('base64'):
                forms += [b'\r\n \t'.join(needle[i:i + 5] for i in range(0, len(needle), 5))]
            for form in forms:
                with self.subTest(needle=number):
                    # ASCII synthetic key makes its UTF-16 byte forms valid
                    # UTF-8 strings too (including NULs) for this direct test.
                    message = 'diagnostic prefix: ' + form.decode() + ' :suffix'
                    self.assertEqual(secret_scan.redact_diagnostic(message, needles), '[redacted]')
        self.assertEqual(secret_scan.redact_diagnostic('ordinary contract error', needles), 'ordinary contract error')

    def test_surrounding_environment_whitespace_uses_canonical_key(self):
        import lawapi
        padded = ' \t' + KEY + '\t  '
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): KEY}):
            expected = secret_scan.environment_needles()
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): padded}):
            self.assertEqual(lawapi.key(), KEY)  # Environment present: no file fallback.
            self.assertEqual(secret_scan.environment_needles(), expected)
        for encoding, needle in expected:
            with self.subTest(encoding=encoding):
                self.write(needle)
                self.assertEqual(self.run_scan(env=dict(self.env, **{'LAW_O' + 'C': padded})).returncode, 1)
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): padded}):
            needles = secret_scan.environment_needles()
            self.assertEqual(secret_scan.redact_diagnostic('duplicate: ' + KEY.encode().hex(), needles), '[redacted]')
            with patch.object(secret_scan, 'environment_needles', wraps=secret_scan.environment_needles) as derive:
                errors, _, _ = validate.validate(self.root)
            derive.assert_called_once()
            self.assertTrue(any('LAW_OC exposure' in error for error in errors))

    def test_external_dependency_bytes_are_checked_before_parsing(self):
        self.write(json.dumps({'kapa_skills': {'commit': 'WORKTREE'}}).encode(), 'deps.lock')
        encoded = KEY.encode().hex()
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as directory:
            sibling = Path(directory)
            (sibling / 'docs').mkdir()
            (sibling / 'docs/law-index.json').write_text('{"schema": 1, "hidden": "' + encoded + '"}', encoding='utf-8')
            with patch.dict(os.environ, dict(self.env, KK_SKILLS_ROOT=str(sibling))):
                errors, warnings, count = validate.validate(self.root)
            self.assertTrue(any('LAW_OC exposure' in error for error in errors))
            self.assertEqual((warnings, count), ([], 0))
            self.assertTrue(all(encoded not in error and KEY not in error for error in errors))

    def test_pinned_dependency_snapshot_is_inspected_before_json(self):
        import common
        commit = 'a' * 40
        encoded = base64.b64encode(KEY.encode()).decode()
        raw = ('{"' + encoded + '": 1, "' + encoded + '": 2}').encode()
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as directory:
            with patch.dict(os.environ, dict(self.env, KK_SKILLS_ROOT=directory)):
                needles = secret_scan.environment_needles()
                def inspect(path, data):
                    self.assertEqual(path.name, 'law-index.json')
                    self.assertEqual(data, raw)
                    if next(secret_scan.matching_encodings(data, needles), None):
                        raise secret_scan.ScanError('Credential-bearing snapshot was not parsed.')
                read_text = lambda path: json.dumps({'kapa_skills': {'commit': commit}})
                result = subprocess.CompletedProcess([], 0, stdout=raw)
                with patch.object(common.subprocess, 'run', return_value=result):
                    with self.assertRaisesRegex(secret_scan.ScanError, 'snapshot was not parsed'):
                        common.load_index(self.root, read_text=read_text, inspect_bytes=inspect)

    def test_ignored_skill_files_are_not_opened_by_secondary_walks(self):
        from tools.test_tools import fixture
        with fixture() as root, patch.dict(os.environ, self.env):
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            (root / '.gitignore').write_text('local-only/\n', encoding='utf-8')
            (root / 'local-only').mkdir()
            ignored = root / 'local-only/SKILL.md'
            ignored.write_bytes(KEY.encode())
            read_bytes = Path.read_bytes
            def guarded(path):
                self.assertNotEqual(path, ignored)
                return read_bytes(path)
            with patch.object(Path, 'read_bytes', guarded):
                self.assertEqual(validate.validate(root)[0], [])

    def test_binary_file_is_not_skipped(self):
        self.assert_encoding(b'\xff\x00\xfe' + KEY.encode() + b'\x80\0', 'utf-8')

    def test_matching_is_case_sensitive(self):
        self.write(KEY.swapcase().encode())
        self.assertEqual(self.run_scan().returncode, 0)

    def test_untracked_files_require_worktree_option(self):
        self.write(KEY.encode(), 'untracked.dat', tracked=False)
        self.assertEqual(self.run_scan().returncode, 0)
        result = self.run_scan('--worktree')
        self.assertEqual(result.returncode, 1)
        self.assertIn('untracked.dat', result.stdout)

    def test_ignored_untracked_files_are_not_read(self):
        self.write(b'.env\n*.local\n', '.gitignore')
        self.write(KEY.encode(), '.env', tracked=False)
        self.write(KEY.encode(), 'private.local', tracked=False)
        self.assertEqual(self.run_scan().returncode, 0)
        self.assertEqual(self.run_scan('--worktree').returncode, 0)
        # Assert exclusion, not just a lack of matches after reading.
        read_bytes = Path.read_bytes
        def guarded(path):
            self.assertNotIn(path.name, {'.env', 'private.local'})
            return read_bytes(path)
        with patch.dict(os.environ, self.env), patch.object(Path, 'read_bytes', guarded):
            self.assertEqual(secret_scan.scan(self.root, worktree=True), [])

    def test_force_tracked_file_is_scanned_despite_ignore_pattern(self):
        self.write(b'*.local\n', '.gitignore')
        self.write(KEY.encode(), 'tracked.local', tracked=False)
        self.git('add', '-f', 'tracked.local')
        self.assertEqual(self.run_scan().returncode, 1)

    def test_unset_and_empty_environment(self):
        for value in (None, ''):
            env = dict(self.env)
            if value is None:
                env.pop('LAW_OC')
            else:
                env['LAW_OC'] = value
            for args, code in (((), 0), (('--require',), 2)):
                result = self.run_scan(*args, env=env)
                self.assertEqual(result.returncode, code)
                self.assertIn('NOTICE', result.stdout)

    def test_invalid_values_fail_without_echo(self):
        for value in ('qz', 'qz9', '***', '    '):
            result = self.run_scan(env=dict(self.env, **{'LAW_O' + 'C': value}))
            self.assertEqual(result.returncode, 2)
            self.assertIn('ERROR', result.stdout)
            self.assertNotIn(value, result.stdout)
            self.assertEqual(result.stderr, '')

    def test_non_repository_is_a_safe_error(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as outside:
            result = self.run_scan(cwd=outside)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Cannot enumerate Git working files.', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_git_failure_has_no_raw_stderr(self):
        with patch.dict(os.environ, self.env), patch.object(secret_scan.subprocess, 'run',
                side_effect=subprocess.CalledProcessError(1, 'git', stderr=KEY.encode())):
            with self.assertRaisesRegex(secret_scan.ScanError, '^Cannot enumerate Git working files.$'):
                secret_scan.scan(self.root)

    def test_working_copy_changes_and_deleted_files(self):
        path = self.write(b'safe')
        self.assertEqual(self.run_scan().returncode, 0)
        path.write_bytes(KEY.encode())
        self.assertEqual(self.run_scan().returncode, 1)
        path.unlink()
        self.assertEqual(self.run_scan().returncode, 0)

    def test_subdirectory_invocation_scans_whole_repository(self):
        self.write(KEY.encode(), 'outside-child.dat')
        child = self.root / 'child'
        child.mkdir()
        self.assertEqual(self.run_scan(cwd=child).returncode, 1)

    def test_filename_cannot_disclose_raw_or_derived_value(self):
        raw_key = 'Name' + 'SensitiveValue9'
        encoded = raw_key.encode().hex()
        for name in (raw_key + '.dat', encoded + '.dat'):
            self.write(raw_key.encode(), name)
        result = self.run_scan(env=dict(self.env, **{'LAW_O' + 'C': raw_key}))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(raw_key, result.stdout + result.stderr)
        self.assertNotIn(encoded, result.stdout + result.stderr)
        self.assertIn('[redacted path]', result.stdout)

    def test_read_failure_is_safe(self):
        self.write(b'safe')
        with patch.dict(os.environ, self.env), patch.object(Path, 'read_bytes', side_effect=OSError(KEY)):
            with self.assertRaises(secret_scan.ScanError) as error:
                secret_scan.scan(self.root)
        self.assertNotIn(KEY, str(error.exception))

    def test_symlink_target_is_not_followed(self):
        target = self.write(KEY.encode(), 'ignored.local', tracked=False)
        self.write(b'*.local\n', '.gitignore')
        link = self.write(b'ignored.local', 'link')
        # Exercise link handling without Windows symlink creation privileges.
        read_bytes = Path.read_bytes
        def guarded(path):
            self.assertNotIn(path, {target, link})
            return read_bytes(path)
        with patch.dict(os.environ, self.env), patch.object(Path, 'is_symlink', lambda path: path == link), patch.object(secret_scan.os, 'readlink', return_value=target.name), patch.object(Path, 'read_bytes', guarded):
            self.assertEqual(secret_scan.scan(self.root, worktree=True), [])

    def test_validator_calls_value_scan_and_rejects_match(self):
        from tools.test_tools import fixture
        with fixture() as root, patch.dict(os.environ, self.env):
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            path = root / 'exposure.txt'
            path.write_bytes(KEY.encode())
            subprocess.run(['git', '-C', str(root), 'add', 'exposure.txt'], check=True, capture_output=True)
            errors, _, _ = validate.validate(root)
            self.assertTrue(any('LAW_OC exposure (utf-8)' in error for error in errors))
            self.assertTrue(all(KEY not in error for error in errors))
            path.write_text('safe', encoding='utf-8')
            self.assertEqual(validate.validate(root)[0], [])
            (root / '.gitignore').write_text('.env\n', encoding='utf-8')
            (root / '.env').write_bytes(KEY.encode())
            self.assertEqual(validate.validate(root)[0], [])

    def test_validator_literal_warning_is_non_fatal_and_single(self):
        from tools.test_tools import fixture
        with fixture() as root, patch.dict(os.environ, {'LAW_OC': ''}):
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            literal = 'example' + '-not-a-real-key'
            text = 'OC = "' + literal + '"\nLAW_OC: "' + literal + '"\n'
            for name in ('first.txt', 'second.txt'):
                (root / name).write_text(text, encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'add', 'first.txt', 'second.txt'], check=True, capture_output=True)
            errors, warnings, _ = validate.validate(root)
            self.assertEqual(errors, [])
            self.assertEqual(sum('quoted OC/LAW_OC literal' in warning for warning in warnings), 1)
            self.assertTrue(all(literal not in warning for warning in warnings))


if __name__ == '__main__':
    unittest.main()
