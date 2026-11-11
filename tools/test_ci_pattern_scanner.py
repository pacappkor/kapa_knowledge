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
        self.git('init', '-q')
        self.git('config', 'user.email', 'ci@example.invalid')
        self.git('config', 'user.name', 'CI fixture')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'tools').mkdir()
        for name in MODULES:
            (self.root / 'tools' / name).write_bytes((ROOT / 'tools' / name).read_bytes())
        self.commit()
        self.env.update(CI_EVENT='pull_request', CI_PR_BASE=self.git('rev-parse', 'HEAD').decode().strip(),
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
        # An explicit root also works when cwd is not the worktree.
        for cwd in (self.root, self.runner):
            result = subprocess.run([sys.executable, '-I', '-B', str(scanner), '--root', str(self.root)],
                                    cwd=cwd, env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("'payload':1: github-token [masked]", result.stdout)
            self.assertNotIn(payload, result.stdout + result.stderr)

    def test_only_absent_base_scanner_bootstraps_with_notice(self):
        self.git('rm', 'tools/pattern_scan.py')
        self.commit()
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        (self.root / 'tools/pattern_scan.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('::notice::Base revision has no tools/pattern_scan.py', result.stdout)
        self.assertEqual(self.scanner(), self.root / 'tools/pattern_scan.py')
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

    def test_invalid_or_missing_commit_does_not_bootstrap(self):
        for revision in ('', 'HEAD', 'f' * 40):
            self.env['CI_PR_BASE'] = revision
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
