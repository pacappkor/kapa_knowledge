# SPDX-License-Identifier: GPL-3.0-only
"""Documentation-only edits must not bypass the snapshot by skipping unittest."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

CI = Path(__file__).resolve().parents[1] / '.github/ci'
spec = importlib.util.spec_from_file_location('ci_docs', CI / 'ci_docs.py')
ci_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_docs)


class DocumentationCITests(unittest.TestCase):
    def test_committed_snapshot_is_current(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(ci_docs.main(), 0)

    def test_changed_or_added_document_is_rejected_without_rewriting_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            (root / 'README.md').write_bytes(b'original\n')
            (root / 'tools').mkdir()
            snapshot = root / 'tools/doc_command_snapshot.json'
            snapshot.write_text(json.dumps(ci_docs.document_snapshot(root)), encoding='utf-8')
            before = snapshot.read_bytes()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ci_docs.main(root), 0)
            (root / 'README.md').write_bytes(b'PRIVATE_CHANGED_DOCUMENT_BODY\n')
            (root / 'docs').mkdir()
            (root / 'docs/extra.BIN').write_bytes(b'\x00\xff')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(ci_docs.main(root), 1)
            self.assertNotIn('PRIVATE_CHANGED_DOCUMENT_BODY', output.getvalue())
            self.assertEqual(snapshot.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
