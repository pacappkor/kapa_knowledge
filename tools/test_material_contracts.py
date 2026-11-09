# SPDX-License-Identifier: GPL-3.0-only
"""Offline membership, source assertion, publication and provenance regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import material_contracts as contracts
import validate
import build_material_catalog


class VersionTests(unittest.TestCase):
    def test_membership_keeps_multiple_effective_dates_without_article_claim(self):
        index = {'laws': {'123456': {'versions_file': 'sources/laws/test/versions/act.json'}}}
        raw = json.dumps({'lsId': '123456', 'versions': [
            {'lsiSeq': '7', 'efYd': '20260101'}, {'lsiSeq': '7', 'efYd': '20270101'}]}).encode()
        result = contracts.version_reference('law/123456@7', index, lambda _: raw)
        self.assertEqual(result['catalog_status'], 'verified-version-list')
        self.assertEqual(len(result['entries']), 2)
        self.assertEqual(result['metadata_sha256'], common.sha(raw))
        self.assertEqual(result['article_text_status'], 'unavailable')
        self.assertEqual(result['applicability_status'], 'unverified')
        for ident in ('law/123456@7#a2', 'law/123456', 'law/123456@unknown'):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                contracts.version_reference(ident, index, lambda _: raw)
        self.assertEqual(contracts.version_reference('law/123456@8', index, lambda _: raw)
                         ['catalog_status'], 'unavailable')

    def test_wrong_law_malformed_metadata_and_unsafe_paths_fail_closed(self):
        index = {'laws': {'123456': {'versions_file': 'sources/laws/test/versions/act.json'}}}
        for raw in (b'{"lsId":"654321","versions":[{"lsiSeq":"7"}]}',
                    b'{"lsId":"123456","versions":[null]}',
                    b'{"lsId":"123456","versions":{}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                contracts.version_reference('law/123456@7', index, lambda _: raw)
        index['laws']['123456']['versions_file'] = '../outside.json'
        with self.assertRaises(ValueError):
            contracts.version_reference('law/123456@7', index, lambda _: self.fail('unsafe read'))

    def test_current_index_and_absent_predecessor_are_distinct(self):
        index = {'laws': {'123456': {'current': {'lsiSeq': '7'}}}}
        read = lambda _: self.fail('unexpected metadata read')
        self.assertEqual(contracts.version_reference('law/123456@7', index, read)
                         ['catalog_status'], 'verified-current-index')
        self.assertEqual(contracts.version_reference('law/654321@7', index, read)
                         ['catalog_status'], 'unavailable')


class CatalogTests(unittest.TestCase):
    def build(self, research=None, history=None):
        root = common.CODE_ROOT
        index, sibling, commit = common.load_index(root)
        def read(name):
            if research is not None and name == contracts.EVIDENCE:
                return json.dumps(research, ensure_ascii=False).encode()
            if history is not None and name == contracts.HISTORY:
                return json.dumps(history, ensure_ascii=False).encode()
            return (root / name).read_bytes()
        return contracts.build_catalog(read, index, commit,
                    lambda name: common.dependency_bytes(root, sibling, commit, name))

    def test_required_identity_items_cannot_be_deleted_or_renamed_before_generation(self):
        root = common.CODE_ROOT
        research = common.readjson((root / contracts.EVIDENCE).read_bytes())
        original_read = Path.read_bytes
        for key in contracts.IDENTITY_SOURCES:
            for action in ('delete', 'rename'):
                changed = copy.deepcopy(research)
                if action == 'delete':
                    changed['items'] = [r for r in changed['items'] if r['item'] != key]
                else:
                    next(r for r in changed['items'] if r['item'] == key)['item'] = 'unrecognized/' + key
                def read(path):
                    if path == root / contracts.EVIDENCE:
                        return json.dumps(changed, ensure_ascii=False).encode()
                    if path == root / contracts.HISTORY:
                        self.fail('Incomplete identity set reached historical generation')
                    return original_read(path)
                with self.subTest(key=key, action=action), \
                        patch.object(Path, 'read_bytes', read), \
                        patch.object(build_material_catalog, 'save_json') as save:
                    with self.assertRaisesRegex(ValueError, 'Required held identity'):
                        self.build(research=changed)
                    with self.assertRaisesRegex(ValueError, 'Required held identity'):
                        build_material_catalog.main()
                    save.assert_not_called()

    def test_identity_completeness_allows_unrelated_faq_extensions(self):
        research = common.readjson((common.CODE_ROOT / contracts.EVIDENCE).read_bytes())
        extra = copy.deepcopy(next(r for r in research['items'] if r['item'].startswith('faq/')))
        old_sid = extra['item'].split('/')[1]
        extra['item'] = 'faq/999999999'
        for evidence in extra['evidence']:
            evidence['url'] = evidence['url'].replace(old_sid, '999999999')
        research['items'].append(extra)
        catalog = self.build(research=research)
        self.assertEqual({r['case_no'] for r in catalog['records'] if r['kind'] == 'identity-hold'},
                         set(contracts.IDENTITY_SOURCES))
        self.assertEqual(sum(r['kind'] == 'faq' for r in catalog['records']), 12)
        self.assertTrue(any(r['id'] == 'faq/molit/lawgo/999999999' for r in catalog['records']))

    def test_current_catalog_bytes_remain_identical_without_regeneration(self):
        generated = self.build()
        self.assertEqual(common.canonical(generated),
                         (common.CODE_ROOT / contracts.CATALOG).read_bytes())

    def test_real_pilot_catalog_is_reproducible_and_explicitly_held(self):
        catalog = self.build()
        saved = common.readjson((common.CODE_ROOT / contracts.CATALOG).read_bytes())
        self.assertEqual(catalog, saved)
        faqs = [r for r in catalog['records'] if r['kind'] == 'faq']
        holds = [r for r in catalog['records'] if r['kind'] == 'identity-hold']
        self.assertEqual(len(faqs), 11)
        self.assertEqual(len(holds), 2)
        for row in faqs:
            self.assertEqual(row['case_no'], '')
            self.assertEqual(row['source_identifiers']['lawgo'], row['source_id'])
            self.assertEqual(row['source_envelope_status'], 'unavailable')
            self.assertTrue(row['publication_hold'])
            self.assertEqual(set(row) - {'provenance'}, set(row['provenance']))
        for row in holds:
            self.assertEqual(len(row['assertions']), 2)
            self.assertEqual(row['identity_status'], 'unresolved')
            self.assertTrue(row['publication_hold'])
            self.assertEqual(len({a['asserted_replied'] for a in row['assertions']}), 2)
        versions = catalog['historical_versions']
        self.assertEqual(len(versions), 48)
        self.assertEqual(sum(v['catalog_status'] == 'unavailable' for v in versions), 38)
        missing_laws = {v['id'].split('@')[0] for v in versions
                        if v['unavailable_reason'] == 'law-id-absent-from-pinned-index'}
        self.assertEqual(missing_laws, {'law/001826', 'law/002258', 'law/006297'})
        self.assertTrue(all(a['article_id'] is None and a['publication_hold']
                            for a in catalog['historical_case_annotations']))

    def test_identity_url_pairs_bind_exact_official_record_not_just_numeric_ids(self):
        research = common.readjson((common.CODE_ROOT / contracts.EVIDENCE).read_bytes())
        item_index = next(i for i, r in enumerate(research['items'])
                          if r['item'] == '토지정책과-308')
        for field, value in (
                ('law_url', 'https://example.org/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40786'),
                ('law_url', 'https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40696'),
                ('law_url', 'https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40786&ID=1'),
                ('upstream_url', 'https://example.org/lips/nya/lrn/localRegulationDetail.do?nttNo=37805'),
                ('upstream_url', 'https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37808'),
                ('upstream_url', 'https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37805#x'),
                ('upstream_url', 'https://www.laiis.go.kr@evil.example/lips/nya/lrn/localRegulationDetail.do?nttNo=37805')):
            changed = copy.deepcopy(research)
            changed['items'][item_index]['evidence'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'link mismatch'):
                self.build(research=changed)

    def test_provenance_separates_empty_machine_identity_analysis_and_nested_hash(self):
        for row in self.build()['records']:
            self.assertEqual(row['provenance']['limitations'], 'analysis')
            self.assertTrue(set(row['provenance'].values()) <= {'source', 'summary', 'analysis', 'machine'})
            if row['kind'] == 'faq':
                self.assertEqual(row['case_no'], '')
                self.assertEqual(row['provenance']['case_no'], 'machine')
            else:
                self.assertEqual(row['provenance']['assertions'], 'machine')
                for assertion in row['assertions']:
                    self.assertEqual(set(assertion) - {'provenance'}, set(assertion['provenance']))
                    self.assertEqual(assertion['provenance']['reply_sha256'], 'machine')
                    self.assertEqual(assertion['provenance']['asserted_replied'], 'source')
                    self.assertEqual(assertion['provenance']['source_url'], 'source')

    def test_historical_key_document_and_bounded_path_must_match(self):
        original = common.readjson((common.CODE_ROOT / contracts.HISTORY).read_bytes())
        first = next(iter(original['cases']))
        for field, value in (
                ('case_id', 'case/대법원/unrelated'),
                ('case_file', '../outside.md'),
                ('case_file', '/cases/대법원/1992/92누4833.md'),
                ('case_file', 'cases/대법원/1992/../92누4833.md'),
                ('case_file', 'cases\\대법원\\1992\\92누4833.md'),
                ('case_file', 'cases/대법원/1992/missing.md'),
                ('case_file', 'cases/대법원/1993/92누2653.md'),
                ('decision_date', '19920101')):
            history = copy.deepcopy(original)
            history['cases'][first][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, OSError)):
                self.build(history=history)
        history = copy.deepcopy(original)
        history['cases']['case/대법원/unrelated'] = history['cases'].pop(first)
        with self.assertRaisesRegex(ValueError, 'key/identity mismatch'):
            self.build(history=history)

    def test_generator_checks_case_link_before_read_or_write(self):
        import stat
        from types import SimpleNamespace
        root = common.CODE_ROOT
        historical = common.readjson((root / contracts.HISTORY).read_bytes())
        target = root / next(iter(historical['cases'].values()))['case_file']
        original_lstat = Path.lstat
        original_read = Path.read_bytes
        def linked(path, *args, **kwargs):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)
        def guarded(path):
            if path == target:
                self.fail('Linked historical case was read')
            return original_read(path)
        with patch.object(Path, 'lstat', linked), patch.object(Path, 'read_bytes', guarded), \
                patch.object(build_material_catalog, 'save_json') as save:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                build_material_catalog.main()
        save.assert_not_called()

    def test_deleting_both_catalog_and_research_cannot_remove_publication_hold(self):
        root = common.CODE_ROOT
        original_read = Path.read_bytes
        inventory = validate.secret_scan.repository_files
        for deleted in ({contracts.CATALOG, contracts.EVIDENCE}, contracts.CATALOG_INPUTS):
            def missing(*args, **kwargs):
                git_root, paths = inventory(*args, **kwargs)
                return git_root, [p for p in paths if p not in deleted]
            def promoted(path):
                if path.relative_to(root).as_posix() in deleted:
                    self.fail('Deleted catalog input must not be read')
                raw = original_read(path)
                if path.name.endswith('-308.md') and 'interpretations' in path.parts:
                    return raw.replace(b'progress: "relations-reviewed"', b'progress: "published"')
                return raw
            with self.subTest(deleted=deleted), \
                    patch.object(validate.secret_scan, 'repository_files', missing), \
                    patch.object(Path, 'read_bytes', promoted):
                errors, _, _ = validate.validate(root)
            self.assertTrue(any('requires its held material catalog' in e for e in errors))
            self.assertTrue(any('prevents publication' in e for e in errors))

    def test_evidence_hash_changes_and_forged_source_links_are_rejected(self):
        research = common.readjson((common.CODE_ROOT / contracts.EVIDENCE).read_bytes())
        changed = copy.deepcopy(research)
        item = next(i for i in changed['items'] if i['item'].startswith('faq/'))
        item['full_reply'] += ' Additional source text'
        rows = self.build(changed)['records']
        before = next(r for r in self.build()['records'] if r['evidence_item'] == item['item'])
        after = next(r for r in rows if r['evidence_item'] == item['item'])
        self.assertNotEqual(before['evidence_sha256'], after['evidence_sha256'])
        self.assertNotEqual(before['reply_sha256'], after['reply_sha256'])
        link = next(e for e in item['evidence'] if e.get('epUnionSn'))
        link['source_link'] += '&unexpected=1'
        with self.assertRaisesRegex(ValueError, 'source link mismatch'):
            self.build(changed)

    def test_validator_rejects_catalog_tampering_missing_catalog_and_publication(self):
        # Mock only the file inventory: exercise the validator against real source
        # and dependency bytes, replacing a single selected text in memory.
        root = common.CODE_ROOT
        original = Path.read_bytes
        catalog = self.build()
        catalog['records'][0]['publication_hold'] = False
        def altered(path):
            if path == root / contracts.CATALOG:
                return json.dumps(catalog).encode()
            return original(path)
        with patch.object(Path, 'read_bytes', altered):
            errors, _, _ = validate.validate(root)
        self.assertTrue(any('derived catalog mismatch' in e for e in errors))
        def published(path):
            raw = original(path)
            if path.name.endswith('-308.md') and 'interpretations' in path.parts:
                return raw.replace(b'progress: "relations-reviewed"', b'progress: "published"')
            return raw
        with patch.object(Path, 'read_bytes', published):
            errors, _, _ = validate.validate(root)
        self.assertTrue(any('prevents publication' in e for e in errors))
        repository_files = validate.secret_scan.repository_files
        def missing(*args, **kwargs):
            git_root, paths = repository_files(*args, **kwargs)
            return git_root, [p for p in paths if p != contracts.CATALOG]
        with patch.object(validate.secret_scan, 'repository_files', missing):
            errors, _, _ = validate.validate(root)
        self.assertTrue(any('requires its held material catalog' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
