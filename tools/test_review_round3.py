# SPDX-License-Identifier: GPL-3.0-only
"""Offline regressions for the third outstanding PR 1 review batch."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tools.test_tools import fixture
from tools.test_review_regressions import response, accept_edge
import build_review_manifest
import collect_article
import common
import fetch_material
import lawapi
import lawweb
import migrate_review_digest
import validate


class RoundThreeRegressions(unittest.TestCase):
    def test_4508033914_pinned_review_contents_required_before_any_migration(self):
        for relations in (False, True):
            with self.subTest(relations=relations), fixture() as root, patch.object(lawapi, 'request', side_effect=response), patch.object(migrate_review_digest, 'resolve_commit', return_value='pinned'), patch.object(migrate_review_digest, 'build') as pinned_build:
                document = root / fetch_material.fetch('prec', '1')['document']
                fm = common.frontmatter(document.read_text(encoding='utf-8'))
                edge = common.relation('cites', fm['id'], 'law/009471@261727#a25', found_by='manual')
                review_path, row = accept_edge(root, edge)
                common.add_relations([edge])
                row.pop('source_sha256')
                if not relations:
                    row.pop('relation_review')
                    row.pop('relation_snapshot')
                    row.update(target=fm['id'], reference_status='current-usable')
                pinned = json.dumps(row, ensure_ascii=False)
                outputs = [SimpleNamespace(stdout='a' * 40), SimpleNamespace(stdout='reviews/2026/test.jsonl\n')]
                if relations:
                    outputs.append(SimpleNamespace(stdout=json.dumps(edge).encode('utf-8')))
                outputs.append(SimpleNamespace(stdout=pinned.encode('utf-8')))
                with patch.object(build_review_manifest.subprocess, 'run', side_effect=outputs) as git:
                    entries = build_review_manifest.build(root, 'pinned', relations=relations)
                self.assertEqual(entries, [dict(id=row['id'], review_sha256=common.sha(common.canonical(row, reject_masked=True)))])
                self.assertEqual(git.call_args.args[0][-1], 'a' * 40 + ':reviews/2026/test.jsonl')
                manifest = root / 'manifest.json'
                manifest.write_text(json.dumps(entries), encoding='utf-8')
                # Every pinned field matters, even when the record ID survives.
                for changes in ({'target': 'case/대법원/other'}, {'decision': 'reject'},
                                {'evidence': {'source': 'https://example.test', 'quote': 'changed'}},
                                {'reviewer_model': 'other-model'}, {'reviewed_at': '2026-01-02T00:00:00Z'}):
                    changed = dict(row, **changes)
                    review_path.write_text(pinned + '\n' + json.dumps(dict(row, id='not-allowed')) + '\n', encoding='utf-8')
                    # An earlier matching row must not be written before a later mismatch.
                    second = dict(changed, id='second')
                    pinned_build.return_value = entries + [dict(id='second', review_sha256=common.sha(common.canonical(dict(row, id='second'))))]
                    manifest.write_text(json.dumps(pinned_build.return_value), encoding='utf-8')
                    review_path.write_text(pinned + '\n' + json.dumps(second), encoding='utf-8')
                    before = review_path.read_bytes()
                    with self.assertRaisesRegex(ValueError, 'review content'):
                        migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned')
                    self.assertEqual(review_path.read_bytes(), before)
                pinned_build.return_value = entries
                manifest.write_text(json.dumps(entries), encoding='utf-8')
                # Reformatting/key order is not a content change.
                review_path.write_text(json.dumps(dict(reversed(list(row.items())))), encoding='utf-8')
                self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned'), 1)
                self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned'), 0)
                manifest.write_text(json.dumps([row['id']]), encoding='utf-8')
                with self.assertRaises(ValueError):
                    migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned')

    def test_4508039354_forged_manifest_rejected_against_pinned_commit(self):
        for relations in (False, True):
            with self.subTest(relations=relations), fixture() as root, patch.object(migrate_review_digest, 'resolve_commit', return_value='pinned'):
                entries = [dict(id='historical', review_sha256='a' * 64)]
                manifest = root / 'manifest.json'
                for forged in ([dict(id='historical', review_sha256='b' * 64)],
                               [dict(id='ad-hoc', review_sha256='a' * 64)],
                               entries + [dict(id='extra', review_sha256='c' * 64)]):
                    manifest.write_text(json.dumps(forged), encoding='utf-8')
                    with patch.object(migrate_review_digest, 'build', return_value=entries) as pinned:
                        with self.assertRaisesRegex(ValueError, 'pinned commit'):
                            migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned')
                        pinned.assert_called_once_with(root, 'pinned', relations=relations)
                manifest.write_text(json.dumps(entries), encoding='utf-8')
                with patch.object(migrate_review_digest, 'build', side_effect=ValueError('unavailable pinned commit')):
                    with self.assertRaisesRegex(ValueError, 'unavailable pinned commit'):
                        migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=relations, _expected_commit='pinned')


    def test_4508033920_detail_tracks_match_declared_source(self):
        with fixture() as root:
            for source in ('prec', 'expc', 'cgmexpc', 'molitCgmExpc'):
                record = dict(source=source, query='1', started='2026-01-01T00:00:00Z',
                              finished='2026-01-01T00:01:00Z', tracks={source: dict(status='success', count=1)})
                path = root / 'runs' / source / '2026-01-01-1.json'
                for tracks in ({source: dict(status='success', count=1)},
                               {'wrong': dict(status='success', count=1)},
                               {source: dict(status='success', count=1), 'wrong': dict(status='success', count=1)}):
                    record['tracks'] = tracks
                    valid = set(tracks) == {source}
                    self.assertEqual(validate.run_valid(record), valid)
                    common.save_json(path, record)
                    self.assertEqual(validate.validate(root)[0] == [], valid)
                path.unlink()
            self.assertTrue(validate.run_valid(record, supplemental=True))

    def test_4508033927_automatic_relation_canonical_fields(self):
        def linked_response(*args, **kwargs):
            data, url = response(*args, **kwargs)
            data['PrecService']['참조조문'] = '테스트법 제25조'
            return data, url
        with fixture() as root, patch.object(lawapi, 'request', side_effect=linked_response):
            fetch_material.fetch('prec', '1')
            path = root / 'relations/relations.jsonl'
            row = common.readjson(path.read_text(encoding='utf-8'))
            self.assertEqual(validate.validate(root)[0], [])
            for field, value in (('evidence', 'fabricated quote'), ('reviewed_by', 'bogus-model'),
                                 ('reviewed_at', '2026-01-01T00:00:00Z')):
                changed = dict(row, **{field: value})
                path.write_text(json.dumps(changed), encoding='utf-8')
                self.assertTrue(any('automatic relations differ' in e for e in validate.validate(root)[0]), field)
            path.write_text(json.dumps(row), encoding='utf-8')
            self.assertEqual(validate.validate(root)[0], [])
            # Mixed/manual discovery is retained rather than compared as generated data.
            mixed = copy.deepcopy(row)
            mixed.update(found_by=['cites-article', 'manual'], evidence='manual evidence')
            path.write_text(json.dumps(mixed), encoding='utf-8')
            self.assertEqual(validate.validate(root)[0], [])

    def test_4508033933_detail_run_day_uses_single_started_read(self):
        before = '2026-01-01T23:59:59+00:00'
        after = '2026-01-02T00:00:00+00:00'
        for fails in (False, True):
            with self.subTest(fails=fails), fixture() as root:
                def fetched(kind, ident, *, run_path, started):
                    self.assertTrue(validate.run_path_valid(run_path.relative_to(root), {'source': kind, 'started': started}))
                    self.assertEqual(started, before)
                    if fails:
                        raise ValueError('offline failure')
                with patch.object(fetch_material, 'now', side_effect=[before, after, after]), patch.object(fetch_material, 'fetch', side_effect=fetched):
                    self.assertEqual(fetch_material.run_fetch('prec', '1'), int(fails))
                self.assertEqual(validate.validate(root)[0], [])

    def test_4508033933_article_run_day_uses_single_started_read(self):
        with fixture() as root, patch.object(collect_article, 'ROOT', root), patch.object(sys, 'argv', ['collect_article', 'law/009471@261727#a25']):
            index = dict(laws={'009471': {'name': '테스트법'}}, articles={'law/009471@261727#a25': {}})
            with patch.object(collect_article, 'now', side_effect=['2026-01-01T23:59:59+00:00', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:01+00:00']), patch.object(collect_article, 'load_index', return_value=(index, root, 'WORKTREE')), patch.object(lawweb, 'context', return_value={}), patch.object(lawweb, 'linked', return_value=[]):
                self.assertEqual(collect_article.main(), 0)
            self.assertEqual(validate.validate(root)[0], [])
            run = common.readjson((root / 'runs/article/2026-01-01-1.json').read_text(encoding='utf-8'))
            self.assertEqual(run['started'], '2026-01-01T23:59:59+00:00')

    def test_4508033935_article_candidate_and_run_rollback_together(self):
        for failure in ('stage', 'replace', 'directory'):
            for preexisting in (False, True):
                with self.subTest(failure=failure, preexisting=preexisting), fixture() as root, patch.object(collect_article, 'ROOT', root), patch.object(sys, 'argv', ['collect_article', 'law/009471@261727#a25']):
                    candidate = root / 'sources/candidates/article-2026-01-01-1.jsonl'
                    candidate.parent.mkdir(parents=True)
                    if preexisting:
                        candidate.write_text('preserve existing bytes\n', encoding='utf-8')
                    before = candidate.read_bytes() if preexisting else None
                    save, replace, mkdir = common.save_json, common.os.replace, Path.mkdir
                    def fail_save(path, row):
                        if failure == 'stage' and path.parent == root / 'runs/article':
                            raise OSError('run staging failed')
                        return save(path, row)
                    def fail_replace(src, dst):
                        if failure == 'replace' and dst.parent == root / 'runs/article':
                            raise OSError('run replacement failed')
                        return replace(src, dst)
                    def fail_mkdir(path, *args, **kwargs):
                        if failure == 'directory' and path == root / 'runs/article':
                            raise OSError('run directory unwritable')
                        return mkdir(path, *args, **kwargs)
                    with patch.object(collect_article, 'now', return_value='2026-01-01T00:00:00Z'), patch.object(collect_article, 'load_index', side_effect=ValueError('offline dependency failure')), patch.object(collect_article, 'save_json', side_effect=fail_save), patch.object(common.os, 'replace', side_effect=fail_replace), patch.object(Path, 'mkdir', new=fail_mkdir):
                        with self.assertRaises(OSError):
                            collect_article.main()
                    self.assertEqual(candidate.read_bytes() if candidate.exists() else None, before)
                    self.assertEqual(list((root / 'runs/article').glob('*.json')), [])
                    self.assertEqual(list(root.rglob('.*-*')), [])
                    if preexisting:
                        candidate.unlink()
                    self.assertEqual(validate.validate(root)[0], [])


if __name__ == '__main__':
    unittest.main()
