# SPDX-License-Identifier: GPL-3.0-only
"""Execute inline pattern-tool preparation without trusting proposed PR tooling."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
PREPARATION = textwrap.dedent(WORKFLOW.split("          python -I -B - <<'PY'\n", 1)[1]
                              .split('          PY\n', 1)[0])
# Fixtures use a local trusted origin; production allows HTTPS transport only.
PREPARATION = PREPARATION.replace("GIT_ALLOW_PROTOCOL='https'", "GIT_ALLOW_PROTOCOL='file'")
MODULES = ('pattern_scan.py', 'secret_scan.py', 'credentials.py', 'git_read.py')


class TrustedPatternScannerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / 'pr'
        self.root.mkdir()
        self.runner = self.directory / 'runner'
        self.runner.mkdir()
        self.output = self.directory / 'output'
        self.env = {k: v for k, v in os.environ.items()
                    if not k.upper().startswith('GIT_') and k.upper() not in {'LAW_OC', 'LAW_OC_FILE'}}
        self.git('init', '-q', '-b', 'main')
        self.git('remote', 'add', 'origin', str(self.root))
        self.git('config', 'user.email', 'ci@example.invalid')
        self.git('config', 'user.name', 'CI fixture')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'tools').mkdir()
        for name in MODULES:
            (self.root / 'tools' / name).write_bytes((ROOT / 'tools' / name).read_bytes())
        self.commit()
        self.env.update(CI_EVENT='pull_request', CI_DEFAULT_BRANCH='main',
                        CI_PR_BASE=self.git('rev-parse', 'HEAD').decode().strip(),
                        RUNNER_TEMP=str(self.runner), GITHUB_OUTPUT=str(self.output))

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, env=self.env,
                              check=True, capture_output=True, input=b'').stdout

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture revision')

    def prepare(self):
        return subprocess.run([sys.executable, '-I', '-B', '-c', PREPARATION],
                              cwd=self.root, env=self.env, capture_output=True, text=True)

    def scanner(self):
        return Path(self.output.read_text(encoding='utf-8').splitlines()[-1].split('=', 1)[1])

    def test_hostile_pr_modules_and_allowlist_do_not_bypass_tracked_scan(self):
        # Neuter every PR module, including the scanner's embedded allowlist.
        for name in MODULES:
            (self.root / 'tools' / name).write_text('raise SystemExit(0)\n', encoding='utf-8')
        for name in ('sitecustomize.py', 'subprocess.py', 'secret_scan.py'):
            (self.root / name).write_text("raise RuntimeError('shadow executed')\n", encoding='utf-8')
        payload = 'gh' + 'p_' + 'A1b2C3d4E5f6G7h8I9j0' * 2
        (self.root / 'payload').write_text(payload, encoding='utf-8')
        self.git('add', 'payload')
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        scanner = self.scanner()
        self.assertFalse(scanner.is_relative_to(self.root))
        self.assertEqual({p.name for p in scanner.parent.iterdir()}, set(MODULES))
        for name in MODULES:
            self.assertEqual((scanner.parent / name).read_bytes(), (ROOT / 'tools' / name).read_bytes())
        # An explicit root also works when cwd is not the worktree.
        for cwd in (self.root, self.runner):
            result = subprocess.run([sys.executable, '-I', '-B', str(scanner), '--root', str(self.root)],
                                    cwd=cwd, env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("'payload':1: github-token [masked]", result.stdout)
            self.assertNotIn(payload, result.stdout + result.stderr)

    def test_extracted_scanner_covers_untracked_and_runtime_syntax(self):
        value = 'aB3dE6gH9jK2' + 'mN5pQ8sT1vW4yZ7'
        self.assertEqual(self.prepare().returncode, 0)
        scanner = self.scanner()
        sample = self.root / 'untracked.env'
        (self.root / '.gitignore').write_text('ignored.env\n', encoding='utf-8')
        (self.root / 'ignored.env').write_text('token=' + value, encoding='utf-8')
        (self.root / 'runtime.py').write_text(
            'access_token = get_access_token_from_environment()\n'
            'token = self.config.token_value\n', encoding='utf-8')
        for text, blocked in (
            ('O' + 'C=${LAW_OC}; echo done', False),
            ('O' + 'C=${LAW_OC}; token=' + repr(value), True),
            ('password: ' + value + '=', True),
            ('token=' + value[:12] + '_FAKE_' + value[12:], True),
            ('token=hf_FAKE-NOT-A-REAL-TOKEN', False),
        ):
            with self.subTest(blocked=blocked):
                sample.write_text(text, encoding='utf-8')
                result = subprocess.run(
                    [sys.executable, '-I', '-B', str(scanner), '--root', str(self.root)],
                    cwd=self.runner, env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, int(blocked), result.stdout + result.stderr)
                self.assertNotIn('ignored.env', result.stdout)
                self.assertNotIn('runtime.py', result.stdout)
                self.assertNotIn(value, result.stdout + result.stderr)
                if blocked:
                    self.assertIn("'untracked.env':1: generic-secret [masked]", result.stdout)

    def test_absent_base_scanner_skips_gate_without_executing_pr_copy(self):
        self.git('rm', 'tools/pattern_scan.py')
        self.commit()
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        marker = self.root / 'pr-scanner-executed'
        (self.root / 'tools/pattern_scan.py').write_text(
            "from pathlib import Path\nPath('pr-scanner-executed').touch()\n"
            "raise SystemExit('PR scanner must never run as the gate')\n", encoding='utf-8')
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('::notice::Trusted main has no tools/pattern_scan.py', result.stdout)
        self.assertIn('blocking pattern scan skipped', result.stdout)
        self.assertIn('the scanner exists on main', result.stdout)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'scanner=\n')
        blocking = WORKFLOW.split('      - name: Block credential-shaped content without secrets', 1)[1]
        self.assertIn("        if: steps.pattern-scanner.outputs.scanner != ''\n", blocking)
        # Reproduce the workflow's nonempty-output guard before invoking Python.
        scanner = self.output.read_text(encoding='utf-8').strip().partition('=')[2]
        if scanner:
            subprocess.run([sys.executable, '-I', '-B', scanner, '--root', '.'],
                           cwd=self.root, env=self.env, capture_output=True, check=True)
        self.assertFalse(marker.exists())
        self.assertEqual(list(self.runner.iterdir()), [])

    def test_missing_dependency_and_nonregular_scanner_fail_closed(self):
        self.git('rm', 'tools/credentials.py')
        self.commit()
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())
        blob = self.git('hash-object', '-w', '--stdin').decode().strip()
        self.git('update-index', '--cacheinfo', '120000,' + blob + ',tools/pattern_scan.py')
        self.git('commit', '-qm', 'linked scanner fixture')
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_non_main_base_still_uses_main_scanner(self):
        self.git('checkout', '-qb', 'untrusted-base')
        (self.root / 'tools/pattern_scan.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        self.commit()
        self.env.update(CI_PR_BASE_REF='untrusted-base',
                        CI_PR_BASE=self.git('rev-parse', 'HEAD').decode().strip())
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.scanner().read_bytes(), (ROOT / 'tools/pattern_scan.py').read_bytes())

    def test_invalid_default_or_unavailable_main_fails_closed(self):
        for branch in ('', 'other', 'refs/heads/main'):
            self.env['CI_DEFAULT_BRANCH'] = branch
            result = self.prepare()
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('::notice::', result.stdout)
            self.assertFalse(self.output.exists())
        self.env['CI_DEFAULT_BRANCH'] = 'main'
        self.git('checkout', '-qb', 'other')
        self.git('branch', '-D', 'main')
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('::notice::', result.stdout)
        self.assertFalse(self.output.exists())

    def test_non_pr_uses_checked_out_tool_without_base_lookup(self):
        for event in ('push', 'workflow_dispatch'):
            self.env.update(CI_EVENT=event, CI_PR_BASE='invalid')
            result = self.prepare()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.scanner(), self.root / 'tools/pattern_scan.py')

    def test_extraction_inside_worktree_is_rejected(self):
        self.env['RUNNER_TEMP'] = str(self.root)
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
