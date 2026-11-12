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

    def test_nested_python_targets(self):
        for target in ('((access_token, other), x)', '[[access_token, other], x]',
                       '(x, (other, access_token))', '((access_token,), x)',
                       'access_token, (other, x)'):
            self.check(target + ' = (("VALUE", "ok"), "x")', 'sample.py')
            self.check(target + ' = runtime_values', 'sample.py', False)
        # Target traversal itself does not consume the Python recursion limit.
        text = '(' * 1200 + 'access_token' + ',)' * 1200 + ' = "<hi>"'
        pairs = pattern_scan.bracket_pairs(text, kind='python')
        self.assertEqual(len(pattern_scan.parallel_assignment(text, 0, 'python', pairs)[1]), 1)

    def test_jvm_runtime_lookups(self):
        for suffix in ('java', 'kt', 'kts', 'groovy', 'scala'):
            for method in ('getenv', 'getProperty'):
                self.check('val accessToken = System.' + method + '("VALUE")',
                           'sample.' + suffix, False)
                self.check('val accessToken = System.' + method + '("CONFIG", "VALUE")',
                           'sample.' + suffix)
                self.check('val accessToken = System.' + method + '("VALUE") + "VALUE"',
                           'sample.' + suffix)

    def test_kotlin_escaped_names(self):
        for suffix in ('kt', 'kts'):
            for target in ('`access token`', '`api key`', '`access-token`'):
                self.check('var ' + target + ' = "VALUE"', 'sample.' + suffix)
            self.check('var `access token` = System.getProperty("VALUE")',
                       'sample.' + suffix, False)
        self.check('`access token` = "VALUE"', 'sample.js', False)

    def test_shell_parameter_operator_literals(self):
        for rhs in ('${SOURCE/x/VALUE}', '${SOURCE//x/VALUE}', '${SOURCE/#x/VALUE}',
                    '${SOURCE/%x/VALUE}', '${SOURCE/VALUE/x}', '${SOURCE#VALUE}',
                    '${SOURCE##VALUE}', '${SOURCE%VALUE}', '${SOURCE%%VALUE}',
                    '${SOURCE^VALUE}', '${SOURCE^^VALUE}', '${SOURCE,VALUE}',
                    '${SOURCE,,VALUE}', '${SOURCE/x/"VALUE"}', '${SOURCE/x/${OTHER:-VALUE}}'):
            self.check('access_token=' + rhs, 'sample.sh')
            text = OC_NAME + '=' + rhs.replace('VALUE', 'FAKEVALUE')
            self.assertEqual(list(pattern_scan.findings(text, 'sample.sh')), [(1, 'law-oc')])
        for rhs in ('${VAR}', '${VAR:-}', '${VAR//$PATTERN/$OTHER}', '${VAR@Q}',
                    '${#VAR}', '${!VAR}'):
            self.assertFalse(list(pattern_scan.findings(OC_NAME + '=' + rhs, 'sample.sh')))

    def test_ruby_regex_quote_ownership(self):
        for regex in ("/'/", '/[\"\']/i', r'/a\/' + "'/", '/access_token = fake/'):
            self.check('x =~ ' + regex + '; access_token = "VALUE"', 'sample.rb')
        self.check("x =~ /'/; access_token = 'VALUE'", 'sample.rb')
        self.check("x !~ /[']/; access_token = 'VALUE'", 'sample.rb')
        self.check('x = /access_token = "VALUE"/', 'sample.rb', False)
        self.check('x = a / b; access_token = "VALUE"', 'sample.rb')

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

    def test_dollar_templates(self):
        forms = [('groovy', '$/', '/$'), ('groovy', '/', '/'),
                 ('groovy', '"', '"'), ('groovy', '"""', '"""'),
                 ('kt', '"', '"'), ('kt', '"""', '"""'),
                 ('dart', '"', '"'), ('dart', "'", "'"),
                 ('dart', '"""', '"""'), ('dart', "'''", "'''")]
        for suffix, opening, closing in forms:
            path = 'sample.' + suffix
            for expression in ('${getAccessTokenFromEnvironment()}', '$runtimeCredentialName',
                               '${lookup("' + VALUE + '", {x: runtime})}'):
                text = 'def accessToken = ' + opening + expression + closing
                self.assertFalse(list(pattern_scan.findings(text, path)), text)
                self.assertFalse(list(pattern_scan.findings(
                    OC_NAME + ' = ' + opening + expression + closing, path)), text)
                self.check('accessToken = ' + opening + 'VALUE' + expression + closing, path)
                self.check('accessToken = ' + opening + expression + ':VALUE' + closing, path)
            # Static chunks must not be joined across runtime expressions.
            self.check('accessToken = ' + opening + VALUE[:12] + '${runtime}' +
                       VALUE[12:] + closing, path, False)
        for quote in ("'", "'''"):
            text = 'accessToken = ' + quote + '${getAccessTokenFromEnvironment()}' + quote
            self.assertEqual(list(pattern_scan.findings(text, 'sample.groovy')),
                             [(1, 'generic-secret')])
        self.assertEqual(list(pattern_scan.findings(
            'accessToken' + ' = r"${getAccessTokenFromEnvironment()}"', 'sample.dart')),
            [(1, 'generic-secret')])

    def test_runtime_reference_table(self):
        forms = {
            'cs': ['Environment.GetEnvironmentVariable("KEY")', 'configuration["KEY"]',
                   'config.GetValue<string>("KEY")'],
            'java': ['System.getenv("KEY")', 'System.getProperty("KEY")'],
            'go': ['os.Getenv("KEY")', 'os.LookupEnv("KEY")'],
            'rs': ['env::var("KEY")', 'std::env::var("KEY")', 'env!("KEY")'],
            'rb': ['ENV["KEY"]', 'ENV.fetch("KEY", runtime)'],
            'php': ['getenv("KEY")', '$_ENV["KEY"]'],
            'ps1': ['$env:KEY'],
            'js': ['process.env.KEY', 'process.env["KEY"]'],
            'ts': ['process.env.KEY', 'process.env["KEY"]'],
            'py': ['os.getenv("KEY")', 'os.environ["KEY"]',
                   'os.environ.get("KEY")', 'getenv("KEY")'],
        }
        for suffix, expressions in forms.items():
            path = 'sample.' + suffix
            for expression in expressions:
                # Even credential-shaped/high-entropy lookup keys are names.
                for key in ('LAW_' + OC_NAME, VALUE):
                    rhs = expression.replace('KEY', key)
                    for name in (OC_NAME, 'accessToken'):
                        text = name + ' = ' + rhs
                        self.assertFalse(list(pattern_scan.findings(text, path)), text)
                    self.check('accessToken = ' + rhs + ' + "VALUE"', path)
            self.check('accessToken = unknownRuntime("VALUE")', path)
        defaults = {'cs': 'config.GetValue<string>("KEY", "VALUE")',
                    'java': 'System.getProperty("KEY", "VALUE")',
                    'rb': 'ENV.fetch("KEY", "VALUE")',
                    'py': 'os.getenv("KEY", "VALUE")'}
        for suffix, expression in defaults.items():
            self.check('accessToken = ' + expression, 'sample.' + suffix)
            text = OC_NAME + ' = ' + expression.replace('VALUE', VALUE)
            self.assertEqual(list(pattern_scan.findings(text, 'sample.' + suffix)),
                             [(1, 'law-oc')])

    def test_review_operator_adversarial_guards(self):
        cases = [('var `ordinary name` = runtime; ' * 5000, 'sample.kt'),
                 ('x =~ /[\"\']/; ' * 5000 + 'access_token = "<hi>"', 'sample.rb'),
                 ('access_token=${SOURCE/' + 'x' * 100000 + '/<hi>}', 'sample.sh')]
        for text, path in cases:
            start = time.perf_counter()
            self.assertFalse(list(pattern_scan.findings(text, path)))
            self.assertLess(time.perf_counter() - start, 2, path)

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
