# SPDX-License-Identifier: GPL-3.0-only
"""Pinned metadata must work without private-repository credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import vendor_skills
import validate


class VendorTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / 'repo'
        root.mkdir()
        commit = 'a' * 40
        index = {'schema': 1, 'laws': {'123456': {
            'current': {'lsiSeq': '456'},
            'versions_file': 'sources/laws/example/versions/act.json'}},
            'articles': {}, 'standards': {}}
        blobs = {'docs/law-index.json': json.dumps(index).encode(),
                 'sources/laws/example/versions/act.json':
                 b'{"versions": [{"lsiSeq": "123"}]}\n'}
        for name, raw in blobs.items():
            path = root / 'vendor/kapa_skills' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        lock = {'kapa_skills': {'commit': commit, 'vendor': {'commit': commit,
                'files': {name: common.sha(raw) for name, raw in blobs.items()}}}}
        (root / 'deps.lock').write_text(json.dumps(lock), encoding='utf-8')
        missing = patch.dict(os.environ, {'KK_SKILLS_ROOT': str(root / 'absent')})
        missing.start()
        self.addCleanup(missing.stop)
        return root, lock, index

    def test_committed_metadata_matches_lock(self):
        root = common.CODE_ROOT
        lock = common.readjson((root / 'deps.lock').read_text(encoding='utf-8'))['kapa_skills']
        files = common.vendor_manifest(lock)
        self.assertEqual(lock['vendor']['commit'], lock['commit'])
        for name in files:
            with self.subTest(path=name):
                self.assertEqual(common.sha(common.vendor_bytes(root, lock, name)), files[name])
        self.assertEqual({path.relative_to(root / 'vendor/kapa_skills').as_posix()
                          for path in (root / 'vendor/kapa_skills').rglob('*') if path.is_file()}, set(files))
        with patch.dict(os.environ, {'KK_SKILLS_ROOT': str(root / 'missing-skills')}):
            index, _, _ = common.load_index(root)
        self.assertEqual(set(files), set(vendor_skills.metadata_paths(index)))

    def test_missing_sibling_uses_hash_verified_metadata(self):
        root, lock, index = self.fixture()
        inspected = []
        result, sibling, commit = common.load_index(root, inspect_bytes=lambda p, b: inspected.append(p))
        self.assertEqual(result, index)
        self.assertEqual(len(inspected), 2)
        self.assertEqual(commit, lock['kapa_skills']['commit'])
        raw = common.dependency_bytes(root, sibling, commit,
                                      index['laws']['123456']['versions_file'])
        self.assertEqual(common.readjson(raw)['versions'][0]['lsiSeq'], '123')

    def test_index_and_history_tampering_fail_before_json_parsing(self):
        for name in ('docs/law-index.json', 'sources/laws/example/versions/act.json'):
            with self.subTest(path=name):
                root, _, _ = self.fixture()
                (root / 'vendor/kapa_skills' / name).write_bytes(b'not JSON')
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    common.load_index(root)

    def test_validator_does_not_open_ignored_vendor_metadata(self):
        root, _, _ = self.fixture()
        subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
        (root / '.gitignore').write_text('vendor/\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(root), 'add', 'deps.lock', '.gitignore'],
                       check=True, capture_output=True)
        original = Path.read_bytes
        opened = []
        def read(path):
            opened.append(path)
            return original(path)
        with patch.object(Path, 'read_bytes', read):
            errors, _, _ = validate.validate(root)
        self.assertTrue(any('outside validation file selection' in error for error in errors))
        self.assertFalse(any(path.is_relative_to(root / 'vendor') for path in opened))

    def test_inspector_can_stop_vendor_before_parsing(self):
        root, _, _ = self.fixture()
        def stop(path, raw):
            raise ValueError('stop before parse')
        with patch.object(common, 'readjson', wraps=common.readjson) as parse:
            with self.assertRaisesRegex(ValueError, 'stop before parse'):
                common.load_index(root, inspect_bytes=stop)
        # Only deps.lock was parsed, not a vendor blob.
        self.assertEqual(parse.call_count, 1)

    def test_missing_blob_fails_closed(self):
        root, _, _ = self.fixture()
        (root / 'vendor/kapa_skills/docs/law-index.json').unlink()
        with self.assertRaises(ValueError):
            common.load_index(root)

    def test_lock_revision_drift_and_worktree_fail_closed(self):
        for commit in ('b' * 40, 'WORKTREE'):
            root, lock, _ = self.fixture()
            lock['kapa_skills']['commit'] = commit
            (root / 'deps.lock').write_text(json.dumps(lock), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '잠금 오류'):
                common.load_index(root)

    def test_incomplete_manifest_fails_closed(self):
        root, lock, _ = self.fixture()
        del lock['kapa_skills']['vendor']['files']['sources/laws/example/versions/act.json']
        (root / 'deps.lock').write_text(json.dumps(lock), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '목록 불일치'):
            common.load_index(root)

    def test_vendor_parent_symlink_is_refused(self):
        root, _, _ = self.fixture()
        original = Path.lstat
        def metadata(path, *args, **kwargs):
            if path == root / 'vendor':
                from types import SimpleNamespace
                import stat
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), self.assertRaisesRegex(ValueError, 'Unsafe output path'):
            common.load_index(root)

    def test_existing_but_broken_checkout_does_not_silently_fall_back(self):
        root, _, _ = self.fixture()
        sibling = root / 'absent'
        sibling.mkdir()
        with patch.object(common, 'run_git', side_effect=OSError('missing object')):
            with self.assertRaisesRegex(ValueError, '잠금 판본'):
                common.load_index(root)

    def test_unsafe_version_metadata_names_refused(self):
        for name in ('../outside.json', '/outside.json', 'sources/laws/../versions/x.json',
                     'sources/laws/a/versions/../../x.json', 'C:/outside.json',
                     'sources\\laws\\a\\versions\\x.json', 123):
            with self.subTest(path=name), self.assertRaises(ValueError):
                vendor_skills.metadata_paths({'laws': {'x': {'versions_file': name}}})

    def test_refresh_uses_pinned_objects_not_working_tree(self):
        root, _, _ = self.fixture()
        sibling = root.parent / 'skills'
        sibling.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(sibling), *args], check=True,
                                  capture_output=True).stdout.decode().strip()
        git('init', '-q')
        git('config', 'user.name', 'CI fixture')
        git('config', 'user.email', 'ci@example.invalid')
        pinned = b'{"schema": 1, "laws": {}, "articles": {}, "standards": {}}\n'
        (sibling / 'docs').mkdir()
        (sibling / 'docs/law-index.json').write_bytes(pinned)
        git('add', '.')
        git('commit', '-qm', 'pinned')
        commit = git('rev-parse', 'HEAD')
        (sibling / 'docs/law-index.json').write_bytes(b'changed worktree')
        (root / 'deps.lock').write_text(json.dumps({'kapa_skills': {'commit': commit}}), encoding='utf-8')
        with patch.object(common, 'ROOT', root), patch.object(vendor_skills, 'check_tracked_links'):
            self.assertEqual(vendor_skills.refresh(root, sibling), 1)
        self.assertEqual((root / 'vendor/kapa_skills/docs/law-index.json').read_bytes(), pinned)
        lock = common.readjson((root / 'deps.lock').read_text())['kapa_skills']
        self.assertEqual(lock['vendor']['files'], {'docs/law-index.json': common.sha(pinned)})
        self.assertEqual(lock['vendor']['commit'], commit)


if __name__ == '__main__':
    unittest.main()
