# SPDX-License-Identifier: GPL-3.0-only
"""Empty-tree fallback must still reject whitespace in authored files."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/ci/ci_whitespace.sh'


class WhitespaceTests(unittest.TestCase):
    def test_empty_tree_checks_authored_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, input=b'', stderr=subprocess.PIPE).decode().strip()

            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'CI test')
            git('config', 'core.autocrlf', 'false')
            readme = root / 'README.md'
            readme.write_text('clean\n', encoding='utf-8', newline='')
            git('add', '.')
            git('commit', '-qm', 'clean fixture')
            empty = git('hash-object', '-t', 'tree', '--stdin')

            def check(base):
                return subprocess.run(['bash', str(SCRIPT), base], cwd=root,
                                      capture_output=True, text=True)

            clean = check(empty)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            readme.write_text('bad  \n', encoding='utf-8', newline='')
            git('add', '.')
            git('commit', '-qm', 'bad authored fixture')
            result = check(empty)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('README.md', result.stdout)
            skipped = check(git('rev-parse', 'HEAD'))
            self.assertEqual(skipped.returncode, 0)
            self.assertIn('Whitespace check skipped', skipped.stdout)


if __name__ == '__main__':
    unittest.main()
