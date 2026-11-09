# SPDX-License-Identifier: GPL-3.0-only
"""Selection must include deleted paths and be conservative on uncertain bases."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

CI = Path(__file__).resolve().parents[1] / '.github/ci'
spec = importlib.util.spec_from_file_location('ci_changes', CI / 'ci_changes.py')
ci_changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_changes)


class ChangeSelectionTests(unittest.TestCase):
    def test_documents_and_data_skip_tool_suite(self):
        for path in ('README.md', 'docs/SCHEMA.md', 'sources/prec/1.json',
                     'relations/relations.jsonl', 'reviews/2026/x.jsonl',
                     'issues/new/coverage.md', 'LICENSE'):
            with self.subTest(path=path):
                self.assertEqual(ci_changes.classify([path]), dict(validate=True, tests=False))

    def test_code_dependency_workflow_and_unknown_select_all(self):
        for path in ('tools/common.py', '.github/ci/ci_changes.py',
                     '.github/workflows/ci.yml', 'deps.lock',
                     'vendor/kapa_skills/docs/law-index.json', '.gitattributes', 'unknown.file'):
            with self.subTest(path=path):
                self.assertTrue(all(ci_changes.classify([path]).values()))

    def test_empty_and_forced(self):
        self.assertFalse(any(ci_changes.classify([]).values()))
        self.assertTrue(all(ci_changes.classify([], all_checks=True).values()))

    def test_rename_tool_to_document_is_not_hidden_by_rename_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True,
                                      capture_output=True).stdout.decode().strip()
            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'CI test')
            git('config', 'diff.renames', 'true')
            (root / 'tools').mkdir()
            (root / 'tools/example.py').write_text('pass\n')
            git('add', '.')
            git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            git('mv', 'tools/example.py', 'README.md')
            git('commit', '-qm', 'rename')
            output = root / 'output'
            with patch.object(ci_changes, 'ROOT', root), patch.dict(os.environ, {
                    'CI_EVENT': 'pull_request', 'CI_BASE': base,
                    'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(root / 'summary')}):
                ci_changes.main()
            flags = dict(line.split('=', 1) for line in output.read_text().splitlines())
            self.assertEqual(flags['validate'], 'true')
            self.assertEqual(flags['tests'], 'true')
            self.assertEqual(flags['whitespace_base'], base)

    def test_failed_diff_selects_all(self):
        resolver = 'base=' + 'a' * 40 + '\nall=false\nwhitespace_base=' + 'a' * 40 + '\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output'
            with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output),
                            'GITHUB_STEP_SUMMARY': str(root / 'summary')}), \
                    patch.object(ci_changes.subprocess, 'check_output', return_value=resolver), \
                    patch.object(ci_changes.subprocess, 'run', side_effect=OSError('diff failed')):
                ci_changes.main()
            self.assertIn('validate=true', output.read_text())
            self.assertIn('tests=true', output.read_text())


if __name__ == '__main__':
    unittest.main()
