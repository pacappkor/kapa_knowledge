# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the shared resolver with real Git histories."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / '.github/ci'


class BaseTests(unittest.TestCase):
    def test_histories_and_whitespace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, input=b'', stderr=subprocess.PIPE).decode().strip()

            def commit(text):
                (root / 'README.md').write_bytes(text.encode())
                git('add', 'README.md')
                git('commit', '-qm', 'fixture')
                return git('rev-parse', 'HEAD')

            def check(event, before, base, all_checks, bad=True):
                summary = root / 'summary'
                summary.unlink(missing_ok=True)
                result = subprocess.check_output(
                    ['bash', str(TOOLS / 'ci_base.sh')], cwd=root, text=True, stderr=subprocess.PIPE,
                    env={**os.environ, 'CI_EVENT': event, 'CI_BASE': before,
                         'CI_BEFORE': before, 'GITHUB_STEP_SUMMARY': str(summary)})
                resolved = dict(line.split('=', 1) for line in result.splitlines())
                self.assertEqual(resolved['whitespace_base'], base)
                self.assertEqual(resolved['all'], str(all_checks).lower())
                if event == 'pull_request' and all_checks:
                    self.assertEqual(resolved['base'], '')
                if all_checks and base == git('rev-parse', 'HEAD'):
                    self.assertIn('rewind introduces no new commits', summary.read_text())
                diff = subprocess.run(['git', 'diff', '--check', base, 'HEAD'],
                                      cwd=root, capture_output=True)
                self.assertEqual(diff.returncode != 0, bad)

            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'CI test')
            git('config', 'core.autocrlf', 'false')
            initial = commit('base\n')
            early = commit('base\nbad  \n')
            before = commit('base\nbad  \nclean tip\n')
            git('tag', 'reachable-before', before)
            empty = git('hash-object', '-t', 'tree', '--stdin')
            check('push', initial, initial, False)
            check('pull_request', initial, initial, False)
            for missing in ('', '0' * 40, 'f' * 40):
                check('push', missing, empty, True)
            check('pull_request', 'f' * 40, empty, True)
            check('workflow_dispatch', before, early, True, bad=False)
            git('checkout', '-q', '--detach', early)
            check('push', before, early, True, bad=False)
            git('checkout', '-q', '--detach', initial)
            commit('base\nrewritten bad  \n')
            check('push', before, initial, True)
            git('checkout', '-q', '--orphan', 'orphan')
            commit('base\nbad  \nclean tip\n')
            check('push', before, empty, True)
            check('workflow_dispatch', before, empty, True)
            check('pull_request', before, empty, True)
            commit('base\nbad  \nsecond orphan commit\n')
            check('pull_request', before, empty, True)
            check('push', git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD'), False, bad=False)


if __name__ == '__main__':
    unittest.main()
