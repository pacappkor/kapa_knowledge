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

    def test_round_six_regressions(self):
        for declaration in ('function ', 'function* ', 'async function ',
                            'const obj = { method', 'const obj = { first() {}, method'):
            for name, rule in ((OC_NAME, 'law-oc'), ('accessToken', 'generic-secret')):
                for default, expected in (('', []), (' = ' + repr(VALUE), [(1, rule)])):
                    text = declaration + '(' + name + ': string' + default + ') {}'
                    self.assertEqual(list(pattern_scan.findings(text, 'sample.ts')), expected)
        for regex in ("/'/", '/[\"\']/g', r"/a\/'b/i"):
            for name, rule in ((OC_NAME, 'law-oc'), ('accessToken', 'generic-secret')):
                for value, expected in ((VALUE, [(1, rule)]), ('<hi>', [])):
                    self.assertEqual(list(pattern_scan.findings(
                        'const r = ' + regex + '; ' + name + ' = ' + repr(value), 'sample.js')),
                        expected)
        for expression in ('config.get("' + OC_NAME + '")',
                           'os.environ.get("LAW_' + OC_NAME + '")',
                           'os.getenv("X")', 'process.env.X'):
            self.assertFalse(list(pattern_scan.findings(OC_NAME + ' = ' + expression, 'sample.py')))
        self.assertFalse(list(pattern_scan.findings(
            OC_NAME + ' = config.get(' + repr(VALUE) + ')', 'sample.py')))
        for expression in ('config.get("X", ' + repr(VALUE) + ')',
                           'os.getenv("X", ' + repr(VALUE) + ')'):
            self.assertEqual(list(pattern_scan.findings(OC_NAME + ' = ' + expression, 'sample.py')),
                             [(1, 'law-oc')])
        for operator in ('=', 'return ', 'throw ', '(', '[', '!', '&&', '?'):
            self.assertEqual(list(pattern_scan.findings(
                'const r ' + operator + "/'/; accessToken = " + repr(VALUE), 'sample.js')),
                [(1, 'generic-secret')])
        self.assertEqual(list(pattern_scan.findings(
            'const n = a / b; accessToken = ' + repr(VALUE), 'sample.js')),
            [(1, 'generic-secret')])
        for prefix, quote, reference, path in (('f', '"', '{key}', 'sample.py'),
                                               ('', '`', '${key}', 'sample.js')):
            for value, expected in ((reference, []), (VALUE, [(1, 'law-oc')])):
                text = 'url = ' + prefix + quote + 'https://law.go.kr/DRF?' + OC_NAME + '=' + value + '&target=law' + quote
                self.assertEqual(list(pattern_scan.findings(text, path)), expected)

    def test_round_seven_regressions(self):
        def check(text, path, expected):
            self.assertEqual(list(pattern_scan.findings(text, path)),
                             [(1, 'generic-secret')] if expected else [], (text, path))

        for keyword in ('else', 'do', 'return', 'typeof', 'case', 'throw', 'void',
                        'delete', 'in', 'of', 'instanceof', 'new', 'yield', 'await', '}'):
            for value in (VALUE, '<hi>'):
                check('if (x) {} ' + keyword + " /'/.test(s); accessToken = " + repr(value),
                      'sample.js', value == VALUE)
        check('const n = a / b; accessToken = ' + repr(VALUE), 'sample.js', True)
        for annotation in ('Record<string, string>', 'string | number', 'Box<Map<K, V>>',
                           '[string, number]', '(x: string) => string',
                           '{ value: string }', 'Array<(x: string) => string>'):
            check('const fn = (accessToken: string): ' + annotation + ' => ""', 'sample.ts', False)
            check('const fn = (accessToken: string = ' + repr(VALUE) + '): ' + annotation + ' => ""',
                  'sample.ts', True)
        for path in ('sample.py', 'sample.js'):
            getter_key = 'LAW_OFFICIAL_' + 'CREDENTIAL_ACCESS_IDENTIFIER'
            check('accessToken = config.get(' + repr(getter_key) + ')', path, False)
            check('accessToken = config.get(' + repr(VALUE) + ')', path, False)
            check('accessToken = config.get("name", ' + repr(VALUE) + ')', path, True)
        for path in ('sample.json', 'sample.yaml', 'sample.js'):
            for name in ('access token', 'api key', 'access-token', 'api-key'):
                for value in (VALUE, '<hi>'):
                    for quote in ('\"', "'"):
                        check('{' + quote + name + quote + ': ' + quote + value + quote + '}',
                              path, value == VALUE)
        for option in ('--access-token=', '--api-key ', '-p ', '-access-token '):
            for value in (VALUE, '$TOKEN', '<hi>'):
                check('run ' + option + value, 'sample.sh', value == VALUE)
            check('run ' + option + '$TOKEN --description ' + VALUE, 'sample.sh', False)
        for path in ('sample.c', 'sample.cpp', 'sample.php'):
            check('consume(accessToken->value, ' + repr(VALUE) + ')', path, False)
            check('accessToken = ' + repr(VALUE) + ';', path, True)
        for path in ('sample.py', 'sample.js'):
            check('request(access_token=get_access_token(), description=' + repr(VALUE) + ')', path, False)
            check('request(access_token=' + repr(VALUE) + ')', path, True)
            check('request(access_token=get_access_token(' + repr(VALUE) + '))', path, True)
        for chain in ('config.credentials[0].access_token', 'config["credentials"].accessToken',
                      'config[0][1].accessToken', 'config["access token"]'):
            for value in (VALUE, '<hi>'):
                check(chain + ' = ' + repr(value), 'sample.js', value == VALUE)
        check('config[token] = ' + repr(VALUE), 'sample.js', False)

    def test_long_indexed_member_chains_linear_work(self):
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);import pattern_scan;'
                'exec("for tail in [\'\', \'accessToken = \' + repr(\'aB3dE6gH9jK2\' + \'mN5pQ8sT1vW4yZ7\')]:\\n "'
                '+"text=\'config\'+\'[0].member\'*15000+\'.\'+tail\\n "'
                '+"start=time.perf_counter()\\n "'
                '+"assert bool(list(pattern_scan.findings(text,\'sample.js\')))==bool(tail)\\n "'
                '+"elapsed=time.perf_counter()-start\\n assert elapsed<2, elapsed\\n print(elapsed)")')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT.parent)],
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_adversarial_name_scans_linear_work(self):
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);import pattern_scan;'
                'cases=["a."*20000,"a . "*20000,"A"*100000,'
                '"a-"*50000,"a."*20000+"[",chr(34)+"a."*20000];'
                'exec("for text in cases:\\n start=time.perf_counter()\\n "'
                '+"assert not list(pattern_scan.findings(text,\'sample.ts\'))\\n "'
                '+"elapsed=time.perf_counter()-start\\n assert elapsed<2, elapsed\\n print(elapsed)")')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT.parent)],
                                capture_output=True, text=True, timeout=15, check=True)
        self.assertEqual(len(result.stdout.splitlines()), 6)
        text = 'a.' * 20000 + 'accessToken = ' + repr(VALUE)
        self.assertEqual(list(pattern_scan.findings(text, 'sample.ts')), [(1, 'generic-secret')])

    def test_large_flow_object_linear_work(self):
        # A child provides a hard guard even if the scanner regresses to cubic.
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);import pattern_scan;'
                'text="{"+",".join([chr(34)+"token"+chr(34)+":"+chr(34)+"example"+chr(34)]*3000)+"}";'
                'start=time.perf_counter();assert not list(pattern_scan.findings(text,"sample.json"));'
                'print(time.perf_counter()-start)')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT.parent)],
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertLess(float(result.stdout), 2.0)
        text = '{' + ','.join(['"token":"example"'] * 3000) + ',"token":' + repr(VALUE) + '}'
        self.assertEqual(self.rules(text), {'generic-secret'})

    def test_large_elisions_linear_work(self):
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);import pattern_scan;'
                'text=("In the "+chr(39)+"90s ")*19000;'
                'start=time.perf_counter();assert not list(pattern_scan.findings(text));'
                'print(time.perf_counter()-start)')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT.parent)],
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertLess(float(result.stdout), 2.0)
        text = ("In the '90s " * 19000) + 'token=' + repr(VALUE)
        self.assertEqual(self.rules(text), {'generic-secret'})

    def test_source_assignment_comment_trivia(self):
        for path in ('sample.js', 'sample.ts', 'sample.jsx', 'sample.tsx',
                     'sample.mjs', 'sample.cjs'):
            for name, rule in (('accessToken', 'generic-secret'), (OC_NAME, 'law-oc')):
                for middle in (' /* compatibility */ = ',
                               ' /* one */ /* two */ = ',
                               ' /* before */ : /* type */ string /* after */ = '):
                    for value, expected in ((VALUE, [(1, rule)]), ('<hi>', []),
                                            ('${NAME}', []), ('example', [])):
                        text = 'const ' + name + middle + repr(value)
                        with self.subTest(path=path, middle=middle, value=value):
                            self.assertEqual(list(pattern_scan.findings(text, path)), expected)
                # Comments cannot bridge lines in this single-line heuristic.
                for comment in (' // compatibility', ' /* compatibility'):
                    text = name + comment + '\n = ' + repr(VALUE)
                    self.assertFalse(list(pattern_scan.findings(text, path)))
            self.assertFalse(list(pattern_scan.findings(
                'const tokenizer /* compatibility */ = ' + repr(VALUE), path)))
        for middle in ('  = ', '\t = ', ': str  = '):
            self.assertEqual(list(pattern_scan.findings('token' + middle + repr(VALUE), 'sample.py')),
                             [(1, 'generic-secret')])
            self.assertFalse(list(pattern_scan.findings('token' + middle + '"<hi>"', 'sample.py')))
        self.assertFalse(list(pattern_scan.findings(
            'token /* not Python trivia */ = ' + repr(VALUE), 'sample.py')))

    def test_unknown_unbalanced_comment_linear_work(self):
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);import pattern_scan;'
                'text="/* "*76000;'
                'start=time.perf_counter();assert not list(pattern_scan.findings(text,"unknown.ext"));'
                'print(time.perf_counter()-start)')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SCRIPT.parent)],
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertLess(float(result.stdout), 2.0)

    def test_comment_syntax_across_file_types(self):
        paths = ('sample.c', 'sample.h', 'sample.cpp', 'sample.hpp', 'sample.cs',
                 'sample.java', 'sample.go', 'sample.rs', 'sample.kt', 'sample.swift',
                 'sample.php', 'sample.js', 'sample.tsx', 'sample.css', 'sample.scss',
                 'sample.sql', 'sample.unknown', 'extensionless')
        for path in paths:
            for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
                for trivia in ('/* compatibility */', '/* first */ /* second */'):
                    prefix = 'const char *' + name + ' ' + trivia + ' = '
                    with self.subTest(path=path, name=name, trivia=trivia):
                        self.assertEqual(list(pattern_scan.findings(prefix + repr(VALUE), path)),
                                         [(1, rule)])
                        for safe in ('example', '<hi>', '${NAME}'):
                            self.assertFalse(list(pattern_scan.findings(prefix + repr(safe), path)))
                self.assertFalse(list(pattern_scan.findings(
                    name + ' /* unbalanced\n = ' + repr(VALUE), path)))
            self.assertFalse(list(pattern_scan.findings(
                'tokenizer /* trivia */ = ' + repr(VALUE), path)))
        for path in ('sample.py', 'sample.sh', 'sample.yaml', 'sample.toml', 'sample.ini'):
            self.assertFalse(list(pattern_scan.findings(
                'token /* not trivia */ = ' + repr(VALUE), path)))
        # Unknown syntax must not hide nesting behind an unbalanced opener.
        with self.assertRaises(pattern_scan.ScanError):
            list(pattern_scan.findings('/* ' + '(' * 65, 'sample.unknown'))
        for path, comment in (('sample.py', '#'), ('sample.sh', '#'),
                              ('sample.yaml', '#'), ('sample.toml', '#'),
                              ('sample.ini', ';'), ('sample.sql', '--'),
                              ('sample.c', '//'), ('sample.lua', '--')):
            self.assertFalse(list(pattern_scan.findings(comment + ' ' + '(' * 100, path)))
        # Do not remove markers inside quoted literals; keep comment examples scanned.
        self.assertEqual(list(pattern_scan.findings(
            OC_NAME + ' = "/* literal */"', 'sample.c')), [(1, 'law-oc')])
        self.assertEqual(list(pattern_scan.findings(
            '// token=' + repr(VALUE), 'sample.c')), [(1, 'generic-secret')])

    def test_shebang_classification_and_semantics(self):
        provider = 'ghp' + '_' + VALUE * 2
        for interpreter in ('sh', 'bash', 'zsh', 'dash', 'ksh'):
            for shebang in ('#!/bin/' + interpreter,
                            '#!/usr/bin/env ' + interpreter,
                            '#!/usr/bin/env -S ' + interpreter + ' -eu'):
                for path in (None, 'runner', 'runner.py', 'runner.txt'):
                    prefix = shebang + '\n'
                    self.assertEqual(pattern_scan.file_type(prefix, path), 'shell')
                    self.assertIn((2, 'github-token'), list(pattern_scan.findings(
                        prefix + 'token="<placeholder>" printf "<' + provider + '>"', path)))
                    self.assertFalse(list(pattern_scan.findings(
                        prefix + 'token="<prefix ' + provider + '>"', path)))
                    rhs = '"' + VALUE[:10] + '"' + VALUE[10:]
                    self.assertIn((2, 'generic-secret'), list(pattern_scan.findings(
                        prefix + 'token=' + rhs, path)))
                    self.assertFalse(list(pattern_scan.findings(
                        prefix + 'token="${NAME}"', path)))
        for interpreter, kind in (('python', 'python'), ('python3', 'python'),
                                  ('python3.12', 'python'), ('node', 'javascript'),
                                  ('nodejs', 'javascript')):
            for shebang in ('#!/usr/bin/' + interpreter, '#!/usr/bin/env ' + interpreter):
                for path in (None, 'runner', 'runner.sh'):
                    prefix = shebang + '\n'
                    self.assertEqual(pattern_scan.file_type(prefix, path), kind)
                    self.assertFalse(list(pattern_scan.findings(prefix + 'token=' + VALUE, path)))
                    self.assertEqual(list(pattern_scan.findings(
                        prefix + 'token=' + repr(VALUE), path)), [(2, 'generic-secret')])
                    self.assertFalse(list(pattern_scan.findings(
                        prefix + 'token="' + VALUE[:10] + '" "' + VALUE[10:] + '"', path)))
                    if kind == 'javascript':
                        self.assertFalse(list(pattern_scan.findings(
                            prefix + 'token => ' + repr(VALUE), path)))
                        self.assertEqual(list(pattern_scan.findings(
                            prefix + 'token /* trivia */ = ' + repr(VALUE), path)),
                            [(2, 'generic-secret')])
        for text in ('ordinary\n#!/bin/bash', '#!/bin/notbash', '#!/usr/bin/env pythonish'):
            self.assertEqual(pattern_scan.file_type(text, 'runner'), 'unknown')

    def test_shell_placeholder_scope_ends_at_word(self):
        provider = 'ghp' + '_' + VALUE * 2
        wrapped = '<' + provider + '>'
        for path in ('sample.sh', 'sample.bash', 'sample.zsh', '.env', 'sample.env', 'sample.ini'):
            for whitespace in (' ', '\t'):
                for rhs in ('"<placeholder>"', "'<placeholder>'", '<placeholder>',
                            '"${NAME:-<placeholder>}"', '$(read_value "two words")'):
                    text = 'token=' + rhs + whitespace + 'printf ' + repr(wrapped)
                    self.assertIn((1, 'github-token'), list(pattern_scan.findings(text, path)))
            # Spaces inside quotes, escaped spaces and expansion bodies are not boundaries.
            for rhs in (repr('<prefix ' + provider + '>'),
                        '"<prefix ' + provider + '>"', '<prefix' + chr(92) + ' ' + provider + '>'):
                self.assertFalse(list(pattern_scan.findings('token=' + rhs, path)))
            self.assertFalse(list(pattern_scan.findings('token=' + repr(wrapped), path)))
            self.assertFalse(list(pattern_scan.findings('token="<placeholder>" printf ordinary', path)))
            self.assertIn((1, 'github-token'), list(pattern_scan.findings('token=' + provider, path)))

    def test_shell_single_operator_boundaries(self):
        for operator in ('&', '|'):
            for path in (None, 'sample.sh', '.env'):
                prefix = OC_NAME + '=${LAW_OC} ' + operator
                self.assertFalse(list(pattern_scan.findings(prefix + ' echo done', path)))
                self.assertEqual(list(pattern_scan.findings(prefix + ' token=' + repr(VALUE), path)),
                                 [(1, 'generic-secret')])
                self.assertEqual(list(pattern_scan.findings(
                    OC_NAME + '=' + repr(VALUE + operator + 'tail'), path)), [(1, 'law-oc')])
        self.assertEqual(self.rules('https://x/?' + OC_NAME + '=' + VALUE + '&x=y'), {'law-oc'})
        self.assertFalse(self.rules('https://x/?' + OC_NAME + '=${LAW_OC}&x=y'))

    def test_flow_sequence_colon_bounds(self):
        for path in (None, 'sample.yaml', 'sample.yml'):
            for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
                for safe in ('${LAW_OC}', '<hi>', 'example', ''):
                    text = 'entries: [' + name + ': "' + safe + '", description: "' + VALUE + '"]'
                    self.assertFalse(list(pattern_scan.findings(text, path)))
                for suffix in (']', ', description: "hello"]'):
                    self.assertEqual(list(pattern_scan.findings(
                        'entries: [' + name + ': ' + repr(VALUE) + suffix, path)), [(1, rule)])

    def test_source_ternary_colons(self):
        for path in ('sample.js', 'sample.ts', 'sample.tsx', 'sample.jsx'):
            for name in ('accessToken', OC_NAME):
                for value in ('<hi>', VALUE):
                    for prefix in ('ok ? ', 'ok ? nested ? x : ', 'ok ? (x) : nested ? '):
                        self.assertFalse(list(pattern_scan.findings(
                            prefix + name + ' : ' + repr(value), path)))
                for prefix in ('const x = {', 'ok ? {'):
                    self.assertTrue(list(pattern_scan.findings(
                        prefix + name + ': ' + repr(VALUE) + '}', path)))
                self.assertTrue(list(pattern_scan.findings(name + ': string = ' + repr(VALUE), path)))
                self.assertFalse(list(pattern_scan.findings(name + ': string = "<hi>"', path)))
            for operator in ('??', '?.member', '?: string;'):
                self.assertTrue(list(pattern_scan.findings(
                    'ordinary ' + operator + ' const x = {' + OC_NAME + ': ' + repr(VALUE) + '}', path)))
        self.assertEqual(self.rules(OC_NAME + ': "literal"'), {'law-oc'})

    def test_shell_positional_and_special_references(self):
        refs = ['$' + str(n) for n in range(10)] + ['${10}']
        refs += ['$' + char for char in '@*#?$!-']
        for ref in refs:
            self.assertTrue(pattern_scan.placeholder(ref))
            for quote in ('', '"', "'"):
                for name in (OC_NAME, 'token'):
                    text = name + '=' + quote + ref + quote
                    self.assertFalse(list(pattern_scan.findings(text, 'sample.sh')))
                    self.assertTrue(list(pattern_scan.findings(
                        name + '=' + quote + ref + VALUE + quote, 'sample.sh')))

    def test_null_sentinels_and_quoted_null_strings(self):
        for path in (None, 'sample.json', 'sample.yaml'):
            for name in (OC_NAME, 'token'):
                for value in ('null', 'Null', 'NULL', '~', ''):
                    for text in (name + ': ' + value,
                                 '{"' + name + '": ' + value + '}',
                                 'entries: [' + name + ': ' + value + ', description: "hello"]'):
                        self.assertFalse(list(pattern_scan.findings(text, path)))
                self.assertTrue(list(pattern_scan.findings(name + ': ' + repr(VALUE), path)))
            # A quoted null is a real string, not a null sentinel.
            self.assertEqual(list(pattern_scan.findings(OC_NAME + ': "null"', path)), [(1, 'law-oc')])
            self.assertFalse(list(pattern_scan.findings('token: "null"', path)))

    def test_structural_depth_ignores_literals_and_comments(self):
        for text in ('ordinary = ' + repr('(' * 1000),
                     '# ' + '(' * 1000, '// ' + '[' * 1000,
                     '/* ' + '{' * 1000 + ' */ ordinary = "example"'):
            self.assertFalse(self.rules(text))
        for opening, closing in (('(', ')'), ('[', ']'), ('{', '}')):
            self.assertFalse(self.rules(opening * 64 + closing * 64))
            with self.assertRaises(pattern_scan.ScanError):
                self.rules(opening * 65 + closing * 65)
        self.assertEqual(self.rules('ordinary = ' + repr('(' * 1000) + '; token=' + repr(VALUE)),
                         {'generic-secret'})

    def test_query_scope_is_local_to_url(self):
        for prefix in ('note="?"; ', 'note=?; ', 'note=? ', 'note="https://x/?"; ',
                       '"unrelated?"; '):
            text = prefix + OC_NAME + '="${LAW_OC}&<hi>"'
            self.assertEqual(self.rules(text), {'law-oc'})
        for quote in ('', '"', "'"):
            text = quote + 'https://x/?' + OC_NAME + '=${LAW_OC}&target=law' + quote
            self.assertFalse(self.rules(text))
            self.assertEqual(self.rules(text.replace('${LAW_OC}', VALUE)), {'law-oc'})

    def test_leading_elisions_do_not_hide_assignments(self):
        for elision in ("'90s", "'em", "'n'", "'tis", "'cause"):
            text = 'In the ' + elision + ' token=' + repr(VALUE)
            self.assertEqual(self.rules(text), {'generic-secret'})
            self.assertFalse(self.rules('In the ' + elision + ' token="example"'))
        self.assertFalse(self.rules("ordinary = 'plain single quoted prose'"))
        self.assertEqual(self.rules('token=' + repr(VALUE)), {'generic-secret'})

    def test_parameter_exemption_requires_source_signature(self):
        for path in (None, 'sample.yaml', 'sample.json', 'sample.txt', 'sample.ts'):
            for name, value, rule in (('token', VALUE, 'generic-secret'), (OC_NAME, 'VALUE', 'law-oc')):
                self.assertEqual(list(pattern_scan.findings('entries: [' + name + ': ' + repr(value) + ']', path)),
                                 [(1, rule)])
            self.assertFalse(list(pattern_scan.findings('entries: [token: "<hi>"]', path)))
        for path in ('sample.py', 'sample.js', 'sample.ts', 'sample.jsx', 'sample.tsx', 'sample.mjs', 'sample.cjs'):
            for prefix, suffix in (('def f(', '): pass'), ('function f(', ') {}'),
                                   ('const f = (', ') => 0'), ('class C { method(', ') {} }')):
                self.assertFalse(list(pattern_scan.findings(prefix + OC_NAME + ': string' + suffix, path)))
                self.assertEqual(list(pattern_scan.findings(prefix + 'token: string = ' + repr(VALUE) + suffix, path)),
                                 [(1, 'generic-secret')])
        self.assertEqual(list(pattern_scan.findings('def f(' + OC_NAME + ': string): pass', 'sample.txt')),
                         [(1, 'law-oc')])

    def test_work_limits_fail_closed(self):
        with patch.object(pattern_scan, 'MAX_LINE_CHARS', 10):
            with self.assertRaises(pattern_scan.ScanError):
                self.rules('ordinary prose' * 2)
        with patch.object(pattern_scan, 'MAX_FILE_WORK', 20):
            with self.assertRaises(pattern_scan.ScanError):
                self.rules(('ordinary text\n') * 3)
        with patch.object(pattern_scan, 'MAX_LINE_WORK', 100):
            with self.assertRaises(pattern_scan.ScanError):
                self.rules(('token=example ' * 20) + repr(VALUE))
        with self.assertRaises(pattern_scan.ScanError):
            self.rules('token=' + '(' * 100 + repr(VALUE))
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            (root / 'sample').write_bytes(b'x' * 100)
            with patch.object(pattern_scan, 'MAX_FILE_BYTES', 50), patch.object(
                    pattern_scan, 'repository_files', return_value=(root, ['sample'])):
                with self.assertRaises(pattern_scan.ScanError):
                    pattern_scan.scan(root)

    def test_adjacent_shell_static_fragments(self):
        # VALUE's first ten characters reproduce the reported quoted/bare split.
        for path in ('sample.sh', 'sample.bash', '.env', 'sample.env', 'sample.ini',
                     'sample.txt', None):
            for rhs in ('"' + VALUE[:10] + '"' + VALUE[10:],
                        '"' + VALUE[:8] + '"' + VALUE[8:16] + "'" + VALUE[16:] + "'",
                        VALUE[:8] + "'" + VALUE[8:16] + "'" + '"' + VALUE[16:] + '"'):
                with self.subTest(path=path, rhs=rhs):
                    self.assertEqual(list(pattern_scan.findings('token=' + rhs, path)),
                                     [(1, 'generic-secret')])
            for expansion in ('$VAR', '${VAR}', '$(read_value)', '`read_value`'):
                for rhs in ('"' + VALUE[:10] + '"' + expansion + "'" + VALUE[10:] + "'",
                            '"' + VALUE[:10] + expansion + VALUE[10:] + '"'):
                    self.assertFalse(list(pattern_scan.findings('token=' + rhs, path)))
            for separator in (' ', '&', '|', ';', '(', ')'):
                self.assertFalse(list(pattern_scan.findings(
                    'token="' + VALUE[:10] + '"' + separator + "'" + VALUE[10:] + "'", path)))
            self.assertFalse(list(pattern_scan.findings(OC_NAME + '="${LAW_OC}"&suffix', path)))
            self.assertEqual(list(pattern_scan.findings(
                ''.join(('token=', '"${VAR}"', VALUE)), path)), [(1, 'generic-secret')])
        for path in ('sample.py', 'sample.js', 'sample.ts'):
            # Preserve source behavior; Python implicit concatenation is not folded.
            for separator in (' ', ' + '):
                self.assertFalse(list(pattern_scan.findings(
                    'token="' + VALUE[:10] + '"' + separator + '"' + VALUE[10:] + '"', path)))

    def test_shell_commands_are_runtime(self):
        commands = ('$(get_access_token_from_environment)', '$(read_law_oc)',
                    '$(outer "$(inner)" ")" )', '`read_law_oc`')
        for name in ('access_token', OC_NAME):
            for command in commands:
                for quote in ('', '"'):
                    for tail, expected in (('', False), (VALUE, True)):
                        text = name + '=' + quote + command + tail + quote
                        with self.subTest(text=text):
                            self.assertEqual(bool(list(pattern_scan.findings(text, 'sample.sh'))), expected)
        self.assertFalse(self.rules('access_token="$(get_access_token_from_environment)"'))
        self.assertFalse(self.rules(OC_NAME + '=$(read_law_oc)'))

    def test_provider_exemption_rhs_scope(self):
        provider = 'ghp' + '_' + VALUE * 2
        for boundary in (',', ';', ')', '}', ']', ' && ', ' || '):
            self.assertIn('github-token', self.rules(
                'token=<' + provider + '>' + boundary + ' print("<' + provider + '>")'))
            self.assertIn('github-token', self.rules(
                'token=<' + provider + '>' + boundary + ' leaked=' + provider))
            self.assertFalse(self.rules('token=<' + provider + '>'))

    def test_quoted_annotation_members_and_parameters(self):
        for annotation, path in (('Literal["legacy"] | str', 'sample.py'),
                                 ('"a" | "b" | string', 'sample.ts')):
            self.assertFalse(list(pattern_scan.findings('token: ' + annotation + ' = "<hi>"', path)))
            self.assertEqual(list(pattern_scan.findings('token: ' + annotation + ' = ' + repr(VALUE), path)),
                             [(1, 'generic-secret')])
        for prefix, suffix, path in (('def f(token: str', '): return ""', 'sample.py'),
                                     ('const fn = (accessToken: string', ') => ""', 'sample.ts'),
                                     ('function f(apiKey: string', ') { return "<hi>" }', 'sample.ts')):
            self.assertFalse(list(pattern_scan.findings(prefix + suffix, path)))
            self.assertFalse(list(pattern_scan.findings(prefix + ' = "<hi>"' + suffix, path)))
            self.assertEqual(list(pattern_scan.findings(prefix + ' = ' + repr(VALUE) + suffix, path)),
                             [(1, 'generic-secret')])

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

    def test_object_colon_rhs_bounds(self):
        self.assertFalse(self.rules('{"' + OC_NAME + '": "${LAW_OC}", "description": "hello"}'))
        for path in (None, 'sample.json', 'sample.yaml', 'sample.js'):
            for name, rule in ((OC_NAME, 'law-oc'), ('token', 'generic-secret')):
                for safe in ('${LAW_OC}', 'example', ''):
                    text = '{' + repr(name) + ': ' + repr(safe) + ', "description": ' + repr(VALUE) + '}'
                    self.assertFalse(list(pattern_scan.findings(text, path)))
                for suffix in (', "x": 1}', '}', '}, 1]'):
                    text = '{' + repr(name) + ': ' + repr(VALUE) + suffix
                    self.assertEqual(list(pattern_scan.findings(text, path)), [(1, rule)])
                self.assertEqual(list(pattern_scan.findings(
                    '{' + repr(name) + ': factory({"x": ' + repr(VALUE) + '}), "y": 1}', path)),
                    [(1, rule)])
        self.assertFalse(self.rules('{"x": "{", ' + repr(OC_NAME) + ': "${LAW_OC}", "y": "hello"}'))
        self.assertEqual(self.rules('{' + repr(OC_NAME) + ': "literal, } ]", "x": 1}'), {'law-oc'})

    def test_comparisons_and_arrows_are_not_assignments(self):
        for name in (OC_NAME, 'token'):
            for operator in ('==', '===', '!=', '<=', '>=', '=>'):
                self.assertFalse(self.rules('if ' + name + ' ' + operator + ' ' + repr(VALUE) + ':'))
            for operator in ('=', ':=', '+='):
                self.assertTrue(self.rules(name + operator + repr(VALUE)))
        self.assertFalse(self.rules('if ' + OC_NAME + ' == "disabled":'))
        self.assertFalse(self.rules('token === "x"'))

    def test_static_template_chunks_are_independent(self):
        for prefix, expression in (('`', '${userId}'), ('f"', '{userId}')):
            close = '`' if prefix == '`' else '"'
            self.assertFalse(self.rules('token = ' + prefix + 'https://example.com/' + expression + '/callback' + close))
            self.assertFalse(self.rules('token = ' + prefix + VALUE[:12] + expression + VALUE[12:] + close))
            self.assertEqual(self.rules('token = ' + prefix + expression + VALUE + close), {'generic-secret'})

    def test_python_f_string_interpolations(self):
        for prefix in ('f', 'F', 'rf', 'fr', 'RF', 'FR', 'rF', 'Fr'):
            for expression in ('get_access_token_from_environment()', 'x // 2', 'lookup({"x": runtime})',
                               'lookup(' + repr(VALUE) + ')'):
                rhs = prefix + "'{" + expression + "}'"
                self.assertFalse(self.rules('token = ' + rhs))
                self.assertFalse(self.rules(OC_NAME + ' = ' + rhs))
                self.assertEqual(self.rules('token = ' + prefix + "'{" + expression + '}' + VALUE + "'"), {'generic-secret'})
        self.assertEqual(self.rules('token = f"{{' + VALUE + '}}"'), {'generic-secret'})
        self.assertEqual(list(pattern_scan.static_chunks('{{x}}{runtime}tail', formatted=True)), ['{x}', 'tail'])
        self.assertEqual(list(pattern_scan.static_chunks(chr(92) + '{runtime}tail', formatted=True)), [chr(92), 'tail'])
        self.assertFalse(self.rules('token = f"{get_access_token_from_environment()}"'))

    def test_annotation_unions_and_generics(self):
        for path in (None, 'sample.py', 'sample.ts'):
            for annotation in ('str | None', 'Optional[str]', 'string | undefined',
                               'Map<string, Optional[str]]'):
                prefix = 'token: ' + annotation + ' = '
                self.assertEqual(list(pattern_scan.findings(prefix + repr(VALUE), path)), [(1, 'generic-secret')])
                self.assertFalse(list(pattern_scan.findings(prefix + '"example"', path)))

    def test_bracketed_config_words_and_source_arrows(self):
        for path in ('.env', 'sample.sh', 'sample.toml'):
            value = VALUE[:12] + '[' + VALUE[12:] + ']'
            self.assertEqual(list(pattern_scan.candidates(value)), [value])
            self.assertEqual(list(pattern_scan.findings('token=' + value, path)), [(1, 'generic-secret')])
            self.assertFalse(list(pattern_scan.findings('token=short[ordinary]', path)))
            self.assertEqual(list(pattern_scan.findings('token => ' + repr(VALUE), path)), [(1, 'generic-secret')])
        for path in ('sample.js', 'sample.ts', 'sample.tsx'):
            self.assertFalse(list(pattern_scan.findings('tokens.map(accessToken => ' + repr(VALUE) + ')', path)))
            self.assertEqual(list(pattern_scan.findings('accessToken = ' + repr(VALUE), path)), [(1, 'generic-secret')])
            self.assertFalse(list(pattern_scan.findings('token = settings[' + repr(VALUE) + ']', path)))

    def test_generic_assignments(self):
        for key in ('api_key', 'api-key', 'apikey', 'service_key', 'service-key',
                    'secret', 'token', 'password', 'client_secret', 'access_token'):
            for separator in ('=', ': '):
                self.assertIn('generic-secret', self.rules(key + separator + '"' + VALUE + '"'))
        self.assertFalse(self.rules('password=' + 'a' * 40))
        self.assertFalse(self.rules('token=short'))

    def test_statement_rhs_bounds(self):
        for separator in (';', '&&', '||', '|', '\n'):
            prefix = OC_NAME + '=${LAW_OC}' + separator
            self.assertFalse(self.rules(prefix + ' echo done'))
            self.assertFalse(self.rules(prefix + ' echo ' + repr(VALUE)))
            self.assertEqual(self.rules(prefix + ' token=' + repr(VALUE)), {'generic-secret'})
            self.assertEqual(self.rules('token=' + repr(VALUE + separator + VALUE)), {'generic-secret'})
        self.assertEqual(self.rules('token=${NAME:-' + VALUE + ';suffix}'), {'generic-secret'})

    def test_padded_colon_values(self):
        for suffix in ('=', '=='):
            self.assertEqual(self.rules('password: ' + VALUE + suffix), {'generic-secret'})
        self.assertFalse(self.rules('password: example='))
        self.assertEqual(self.rules('token: str = ' + repr(VALUE)), {'generic-secret'})

    def test_runtime_references_and_source_literals(self):
        for path in ('sample.py', 'sample.js', 'sample.ts'):
            for rhs in ('get_access_token_from_environment()', 'self.config.token_value',
                        'settings[' + repr(VALUE) + ']', VALUE, 'left + right'):
                self.assertFalse(list(pattern_scan.findings('token = ' + rhs, path)))
                self.assertFalse(list(pattern_scan.findings(OC_NAME + ' = ' + rhs, path)))
            for rhs in (repr(VALUE), 'Token(' + repr(VALUE) + ')'):
                self.assertEqual(list(pattern_scan.findings('token = ' + rhs, path)),
                                 [(1, 'generic-secret')])
        self.assertEqual(list(pattern_scan.findings(
            'url = "https://law.go.kr/DRF?' + OC_NAME + '=' + VALUE + '&target=law"',
            'sample.py')), [(1, 'law-oc')])
        for path in ('.env', 'sample.ini', 'sample.toml', 'sample.yaml', 'sample.sh'):
            self.assertEqual(list(pattern_scan.findings('token=' + VALUE, path)),
                             [(1, 'generic-secret')])
        for rhs in ('get_access_token_from_environment()', 'self.config.token_value'):
            self.assertFalse(self.rules('token = ' + rhs))

    def test_delimited_fake_is_not_a_placeholder(self):
        for value in (VALUE[:12] + '_FAKE_' + VALUE[12:],
                      'FAKE_' + VALUE, VALUE + '_EXAMPLE', 'arbitrary_FAKE_TOKEN'):
            self.assertFalse(pattern_scan.placeholder(value))
            if pattern_scan.high_entropy(value):
                self.assertIn('generic-secret', self.rules('token=' + repr(value)))
        for value in ('hf_FAKE-NOT-A-REAL-TOKEN', 'YOUR_API_KEY_HERE',
                      'EXAMPLE_TOKEN', '<anything>', '*' * 30, 'ghp_EXAMPLE_TOKEN'):
            self.assertTrue(pattern_scan.placeholder(value))
            self.assertFalse(self.rules('token=' + repr(value)))

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
            for operator in ('=', ':=', ':', '->', '?='):
                for prefix in ('', 'b', 'r', 'u', 'f', 'br', 'rb', 'BR', 'rB'):
                    with self.subTest(name=name, operator=operator, prefix=prefix):
                        self.assertEqual(self.rules(name + operator + prefix + repr(VALUE)),
                                         {'generic-secret'})
        for name in (OC_NAME, 'law_' + OC_NAME.lower(), 'law' + OC_NAME.title()):
            for operator in (':-', '-', ':=', ':+', '=', '+'):
                value = '${NAME' + operator + VALUE + '}'
                for quote in ('', '"', "'"):
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

    def test_template_interpolations_are_not_static_credentials(self):
        expressions = (
            'getAccessTokenFromEnvironment()',
            'lookup({nested: {value: runtimeValue}})',
            'lookup("}", {value: runtimeValue})',
            'lookup(`nested${lookup({value: runtimeValue})}tail`)',
            'lookup(`nested${lookup("}")}tail`, {value: runtimeValue})',
            'lookup(/* } */ runtimeValue)',
            'lookup(' + repr(VALUE) + ')',
        )
        for path in (None, 'sample.js', 'sample.ts', 'sample.tsx'):
            for expression in expressions:
                with self.subTest(path=path, expression=expression):
                    template = '${' + expression + '}'
                    self.assertFalse(list(pattern_scan.findings(
                        'accessToken = `' + template + '`', path)))
                    self.assertEqual(list(pattern_scan.findings(
                        'access' + 'Token = `prefix' + template + VALUE + '`', path)),
                        [(1, 'generic-secret')])
                    self.assertEqual(list(pattern_scan.findings(
                        'access' + 'Token = `' + VALUE + template + 'suffix`', path)),
                        [(1, 'generic-secret')])
        self.assertFalse(self.rules('token = `prefix${runtimeValue}suffix`'))
        self.assertEqual(self.rules('token = `' + chr(92) + '${' + VALUE + '}`'),
                         {'generic-secret'})

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
            for wrapper in ('<{}>',):
                for quote in ('', '"', "'"):
                    with self.subTest(rule=rule, wrapper=wrapper, quote=quote):
                        self.assertFalse(self.rules('token=' + quote + wrapper.format(value) + quote))
            for wrapper in ('FAKE_{}', '{}_FAKE'):
                self.assertIn('generic-secret', self.rules('token=' + repr(wrapper.format(value))))
            self.assertIn(rule, self.rules('token=' + value))
            self.assertIn(rule, self.rules('Documentation mentions ' + value))
            self.assertIn(rule, self.rules('print("' + value + '")'))
            self.assertIn(rule, self.rules('token=<example>; print("' + value + '")'))
            self.assertIn(rule, self.rules('token=<example>; print("<' + value + '>")'))
            self.assertIn(rule, self.rules('print("token=example", "<' + value + '>")'))

    def test_escaped_shell_whitespace(self):
        value = VALUE[:12] + ' ' + VALUE[12:]
        for whitespace in (' ', '\t'):
            escaped = VALUE[:12] + chr(92) + whitespace + VALUE[12:]
            self.assertEqual(list(pattern_scan.candidates(escaped)),
                             [value.replace(' ', whitespace)])
            self.assertEqual(self.rules('accessToken=' + escaped), {'generic-secret'})
        self.assertFalse(self.rules('accessToken=' + VALUE[:12] + ' ' + VALUE[12:]))
        self.assertFalse(self.rules('accessToken=short' + chr(92) + ' word'))

    def test_provider_environment_names(self):
        for value, rule in (('ghp' + '_' + VALUE * 2, 'github-token'),
                            ('hf' + '_' + VALUE * 2, 'huggingface-token'),
                            ('AK' + 'IA' + 'A1B2C3D4' * 2, 'aws-access-key')):
            for wrapper in ('${%s}', '$%s', '$env:%s', '%%%s%%',
                            'os.getenv("%s")', "getenv('%s')",
                            'os.environ["%s"]', "environ['%s']",
                            'process.env.%s', '${{ secrets.%s }}'):
                reference = wrapper % value
                for prefix in ('', 'token='):
                    with self.subTest(wrapper=wrapper, prefix=prefix):
                        self.assertFalse(self.rules(prefix + reference))
            self.assertIn(rule, self.rules('token="${' + value + '}' + VALUE + '"'))
            for text in (value, 'A prose mention of ' + value, 'print("' + value + '")'):
                self.assertIn(rule, self.rules(text))

    def test_whole_placeholder_shapes(self):
        for marker in ('***', '•••', '●●●', 'FAKE', 'EXAMPLE'):
            value = VALUE[:12] + marker + VALUE[12:]
            self.assertFalse(pattern_scan.placeholder(value))
            self.assertEqual(self.rules('token=' + repr(value)), {'generic-secret'})
        for marker in ('FAKE', 'EXAMPLE'):
            for value in (marker + VALUE, VALUE + marker):
                self.assertFalse(pattern_scan.placeholder(value))
                self.assertEqual(self.rules('token=' + repr(value)), {'generic-secret'})
        for value in ('***', '•••', '●●●', '<value>', 'FAKE', 'EXAMPLE',
                      'NOT-A-REAL-TOKEN', 'YOUR_KEY', 'hf_FAKE-NOT-A-REAL-TOKEN'):
            self.assertTrue(pattern_scan.placeholder(value))
            self.assertFalse(self.rules('token=' + repr(value)))
        provider = 'ghp' + '_' + VALUE * 2
        for value in ('***' + provider, provider + '***', provider + 'FAKE'):
            self.assertIn('github-token', self.rules('token=' + repr(value)))

    def test_contraction_statement_boundaries(self):
        for contraction in ("Don't", "it's", "user's"):
            for quote in ('"', "'", ''):
                self.assertEqual(self.rules(contraction + ' token=' + quote + VALUE + quote),
                                 {'generic-secret'})
                self.assertFalse(self.rules(contraction + ' token=' + quote + 'example' + quote))
            self.assertFalse(self.rules(contraction + ' echo "token=example"; other="' + VALUE + '"'))
        self.assertFalse(self.rules("echo 'token=example'; other=\"" + VALUE + '"'))

    def test_possessive_apostrophes_before_assignments(self):
        for prose in ("Users'", "users',", "Users'.", "Users':", "Users' notes"):
            for quote in ('', "'", '"'):
                with self.subTest(prose=prose, quote=quote):
                    self.assertEqual(self.rules(prose + ' token=' + quote + VALUE + quote),
                                     {'generic-secret'})
                    for safe in ('', 'example', '${NAME}', '<hi>'):
                        self.assertFalse(self.rules(prose + ' token=' + quote + safe + quote))
            self.assertFalse(self.rules(prose + ' token=\'\'; other=' + repr(VALUE)))
        self.assertEqual(list(pattern_scan.quote_spans("Users'")), [])
        self.assertFalse(self.rules("echo 'token=example'; other=" + repr(VALUE)))
        self.assertEqual(self.rules("token=r'" + VALUE + "'"), {'generic-secret'})

    def test_inner_equals_in_bare_values(self):
        value = VALUE[:12] + '=' + VALUE[12:]
        for path in (None, '.env', 'sample.sh', 'sample.toml'):
            with self.subTest(path=path):
                self.assertEqual(list(pattern_scan.findings('token=' + value, path)),
                                 [(1, 'generic-secret')])
                self.assertFalse(list(pattern_scan.findings('token=example=short', path)))
                self.assertFalse(list(pattern_scan.findings(
                    'token=example=; other=' + repr(VALUE), path)))
        self.assertEqual(list(pattern_scan.candidates(value)), [value])
        self.assertFalse(self.rules('token=' + VALUE[:12] + '= ' + VALUE[12:]))
        self.assertFalse(self.rules('token=example= # ' + VALUE))

    def test_bare_shell_word_punctuation(self):
        for punctuation in (':', '=', '/', '+', '@', '%', ',', '.', '-'):
            value = VALUE[:12] + punctuation + VALUE[12:]
            for path in ('.env', 'sample.sh', 'sample.yaml', 'sample.toml'):
                with self.subTest(punctuation=punctuation, path=path):
                    for separator in ('=', ': '):
                        self.assertEqual(list(pattern_scan.findings(
                            'accessToken' + separator + value, path)),
                            [(1, 'generic-secret')])
                    self.assertFalse(list(pattern_scan.findings(
                        'accessToken=short' + punctuation + 'word', path)))
                    self.assertFalse(list(pattern_scan.findings(
                        'accessToken=example; other=' + value, path)))
            for path in ('sample.py', 'sample.js', 'sample.ts'):
                self.assertFalse(list(pattern_scan.findings('accessToken=' + value, path)))
        self.assertFalse(self.rules('accessToken=' + VALUE[:12] + ' ' + VALUE[12:]))
        self.assertFalse(self.rules('accessToken: Optional[str]'))
        self.assertEqual(self.rules('accessToken: str = ' + repr(VALUE)), {'generic-secret'})

    def test_toml_quoted_dotted_prefixes(self):
        for prefix in ('"service config".', 'a."b c".', "'service config'.",
                       'a . "b c" . ', '"service config".nested.'):
            for name in ('clientSecret', 'api_key', 'accessToken'):
                with self.subTest(prefix=prefix, name=name):
                    self.assertEqual(list(pattern_scan.findings(
                        prefix + name + ' = ' + repr(VALUE), 'sample.toml')),
                        [(1, 'generic-secret')])
                    for safe in ('', '<hi>', 'example', '${NAME}'):
                        self.assertFalse(self.rules(prefix + name + ' = ' + repr(safe)))
            self.assertFalse(self.rules(prefix + 'monkey = ' + repr(VALUE)))
        self.assertEqual(self.rules('"service config".' + OC_NAME + '=' + repr(VALUE)),
                         {'law-oc'})

        for prefix in ('"api_key config".', "'secret token'.", 'a."private_key".'):
            self.assertFalse(self.rules(prefix + 'monkey = ' + repr(VALUE)))

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
            self.assertIn("'untracked.dat':1: law-oc [masked]", result.stdout)
            (root / '.gitignore').write_text('ignored.dat\n', encoding='utf-8')
            (root / 'ignored.dat').write_text(OC_NAME + '=' + VALUE, encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), '--root', temp],
                                    cwd=SCRIPT.parent, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("'untracked.dat':1: law-oc [masked]", result.stdout)
            self.assertNotIn('ignored.dat', result.stdout)

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
