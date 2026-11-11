# SPDX-License-Identifier: GPL-3.0-only
"""Keep secret-free checks separate from the credential-bearing job."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml'


class WorkflowTests(unittest.TestCase):
    def test_secret_is_first_repository_run_and_scoped_to_one_step(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        offline, credential = text.split('\n  credential-scan:\n', 1)
        self.assertNotIn('secrets.', offline)
        self.assertNotIn('--require', offline)
        commands = re.findall(r'^\s+run: (.+)$', credential, re.MULTILINE)
        self.assertEqual(commands, ['|', 'python -I -B "$TRUSTED_SCANNER/secret_scan.py" --require --worktree'])
        self.assertEqual(text.count('${{ secrets.LAW_OC }}'), 1)
        self.assertEqual(text.count('LAW_OC:'), 1)
        self.assertIn('      - name: Scan actual LAW_OC value\n'
                      '        env:\n          TRUSTED_SCANNER: ${{ steps.scanner.outputs.directory }}\n'
                      '          LAW_OC: ${{ secrets.LAW_OC }}\n'
                      '        run: python -I -B "$TRUSTED_SCANNER/secret_scan.py" --require --worktree', credential)
        preparation, scanner = credential.split('      - name: Scan actual LAW_OC value', 1)
        self.assertNotIn('secrets.', preparation)
        self.assertIn("python -I -B - <<'PY'", preparation)
        self.assertNotIn('from tools', preparation)
        self.assertNotIn('sys.path', preparation)
        self.assertIn("('secret_scan.py', 'credentials.py', 'git_read.py')", preparation)
        self.assertIn('CI_PR_BASE_REF: ${{ github.event.pull_request.base.ref }}', preparation)
        self.assertLess(preparation.index("os.environ.get('CI_PR_BASE_REF')"),
                        preparation.index("revision = os.environ['CI_PR_BASE']"))
        self.assertNotIn('if:', scanner)
        for command in re.findall(r'^\s+run: (.+)$', text, re.MULTILINE):
            if command.startswith('python '):
                self.assertTrue(command.startswith('python -I -B '))
        self.assertNotIn('echo', '\n'.join(commands))

    def test_basic_hosted_runner_and_triggers(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('on:\n  pull_request:\n  push:\n  workflow_dispatch:\n', text)
        for required in ('    runs-on: ubuntu-latest', '          python-version: \'3.12\'',
                         'permissions:\n  contents: read', 'persist-credentials: false',
                         'PYTHONDONTWRITEBYTECODE: "1"'):
            self.assertIn(required, text)
        self.assertNotIn('pull_request_target', text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('matrix:', text)
        self.assertEqual(text.count('    runs-on:'), 2)
        self.assertEqual(text.count('persist-credentials: false'), 2)

    def test_only_credential_job_has_an_event_gate(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        offline, credential = text.split('\n  credential-scan:\n', 1)
        self.assertNotIn('    if:', offline)
        gate = credential.split('    runs-on:', 1)[0]
        self.assertEqual(gate, "    if: >-\n"
                         "      github.event_name == 'workflow_dispatch' ||\n"
                         "      (github.event_name == 'push' && github.ref == 'refs/heads/main') ||\n"
                         "      (github.event_name == 'pull_request' &&\n"
                         "       github.event.pull_request.head.repo.full_name == github.repository)\n")

    def test_offline_checks_always_validate_and_test(self):
        text = WORKFLOW.read_text(encoding='utf-8').split('\n  credential-scan:\n', 1)[0]
        for command in ('tools/secret_scan.py --worktree', 'tools/validate.py --check-links',
                        'tools/validate.py', '.github/ci/ci_docs.py',
                        '.github/ci/ci_tests_supervise.py', '.github/ci/ci_integrity.py'):
            self.assertIn('run: python -I -B ' + command + '\n', text)
        self.assertNotIn('        if:', text)
        self.assertIn('run: bash .github/ci/ci_whitespace.sh "$BASE_SHA"', text)


if __name__ == '__main__':
    unittest.main()
