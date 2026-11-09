# SPDX-License-Identifier: GPL-3.0-only
"""Execute the inline preparation against hostile PR files using a synthetic key."""
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
KEY = 'fixture-only-credential-7192'


class TrustedScannerTests(unittest.TestCase):
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
        for name in ('secret_scan.py', 'credentials.py', 'git_read.py'):
            (self.root / 'tools' / name).write_bytes((ROOT / 'tools' / name).read_bytes())
        self.git('add', '.')
        self.git('commit', '-qm', 'trusted base')
        self.base = self.git('rev-parse', 'HEAD').decode().strip()
        self.env.update(CI_EVENT='pull_request', CI_PR_BASE=self.base, CI_PR_BASE_REF='main',
                        CI_PUSH_SHA='f' * 40, CI_DEFAULT_BRANCH='main',
                        RUNNER_TEMP=str(self.runner), GITHUB_OUTPUT=str(self.output))

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, env=self.env,
                              check=True, capture_output=True, input=b'').stdout

    def prepare(self):
        return subprocess.run([sys.executable, '-I', '-B', '-c', PREPARATION],
                              cwd=self.root, env=self.env, capture_output=True, text=True)

    def scan(self, *, key=KEY):
        values = dict(line.split('=', 1) for line in self.output.read_text(encoding='utf-8').splitlines())
        self.extracted = Path(values['directory'])
        env = dict(self.env)
        if key is not None:
            env['LAW_OC'] = key
        return subprocess.run([sys.executable, '-I', '-B', str(self.extracted / 'secret_scan.py'),
                               '--require', '--worktree'], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def test_hostile_pr_scanner_dependencies_and_shadows_are_not_executed(self):
        hostile = "raise RuntimeError('proposed code executed')\n"
        for name in ('secret_scan.py', 'credentials.py', 'git_read.py'):
            (self.root / 'tools' / name).write_text(hostile, encoding='utf-8')
        for name in ('credentials.py', 'git_read.py', 'sitecustomize.py', 'subprocess.py'):
            (self.root / name).write_text(hostile, encoding='utf-8')
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.extracted.is_relative_to(self.root))
        self.assertEqual({p.name for p in self.extracted.iterdir()},
                         {'secret_scan.py', 'credentials.py', 'git_read.py'})
        for name in ('secret_scan.py', 'credentials.py', 'git_read.py'):
            self.assertEqual((self.extracted / name).read_bytes(),
                             self.git('cat-file', '-p', self.base + ':tools/' + name))

    def test_pr_tracked_and_untracked_exposures_are_still_detected(self):
        self.assertEqual(self.prepare().returncode, 0)
        for name, data in (('tools/credentials.py', KEY.encode()),
                           ('new-payload.bin', KEY.encode('utf-16-le')),
                           (KEY + '.txt', b'pathname only')):
            path = self.root / name
            previous = path.read_bytes() if path.exists() else None
            path.write_bytes(data)
            result = self.scan()
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(KEY, result.stdout + result.stderr)
            if previous is None:
                path.unlink()
            else:
                path.write_bytes(previous)

    def test_absent_secret_fails_required_scan(self):
        self.assertEqual(self.prepare().returncode, 0)
        self.assertEqual(self.scan(key=None).returncode, 2)

    def test_invalid_or_missing_base_never_falls_back_to_pr(self):
        for revision in ('', 'HEAD', 'f' * 40):
            with self.subTest(revision=revision):
                self.env['CI_PR_BASE'] = revision
                self.assertNotEqual(self.prepare().returncode, 0)
                self.assertFalse(self.output.exists())

    def test_hostile_nondefault_base_is_rejected_before_git_or_extraction(self):
        self.git('checkout', '-qb', 'branch-B')
        (self.root / 'tools/secret_scan.py').write_text(
            "raise RuntimeError('hostile base scanner executed')\n", encoding='utf-8')
        self.git('add', 'tools/secret_scan.py')
        self.git('commit', '-qm', 'hostile regular scanner on nondefault branch')
        self.env.update(CI_PR_BASE_REF='branch-B',
                        CI_PR_BASE=self.git('rev-parse', 'HEAD').decode().strip())
        # A valid commit with regular scanner blobs must still be rejected.
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('accepted default branch', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.runner.iterdir()), [])
        blocked_git = ("import subprocess\n"
                       "def no_git(*args, **kwargs):\n"
                       "    raise RuntimeError('Git reached before base approval')\n"
                       "subprocess.run = no_git\n")
        result = subprocess.run([sys.executable, '-I', '-B', '-c', blocked_git + PREPARATION],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertIn('accepted default branch', result.stderr)
        self.assertNotIn('Git reached', result.stderr)
        # Even the SHA is not read before checking the event's base ref.
        del self.env['CI_PR_BASE']
        result = self.prepare()
        self.assertIn('accepted default branch', result.stderr)
        self.assertNotIn('KeyError', result.stderr)

    def test_missing_mismatched_or_renamed_default_base_is_rejected(self):
        for base_ref, default in (('', 'main'), ('main', 'other'),
                                  ('other', 'other'), ('', '')):
            with self.subTest(base_ref=base_ref, default=default):
                self.env.update(CI_PR_BASE_REF=base_ref, CI_DEFAULT_BRANCH=default)
                result = self.prepare()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('accepted default branch', result.stderr)
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.runner.iterdir()), [])

    def test_missing_or_linked_trusted_dependency_fails_closed(self):
        self.git('rm', 'tools/credentials.py')
        self.git('commit', '-qm', 'missing dependency')
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())
        blob = self.git('hash-object', '-w', '--stdin').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '120000,' + blob + ',tools/credentials.py')
        self.git('commit', '-qm', 'linked dependency')
        self.env['CI_PR_BASE'] = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_main_push_and_manual_default_branch_use_pinned_objects(self):
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        for event in ('push', 'workflow_dispatch'):
            with self.subTest(event=event):
                self.env.update(CI_EVENT=event, CI_PUSH_SHA=self.base, CI_PR_BASE='invalid')
                self.assertEqual(self.prepare().returncode, 0)
                self.assertEqual(self.scan().returncode, 0)

    def test_extraction_into_pr_tree_is_refused(self):
        self.env['RUNNER_TEMP'] = str(self.root)
        self.assertNotEqual(self.prepare().returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
