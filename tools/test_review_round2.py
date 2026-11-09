# SPDX-License-Identifier: GPL-3.0-only
"""Offline regressions for the second outstanding PR 1 review batch."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.test_tools import fixture, write_candidates
from tools.test_review_regressions import response, accept_edge, edit_frontmatter
import common
import fetch_material
import lawapi
import migrate_review_digest
import validate


class RoundTwoRegressions(unittest.TestCase):
    def test_4507955047_4507956013_relation_approval_bound_to_source_digest(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            document = root / fetch_material.fetch('prec', '1')['document']
            fetch_material.fetch('prec', '2')
            fm = common.frontmatter(document.read_text(encoding='utf-8'))
            edge = common.relation('overrules', fm['id'], 'case/대법원/2', found_by='manual')
            review_path, record = accept_edge(root, edge)
            common.add_relations([edge])
            self.assertEqual(validate.validate(root)[0], [])
            old_review = review_path.read_bytes()
            saved_path = root / 'sources/prec/1.json'
            saved = common.readjson(saved_path.read_text(encoding='utf-8'))
            saved['payload']['PrecService']['판례내용'] = 'replacement source text'
            saved['sha256'] = common.sha(common.canonical(saved['payload']))
            common.save_json(saved_path, saved)
            edit_frontmatter(document, source_sha256=saved['sha256'])
            fetch_material.rerender_saved(document)
            self.assertTrue(any('relation_review' in error for error in validate.validate(root)[0]))
            self.assertEqual(review_path.read_bytes(), old_review)
            # Stale history is allowed after a visible downgrade, not as approval.
            edge['review'] = 'needs-review'
            (root / 'relations/relations.jsonl').write_text(json.dumps(edge), encoding='utf-8')
            edit_frontmatter(document, relation_recheck=[edge['id']])
            self.assertEqual(validate.validate(root)[0], [])
            # Reconfirmation requires the current source digest.
            edge['review'] = 'confirmed'
            (root / 'relations/relations.jsonl').write_text(json.dumps(edge), encoding='utf-8')
            text = document.read_text(encoding='utf-8')
            fm = common.frontmatter(text)
            fm.pop('relation_recheck'); fm['provenance'].pop('relation_recheck')
            from tools.test_tools import write_doc
            write_doc(document, fm, text.split('\n---\n', 1)[1])
            record['source_sha256'] = saved['sha256']
            review_path.write_text(json.dumps(record), encoding='utf-8')
            self.assertEqual(validate.validate(root)[0], [])
            for bad in (None, True, 'bad', 'A' * 64):
                record['source_sha256'] = bad
                review_path.write_text(json.dumps(record), encoding='utf-8')
                self.assertTrue(validate.validate(root)[0])
            record.pop('source_sha256')
            review_path.write_text(json.dumps(record), encoding='utf-8')
            self.assertTrue(any('relation_review' in error for error in validate.validate(root)[0]))

    def test_relation_digest_migration_is_manifest_scoped_and_idempotent(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response), patch.object(migrate_review_digest, 'resolve_commit', return_value='pinned'), patch.object(migrate_review_digest, 'build') as pinned:
            document = root / fetch_material.fetch('prec', '1')['document']
            fm = common.frontmatter(document.read_text(encoding='utf-8'))
            edge = common.relation('cites', fm['id'], 'law/009471@261727#a25', found_by='manual')
            review_path, record = accept_edge(root, edge)
            common.add_relations([edge])
            record.pop('source_sha256')
            other = dict(record, id='not-in-manifest')
            review_path.write_text(json.dumps(record) + '\n' + json.dumps(other), encoding='utf-8')
            manifest = root / 'manifest.json'
            entries = [dict(id=record['id'], review_sha256=common.sha(common.canonical(record)))]
            pinned.return_value = entries
            manifest.write_text(json.dumps(entries), encoding='utf-8')
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=True, _expected_commit='pinned'), 1)
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=True, _expected_commit='pinned'), 0)
            rows = [json.loads(line) for line in review_path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(rows[0]['source_sha256'], fm['source_sha256'])
            self.assertEqual(rows[0]['source_sha256_basis'], 'migrated-baseline')
            self.assertNotIn('source_sha256', rows[1])
            self.assertEqual(validate.validate(root)[0], [])
            rows[0]['source_sha256'] = 'a' * 64
            review_path.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=True, _expected_commit='pinned'), 0)
            self.assertTrue(any('relation_review' in error for error in validate.validate(root)[0]))
            # Deleted approvals can migrate via their preserved source snapshot.
            (root / 'relations/relations.jsonl').write_text('', encoding='utf-8')
            record.pop('source_sha256', None)
            review_path.write_text(json.dumps(record), encoding='utf-8')
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', relations=True, _expected_commit='pinned'), 1)


    def test_4507956022_external_source_deleted_relation_tombstone(self):
        with fixture() as root:
            index = dict(laws={'009471': {'name': '테스트법'}},
                         articles={'law/009471@261727#a25': {'skill': 'test/SKILL.md'}},
                         standards={'apps@1#1': {}})
            for source in ('law/009471@261727#a25', 'apps@1#1', 'skill/test'):
                edge = common.relation('cites', source, 'law/009471')
                review_path, record = accept_edge(root, edge)
                common.add_relations([edge])
                with patch.object(validate, 'load_index', return_value=(index, root, 'WORKTREE')):
                    self.assertEqual(validate.validate(root)[0], [])
                    (root / 'relations/relations.jsonl').write_text('', encoding='utf-8')
                    self.assertTrue(any('external relation' in error for error in validate.validate(root)[0]))
                    tombstone = dict(record, id='removed', decision='needs-review',
                                     relation_review='needs-review', reviewed_at='2026-01-02T00:00:00Z')
                    for change in ({'reviewed_at': record['reviewed_at']}, {'decision': 'reject'},
                                   {'relation_snapshot': dict(record['relation_snapshot'], src='law/009471')}):
                        review_path.write_text(json.dumps(record) + '\n' + json.dumps(dict(tombstone, **change)), encoding='utf-8')
                        self.assertTrue(validate.validate(root)[0], change)
                    review_path.write_text(json.dumps(record) + '\n' + json.dumps(tombstone), encoding='utf-8')
                    self.assertEqual(validate.validate(root)[0], [])

    def test_4507956028_article_run_requires_candidate_artifact(self):
        with fixture() as root:
            path, run_path, row, run = write_candidates(root)
            self.assertEqual(validate.validate(root)[0], [])
            path.unlink()
            self.assertTrue(any('candidate contract' in error for error in validate.validate(root)[0]))
            path.write_text('', encoding='utf-8')
            self.assertTrue(any('candidate_count mismatch' in error for error in validate.validate(root)[0]))
            run['candidate_count'] = 0
            run['tracks']['expc'] = dict(status='zero', count=0)
            common.save_json(run_path, run)
            self.assertEqual(validate.validate(root)[0], [])
            path.unlink()
            self.assertTrue(any('candidate contract' in error for error in validate.validate(root)[0]))
            run['candidates'] = '../outside.jsonl'
            common.save_json(run_path, run)
            self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]))

    def test_4507956034_machine_run_paths_match_record_identity(self):
        record = dict(source='expc', query='1', started='2026-01-01T00:00:00Z',
                      finished='2026-01-01T00:01:00Z', tracks={'expc': dict(status='success', count=1)})
        with fixture() as root:
            for name in ('runs/wrong/not-a-run-name.json', 'runs/prec/2026-01-01-1.json',
                         'runs/expc/2026-01-02-1.json', 'runs/expc/2026-02-30-1.json',
                         'runs/expc/2026-01-01-0.json', 'runs/expc/nested/2026-01-01-1.json'):
                path = root / name
                common.save_json(path, record)
                self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]), name)
                path.unlink()
            common.save_json(root / 'runs/expc/2026-01-01-1.json', record)
            self.assertEqual(validate.validate(root)[0], [])
            common.save_json(root / 'runs/pilot/legacy-snapshot.json', {'date': '2026-01-01'})
            self.assertEqual(validate.validate(root)[0], [])
            path, run_path, row, run = write_candidates(root)
            run['id'] = 'wrong'
            common.save_json(run_path, run)
            self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]))

    def test_4507956036_balanced_inline_link_labels(self):
        examples = ('[바깥 [안쪽]](missing.md)', '![바깥 [안쪽]](missing.md)',
                    '[바깥 [안 [쪽]]](missing.md "제목")', '[바깥 \\[안쪽\\]](missing.md)',
                    '[바깥\n[안쪽]](missing.md)')
        with fixture() as root:
            for text in examples:
                self.assertEqual(list(validate.link_targets(text)), ['missing.md'], text)
                path = root / 'cases/README.md'
                path.write_text(text, encoding='utf-8')
                self.assertTrue(any('깨진 상대 링크 missing.md' in error for error in validate.validate(root)[0]))
                path.write_text(text.replace('missing.md', '../README.md'), encoding='utf-8')
                self.assertEqual(validate.validate(root)[0], [])
        self.assertEqual(list(validate.link_targets('`[outer [inner]](missing.md)`')), [])
        self.assertEqual(list(validate.inline_link_targets(r'\[escaped](missing.md)')), [])
        self.assertEqual(list(validate.inline_link_targets('[unclosed [label](missing.md)')), ['missing.md'])

    def test_4507956040_machine_success_requires_positive_count(self):
        record = dict(source='prec', query='1', started='2026-01-01T00:00:00Z',
                      finished='2026-01-01T00:01:00Z', tracks={'prec': dict(status='success', count=0)})
        self.assertFalse(validate.run_valid(record))
        with fixture() as root:
            path = root / 'runs/prec/2026-01-01-1.json'
            common.save_json(path, record)
            self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]))
            for status, count in (('zero', 0), ('success', 1), ('failure', 0)):
                record['tracks']['prec'] = dict(status=status, count=count, error='failed')
                common.save_json(path, record)
                self.assertEqual(validate.validate(root)[0], [])
        record['tracks']['prec'] = dict(status='success', count=0)
        self.assertTrue(validate.run_valid(record, supplemental=True))

    def test_4507956042_fetch_run_staging_failure_preserves_artifacts(self):
        for failure in ('stage', 'replace', 'directory'):
            with self.subTest(failure=failure), fixture() as root, patch.object(lawapi, 'request', side_effect=response):
                document = root / fetch_material.fetch('prec', '1')['document']
                paths = (root / 'sources/prec/1.json', document, root / 'relations/relations.jsonl')
                before = {path: path.read_bytes() for path in paths}
                data, url = response('', '', '1')
                data['PrecService']['판례내용'] = 'changed payload'
                save_json, replace, mkdir = common.save_json, fetch_material.os.replace, Path.mkdir
                def fail_save(path, row):
                    if failure == 'stage' and path.parent == root / 'runs/prec' and path.name.startswith('.'):
                        raise OSError('run staging failed')
                    return save_json(path, row)
                def fail_replace(source, target):
                    if failure == 'replace' and target.parent == root / 'runs/prec':
                        raise OSError('run replacement failed')
                    return replace(source, target)
                def fail_mkdir(path, *args, **kwargs):
                    if failure == 'directory' and path == root / 'runs/prec':
                        raise OSError('run directory unwritable')
                    return mkdir(path, *args, **kwargs)
                with patch.object(lawapi, 'request', return_value=(data, url)), patch.object(fetch_material, 'save_json', side_effect=fail_save), patch.object(fetch_material.os, 'replace', side_effect=fail_replace), patch.object(Path, 'mkdir', new=fail_mkdir):
                    if failure == 'directory':
                        with self.assertRaises(OSError):
                            fetch_material.run_fetch('prec', '1')
                    else:
                        self.assertEqual(fetch_material.run_fetch('prec', '1'), 1)
                self.assertEqual({path: path.read_bytes() for path in paths}, before)
                self.assertEqual(validate.validate(root)[0], [])
                self.assertEqual(fetch_material.run_fetch('prec', '1'), 0)
                runs = [json.loads(path.read_text(encoding='utf-8')) for path in (root / 'runs/prec').glob('*.json')]
                self.assertEqual(sum(row['tracks']['prec']['status'] == 'success' for row in runs), 1)
                self.assertEqual(validate.validate(root)[0], [])
