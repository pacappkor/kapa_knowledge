# SPDX-License-Identifier: GPL-3.0-only
"""Whole-file deny-by-default documentation and plumbing-only Git regressions."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from doc_snapshot import (SnapshotError, document_snapshot, load_snapshot,
                          snapshot_difference)
from test_write_safety import direct_writes
import update_doc_snapshot


class RoundSixteenRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('tools', 'rules/nested', 'docs/nested'):
            (self.root / name).mkdir(parents=True)
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)

    def test_4509827699_all_bytes_and_extensions_are_governed(self):
        names = ['rules/nested/guide.txt', 'rules/.hidden', 'docs/nested/PAYLOAD.MD',
                 'docs/commands.HTML', 'docs/data.bin', 'README.extra', 'readme.MD',
                 'AGENTS.notes', 'aGeNtS', 'CLAUDE.md', 'claude.txt', 'SKILL', 'skill.TXT']
        data = b'ordinary prose\r\n\xff\x00 no recognized launcher\n'
        for name in names:
            path = self.root / name
            path.write_bytes(data)
        baseline = document_snapshot(self.root)
        self.assertEqual([row['file'] for row in baseline], sorted(names))
        for row in baseline:
            self.assertEqual(set(row), {'file', 'sha256', 'size'})
            self.assertEqual(row['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(row['size'], len(data))
            path = self.root / row['file']
            for changed in (data + b'\n', data.replace(b'\r\n', b'\n'), b''):
                path.write_bytes(changed)
                self.assertTrue(snapshot_difference(document_snapshot(self.root), baseline))
            path.write_bytes(data)
        self.assertEqual(document_snapshot(self.root), baseline)

    def test_4509827708_additions_deletions_renames_and_plain_prose_fail(self):
        path = self.root / 'docs/plain.txt'
        path.write_bytes(b'Prose without commands.\n')
        baseline = document_snapshot(self.root)
        for changed in (b'New prose without commands.\n', b'<!-- arbitrary HTML -->\n', b''):
            path.write_bytes(changed)
            self.assertTrue(snapshot_difference(document_snapshot(self.root), baseline))
        path.write_bytes(b'Prose without commands.\n')
        path.rename(self.root / 'docs/renamed.data')
        self.assertTrue(snapshot_difference(document_snapshot(self.root), baseline))
        path.write_bytes(b'new file')
        self.assertEqual(len(document_snapshot(self.root)), 2)
        path.unlink()
        (self.root / 'docs/renamed.data').unlink()
        self.assertTrue(snapshot_difference(document_snapshot(self.root), baseline))
        (self.root / 'not-governed.txt').write_bytes(b'not in governed trees')
        self.assertEqual(document_snapshot(self.root), [])

    def test_all_extension_link_and_special_inputs_refused_before_reads(self):
        for relative in ('rules/nested/payload.bin', 'docs/data.HTML', 'README.extra', 'CLAUDE'):
            path = self.root / relative
            path.write_bytes(b'fixture')
            original = Path.lstat
            for mode, flags in ((stat.S_IFLNK, 0), (stat.S_IFREG, 0x400), (stat.S_IFIFO, 0)):
                def metadata(candidate, *args, **kwargs):
                    if candidate == path:
                        return SimpleNamespace(st_mode=mode, st_file_attributes=flags)
                    return original(candidate, *args, **kwargs)
                with self.subTest(path=relative, mode=mode), patch.object(Path, 'lstat', metadata), patch.object(Path, 'read_bytes') as read:
                    with self.assertRaises(SnapshotError):
                        document_snapshot(self.root)
                    read.assert_not_called()
            path.unlink()

    def test_explicit_updater_cli_and_snapshot_schema(self):
        (self.root / 'README.md').write_bytes(b'first\r\n')
        script = common.CODE_ROOT / 'tools/update_doc_snapshot.py'
        env = dict(os.environ, KK_ROOT=str(self.root), LAW_OC='')
        def run():
            return subprocess.run([sys.executable, '-I', '-B', str(script)], env=env,
                                  capture_output=True, text=True)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = load_snapshot(self.root)
        self.assertEqual(document_snapshot(self.root), expected)
        (self.root / 'README.md').write_bytes(b'new prose\n')
        self.assertTrue(snapshot_difference(document_snapshot(self.root), expected))
        self.assertEqual(run().returncode, 0)
        self.assertEqual(document_snapshot(self.root), load_snapshot(self.root))
        self.assertEqual(list(self.root.rglob('__pycache__')), [])

    def test_updater_refuses_linked_output_before_read_or_write(self):
        target = self.root / 'tools/doc_command_snapshot.json'
        target.write_bytes(b'[]')
        original = Path.lstat
        def metadata(path, *args, **kwargs):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return original(path, *args, **kwargs)
        with patch.object(update_doc_snapshot, 'ROOT', self.root), patch.object(common, 'ROOT', self.root), patch.object(Path, 'lstat', metadata), patch.object(update_doc_snapshot, 'document_snapshot') as read, patch.object(Path, 'write_bytes') as write:
            with self.assertRaises(ValueError):
                update_doc_snapshot.main()
            read.assert_not_called()
            write.assert_not_called()

    def test_invalid_snapshot_metadata_never_echoes_arbitrary_fields(self):
        opaque = 'NeverEchoOpaqueInput'
        path = self.root / 'tools/doc_command_snapshot.json'
        for record in ({'file': opaque, 'text': opaque},
                       {'file': 'docs/a', 'sha256': opaque, 'size': 0},
                       {'file': 'docs/a', 'sha256': 'a' * 64, 'size': opaque}):
            path.write_text(json.dumps([record]), encoding='utf-8')
            with self.assertRaises(SnapshotError) as caught:
                load_snapshot(self.root)
            self.assertNotIn(opaque, str(caught.exception))
            self.assertNotIn(opaque, snapshot_difference([record], []))

    def test_4509827716_only_plumbing_and_nontransforming_cat_file_modes(self):
        safe = [['git', 'ls-files', '-s', '-z'], ['git', 'ls-tree', '-r', '--name-only', 'HEAD'],
                ['git', 'rev-parse', '--verify', 'HEAD']]
        safe += [['git', 'cat-file', option, 'HEAD:docs/data'] for option in ('-e', '-t', '-s', '-p')]
        safe += [['git', 'cat-file', '--batch']]
        unsafe = [['git', command] for command in ('show', 'diff', 'log', 'status', 'config', 'check-ignore')]
        unsafe += [['git', command, '--no-ext-diff', '--no-textconv'] for command in ('show', 'diff', 'log')]
        unsafe += [['git', 'cat-file', option, 'HEAD:docs/data'] for option in
                   ('--textconv', '--filters', '--batch-check', '--batch-command', '--buffer', '--follow-symlinks', 'blob')]
        unsafe += [['git', 'cat-file'], ['git', 'cat-file', '-p'],
                   ['git', 'cat-file', '--batch', '--filters'],
                   ['git', 'cat-file', '-p', '-t', 'HEAD']]
        for argv in safe + unsafe:
            source = 'from git_read import run_git\nrun_git(root, ' + repr(argv[1:]) + ')'
            with self.subTest(argv=argv):
                self.assertEqual(bool(direct_writes(source, 'production.py')), argv in unsafe)

    def test_cat_file_reads_blob_without_configured_textconv_or_filters(self):
        # Poisoned driver names are harmless unless Git attempts to execute one.
        subprocess.run(['git', '-C', str(self.root), 'config', 'diff.poison.textconv',
                        'no-such-doc-snapshot-textconv-program'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'config', 'filter.poison.smudge',
                        'no-such-doc-snapshot-smudge-program'], check=True, capture_output=True)
        (self.root / '.gitattributes').write_bytes(b'*.bin diff=poison filter=poison\n')
        payload = b'raw\x00blob\xff\n'
        oid = subprocess.run(['git', '-C', str(self.root), 'hash-object', '-w', '--stdin'],
                             input=payload, check=True, capture_output=True).stdout.decode().strip()
        result = subprocess.run(['git', '-C', str(self.root), 'cat-file', '-p', oid],
                                check=True, capture_output=True)
        self.assertEqual(result.stdout, payload)
        self.assertEqual(result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
