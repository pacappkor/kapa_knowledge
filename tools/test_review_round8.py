# SPDX-License-Identifier: GPL-3.0-only
"""Output containment and tracked-link security regressions, without network."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.test_tools import fixture
import common
import fetch_material
import validate


class RoundEightRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'repo'
        self.outside = self.base / 'outside'
        self.root.mkdir()
        self.outside.mkdir()
        root_patch = patch.object(common, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def git(self, *args, data=None):
        return subprocess.run(['git', '-C', str(self.root), *args], input=data,
                              check=True, capture_output=True).stdout

    def test_4508820428_normal_nested_outputs_and_replacement(self):
        old = self.root / 'old.json'
        new = self.root / 'nested/deep/new.json'
        old.write_text('before', encoding='utf-8')
        with common.staged_files([old, new]) as staged:
            staged[old].write_text('after', encoding='utf-8')
            staged[new].write_text('created', encoding='utf-8')
        self.assertEqual(old.read_text(encoding='utf-8'), 'after')
        self.assertEqual(new.read_text(encoding='utf-8'), 'created')
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['nested', 'old.json'])

    def test_outside_and_parent_traversal_rejected_before_staging(self):
        targets = [self.outside / 'new/file.json', self.root / '../outside/file.json', self.root]
        for target in targets:
            with self.subTest(case=targets.index(target)), patch.object(common.tempfile, 'mkstemp') as create:
                with self.assertRaisesRegex(ValueError, '^Unsafe output path; repository-local real directories required.$'):
                    with common.staged_files([target]):
                        self.fail('unsafe staging yielded')
                create.assert_not_called()
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_all_targets_preflighted_before_creating_any_output_directory(self):
        first = self.root / 'not-created/file.json'
        non_directory = self.root / 'plain-file'
        non_directory.write_text('sentinel', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Unsafe output path'), patch.object(common.tempfile, 'mkstemp') as create:
            with common.staged_files([first, non_directory / 'file.json']):
                self.fail('unsafe staging yielded')
        create.assert_not_called()
        self.assertFalse(first.parent.exists())
        self.assertEqual(non_directory.read_text(encoding='utf-8'), 'sentinel')

    def test_mocked_symlink_junction_and_reparse_components_are_rejected(self):
        parent = self.root / 'sources'
        parent.mkdir()
        target = parent / 'new.json'
        original = Path.lstat
        cases = [(parent, stat.S_IFLNK, 0), (parent, stat.S_IFDIR, 0x400),
                 (self.root, stat.S_IFDIR, 0x400), (target, stat.S_IFLNK, 0),
                 (target, stat.S_IFREG, 0x400)]
        for number, (unsafe, mode, attributes) in enumerate(cases):
            def metadata(path, *args, **kwargs):
                if path == unsafe:
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original(path, *args, **kwargs)
            with self.subTest(component=number), patch.object(Path, 'lstat', metadata), patch.object(common.tempfile, 'mkstemp') as create:
                with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                    with common.staged_files([target]):
                        self.fail('unsafe staging yielded')
                create.assert_not_called()
        self.assertEqual(list(parent.iterdir()), [])

    def test_resolved_destination_must_remain_beneath_root(self):
        target = self.root / 'file.json'
        original = Path.resolve
        def resolved(path, *args, **kwargs):
            return self.outside / 'file.json' if path == target else original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', resolved), patch.object(common.tempfile, 'mkstemp') as create:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                with common.staged_files([target]):
                    self.fail('unsafe staging yielded')
            create.assert_not_called()

    def test_parent_rechecked_before_publication(self):
        parent = self.root / 'sources'
        parent.mkdir()
        target = parent / 'file.json'
        original = Path.lstat
        unsafe = False
        def metadata(path, *args, **kwargs):
            if unsafe and path == parent:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), patch.object(common.os, 'replace') as replace:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                with common.staged_files([target]) as staged:
                    staged[target].write_text('new', encoding='utf-8')
                    unsafe = True
            replace.assert_not_called()
        self.assertFalse(target.exists())

    def test_failure_audit_also_rejects_reparse_parent(self):
        runs = self.root / 'runs'
        runs.mkdir()
        original = Path.lstat
        def metadata(path, *args, **kwargs):
            if path == runs:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), patch.object(fetch_material, 'ROOT', self.root), patch.object(fetch_material, 'fetch', side_effect=ValueError('invalid input')), patch.object(fetch_material, 'save_json') as save:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                fetch_material.run_fetch('prec', '1')
            save.assert_not_called()
        self.assertEqual(list(runs.iterdir()), [])

    def test_real_directory_and_file_symlinks_never_followed(self):
        sentinel = self.outside / 'sentinel.json'
        sentinel.write_text('unchanged', encoding='utf-8')
        directory = self.root / 'linked-directory'
        file = self.root / 'linked-file.json'
        try:
            directory.symlink_to(self.outside, target_is_directory=True)
            file.symlink_to(sentinel)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable; mock coverage remains active')
        for target in (directory / 'new.json', file):
            with self.subTest(directory=target != file), self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                with common.staged_files([target]):
                    self.fail('unsafe staging yielded')
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'unchanged')
        self.assertEqual(list(self.outside.iterdir()), [sentinel])

    def test_4508820428_validator_rejects_git_symlink_mode_without_os_link(self):
        self.git('init', '-q')
        oid = self.git('hash-object', '-w', '--stdin', data=b'../outside').decode().strip()
        # Git index metadata exercises the policy even on Windows without link
        # privileges, and even if the working path is an ordinary file.
        self.git('update-index', '--add', '--cacheinfo', f'120000,{oid},linked.txt')
        (self.root / 'linked.txt').write_text('ordinary file', encoding='utf-8')
        self.assertFalse((self.root / 'linked.txt').is_symlink())
        with patch.dict(os.environ, {'LAW_OC': ''}), patch.object(validate, 'load_index') as load:
            errors, warnings, count = validate.validate(self.root)
        load.assert_not_called()
        self.assertEqual(errors, ['repository: tracked symlinks are not allowed'])
        self.assertEqual((warnings, count), ([], 0))

    def test_validator_allows_normal_tracked_files(self):
        with fixture() as root, patch.dict(os.environ, {'LAW_OC': ''}):
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'add', '--', 'AGENTS.md'], check=True, capture_output=True)
            self.assertEqual(validate.validate(root)[0], [])
