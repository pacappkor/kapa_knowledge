# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic, offline regressions for credential and run chronology findings."""
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from tools.test_tools import fixture
import collect_article
import common
import credentials
import fetch_material
import lawapi
import lawweb
import secret_scan
import validate

KEY = 'RunSynthetic' + 'Oc9/+?Value'
ARTICLE = 'law/009471@261727#a25'


class RoundSixRegressions(unittest.TestCase):
    def test_4508732344_shared_canonical_environment_masking(self):
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): ' \t' + KEY + '\t\n '}):
            self.assertEqual(credentials.environment_key(), KEY)
            self.assertEqual(lawapi.key(), KEY)
            self.assertIn(('utf-8', KEY.encode()), secret_scan.environment_needles())
            value = {'nested': ['prefix ' + KEY + ' suffix'], 'OC': KEY}
            self.assertEqual(common.mask(value), {'nested': ['prefix *** suffix'], 'OC': '***'})
            self.assertNotIn(KEY.encode(), common.canonical(value))
            with self.assertRaisesRegex(ValueError, 'unmasked secret'):
                common.canonical(value, reject_masked=True)
            with tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as folder:
                path = Path(folder) / 'masked.json'
                with patch.object(common, 'ROOT', Path(folder)):
                    common.save_json(path, value)
                self.assertNotIn(KEY, path.read_text(encoding='utf-8'))

    def test_shared_environment_helper_does_not_fall_back_for_whitespace(self):
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): ' \t '}), patch.object(Path, 'read_text') as read:
            self.assertEqual(credentials.environment_key(), '')
            with self.assertRaises(RuntimeError):
                lawapi.key()
            with self.assertRaises(secret_scan.ScanError):
                secret_scan.environment_needles()
            read.assert_not_called()

    def test_4508732351_article_preflight_duplicate_keys_redacted(self):
        forms = [KEY, KEY.encode().hex(),
                 quote(KEY, safe='').replace('%2F', '%2f').replace('%3F', '%3f'),
                 base64.b64encode(KEY.encode()).decode()]
        for number, form in enumerate(forms):
            with self.subTest(form=number), tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as folder:
                root = Path(folder)
                (root / 'cases').mkdir()
                (root / 'cases/broken.md').write_text('---\n' + form + ': 1\n' + form + ': 2\n---\n', encoding='utf-8')
                output = io.StringIO()
                with patch.dict(os.environ, {('LAW_O' + 'C' + ''): ' \t' + KEY + ' '}), patch.object(collect_article, 'ROOT', root), patch.object(common, 'ROOT', root), patch.object(sys, 'argv', ['collect_article', ARTICLE]), patch.object(collect_article, 'load_index') as load, redirect_stdout(output):
                    self.assertEqual(collect_article.main(), 1)
                load.assert_not_called()
                run = json.loads(next((root / 'runs/article').glob('*.json')).read_text(encoding='utf-8'))
                self.assertEqual(run['tracks']['preflight']['error'], '[redacted]')
                self.assertNotIn(form, output.getvalue())
                self.assertTrue(validate.run_valid(run))

    def test_4508732351_all_article_failure_tracks_use_shared_redactor(self):
        forms = [KEY.encode().hex().upper(), quote(KEY, safe=''),
                 '\r\n \t'.join(base64.b64encode(KEY.encode()).decode()[i:i + 5]
                               for i in range(0, len(base64.b64encode(KEY.encode())), 5))]
        for track in ('dependency', 'context', next(iter(lawweb.ENDPOINTS))):
            for number, form in enumerate(forms):
                with self.subTest(track=track, form=number), tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as folder:
                    root = Path(folder)
                    output = io.StringIO()
                    index = {'articles': {ARTICLE: {}}, 'laws': {'009471': {'name': '테스트법'}}}
                    error = ValueError('diagnostic: ' + form)
                    with patch.dict(os.environ, {('LAW_O' + 'C' + ''): ' \t' + KEY + ' '}), patch.object(collect_article, 'ROOT', root), patch.object(common, 'ROOT', root), patch.object(sys, 'argv', ['collect_article', ARTICLE]), patch.object(collect_article, 'load_index', **({'side_effect': error} if track == 'dependency' else {'return_value': (index, root, 'WORKTREE')})), patch.object(lawweb, 'context', **({'side_effect': error} if track == 'context' else {'return_value': {}})), patch.object(lawweb, 'linked', side_effect=error), redirect_stdout(output):
                        self.assertEqual(collect_article.main(), 1)
                    run_path = next((root / 'runs/article').glob('*.json'))
                    run = json.loads(run_path.read_text(encoding='utf-8'))
                    self.assertEqual(run['tracks'][track]['error'], '[redacted]')
                    self.assertNotIn(form, output.getvalue() + run_path.read_text(encoding='utf-8'))
                    self.assertTrue(validate.run_valid(run))

    def test_4508732351_fetch_failures_cover_every_documented_representation(self):
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): KEY}):
            needles = secret_scan.environment_needles()
        for number, (_, needle) in enumerate(needles):
            with self.subTest(form=number), tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP')) as folder:
                root = Path(folder)
                output = io.StringIO()
                # This ASCII synthetic key's UTF-16 byte forms are valid UTF-8
                # diagnostic strings too, including their NUL characters.
                form = needle.decode('utf-8')
                with patch.dict(os.environ, {('LAW_O' + 'C' + ''): ' \t' + KEY + ' '}), patch.object(fetch_material, 'ROOT', root), patch.object(common, 'ROOT', root), patch.object(fetch_material, 'fetch', side_effect=ValueError('diagnostic: ' + form)), redirect_stdout(output):
                    self.assertEqual(fetch_material.run_fetch('prec', '1'), 1)
                run_path = next((root / 'runs/prec').glob('*.json'))
                run = json.loads(run_path.read_text(encoding='utf-8'))
                error = run['tracks']['prec']['error']
                self.assertFalse(list(secret_scan.matching_encodings(error.encode(), needles)))
                self.assertNotIn(form, output.getvalue())
                self.assertTrue(validate.run_valid(run))

    def test_shared_redactor_fails_closed_for_invalid_environment(self):
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): 'qz'}):
            self.assertEqual(secret_scan.redact_diagnostic('error qz'), '[redacted]')
        with patch.dict(os.environ, {'LAW_OC': ''}):
            self.assertEqual(secret_scan.redact_diagnostic('ordinary error'), 'ordinary error')

    def test_4508732357_run_chronology_compares_absolute_instants(self):
        row = dict(source='prec', query='1', tracks={'prec': dict(status='zero', count=0)})
        cases = [
            ('2026-01-01T00:00:00Z', '2025-12-31T23:59:59Z', False),
            ('2026-01-01T00:00:00.2Z', '2026-01-01T00:00:00.1Z', False),
            ('2026-01-01T23:30:00-01:00', '2026-01-02T00:00:00Z', False),
            ('2026-01-02T00:30:00+01:00', '2026-01-01T23:40:00Z', True),
            ('2026-01-01T00:00:00Z', '2026-01-01T01:00:00+01:00', True),
            ('2026-01-01T00:00:00Z', '2026-01-01T00:00:00.1Z', True),
        ]
        for started, finished, valid in cases:
            with self.subTest(started=started, finished=finished):
                timed = dict(row, started=started, finished=finished)
                self.assertEqual(validate.run_valid(timed), valid)
                self.assertEqual(validate.run_valid(timed, supplemental=True), valid)
        self.assertTrue(validate.run_valid({'date': '2026-01-01'}, supplemental=True))

    def test_4508732357_repository_rejects_reversed_run(self):
        with fixture() as root, patch.dict(os.environ, {'LAW_OC': ''}):
            row = dict(source='prec', query='1', started='2026-01-01T12:00:00Z',
                       finished='2026-01-01T11:59:59Z', tracks={'prec': dict(status='zero', count=0)})
            path = root / 'runs/prec/2026-01-01-1.json'
            common.save_json(path, row)
            self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]))
            row['finished'] = row['started']
            common.save_json(path, row)
            self.assertEqual(validate.validate(root)[0], [])
