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
        self.assertEqual(text.count(('LAW_O' + 'C' + ':')), 1)
        self.assertIn('      - name: Scan actual LAW_OC value\n'
                      '        env:\n          TRUSTED_SCANNER: ${{ steps.scanner.outputs.directory }}\n'
                      + ('          LAW_' + 'OC' + ': ${{ secrets.LAW_' + 'OC' + ' }}\n')
                      + '        run: python -I -B "$TRUSTED_SCANNER/secret_scan.py" --require --worktree', credential)
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
        self.assertNotRegex(offline, r'(?m)^    if:')
        gate = credential.split('    runs-on:', 1)[0]
        self.assertEqual(gate, "    if: >-\n"
                         "      github.event_name == 'workflow_dispatch' ||\n"
                         "      (github.event_name == 'push' && github.ref == 'refs/heads/main') ||\n"
                         "      (github.event_name == 'pull_request' &&\n"
                         "       github.event.pull_request.head.repo.full_name == github.repository &&\n"
                         "       github.base_ref == 'main' &&\n"
                         "       github.event.pull_request.user.login != 'dependabot[bot]' &&\n"
                         "       github.actor != 'dependabot[bot]')\n")

    def test_credential_gate_event_matrix(self):
        credential = WORKFLOW.read_text(encoding='utf-8').split('\n  credential-scan:\n', 1)[1]
        gate = credential.split('    runs-on:', 1)[0].split('if: >-\n', 1)[1]
        cases = (
            ('pull_request', 'refs/pull/5/merge', True, 'main', 'contributor', 'contributor', True),
            ('pull_request', 'refs/pull/5/merge', False, 'main', 'contributor', 'contributor', False),
            ('pull_request', 'refs/pull/5/merge', True, 'release', 'contributor', 'contributor', False),
            ('pull_request', 'refs/pull/5/merge', True, 'main', 'dependabot[bot]', 'contributor', False),
            ('pull_request', 'refs/pull/5/merge', True, 'main', 'contributor', 'dependabot[bot]', False),
            ('pull_request', 'refs/pull/5/merge', True, 'main', 'dependabot[bot]', 'dependabot[bot]', False),
            ('push', 'refs/heads/main', False, '', '', 'dependabot[bot]', True),
            ('push', 'refs/heads/release', True, 'main', 'contributor', 'contributor', False),
            ('workflow_dispatch', 'refs/heads/release', False, '', '', 'dependabot[bot]', True),
        )
        for event, ref, same_repo, base, author, actor, expected in cases:
            with self.subTest(event=event, ref=ref, same_repo=same_repo, base=base,
                              author=author, actor=actor):
                expression = gate
                values = {
                    'github.event.pull_request.head.repo.full_name': 'owner/repo' if same_repo else 'fork/repo',
                    'github.event.pull_request.user.login': author,
                    'github.repository': 'owner/repo',
                    'github.event_name': event,
                    'github.base_ref': base,
                    'github.actor': actor,
                    'github.ref': ref,
                }
                for name, value in values.items():
                    expression = expression.replace(name, repr(value))
                expression = expression.replace('&&', 'and').replace('||', 'or')
                self.assertEqual(eval(' '.join(expression.split()), {'__builtins__': {}}), expected)

    def test_offline_checks_always_validate_and_test(self):
        text = WORKFLOW.read_text(encoding='utf-8').split('\n  credential-scan:\n', 1)[0]
        for command in ('"$PATTERN_SCANNER" --root .', 'tools/secret_scan.py --worktree', 'tools/validate.py --check-links',
                        'tools/validate.py', '.github/ci/ci_docs.py',
                        '.github/ci/ci_tests_supervise.py', '.github/ci/ci_integrity.py'):
            self.assertIn('run: python -I -B ' + command + '\n', text)
        self.assertEqual(re.findall(r'^        if: (.+)$', text, re.MULTILINE),
                         ["steps.pattern-scanner.outputs.scanner != ''"])
        self.assertNotIn('continue-on-error:', text)
        self.assertLess(text.index('run: python -I -B "$PATTERN_SCANNER" --root .'),
                        text.index('run: python -I -B .github/ci/ci_tests_supervise.py'))
        self.assertIn('run: bash .github/ci/ci_whitespace.sh "$BASE_SHA"', text)

    def test_pattern_scanner_uses_base_tooling_and_skips_untrusted_bootstrap(self):
        text = WORKFLOW.read_text(encoding='utf-8').split('\n  credential-scan:\n', 1)[0]
        preparation, blocking = text.split('      - name: Block credential-shaped content without secrets', 1)
        self.assertIn('CI_DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}', preparation)
        self.assertNotIn('CI_PR_BASE:', preparation)
        self.assertIn("if os.environ['CI_EVENT'] == 'pull_request':", preparation)
        self.assertIn("os.environ.get('CI_DEFAULT_BRANCH') != 'main'", preparation)
        self.assertIn("git('cat-file', '-e', revision + '^{commit}')", preparation)
        self.assertIn("'fetch', '--no-tags', '--depth=1', 'origin',", preparation)
        self.assertIn("'+refs/heads/main:refs/remotes/origin/main'", preparation)
        self.assertIn("'refs/remotes/origin/main^{commit}'", preparation)
        self.assertIn("entry = git('ls-tree', revision, '--', 'tools/pattern_scan.py')\n"
                      '              if not entry:', preparation)
        self.assertIn('::notice::Trusted main has no tools/pattern_scan.py', preparation)
        absent = preparation.split('              if not entry:\n', 1)[1].split('              else:', 1)[0]
        self.assertIn('scanner = None', absent)
        self.assertIn('blocking pattern scan skipped', absent)
        self.assertNotIn('subprocess.run', absent)
        self.assertIn("(str(scanner) if scanner is not None else '')", preparation)
        self.assertIn("        if: steps.pattern-scanner.outputs.scanner != ''\n", blocking)
        self.assertIn("('pattern_scan.py', 'secret_scan.py', 'credentials.py', 'git_read.py')", preparation)
        self.assertIn("blobs[name] = git('cat-file', '-p', fields[2])", preparation)
        self.assertIn("re.fullmatch('[0-9a-f]{40}', fields[2])", preparation)
        self.assertNotIn("git('show'", preparation)
        self.assertIn("Path(os.environ['RUNNER_TEMP'])", preparation)
        self.assertNotIn('from tools', preparation)
        self.assertIn('working-directory: ${{ github.workspace }}', blocking)
        self.assertIn('PATTERN_SCANNER: ${{ steps.pattern-scanner.outputs.scanner }}', blocking)

    def test_actions_are_commit_pinned(self):
        for workflow in WORKFLOW.parent.glob('*.yml'):
            for action in re.findall(r'^\s+(?:- )?uses: (\S+)', workflow.read_text(encoding='utf-8'), re.MULTILINE):
                self.assertRegex(action, r'^[^@]+@[0-9a-f]{40}$')
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertEqual(text.count('actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0'), 2)
        self.assertEqual(text.count('actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0'), 2)


if __name__ == '__main__':
    unittest.main()
