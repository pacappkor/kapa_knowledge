# SPDX-License-Identifier: GPL-3.0-only
"""Keep the small credential-bearing workflow's ordering and scope explicit."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml'


class WorkflowTests(unittest.TestCase):
    def test_secret_is_first_repository_run_and_scoped_to_one_step(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        commands = re.findall(r'^\s+run: (.+)$', text, re.MULTILINE)
        self.assertEqual(commands[0], '|')
        self.assertEqual(commands[1], 'python -I -B "$TRUSTED_SCANNER/secret_scan.py" --require --worktree')
        self.assertEqual(text.count('${{ secrets.LAW_OC }}'), 1)
        self.assertEqual(text.count('LAW_OC:'), 1)
        self.assertIn('      - name: Scan actual LAW_OC value\n'
                      '        env:\n          TRUSTED_SCANNER: ${{ steps.scanner.outputs.directory }}\n'
                      '          LAW_OC: ${{ secrets.LAW_OC }}\n'
                      '        run: python -I -B "$TRUSTED_SCANNER/secret_scan.py" --require --worktree', text)
        preparation, scanner = text.split('      - name: Scan actual LAW_OC value', 1)
        self.assertNotIn('secrets.', preparation)
        self.assertNotIn('if:', preparation)
        self.assertIn("python -I -B - <<'PY'", preparation)
        self.assertNotIn('from tools', preparation)
        self.assertNotIn('sys.path', preparation)
        self.assertIn("('secret_scan.py', 'credentials.py', 'git_read.py')", preparation)
        self.assertIn('CI_PR_BASE_REF: ${{ github.event.pull_request.base.ref }}', preparation)
        self.assertLess(preparation.index("os.environ.get('CI_PR_BASE_REF')"),
                        preparation.index("revision = os.environ['CI_PR_BASE']"))
        self.assertNotIn('if:', scanner.split('      - name: Reject tracked', 1)[0])
        for command in commands:
            if command.startswith('python '):
                self.assertTrue(command.startswith('python -I -B '))
        self.assertNotIn('echo', '\n'.join(commands))

    def test_basic_hosted_runner_and_triggers(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('  pull_request:\n    branches: [main]\n', text)
        for required in ('  pull_request:', '  workflow_dispatch:', 'branches: [main]',
                         '    runs-on: ubuntu-latest', '          python-version: \'3.12\'',
                         'permissions:\n  contents: read', 'persist-credentials: false',
                         'PYTHONDONTWRITEBYTECODE: "1"'):
            self.assertIn(required, text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('matrix:', text)
        self.assertEqual(text.count('    runs-on:'), 1)

    def test_unconditional_integrity_and_selected_expensive_checks(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("if: steps.changes.outputs.validate == 'true'", text)
        self.assertIn("if: steps.changes.outputs.tests == 'true'", text)
        self.assertIn('run: python -I -B tools/validate.py --check-links', text)
        self.assertIn('      - name: Check documentation snapshot without rewriting it\n'
                      "        if: steps.changes.outputs.validate == 'true'\n"
                      '        run: python -I -B .github/ci/ci_docs.py', text)
        self.assertIn('run: python -I -B .github/ci/ci_integrity.py', text)
        self.assertIn('run: bash .github/ci/ci_whitespace.sh "$BASE_SHA"', text)


if __name__ == '__main__':
    unittest.main()
