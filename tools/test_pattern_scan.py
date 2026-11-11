# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic credentials are assembled at runtime, never stored verbatim."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pattern_scan

SCRIPT = Path(__file__).with_name('pattern_scan.py').resolve()
OC_NAME = 'O' + 'C'
VALUE = 'aB3dE6gH9jK2' + 'mN5pQ8sT1vW4yZ7'


class PatternTests(unittest.TestCase):
    def rules(self, text):
        return {rule for _, rule in pattern_scan.findings(text)}

    def test_provider_shapes(self):
        for prefix in ('ghp', 'gho', 'ghu', 'ghs', 'ghr', 'github_pat'):
            with self.subTest(prefix=prefix):
                self.assertIn('github-token', self.rules(prefix + '_' + VALUE * 2))
        self.assertIn('huggingface-token', self.rules('hf' + '_' + VALUE * 2))
        self.assertIn('aws-access-key', self.rules('AK' + 'IA' + 'A1B2C3D4' * 2))
        for kind in ('', 'RSA ', 'EC ', 'DSA ', 'OPENSSH ', 'ENCRYPTED '):
            self.assertIn('private-key', self.rules('-----BEGIN ' + kind + 'PRIVATE KEY' + '-----'))

    def test_oc_url_and_assignments(self):
        for text in ('https://law.go.kr/DRF?' + OC_NAME + '=' + VALUE + '&target=law',
                     OC_NAME + '=' + VALUE, '"' + OC_NAME.lower() + '": "' + VALUE + '"', "'" + OC_NAME + "': '" + VALUE + "'"):
            self.assertIn('law-oc', self.rules(text))

    def test_generic_assignments(self):
        for key in ('api_key', 'api-key', 'apikey', 'service_key', 'service-key',
                    'secret', 'token', 'password', 'client_secret', 'access_token'):
            for separator in ('=', ': '):
                self.assertIn('generic-secret', self.rules(key + separator + '"' + VALUE + '"'))
        self.assertFalse(self.rules('password=' + 'a' * 40))
        self.assertFalse(self.rules('token=short'))

    def test_placeholders_and_environment(self):
        for value in ('***', '<value>', 'example', 'FAKE', 'NOT-A-REAL',
                      'YOUR_KEY', '${LAW_OC}', '$LAW_OC', '%LAW_OC%',
                      '${{ secrets.LAW_OC }}', 'os.environ["LAW_OC"]',
                      'os.getenv("LAW_OC")', 'process.env.LAW_OC'):
            with self.subTest(value=value):
                self.assertFalse(self.rules(OC_NAME + '=' + value))
        self.assertFalse(self.rules('protocol=ordinary'))
        self.assertFalse(self.rules('hf' + '_short'))

    def test_tracked_cli_masking_and_utf16(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', temp, 'init', '-q'], check=True, capture_output=True)
            (root / 'tracked.dat').write_text('first\nOC=' + VALUE, encoding='utf-16')
            (root / 'untracked.dat').write_text(OC_NAME + '=' + VALUE, encoding='utf-8')
            subprocess.run(['git', '-C', temp, 'add', '--', 'tracked.dat'], check=True, capture_output=True)
            result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], cwd=temp,
                                    env=dict(os.environ, LAW_OC='', LAW_OC_FILE='must-not-open'),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("'tracked.dat':2: law-oc [masked]", result.stdout)
            self.assertNotIn(VALUE, result.stdout + result.stderr)
            self.assertNotIn('untracked.dat', result.stdout)

    def test_patterns_never_select_credentials(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            with patch.object(pattern_scan, 'repository_files', return_value=(root, [])), \
                    patch('secret_scan.selected_key', side_effect=AssertionError('must not select credentials')):
                self.assertEqual(pattern_scan.scan(root), [])

    def test_safe_diagnostics_and_read_failure(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            name = 'ghp' + '_' + VALUE * 2
            (root / name).mkdir()
            with patch.object(pattern_scan, 'repository_files', return_value=(root, [name])):
                with self.assertRaises(pattern_scan.ScanError) as caught:
                    pattern_scan.scan(root)
            self.assertNotIn(VALUE, str(caught.exception))
            self.assertIn('[redacted path]', str(caught.exception))

    def test_allowlist_is_exact_path_rule_and_line(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as temp:
            root = Path(temp)
            text = OC_NAME + '=' + VALUE
            (root / 'sample').write_text(text, encoding='utf-8')
            entry = ('sample', 'law-oc', hashlib.sha256(text.encode()).hexdigest())
            with patch.object(pattern_scan, 'repository_files', return_value=(root, ['sample'])), \
                    patch.object(pattern_scan, 'ALLOWLIST', {entry}):
                self.assertEqual(pattern_scan.scan(root), [])
                (root / 'sample').write_text(text + 'x', encoding='utf-8')
                self.assertEqual(len(pattern_scan.scan(root)), 1)


if __name__ == '__main__':
    unittest.main()
