# SPDX-License-Identifier: GPL-3.0-only
"""Offline regressions for selected fallback keys, mapping keys and path scope."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.test_tools import fixture
import common
import credentials
import fetch_material
import lawapi
import secret_scan
import validate

KEY = 'FallbackSynthetic' + 'Oc9/+?Value'


@contextmanager
def synthetic_fallback():
    with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as folder:
        path = Path(folder) / 'synthetic-credential.txt'
        path.write_text(' \t' + KEY + '\n', encoding='utf-8-sig')
        with patch.dict(os.environ, {'LAW_OC': '', 'LAW_OC_FILE': str(path)}), patch.object(credentials, '_file_selection', None), patch.object(common, 'ROOT', Path(folder)):
            yield Path(folder), path


class RoundSevenRegressions(unittest.TestCase):
    def test_4508801293_selected_fallback_shared_without_rereading(self):
        with synthetic_fallback() as (_, path):
            self.assertEqual(lawapi.key(), KEY)
            path.unlink()
            with patch.object(Path, 'read_text', side_effect=AssertionError('unexpected credential read')):
                self.assertEqual(credentials.selected_key(), KEY)
                self.assertEqual(lawapi.key(), KEY)
                self.assertEqual(common.mask({'text': KEY}), {'text': '***'})
                self.assertEqual(lawapi.sanitize({'text': KEY}), {'text': '***'})
                for _, needle in secret_scan.value_needles(KEY):
                    self.assertEqual(secret_scan.redact_diagnostic(needle.decode('utf-8')), '[redacted]')
                self.assertIsNone(secret_scan.environment_needles())

    def test_4508801293_fetch_run_redacts_selected_fallback_encodings(self):
        for number, (_, needle) in enumerate(secret_scan.value_needles(KEY)):
            with self.subTest(form=number), synthetic_fallback() as (root, _):
                form = needle.decode('utf-8')
                output = io.StringIO()
                def fail_fetch(*args, **kwargs):
                    self.assertEqual(lawapi.key(), KEY)
                    raise ValueError('failure: ' + form)
                with patch.object(fetch_material, 'ROOT', root), patch.object(common, 'ROOT', root), patch.object(fetch_material, 'fetch', side_effect=fail_fetch), redirect_stdout(output):
                    self.assertEqual(fetch_material.run_fetch('prec', '1'), 1)
                path = next((root / 'runs/prec').glob('*.json'))
                record = json.loads(path.read_text(encoding='utf-8'))
                self.assertFalse(list(secret_scan.matching_encodings(record['tracks']['prec']['error'].encode(), secret_scan.value_needles(KEY))))
                self.assertNotIn(form, output.getvalue())
                self.assertTrue(validate.run_valid(record))

    def test_unselected_fallback_is_never_opened_by_mask_redactor_or_scanner(self):
        with synthetic_fallback() as (root, _):
            with patch.object(Path, 'read_text', side_effect=AssertionError('unexpected credential read')):
                self.assertIsNone(credentials.selected_key())
                self.assertEqual(common.mask('ordinary'), 'ordinary')
                self.assertEqual(secret_scan.redact_diagnostic('ordinary'), 'ordinary')
                self.assertIsNone(secret_scan.scan(root))
            command = [sys.executable, '-I', '-B', str(common.CODE_ROOT / 'tools/secret_scan.py'), '--require']
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(KEY, result.stdout + result.stderr)

    def test_environment_selection_has_priority_and_does_not_open_fallback(self):
        with synthetic_fallback():
            lawapi.key()
            env_key = 'EnvironmentSelected' + 'Synthetic9'
            with patch.dict(os.environ, {'LAW_OC': ' \t' + env_key + ' '}), patch.object(Path, 'read_text') as read:
                self.assertEqual(lawapi.key(), env_key)
                self.assertEqual(common.mask(env_key), '***')
                self.assertEqual(secret_scan.redact_diagnostic(env_key.encode().hex()), '[redacted]')
                self.assertIn(('utf-8', env_key.encode()), secret_scan.environment_needles())
                read.assert_not_called()

    def test_4508801297_mapping_keys_masked_and_canonical_rejects(self):
        payload = {KEY: 'one', 'prefix-' + KEY + '-suffix': 'two',
                   'nested': [{KEY: {'url': KEY}}], 'OC': 'anything'}
        expected = {'***': 'one', 'prefix-***-suffix': 'two',
                    'nested': [{'***': {'url': '***'}}], 'OC': '***'}
        for fallback in (False, True):
            with self.subTest(fallback=fallback), synthetic_fallback() as (root, _):
                with patch.dict(os.environ, {'LAW_OC': '' if fallback else ' \t' + KEY + ' '}):
                    if fallback:
                        lawapi.key()
                    self.assertEqual(common.mask(payload), expected)
                    self.assertEqual(lawapi.sanitize(payload), expected)
                    with self.assertRaisesRegex(ValueError, 'unmasked secret'):
                        common.canonical(payload, reject_masked=True)
                    path = root / 'payload.json'
                    common.save_json(path, payload)
                    self.assertEqual(json.loads(path.read_text(encoding='utf-8')), expected)
                    self.assertNotIn(KEY.encode(), common.canonical(payload))

    def test_mapping_key_redaction_collisions_rejected_without_discarding_data(self):
        with patch.dict(os.environ, {'LAW_OC': KEY}):
            for payload in ({KEY: 'secret-named', '***': 'ordinary'},
                            {'prefix' + KEY: 1, 'prefix***': 2}):
                with self.assertRaisesRegex(ValueError, '^masked mapping keys collide$'):
                    common.mask(payload)
                with self.assertRaises(ValueError):
                    common.canonical(payload, reject_masked=True)
            normal = {'a': 'one', 'nested': [{'b': 'two'}]}
            self.assertEqual(json.loads(common.canonical(normal, reject_masked=True)), normal)

    def nested_checkout(self, root, name):
        parent = root / name
        repo = parent / 'checkout'
        repo.mkdir(parents=True)
        for child in list(root.iterdir()):
            if child != parent:
                shutil.move(str(child), repo / child.name)
        subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True, capture_output=True)
        return repo

    def test_4508801302_checkout_parent_and_external_paths_do_not_match(self):
        key = 'CheckoutParent' + 'SyntheticOc9'
        with fixture() as root, patch.dict(os.environ, {'LAW_OC': key}):
            repo = self.nested_checkout(root, key)
            sibling = root / 'external' / key
            (sibling / 'docs').mkdir(parents=True)
            index = {'schema': 1, 'laws': {'009471': {'name': '테스트법'}},
                     'articles': {'law/009471@261727#a25': {}}, 'standards': {}}
            (sibling / 'docs/law-index.json').write_text(json.dumps(index), encoding='utf-8')
            (repo / 'deps.lock').write_text(json.dumps({'kapa_skills': {'commit': 'WORKTREE'}}), encoding='utf-8')
            with patch.dict(os.environ, {'KK_SKILLS_ROOT': str(sibling)}), patch.object(validate, 'load_index', side_effect=lambda root, **kw: common.load_index(root, **kw)):
                self.assertEqual(secret_scan.scan(repo, worktree=True), [])
                errors, _, _ = validate.validate(repo)
                self.assertEqual(errors, [])
                # External path components stay out of scope, but its content
                # must still be inspected before parsing.
                (sibling / 'docs/law-index.json').write_text(json.dumps(dict(index, note=key.encode().hex())), encoding='utf-8')
                errors, _, _ = validate.validate(repo)
                self.assertTrue(any('[external input]: LAW_OC exposure' in error for error in errors))
                self.assertFalse(any(key in error for error in errors))

    def test_4508801302_per_read_guard_still_checks_relative_pathnames(self):
        key = 'RelativePath' + 'SyntheticOc9'
        with fixture() as root, patch.dict(os.environ, {'LAW_OC': key}):
            (root / (key + '.txt')).write_text('ordinary', encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
            # Bypass the earlier scan to exercise the later per-input guard.
            with patch.object(secret_scan, 'scan', return_value=[]):
                errors, _, _ = validate.validate(root)
            self.assertTrue(any('[redacted path]: LAW_OC exposure' in error for error in errors))
            self.assertFalse(any(key in error for error in errors))
