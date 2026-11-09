# SPDX-License-Identifier: GPL-3.0-only
"""Regression checks for ignored files, committed symlinks and stale blobs."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / '.github/ci/ci_integrity.py'


class IntegrityTests(unittest.TestCase):
    def test_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args, data=None):
                return subprocess.check_output(['git', *args], cwd=root, input=data, stderr=subprocess.PIPE).decode().strip()

            def check(ok):
                result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), 'generated'],
                                        cwd=root, capture_output=True)
                self.assertEqual(result.returncode == 0, ok, result.stderr)

            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'CI test')
            git('config', 'core.autocrlf', 'false')
            generated = root / 'generated'
            generated.write_bytes(b'current\n')
            git('add', '.')
            git('commit', '-qm', 'regular file')
            check(True)
            generated.write_bytes(b'stale\n')
            check(False)
            generated.write_bytes(b'current\n')
            (root / '.gitignore').write_bytes(b'ignored\n')
            git('add', '.gitignore')
            git('commit', '-qm', 'ignore rule')
            (root / 'ignored').write_bytes(b'residue\n')
            check(False)
            (root / 'ignored').unlink()
            git('rm', 'generated')
            (root / '.gitignore').write_bytes(b'generated\n')
            git('add', '.gitignore')
            git('commit', '-qm', 'ignore deleted generated file')
            generated.write_bytes(b'current\n')
            check(False)
            generated.unlink()
            link = git('hash-object', '-w', '--stdin', data=b'target')
            git('update-index', '--add', '--cacheinfo', '120000', link, 'generated')
            git('commit', '-qm', 'symlink generated file')
            check(False)
            result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), '--symlinks-only'],
                                    cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
