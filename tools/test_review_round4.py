# SPDX-License-Identifier: GPL-3.0-only
"""Offline regressions for environment API scope and post-commit output failures."""
import json
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.test_tools import fixture
from tools.test_review_regressions import response
import collect_article
import common
import fetch_material
import lawapi
import lawweb
import migrate_review_digest
import validate


class RoundFourRegressions(unittest.TestCase):


    def test_4508131834_migration_refuses_nonpilot_commit_before_manifest(self):
        with fixture() as root, patch.object(migrate_review_digest, 'resolve_commit', return_value='f' * 40), patch.object(migrate_review_digest, 'build') as build:
            with self.assertRaisesRegex(ValueError, 'fixed pilot commit'):
                migrate_review_digest.migrate(root, manifest=root / 'absent.json', repository=root, commit='forged')
            build.assert_not_called()
        # A short revision is accepted only when Git resolves the exact known
        # commit object; local mirrors do not need a particular remote URL.
        with patch('build_review_manifest.subprocess.run', return_value=SimpleNamespace(stdout=migrate_review_digest.PILOT_COMMIT + '\n')) as git:
            self.assertEqual(migrate_review_digest.resolve_commit('local-mirror', '0f90463'), migrate_review_digest.PILOT_COMMIT)
            self.assertEqual(git.call_args.args[0][-1], '0f90463^{commit}')
            self.assertIn('--no-replace-objects', git.call_args.args[0])
        with fixture() as root, patch.object(migrate_review_digest, 'resolve_commit', side_effect=subprocess.CalledProcessError(1, 'git')), patch.object(migrate_review_digest, 'build') as build:
            with self.assertRaises(subprocess.CalledProcessError):
                migrate_review_digest.migrate(root, manifest=root / 'absent.json', repository=root, commit='0f90463')
            build.assert_not_called()
        result = subprocess.run([sys.executable, '-I', '-B', str(common.CODE_ROOT / 'tools/migrate_review_digest.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('_expected_commit', result.stdout)

    def test_4508131834_replacement_refs_cannot_change_pinned_reviews(self):
        with fixture() as root:
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
            git('init')
            review = root / 'reviews/2026/test.jsonl'
            review.parent.mkdir()
            row = dict(id='pinned', target='case/대법원/1', reference_status='current-usable',
                       reviewer_model='model', reviewed_at='2026-01-01T00:00:00Z', decision='accept',
                       evidence=dict(source='https://example.test', quote='original quotation'))
            review.write_text(json.dumps(row), encoding='utf-8')
            git('add', 'reviews')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-m', 'fixture baseline')
            baseline = git('rev-parse', 'HEAD')
            row['evidence']['quote'] = 'forged quotation'
            review.write_text(json.dumps(row), encoding='utf-8')
            git('add', 'reviews')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-m', 'fixture replacement')
            replacement = git('rev-parse', 'HEAD')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps([dict(id=row['id'], review_sha256=common.sha(common.canonical(row)))]), encoding='utf-8')
            git('replace', baseline, replacement)
            before = review.read_bytes()
            with self.assertRaisesRegex(ValueError, 'manifest differs from pinned commit'):
                migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit=baseline, _expected_commit=baseline)
            self.assertEqual(review.read_bytes(), before)

    def test_4508119042_detail_success_survives_broken_stdout(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            with patch('builtins.print', side_effect=BrokenPipeError('closed output')) as output:
                with self.assertRaises(BrokenPipeError):
                    fetch_material.run_fetch('prec', '1')
            output.assert_called_once()
            runs = list((root / 'runs/prec').glob('*.json'))
            self.assertEqual(len(runs), 1)
            run = common.readjson(runs[0].read_text(encoding='utf-8'))
            self.assertEqual(run['tracks'], {'prec': dict(status='success', count=1)})
            self.assertTrue((root / run['document']).exists())
            self.assertTrue((root / 'sources/prec/1.json').exists())
            self.assertEqual(validate.validate(root)[0], [])

    def test_4508119042_detail_failure_audit_precedes_error_output(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=ValueError('offline failure')):
            with patch('builtins.print', side_effect=BrokenPipeError('closed output')):
                with self.assertRaises(BrokenPipeError):
                    fetch_material.run_fetch('prec', '1')
            runs = list((root / 'runs/prec').glob('*.json'))
            self.assertEqual(len(runs), 1)
            run = common.readjson(runs[0].read_text(encoding='utf-8'))
            self.assertEqual(run['tracks']['prec']['status'], 'failure')
            self.assertEqual(run['tracks']['prec']['error'], 'offline failure')
            self.assertEqual(validate.validate(root)[0], [])

    def test_4508119042_article_audit_survives_broken_stdout(self):
        for has_candidate in (False, True):
            with self.subTest(has_candidate=has_candidate), fixture() as root, patch.object(collect_article, 'ROOT', root), patch.object(sys, 'argv', ['collect_article', 'law/009471@261727#a25']):
                index = dict(laws={'009471': {'name': '테스트법'}}, articles={'law/009471@261727#a25': {}})
                def linked(target, ctx):
                    return [dict(target='prec', source_id='1', found_by=['linked-by-center'])] if has_candidate and target == 'prec' else []
                with patch.object(collect_article, 'load_index', return_value=(index, root, 'WORKTREE')), patch.object(lawweb, 'context', return_value={}), patch.object(lawweb, 'linked', side_effect=linked), patch('builtins.print', side_effect=BrokenPipeError('closed output')):
                    with self.assertRaises(BrokenPipeError):
                        collect_article.main()
                runs = list((root / 'runs/article').glob('*.json'))
                self.assertEqual(len(runs), 1)
                run = common.readjson(runs[0].read_text(encoding='utf-8'))
                self.assertEqual(run['candidate_count'], int(has_candidate))
                self.assertEqual(run['tracks']['prec']['status'], 'success' if has_candidate else 'zero')
                self.assertEqual(len((root / run['candidates']).read_text(encoding='utf-8').splitlines()), int(has_candidate))
                self.assertEqual(validate.validate(root)[0], [])


if __name__ == '__main__':
    unittest.main()
