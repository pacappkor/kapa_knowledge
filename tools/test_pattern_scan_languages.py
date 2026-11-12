# SPDX-License-Identifier: GPL-3.0-only
"""Language-table structural regressions with runtime-built synthetic values."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pattern_scan

VALUE = 'aB3dE6gH9jK2' + 'mN5pQ8sT1vW4yZ7'
OC_NAME = 'O' + 'C'


class LanguageStructureTests(unittest.TestCase):
    def check(self, template, path, expected=True):
        for value in (VALUE, '<hi>'):
            text = template.replace('VALUE', value)
            self.assertEqual(list(pattern_scan.findings(text, path)),
                             [(1, 'generic-secret')] if expected and value == VALUE else [],
                             (path, text))

    def test_raw_brackets_and_getters(self):
        for prefix, suffix in [('R"([")"', 'cpp'), ('r#"[\""#', 'rs'),
                               ('`["`', 'go'), ('@"["""', 'cs'),
                               ('#"[\""#', 'swift')]:
            self.check('auto x = ' + prefix + '; tokens[0] = "VALUE";', 'sample.' + suffix)
        self.check('accessToken = get(R"([")", "VALUE");', 'sample.cpp')
        self.check('accessToken = get(R"(VALUE)");', 'sample.cpp', False)
        self.check('auto x = R"(&;)"; tokens[0] = "VALUE";', 'sample.cpp')

    def test_swift_interpolation(self):
        for hashes in ('', '#', '###'):
            marker = chr(92) + hashes + '('
            for quote in ('"', '"""'):
                opening, closing = hashes + quote, quote + hashes
                for expr in ('runtimeOC', 'get("' + VALUE + '")', '(runtimeOC)'):
                    text = OC_NAME + ' = ' + opening + marker + expr + ')' + closing
                    self.assertFalse(list(pattern_scan.findings(text, 'sample.swift')), text)
                self.check('accessToken = ' + opening + 'VALUE' + marker + 'runtime)' + closing,
                           'sample.swift')
                self.check('accessToken = ' + opening + marker + 'runtime)VALUE' + closing,
                           'sample.swift')
        self.check('accessToken = #"VALUE\\(runtime)"#', 'sample.swift')

    def test_typescript_contexts(self):
        for declaration in ('type T = { accessToken: "VALUE" }',
                            'let x: { apiKey: "VALUE" } = y',
                            'interface T { accessToken: "VALUE" }',
                            'type T = Array<{ accessToken: "VALUE" }>',
                            'let x: Box<{ apiKey: "VALUE" }> = y',
                            'type T = { nested: { apiKey: "VALUE" } }',
                            'factory<{ accessToken: "VALUE" }>();'):
            self.check(declaration, 'sample.ts', False)
        self.check('let x = { accessToken: "VALUE" };', 'sample.ts')
        self.check('class T { run() { let x = { accessToken: "VALUE" }; } }', 'sample.ts')
        self.check('def x = /[";(/; tokens[0] = "VALUE";', 'sample.groovy')
        self.check('accessToken! = "VALUE";', 'sample.ts')
        self.check('let accessToken: string = "VALUE";', 'sample.ts')
        self.check('accessToken != "VALUE";', 'sample.ts', False)

    def test_reference_declarators(self):
        for source, suffix in [('let access_token: &str = "VALUE";', 'rs'),
                               ('const char *accessToken = &"VALUE";', 'cpp'),
                               ('const auto &accessToken = "VALUE";', 'cpp'),
                               ('const char *accessToken = &"VALUE";', 'c')]:
            self.check(source, 'sample.' + suffix)
        self.check('echo done & accessToken="VALUE"', 'sample.sh')
        self.check('accessToken=${TOKEN} & echo VALUE', 'sample.sh', False)

    def test_go_types(self):
        for type_name, initializer in [
                ('map[string]string', 'map[string]string{"x": "VALUE"}'),
                ('[]string', '[]string{"VALUE"}'), ('*string', 'ptr("VALUE")'),
                ('chan string', 'makeChan("VALUE")'), ('<-chan string', 'makeChan("VALUE")'),
                ('chan<- string', 'makeChan("VALUE")'),
                ('func(string) string', 'func(x string) string { return "VALUE" }'),
                ('pkg.Token', 'pkg.Token{"VALUE"}'),
                ('Box[string]', 'Box[string]{"VALUE"}')]:
            self.check('var accessTokens ' + type_name + ' = ' + initializer, 'sample.go')
            self.check('var accessTokens ' + type_name, 'sample.go', False)
            self.check('var description ' + type_name + ' = ' + initializer, 'sample.go', False)

    def test_extension_table(self):
        expected = {'mts': 'typescript', 'cts': 'typescript', 'mjs': 'javascript',
                    'cjs': 'javascript', 'jsx': 'javascript', 'tsx': 'typescript',
                    'pyi': 'python', 'hpp': 'cpp', 'hh': 'cpp', 'cc': 'cpp', 'cxx': 'cpp',
                    'kts': 'kotlin', 'gradle': 'groovy', 'groovy': 'groovy',
                    'swift': 'swift', 'dart': 'dart', 'scala': 'scala', 'php': 'php',
                    'rb': 'ruby', 'ps1': 'powershell'}
        for suffix, kind in expected.items():
            self.assertEqual(pattern_scan.file_type('', 'sample.' + suffix), kind)
            self.check('accessToken = "VALUE";', 'sample.' + suffix)
        for suffix in ('mts', 'cts'):
            self.check('type T = { apiKey: "VALUE" }', 'sample.' + suffix, False)

    def test_groovy_slashy(self):
        for suffix in ('groovy', 'gradle'):
            for opening, closing in [('/', '/'), ('$/', '/$')]:
                self.check('accessToken = ' + opening + 'VALUE' + closing, 'sample.' + suffix)
                self.check('def x = ' + opening + '[\"] ;(' + closing + '; tokens[0] = "VALUE";',
                           'sample.' + suffix)
                self.check('def x = ' + opening + 'VALUE' + closing + '; description = "normal";',
                           'sample.' + suffix, False)
            self.check('def x = a / b; accessToken = "VALUE";', 'sample.' + suffix)
            self.check('accessToken = /<hi>/; description = "VALUE";', 'sample.' + suffix, False)

    def test_language_adversarial_guards(self):
        cases = [('auto x = R"([")"; ' * 3000 + 'tokens[0] = "<hi>"', 'sample.cpp'),
                 ('var accessTokens ' + 'map[string]' * 12000 + 'string', 'sample.go'),
                 ('type T = { ' + 'apiKey: string; ' * 8000 + '}', 'sample.ts'),
                 ('def x = $/' + 'x' * 150000 + '/$; tokens[0] = "<hi>"', 'sample.groovy')]
        for text, path in cases:
            start = time.perf_counter()
            self.assertFalse(list(pattern_scan.findings(text, path)))
            self.assertLess(time.perf_counter() - start, 2, path)


if __name__ == '__main__':
    unittest.main()
