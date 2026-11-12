# SPDX-License-Identifier: GPL-3.0-only
"""네트워크 없이 임시 fixture에서 실패·분리·검토·해시·페이지를 검증한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lawapi
import lawweb
import validate
import fetch_material
import collect_article
from contextlib import contextmanager

@contextmanager
def fixture():
    scratch=Path(os.environ.get('KK_TEST_TMP', tempfile.gettempdir()))
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        root=Path(tmp)
        # Copy code/contracts explicitly, never a checkout's collected data.
        for folder in ('tools', 'rules', '00-knowledge-start', 'templates'):
            shutil.copytree(common.CODE_ROOT/folder, root/folder,
                            ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('AGENTS.md', 'CLAUDE.md', 'deps.lock', 'docs/SCHEMA.md'):
            destination=root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(common.CODE_ROOT/name, destination)
        for folder in ('cases', 'interpretations', 'relations', 'reviews', 'sources', 'issues', 'runs'):
            (root/folder).mkdir()
        # Synthetic navigation stubs satisfy the copied rules' relative links;
        # no source, case, interpretation, review, relation or run is inherited.
        for name in ('README.md', 'docs/RELEASING.md', 'cases/README.md',
                     'interpretations/README.md', 'issues/README.md', 'reviews/README.md'):
            (root/name).write_text('# Test scaffold\n', encoding='utf-8')
        index={'schema':1, 'laws':{'009471':{'name':'테스트법'}}, 'articles':{'law/009471@261727#a25':{}}, 'standards':{}}
        with patch.object(common, 'ROOT', root), patch.object(fetch_material, 'ROOT', root), patch.object(fetch_material, 'load_index', return_value=(index,root,'WORKTREE')), patch.object(validate,'load_index',return_value=(index,root,'WORKTREE')):
            yield root

def write_doc(path, fm, body):
    path.write_text('---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in fm.items())+'---\n'+body, encoding='utf-8')


def write_candidates(root, target='expc', ident='1', **extra):
    article = 'law/009471@261727#a25'
    via = dict(path='article-linked', article=article, date='2026-01-01')
    row = dict(target=target, source_id=ident, article=article, found_via=[via],
               found_by=['linked-by-center'], source_tab=target, source_tabs=[target], **extra)
    path = root / 'sources/candidates/article-2026-01-01-1.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False) + '\n', encoding='utf-8')
    record = dict(id=path.stem, article=article, started='2026-01-01T00:00:00Z', finished='2026-01-01T00:01:00Z',
                  tracks={target: dict(status='success', count=1)}, candidate_count=1,
                  candidates=path.relative_to(root).as_posix())
    run_path = root / 'runs/article/2026-01-01-1.json'
    common.save_json(run_path, record)
    return path, run_path, row, record

class Tests(unittest.TestCase):

    def test_round12_missing_reviewed_relation_integrity(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            edge = common.relation('cites', fm['id'], 'law/009471@261727#a25')
            review = dict(id='removed-edge', target=edge['id'], reviewer_model='model', reviewed_at='2026-01-01T00:00:00Z', decision='accept', relation_review='confirmed', evidence={'source': 'https://example.test', 'quote': 'citation'})
            review['relation_snapshot'] = {key: edge[key] for key in ('type', 'src', 'dst', 'scope')}
            folder = root / 'reviews/2026'; folder.mkdir()
            (folder / 'removed.jsonl').write_text(json.dumps(review), encoding='utf-8')
            self.assertTrue(any('missing relation without recheck' in e for e in validate.validate(root)[0]))
            fm['relation_recheck'] = [edge['id']]; fm['provenance']['relation_recheck'] = 'machine'
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertEqual(validate.validate(root)[0], [])
            fm['progress'] = 'published'
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertTrue(any('source-verified progress' in e for e in validate.validate(root)[0]))
            fm.pop('relation_recheck'); fm['provenance'].pop('relation_recheck')
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertTrue(any('missing relation without recheck' in e for e in validate.validate(root)[0]))
        for value in ('systemctl reboot', '- systemctl reboot', '> systemctl reboot'):
            self.assertTrue(validate.has_command(value), value)


    def test_round12_yaml_values_and_courts(self):
        for value in ('[', '[1,', '{"a":}', '"unfinished', "'unfinished", 'plain [broken', '[one, two]'):
            self.assertTrue(validate.has_command('```yaml\nkey: ' + value + '\n```'), value)
        for value in ('[1, 2]', '{"a": "rm file"}', '"closed"', "'it''s closed'", 'plain scalar'):
            self.assertFalse(validate.has_command('```yaml\nkey: ' + value + '\n```'), value)
        for court in ('법원도서관', '민간법원자료업체', '헌법재판소사칭업체'):
            self.assertFalse(fetch_material.case_source_valid(court, []), court)
        for court in ('대법원', '헌법재판소', '서울고법', '수원지방법원 평택지원', '광주고등법원'):
            self.assertTrue(fetch_material.case_source_valid(court, []), court)

    def test_round12_orphan_envelopes_and_nested_readme(self):
        payload = {'PrecService': {'판례정보일련번호': '1'}}
        good = dict(target='prec', source_id='1', source_url='https://law.go.kr/DRF/lawService.do?target=prec&ID=1', fetched='2026-01-01T00:00:00Z', payload=payload, sha256=common.sha(common.canonical(payload)))
        with fixture() as root:
            source = root / 'sources/prec/1.json'
            common.save_json(source, good)
            self.assertEqual(validate.validate(root)[0], [])
            for change in ({'fetched': 'yesterday'}, {'sha256': '0' * 64}, {'payload': {'PrecService': {'판례정보일련번호': '2'}}}, {'source_url': 'https://law.go.kr/DRF/lawService.do?target=prec&ID=2'}):
                common.save_json(source, dict(good, **change))
                self.assertTrue(any('source envelope contract' in e for e in validate.validate(root)[0]), change)
        fields = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': fields}, good['source_url'])):
            path = root / fetch_material.fetch('prec', '1')['document']
            nested = path.parent / 'README.md'
            path.rename(nested)
            with self.assertRaisesRegex(ValueError, '중복 식별'):
                fetch_material.fetch('prec', '1')

    def test_relation_recheck_recomputed_and_policy(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text', 참조조문='테스트법 제25조')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            relations = root / 'relations/relations.jsonl'
            original = relations.read_text(encoding='utf-8')
            relations.write_text('', encoding='utf-8')
            self.assertTrue(any('automatic relations differ' in e for e in validate.validate(root)[0]))
            edge = common.readjson(original)
            edge['review'] = 'needs-review'
            relations.write_text(json.dumps(edge), encoding='utf-8')
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            fm['relation_recheck'] = [edge['id']]
            fm['provenance']['relation_recheck'] = 'machine'
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertTrue(any('relation_recheck differs' in e for e in validate.validate(root)[0]))
            relations.write_text(original, encoding='utf-8')
            fm.pop('relation_recheck'); fm['provenance'].pop('relation_recheck')
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            saved_path = root / 'sources/prec/1.json'
            saved = common.readjson(saved_path.read_text(encoding='utf-8'))
            saved['payload']['PrecService']['데이터출처명'] = '민간업체'
            saved['sha256'] = common.sha(common.canonical(saved['payload']))
            common.save_json(saved_path, saved)
            fm['source_sha256'] = saved['sha256']
            fm['data_source_name'] = ['민간업체']
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            fetch_material.rerender_saved(path)
            self.assertTrue(any('case source acceptance policy' in e for e in validate.validate(root)[0]))
        self.assertTrue(fetch_material.case_source_valid('수원지법', []))
        self.assertTrue(fetch_material.case_source_valid('서울고법', []))
        self.assertFalse(fetch_material.case_source_valid('민간중재원', []))

    def test_missing_source_fields_migration(self):
        import migrate_source_fields
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            for field in ('ref_articles_raw', 'data_source_name'):
                fm.pop(field); fm['provenance'].pop(field)
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            source = root / 'sources/prec/1.json'; before = source.read_bytes()
            self.assertEqual(migrate_source_fields.migrate(root), 1)
            self.assertEqual(migrate_source_fields.migrate(root), 0)
            self.assertEqual(validate.validate(root)[0], [])
            self.assertEqual(source.read_bytes(), before)

    def test_issue_manual_migration(self):
        import migrate_issue_sections
        with fixture() as root:
            path = root / 'issues/example.md'
            fm = dict(id='issue/example', title='Issue', progress='candidate', reference_status='unreviewed', last_reviewed=None, found_via=[dict(path='manual', query='test', date='2026-01-01')], articles=[], standards=[], skills=[])
            fm['provenance'] = {key: 'machine' for key in fm}
            write_doc(path, fm, fetch_material.BEGIN + '\n## Evidence\nManual text.\n' + fetch_material.END + '\n')
            self.assertTrue(any('issue sections are manual' in e for e in validate.validate(root)[0]))
            self.assertEqual(migrate_issue_sections.migrate(root), 1)
            self.assertEqual(migrate_issue_sections.migrate(root), 0)
            self.assertIn('Manual text.', path.read_text(encoding='utf-8'))
            self.assertEqual(validate.validate(root)[0], [])

    def test_round11_prose_and_data_syntax(self):
        for content in ('kubectl delete namespace production', '```json\nkubectl delete namespace production\n```', '```yaml\nkubectl delete namespace production\n```', '```csv\na,b\nc\n```'):
            with fixture() as root:
                (root / 'cases/README.md').write_text(content, encoding='utf-8')
                self.assertTrue(any('도구 명령' in e for e in validate.validate(root)[0]), content)
        for content in ('```json\n{"title": "Git supports branches"}\n```', '```yaml\ncommand: rm file\n```', '```jsonl\n{"a":1}\n{"b":2}\n```', '```csv\na,b\nc,d\n```', '```tsv\na\tb\nc\td\n```'):
            self.assertFalse(validate.has_command(content), content)
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            for category in ('machine', 'analysis'):
                fm['provenance']['decided'] = category
                write_doc(path, fm, text.split('\n---\n', 1)[1])
                self.assertTrue(any('source provenance differs from payload: decided' in e for e in validate.validate(root)[0]))


    def test_read_path_safe_content(self):
        for text in ('```text\nkubectl delete namespace production\n```', '```unknown\nanything\n```', '`kubectl delete namespace production`', '```\ndata\n```', '    data'):
            self.assertTrue(validate.has_command(text), text)
        for text in ('```json\n{"key": "value"}\n```', '`law/009471@261727#a25`', '`tools/validate.py`'):
            self.assertFalse(validate.has_command(text), text)

    def test_verbatim_court_and_normalized_identity(self):
        import restore_source_court
        payload = dict(판례정보일련번호='1', 법원명='수원지방법원 평택지원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            self.assertEqual(fm['court'], payload['법원명'])
            self.assertEqual(fm['id'], 'case/수원지방법원평택지원/1')
            self.assertEqual(path.parent.parent.name, '수원지방법원평택지원')
            self.assertEqual(validate.validate(root)[0], [])
            fm['court'] = common.court_slug(fm['court'])
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertTrue(any('source provenance differs from payload: court' in e for e in validate.validate(root)[0]))
            before_source = (root / 'sources/prec/1.json').read_bytes()
            self.assertEqual(restore_source_court.restore(root), 1)
            self.assertEqual(restore_source_court.restore(root), 0)
            self.assertEqual(validate.validate(root)[0], [])
            self.assertEqual((root / 'sources/prec/1.json').read_bytes(), before_source)

    def test_forged_source_frontmatter(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            fm['title'] = 'forged title'
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            self.assertTrue(any('source provenance differs from payload: title' in e for e in validate.validate(root)[0]))


    def test_saved_payload_identity(self):
        kinds = [('prec', 'PrecService', '판례정보일련번호', dict(법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')),
                 ('expc', 'ExpcService', '법령해석례일련번호', dict(해석기관명='법제처', 안건번호='1', 회신일자='20200101', 안건명='title', 해석이유='text')),
                 ('cgmexpc', 'CgmExpcService', '법령해석일련번호', dict(해석기관명='국토교통부', 안건번호='1', 해석일자='20200101', 안건명='title', 이유='text'))]
        for kind, service, serial, fields in kinds:
            payload = dict(fields, **{serial: '1'})
            url = 'https://law.go.kr/DRF/lawService.do?target=' + kind + '&ID=1'
            with fixture() as root, patch.object(lawapi, 'request', return_value=({service: payload}, url)), patch.object(lawweb, 'agency_detail', return_value=({service: payload}, url)):
                path = root / fetch_material.fetch(kind, '1')['document']
                source = root / 'sources' / kind / '1.json'
                original = common.readjson(source.read_text(encoding='utf-8'))
                for data in ({service: dict(payload, **{serial: '2'})}, {'WrongService': payload}, {service: payload, 'Extra': {}}):
                    saved = dict(original, payload=data, sha256=common.sha(common.canonical(data)))
                    common.save_json(source, saved)
                    text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
                    fm['source_sha256'] = saved['sha256']
                    write_doc(path, fm, text.split('\n---\n', 1)[1])
                    self.assertTrue(any('payload kind/serial identity mismatch' in e for e in validate.validate(root)[0]), kind)

    def test_reviewed_document_automatic_edge_removal(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text', 참조조문='테스트법 제25조')
        for reviewed_edge in (False, True):
            with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
                path = root / fetch_material.fetch('prec', '1')['document']
                text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
                fm.update(progress='published', reference_status='current-usable', last_reviewed='2026-01-01T00:00:00Z')
                write_doc(path, fm, text.split('\n---\n', 1)[1])
                relations_path = root / 'relations/relations.jsonl'
                edge = common.readjson(relations_path.read_text(encoding='utf-8'))
                manual = common.relation('cites', fm['id'], 'law/009471@261727#a25', scope='manual', found_by='manual')
                if reviewed_edge:
                    edge['review'] = 'confirmed'
                relations_path.write_text(json.dumps(edge) + '\n' + json.dumps(manual) + '\n', encoding='utf-8')
                with patch.object(fetch_material, 'load_index', return_value=({'laws': {}, 'articles': {}}, root, 'WORKTREE')):
                    fetch_material.fetch('prec', '1')
                after = common.frontmatter(path.read_text(encoding='utf-8'))
                rows = [common.readjson(line) for line in relations_path.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(after['progress'], 'source-verified')
                self.assertIn(manual, rows)
                self.assertEqual(edge in rows, reviewed_edge)
                if reviewed_edge:
                    self.assertEqual(after['relation_recheck'], [edge['id']])

    def test_canonical_rejects_unmasked_payload(self):
        credential_key = ''.join(('O', 'C'))
        query = '?' + 'o' + 'C=' + 'fixture-secret'
        with self.assertRaises(ValueError):
            common.canonical({'hidden': query}, reject_masked=True)
        with self.assertRaises(ValueError):
            common.canonical({credential_key: 'fixture-secret'}, reject_masked=True)

    def test_hidden_saved_payload_oc_rejected_before_hashing(self):
        payload = dict(판례정보일련번호='1', 法='unused', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            source = root / 'sources/prec/1.json'
            saved = common.readjson(source.read_text(encoding='utf-8'))
            # The old masked hash would still verify after this raw insertion.
            saved['payload']['PrecService']['hidden'] = '?' + 'O' + 'C=***'
            saved['sha256'] = common.sha(common.canonical(saved['payload']))
            fm = common.frontmatter(path.read_text(encoding='utf-8'))
            text = path.read_text(encoding='utf-8')
            fm['source_sha256'] = saved['sha256']
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            common.save_json(source, saved)
            fetch_material.rerender_saved(path)
            saved['payload']['PrecService']['hidden'] = '?' + 'O' + 'C=fixture-secret'
            source.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            errors = validate.validate(root)[0]
            self.assertTrue(any('stored payload contains unmasked secret' in e for e in errors))
            with self.assertRaises(ValueError):
                fetch_material.rerender_saved(path)

    def test_entire_generated_block_tampering(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text', 참조조문='테스트법 제25조, 알수없는법 제99조')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            original = path.read_text(encoding='utf-8')
            for marker in ('- 원문: ', '- 원문 파일: ', '- SHA256: ', '- 참조 조문: ', '- 미대응: ', '#### 판례내용'):
                path.write_text(original.replace(marker, marker + 'tampered', 1), encoding='utf-8')
                self.assertTrue(any('generated source differs' in e for e in validate.validate(root)[0]), marker)
            path.write_text(original, encoding='utf-8')
            self.assertEqual(validate.validate(root)[0], [])

    def test_reference_review_digest_binding_and_migration(self):
        import migrate_review_digest
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')), patch.object(migrate_review_digest, 'resolve_commit', return_value='pinned'), patch.object(migrate_review_digest, 'build') as pinned:
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            fm.update(reference_status='current-usable', last_reviewed='2026-01-01T00:00:00Z')
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            row = dict(id='r1', target=fm['id'], reference_status='current-usable', reviewer_model='model', reviewed_at=fm['last_reviewed'], decision='accept', evidence={'source': 'https://example.test', 'quote': 'text'})
            review = root / 'reviews/2026/test.jsonl'; review.parent.mkdir()
            review.write_text(json.dumps(row), encoding='utf-8')
            self.assertTrue(validate.validate(root)[0])
            manifest = root / 'manifest.json'
            entries = [dict(id=row['id'], review_sha256=common.sha(common.canonical(row)))]
            pinned.return_value = entries
            manifest.write_text(json.dumps(entries), encoding='utf-8')
            with self.assertRaises(TypeError):
                migrate_review_digest.migrate(root)
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', _expected_commit='pinned'), 1)
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', _expected_commit='pinned'), 0)
            migrated = common.readjson(review.read_text(encoding='utf-8'))
            self.assertEqual(migrated['source_sha256_basis'], 'migrated-baseline')
            other = dict(row, id='not-allowed')
            review.write_text(json.dumps(migrated) + '\n' + json.dumps(other) + '\n', encoding='utf-8')
            self.assertEqual(migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', _expected_commit='pinned'), 0)
            self.assertNotIn('source_sha256', common.readjson(review.read_text(encoding='utf-8').splitlines()[1]))
            review.write_text(json.dumps(migrated), encoding='utf-8')
            missing = [dict(id='missing', review_sha256='a' * 64)]
            pinned.return_value = missing
            manifest.write_text(json.dumps(missing), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'missing from export'):
                migrate_review_digest.migrate(root, manifest=manifest, repository=root, commit='pinned', _expected_commit='pinned')
            self.assertEqual(validate.validate(root)[0], [])
            saved_path = root / 'sources/prec/1.json'
            saved = common.readjson(saved_path.read_text(encoding='utf-8'))
            saved['payload']['PrecService']['판례내용'] = 'new source'
            saved['sha256'] = common.sha(common.canonical(saved['payload']))
            common.save_json(saved_path, saved)
            fm['source_sha256'] = saved['sha256']
            write_doc(path, fm, text.split('\n---\n', 1)[1])
            fetch_material.rerender_saved(path)
            self.assertTrue(any('근거 검토 기록 없음' in e for e in validate.validate(root)[0]))

    def test_index_remapping_resets_progress(self):
        payload = dict(판례정보일련번호='1', 법원명='대법원', 사건번호='1', 선고일자='20200101', 사건명='title', 판례내용='text', 참조조문='테스트법 제25조')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': payload}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            path = root / fetch_material.fetch('prec', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            fm['progress'] = 'published'; write_doc(path, fm, text.split('\n---\n', 1)[1])
            index = {'laws': {'009471': {'name': '테스트법'}}, 'articles': {'law/009471@999#a25': {}}}
            with patch.object(fetch_material, 'load_index', return_value=(index, root, 'WORKTREE')):
                fetch_material.fetch('prec', '1')
            self.assertEqual(common.frontmatter(path.read_text(encoding='utf-8'))['progress'], 'source-verified')

    def test_article_failure_counts_validate(self):
        with fixture() as root, patch.object(collect_article, 'ROOT', root), patch.object(collect_article, 'load_index', side_effect=lambda: common.load_index()), patch.object(sys, 'argv', ['collect_article', 'law/009471@261727#a25']):
            index = {'laws': {'009471': {'name': '테스트법'}}, 'articles': {'law/009471@261727#a25': {}}}
            with patch.object(collect_article, 'load_index', return_value=(index, root, 'WORKTREE')), patch.object(lawweb, 'context', side_effect=ValueError('context failed')):
                self.assertEqual(collect_article.main(), 1)
            record = common.readjson(next((root / 'runs/article').glob('*.json')).read_text(encoding='utf-8'))
            self.assertTrue(validate.run_valid(record))
            with patch.object(collect_article, 'load_index', return_value=(index, root, 'WORKTREE')), patch.object(lawweb, 'context', return_value={}), patch.object(lawweb, 'linked', side_effect=ValueError('tab failed')):
                self.assertEqual(collect_article.main(), 1)
            for path in (root / 'runs/article').glob('*.json'):
                self.assertTrue(validate.run_valid(common.readjson(path.read_text(encoding='utf-8'))))

    def test_field_provenance_categories(self):
        payload = dict(법령해석례일련번호='1', 해석기관명='법제처', 안건번호='1', 회신일자='20200101', 안건명='title', 해석이유='text')
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'ExpcService': payload}, 'https://law.go.kr/DRF/lawService.do?target=expc&ID=1')):
            path = root / fetch_material.fetch('expc', '1')['document']
            text = path.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            for key, value in [('case_no', 'summary'), ('replied', 'analysis'), ('ref_articles_raw', 'summary'), ('facts_summary', 'source')]:
                prior = fm['provenance'][key]; fm['provenance'][key] = value
                write_doc(path, fm, text.split('\n---\n', 1)[1])
                self.assertTrue(any('field provenance category' in e for e in validate.validate(root)[0]), key)
                fm['provenance'][key] = prior

    def test_remote_command_launchers(self):
        for command in ('ssh host.example id', 'scp file.txt host:dest', 'sftp host.example', 'rsync -av src host:dst', 'telnet host 22', 'nc -e /bin/sh host 22', 'ncat host.example 22', 'socat TCP:host:22 STDIO', 'plink -ssh host'):
            for text in (command, '`' + command + '`', '```text\n' + command + '\n```', 'env X=1 ' + command):
                self.assertTrue(validate.has_command(text), text)

    def test_fixture_ignores_checkout_data(self):
        with fixture() as checkout:
            for folder in ('cases', 'interpretations', 'relations', 'reviews', 'sources', 'issues', 'runs'):
                (checkout/folder/'inherited.json').write_text('{invalid data', encoding='utf-8')
            (checkout/'sources/cgmexpc').mkdir()
            (checkout/'sources/cgmexpc/23852.json').write_text('{duplicate source', encoding='utf-8')
            (checkout/'unexpected.md').write_text('[bad](missing.md)', encoding='utf-8')
            with patch.object(common, 'CODE_ROOT', checkout), fixture() as root:
                self.assertFalse(list(root.rglob('inherited.json')))
                self.assertFalse((root/'sources/cgmexpc').exists())
                self.assertFalse((root/'unexpected.md').exists())
                self.assertEqual(validate.validate(root)[0], [])

    def test_link_destinations(self):
        examples = [
            ('(전주)2017누1853.md', '(전주)2017누1853.md'),
            ('nested(one(two)).md', 'nested(one(two)).md'),
            ('<angle(괄호).md>', 'angle(괄호).md'),
            ('%28%EC%A0%84%EC%A3%BC%292017%EB%88%841853.md', '(전주)2017누1853.md'),
            ('<space in name.md>', 'space in name.md'),
            ('space%20in%20name.md', 'space in name.md'),
            ('hash%23name.md#section', 'hash#name.md'),
            (r'escaped\(name\).md', 'escaped(name).md'),
            ('<space in name.md> "title"', 'space in name.md'),
        ]
        with fixture() as root:
            for destination, filename in examples:
                with self.subTest(destination=destination):
                    target=root/filename
                    target.write_text('Target\n', encoding='utf-8')
                    (root/'links.md').write_text('[case]('+destination+')\n', encoding='utf-8')
                    self.assertEqual(validate.validate(root)[0], [])
                    target.unlink()
                    errors=validate.validate(root)[0]
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn('깨진 상대 링크', errors[0])
        for invalid in ('[x](unbalanced(one.md)', '[x](<missing.md)', '[x](bare space.md)'):
            self.assertEqual(list(validate.link_targets(invalid)), [], invalid)

    def test_relation_endpoint_contracts(self):
        examples = {'case':'case/대법원/1', 'interp':'interp/moleg/1', 'article':'law/009471@261727#a25', 'law':'law/009471', 'standard':'apps@1#x', 'skill':'skill/test', 'issue':'issue/test'}
        self.assertEqual(set(validate.ENDPOINTS), validate.TYPES)
        with fixture() as root:
            for kind, allowed in validate.ENDPOINTS.items():
                for src, src_id in examples.items():
                    for dst, dst_id in examples.items():
                        with self.subTest(kind=kind, src=src, dst=dst):
                            row=common.relation(kind,src_id,dst_id)
                            (root/'relations/relations.jsonl').write_text(json.dumps(row),encoding='utf-8')
                            errors=validate.validate(root)[0]
                            self.assertEqual(any('끝점 계약' in e for e in errors),(src,dst) not in allowed)

    def test_relation_required_strings_never_crash(self):
        with fixture() as root:
            for field in ('id','type','src','dst','scope','review'):
                for value in (None,True,42,[],{}):
                    row=common.relation('cites','law/009471','law/009471')
                    row[field]=value
                    (root/'relations/relations.jsonl').write_text(json.dumps(row),encoding='utf-8')
                    self.assertTrue(any('필수 문자열' in e for e in validate.validate(root)[0]),(field,value))

    def test_document_required_strings_never_crash(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);body=text.split('\n---\n',1)[1]
            for field in ('id','title','court','case_no','progress','reference_status','source_url','applied_version'):
                for value in (None,True,42,[],{}):
                    bad=dict(fm);bad[field]=value;write_doc(p,bad,body)
                    self.assertTrue(any('필수 문자열' in e for e in validate.validate(root)[0]),(field,value))

    def test_script_fences_and_bare_tools(self):
        for language in ('bash','sh','text','json','python'):
            self.assertEqual(validate.has_command('```'+language+'\nanything\n```'), language != 'text', language)
        for tool in ('git','curl','wget','python','py','python3','bash','sh','zsh','pwsh','powershell','cmd','./run','.\\run','tools/run','npm','pip','gh','rm','mv','cp'):
            for text in (tool+' --help','```'+tool+' --help\n```','```text\n'+tool+' --help\n```'):
                self.assertTrue(validate.has_command(text),text)
        for text in ('Python 코드를 쓰지 않는다','git 이력은 보존한다','Python code is used here','`python`','```json\n{"x":1}\n```','We use git status in prose.'):
            self.assertFalse(validate.has_command(text),text)
        with fixture() as root:
            for rel in ('README.md', 'cases/README.md'):
                (root/rel).write_text('# Test documentation\n', encoding='utf-8')
            for rel in ('README.md','docs/SCHEMA.md','cases/README.md','rules/knowledge-reading-rules/SKILL.md'):
                p=root/rel;before=p.read_text(encoding='utf-8')
                p.write_text(before+'\nrm -rf ./data\n',encoding='utf-8')
                self.assertTrue(any('도구 명령' in e for e in validate.validate(root)[0]),rel)
                p.write_text(before,encoding='utf-8')
            p=root/'tools/example.md';p.write_text('```sh\nrm -rf data\n```',encoding='utf-8')
            self.assertTrue(any('도구 명령' in e for e in validate.validate(root)[0]))

    def test_saved_source_url_allowlist(self):
        for kind, paths in validate.SOURCE_PATHS.items():
            for path in paths:
                for host in ('law.go.kr','www.law.go.kr'):
                    query = ('target='+kind+'&ID=1') if path.startswith('/DRF/') else ({'prec':'precSeq','expc':'expcSeq','cgmexpc':'cgmExpcDatSeq'}[kind]+'=1')
                    self.assertTrue(validate.source_url_valid('https://'+host+path+'?'+query,kind,'1'))
            for url in ('http://law.go.kr/DRF/lawService.do','https://evil.test/DRF/lawService.do','https://law.go.kr.evil.test/DRF/lawService.do','https://user@law.go.kr/DRF/lawService.do','https://law.go.kr:443/DRF/lawService.do','https://law.go.kr/DRF/lawService.do/evil','https://law.go.kr/other','https://law.go.kr/DRF/lawService.do#x'):
                self.assertFalse(validate.source_url_valid(url,kind,'1'),url)
        self.assertFalse(validate.source_url_valid('https://law.go.kr/LSW/expcInfoP.do','prec','1'))
        with fixture() as root:
            p=root/'sources/prec/orphan.json';p.parent.mkdir(parents=True)
            p.write_text('{"source_url":"https://evil.test/DRF/lawService.do"}',encoding='utf-8')
            self.assertTrue(any('원본 source_url' in e for e in validate.validate(root)[0]))
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://evil.test/DRF/lawService.do')):
            fetch_material.fetch('prec','1')
            self.assertTrue(any('source_url 오류' in e for e in validate.validate(root)[0]))

    def test_refetch_digest_resets_progress(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',side_effect=lambda *a,**kw: ({'PrecService':dict(payload)},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            for progress in ('candidate','source-verified','relations-reviewed','published'):
                text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);fm['progress']=progress
                write_doc(p,fm,text.split('\n---\n',1)[1])
                fetch_material.fetch('prec','1')
                self.assertEqual(common.frontmatter(p.read_text(encoding='utf-8'))['progress'],progress)
                payload['판례내용']+=' changed'
                fetch_material.fetch('prec','1')
                self.assertEqual(common.frontmatter(p.read_text(encoding='utf-8'))['progress'],'source-verified' if progress in {'relations-reviewed','published'} else progress)

    def test_nonfinite_json_rejected(self):
        for constant in ('NaN','Infinity','-Infinity'):
            for text in (constant,'{"nested":['+constant+']}'):
                with self.assertRaises(ValueError): common.readjson(text)
                with self.assertRaises(ValueError): common.frontmatter('---\nx: '+text+'\n---\n')
            with fixture() as root:
                for rel in ('bad.json','sources/candidates/bad.jsonl','relations/relations.jsonl','reviews/2026/bad.jsonl'):
                    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_text('{"x":'+constant+'}',encoding='utf-8')
                    self.assertTrue(any('비유한 JSON' in e for e in validate.validate(root)[0]),rel)
                    p.unlink()

    def test_confirmed_self_relations_rejected(self):
        with fixture() as root:
            folder=root/'reviews/2026';folder.mkdir(parents=True)
            for kind in sorted(validate.TYPES):
                with self.subTest(kind=kind):
                    row=common.relation(kind,'law/009471','law/009471')
                    row.update(review='confirmed',evidence={'source':'https://example.test','quote':'quote'},reviewed_by='model',reviewed_at='2026-01-01T00:00:00Z')
                    (root/'relations/relations.jsonl').write_text(json.dumps(row),encoding='utf-8')
                    record=dict(id='r1',target=row['id'],relation_review='confirmed',reviewer_model='model',reviewed_at=row['reviewed_at'],evidence=row['evidence'],decision='accept')
                    (folder/'one.jsonl').write_text(json.dumps(record),encoding='utf-8')
                    self.assertTrue(any('자기참조' in e for e in validate.validate(root)[0]))
                    row['review']='unreviewed'
                    (root/'relations/relations.jsonl').write_text(json.dumps(row),encoding='utf-8')
                    self.assertFalse(any('자기참조' in e for e in validate.validate(root)[0]))

    def test_fetch_stages_all_artifacts_before_replacing(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text',참조조문='테스트법 제25조')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1')
            paths=[root/'sources/prec/1.json',root/result['document'],root/'relations/relations.jsonl']
            payload['사건명']='changed'
            paths[2].write_text('{malformed',encoding='utf-8')
            before={p:p.read_bytes() for p in paths}
            with self.assertRaises(ValueError): fetch_material.fetch('prec','1')
            self.assertEqual(before,{p:p.read_bytes() for p in paths})
            paths[2].write_text('',encoding='utf-8')
            before={p:p.read_bytes() for p in paths}
            original=Path.write_bytes
            def fail_document(path,*args,**kwargs):
                if path.name.startswith('.1.md-'): raise OSError('document write failed')
                return original(path,*args,**kwargs)
            with patch.object(Path,'write_bytes',fail_document):
                with self.assertRaises(OSError): fetch_material.fetch('prec','1')
            self.assertEqual(before,{p:p.read_bytes() for p in paths})
            real_replace=os.replace
            def fail_replace(src,dst):
                if Path(dst)==paths[2]: raise OSError('replace failed')
                return real_replace(src,dst)
            with patch.object(fetch_material.os,'replace',side_effect=fail_replace):
                with self.assertRaises(OSError): fetch_material.fetch('prec','1')
            self.assertEqual(before,{p:p.read_bytes() for p in paths})
            self.assertFalse(list(root.rglob('.*-*')))

    def test_command_detection_contexts_not_prose(self):
        for text in ('Python code is used here', 'We use python tools/x.py as an example in prose.', 'Python is useful', '`Python` is a language'):
            self.assertFalse(validate.has_command(text),text)
        for command in ('python tools/x.py', 'py -3 tools/x.py', 'python -m module', 'python3 script.py'):
            for text in (command, '```sh\n'+command+'\n```', '~~~sh\n'+command+'\n~~~', '    '+command, '\t'+command, 'Run `'+command+'` now.'):
                self.assertTrue(validate.has_command(text),text)
        with fixture() as root:
            p=root/'rules/knowledge-reading-rules/SKILL.md'
            p.write_text(p.read_text(encoding='utf-8')+'\nPython code is used here\n',encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])

    def test_evidence_authority_dns_and_port(self):
        for host in ('example.test:bad','example.test:65536','.','localhost','a..test','-a.test','a-.test','a_.test','a'*64+'.test','[not-an-ip]'):
            self.assertFalse(validate.https_url('https://'+host),host)
        for host in ('example.test:443','a-b.example.test','127.0.0.1:443','[::1]:443'):
            self.assertTrue(validate.https_url('https://'+host+'/path'),host)

    def test_rules_require_exact_relative_paths(self):
        with fixture() as root:
            expected=root/'rules/knowledge-reading-rules/SKILL.md'
            nested=root/'rules/nested/knowledge-reading-rules/SKILL.md'
            nested.parent.mkdir(parents=True)
            shutil.copy(expected,nested)
            self.assertTrue(any('두 스킬 분리' in e for e in validate.validate(root)[0]))
            expected.unlink()
            self.assertTrue(any('두 스킬 분리' in e for e in validate.validate(root)[0]))
            shutil.move(nested,expected)
            self.assertEqual(validate.validate(root)[0],[])

    def test_fetched_sentinels_escaped_and_completed_body_checked(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용=fetch_material.END+' injected '+fetch_material.BEGIN+' <!-- BEGIN GENERATED:other -->')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            text=p.read_text(encoding='utf-8');body=text.split('\n---\n',1)[1]
            self.assertEqual(body.count(fetch_material.BEGIN),1)
            self.assertEqual(body.count(fetch_material.END),1)
            self.assertIn('&lt;!-- END GENERATED:source --&gt;',body)
            self.assertIn('&lt;!-- BEGIN GENERATED:other --&gt;',body)
            self.assertEqual(validate.validate(root)[0],[])
            fetch_material.fetch('prec','1')
            source=root/'sources/prec/1.json';before=source.read_bytes()
            # A corrupted template must be rejected before any artifact is committed.
            p.unlink()
            template=(common.CODE_ROOT/'templates/case.md').read_text(encoding='utf-8')
            original=Path.read_text
            def bad_template(path,*args,**kwargs):
                if path==common.CODE_ROOT/'templates/case.md': return template+fetch_material.BEGIN
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',bad_template):
                with self.assertRaises(ValueError): fetch_material.fetch('prec','1')
            self.assertEqual(source.read_bytes(),before)
            self.assertFalse(p.exists())

    def test_agency_detail_and_fetch(self):
        html='''<input id="cgmExpcDatSeq" value="23852"><input id="cgmExpcNo" value="토지-1"><input id="cgmExpcNm" value="제목"><input id="cgmExpcYd" value="20170831"><div class="subtit1">[국토교통부 토지-1, 2017. 8. 31.]</div><h4 id="rpl">【회답】</h4><p>답변</p><h4 id="conLs">【관련법령】</h4><p>테스트법 제25조</p>'''
        with fixture() as root, patch.object(lawweb,'get',return_value=html):
            result=fetch_material.fetch('cgmexpc','23852')
            fm=common.frontmatter((root/result['document']).read_text(encoding='utf-8'))
            self.assertEqual(fm['agency'],'molit')
            self.assertEqual(fm['cgmExpcDatSeq'],'23852')
            self.assertEqual(result['relations'],1)
            self.assertEqual(validate.validate(root)[0],[])
        with patch.object(lawweb,'get',return_value=html):
            with self.assertRaises(ValueError): lawweb.agency_detail('225338')

    def test_refetch_source_fields_refs_and_provenance(self):
        payload=dict(법령해석례일련번호='1',안건번호='1',해석기관명='법제처',회신일자='20200101',안건명='old',해석이유='원문',참조조문='테스트법 제25조')
        with fixture() as root, patch.object(lawapi,'request',side_effect=lambda *a,**kw: ({'ExpcService':dict(payload)},'https://www.law.go.kr/DRF/lawService.do?target=expc&ID=1')):
            folder=root/'sources/candidates';folder.mkdir(parents=True)
            via=dict(path='article-linked',article='law/009471@261727#a25',date='2026-01-01')
            write_candidates(root)
            result=fetch_material.fetch('expc','1');path=root/result['document']
            fm=common.frontmatter(path.read_text(encoding='utf-8'))
            self.assertIn(via,fm['found_via']); self.assertEqual(result['relations'],1)
            text=path.read_text(encoding='utf-8');body=text.split('\n---\n',1)[1]+'\nmanual note\n'
            fm['facts_summary']='manual summary';fm['applied_version']='unknown'
            write_doc(path,fm,body)
            payload.update(안건명='new',참조조문='알수없는법 제99조')
            result=fetch_material.fetch('expc','1')
            text=path.read_text(encoding='utf-8');fm=common.frontmatter(text)
            self.assertEqual(fm['title'],'new'); self.assertEqual(fm['ref_articles_raw'],'알수없는법 제99조')
            self.assertTrue(result['unmapped']);self.assertIn('manual note',text)
            self.assertEqual((root/'relations/relations.jsonl').read_text(encoding='utf-8'),'')
            self.assertEqual(fm['facts_summary'],'manual summary')
            self.assertEqual(fm['found_via'].count(via),1)
            fm['reference_status']='current-usable';write_doc(path,fm,text.split('\n---\n',1)[1])
            before=path.read_bytes();payload['안건명']='changed reviewed'
            with self.assertRaises(ValueError):fetch_material.fetch('expc','1')
            self.assertEqual(before,path.read_bytes())

    def test_case_refetch_updates_source_not_analysis(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='old',판례내용='text',판결유형='old kind',참조조문='')
        with fixture() as root, patch.object(lawapi,'request',side_effect=lambda *a,**kw: ({'PrecService':dict(payload)},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');path=root/result['document']
            text=path.read_text(encoding='utf-8');fm=common.frontmatter(text)
            fm['analysis_note']='keep';fm['provenance']['analysis_note']='analysis'
            write_doc(path,fm,text.split('\n---\n',1)[1])
            payload.update(선고일자='20200202',사건명='new',판결유형='new kind',참조조문='테스트법 제25조')
            fetch_material.fetch('prec','1')
            fm=common.frontmatter(path.read_text(encoding='utf-8'))
            self.assertEqual((fm['title'],fm['decided'],fm['kind']),('new','20200202','new kind'))
            self.assertEqual(fm['analysis_note'],'keep')

    def test_confirmed_relation_requires_matching_history(self):
        with fixture() as root:
            row=common.relation('cites','law/009471@261727#a25','law/009471')
            row.update(review='confirmed',evidence={'source':'https://example.test','quote':'quote'},reviewed_by='model',reviewed_at='2026-01-01T00:00:00+00:00')
            common.add_relations([row])
            def history_errors():return [e for e in validate.validate(root)[0] if 'relation_review' in e]
            self.assertTrue(history_errors())
            folder=root/'reviews/2026';folder.mkdir(parents=True)
            record=dict(id='r1',target=row['id'],relation_review='confirmed',reviewer_model='wrong',reviewed_at=row['reviewed_at'],evidence=row['evidence'],decision='accept')
            p=folder/'one.jsonl';p.write_text(json.dumps(record),encoding='utf-8')
            self.assertTrue(history_errors())
            record['reviewer_model']='model';p.write_text(json.dumps(record),encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])

    def test_issue_required_arrays_and_id_types(self):
        with fixture() as root:
            p=root/'issues/example.md';p.parent.mkdir(exist_ok=True)
            fm=dict(id='issue/example',title='Issue',progress='candidate',reference_status='unreviewed',last_reviewed=None,found_via=[dict(path='manual',query='test',date='2026-01-01')])
            fm['provenance']={k:'machine' for k in fm}
            body='## Manual issue section\n'
            write_doc(p,fm,body)
            self.assertTrue(any('필수 필드 누락' in e for e in validate.validate(root)[0]))
            for k in ('articles','standards','skills'):fm[k]=[];fm['provenance'][k]='machine'
            write_doc(p,fm,body);self.assertEqual(validate.validate(root)[0],[])
            for k,value in [('articles','law/009471@261727#a25'),('articles',['skill/wrong']),('standards',[42]),('skills',['skill/good garbage'])]:
                old=fm[k];fm[k]=value;write_doc(p,fm,body)
                self.assertTrue(any('계약 ID 배열 오류' in e for e in validate.validate(root)[0]))
                fm[k]=old

    def test_review_history_only_year_directory(self):
        with fixture() as root:
            row=common.relation('cites','law/009471@261727#a25','law/009471')
            row.update(review='confirmed',evidence={'source':'https://example.test','quote':'quote'},reviewed_by='model',reviewed_at='2026-01-01T00:00:00Z');common.add_relations([row])
            record=dict(id='review-1',target=row['id'],relation_review='confirmed',evidence=row['evidence'],reviewer_model='model',reviewed_at=row['reviewed_at'],decision='accept')
            for rel in ('reviews/bypass.jsonl','reviews/arbitrary/a.jsonl','reviews/2026/nested/a.jsonl'):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(record),encoding='utf-8')
                errors=validate.validate(root)[0]
                self.assertTrue(any('reviews/YYYY' in e for e in errors))
                self.assertTrue(any('relation_review' in e for e in errors));p.unlink()
            p=root/'reviews/2026/valid.jsonl';p.write_text(json.dumps(record),encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])

    def test_review_url_requires_host_and_no_credentials(self):
        for url in ('https://','https:///missing','https://user:pass@example.test','http://example.test','https://exa mple.test'):
            self.assertFalse(validate.evidence_valid({'source':url,'quote':'quote'}))
        self.assertTrue(validate.evidence_valid({'source':'https://example.test/path?q=1','quote':'quote'}))

    def test_all_python_command_forms_rejected(self):
        for command in ('python -OO tools/fetch_case.py 1', 'python3 -m module', 'python -c "print(1)"', 'python.exe -X utf8 tools/fetch_case.py 1', 'py -3 tools/fetch_case.py 1', '"C:/Python/python.exe" -OO script.py'):
            with fixture() as root:
                p=root/'rules/knowledge-reading-rules/SKILL.md'
                p.write_text(p.read_text(encoding='utf-8')+'\n```sh\n'+command+'\n```\n',encoding='utf-8')
                self.assertTrue(any('도구 명령' in e for e in validate.validate(root)[0]),command)

    def test_empty_list_tab_identity(self):
        for target,form in [('prec','precPageFrm'),('expc','expcPageFrm'),('cgmexpc','cgmExpcResultPageFrm')]:
            with patch.object(lawweb,'get',return_value='<form id="'+form+'">총<strong>0</strong>건</form>'):
                self.assertEqual(lawweb.linked(target,{}),[])
                other='expc' if target=='prec' else 'prec'
                with self.assertRaises(ValueError):lawweb.linked(other,{})
        with patch.object(lawweb,'get',return_value='검색된 자료가 없습니다'):
            with self.assertRaises(ValueError):lawweb.linked('prec',{})

    def test_context_response_identifiers(self):
        values=dict(lsNmKo='테스트법',lsKndCdCls='A0004',lsiSeq='261727',joNo='0025',joBrNo='00')
        def page(v):return ''.join('<input id="'+k+'" value="'+value+'">' for k,value in v.items())
        with patch.object(lawweb,'get',return_value=page(values)):
            self.assertEqual(lawweb.context('261727','0025','00','테스트법')['joNo'],'0025')
        for key in ('lsiSeq','joNo','joBrNo'):
            for value in ('', '9999'):
                bad=dict(values);bad[key]=value
                with patch.object(lawweb,'get',return_value=page(bad)):
                    with self.assertRaises(ValueError):lawweb.context('261727','0025','00','테스트법')

    def test_collection_scan_failure_is_recorded(self):
        with fixture() as root, patch.object(collect_article,'ROOT',root), patch.object(sys,'argv',['collect_article.py','law/009471@261727#a25']), patch.object(lawweb,'context') as context:
            (root/'cases/broken.md').write_text('---\nid: 1\nid: 2\n---\n',encoding='utf-8')
            self.assertEqual(collect_article.main(),1);context.assert_not_called()
            record=json.loads(next((root/'runs/article').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['tracks']['preflight']['status'],'failure')

    def test_source_metadata_and_invalid_destination_no_mutation(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document'];text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);body=text.split('\n---\n',1)[1]
            fm['source_url']='https://unrelated.test';write_doc(p,fm,body)
            self.assertTrue(any('URL/target/ID' in e for e in validate.validate(root)[0]))
            p.write_text(text,encoding='utf-8');source=root/'sources/prec/1.json';saved=source.read_bytes()
            metadata=json.loads(saved)
            for key,value in [('target','expc'),('source_id','999')]:
                bad=dict(metadata);bad[key]=value;common.save_json(source,bad)
                self.assertTrue(any('URL/target/ID' in e for e in validate.validate(root)[0]))
            source.write_bytes(saved);payload['사건명']='updated'
            for malformed in (text.replace(fetch_material.END,''),text.replace(fetch_material.END,fetch_material.END*2),text.replace(fetch_material.BEGIN,'TEMP').replace(fetch_material.END,fetch_material.BEGIN).replace('TEMP',fetch_material.END)):
                p.write_text(malformed,encoding='utf-8');before=p.read_bytes()
                with self.assertRaises(ValueError):fetch_material.fetch('prec','1')
                self.assertEqual(source.read_bytes(),saved);self.assertEqual(p.read_bytes(),before)

    def test_nested_frontmatter_duplicates(self):
        for value in ('{"x":1,"x":2}', '[{"nested":{"x":1,"x":2}}]'):
            with self.assertRaises(ValueError): common.frontmatter('---\nprovenance: '+value+'\n---\n')

    def test_detail_identity_provider_and_destination_conflicts(self):
        for kind,payload,service,serial in [
            ('prec',dict(법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text'),'PrecService','판례정보일련번호'),
            ('expc',dict(해석기관명='법제처',안건번호='1',해석일자='20200101',안건명='title',이유='text'),'ExpcService','법령해석례일련번호')]:
            with fixture() as root:
                payload[serial]='1'
                with patch.object(lawapi,'request',return_value=({'WrongService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
                    with self.assertRaises(ValueError): fetch_material.fetch(kind,'1')
                with patch.object(lawapi,'request',return_value=({service:payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
                    with self.assertRaises(ValueError): fetch_material.fetch(kind,'2')
                    result=fetch_material.fetch(kind,'1');path=root/result['document'];before=path.read_bytes()
                    payload[serial]='2'
                    with self.assertRaises(ValueError): fetch_material.fetch(kind,'2')
                    self.assertEqual(before,path.read_bytes())
                    self.assertFalse((root/'sources'/kind/'2.json').exists())
        with fixture() as root:
            payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text',데이터출처명='민간업체')
            with patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID=1')):
                with self.assertRaises(ValueError): fetch_material.fetch('prec','1')
                payload['데이터출처명']='법원도서관'
                result=fetch_material.fetch('prec','1')
                self.assertEqual(common.frontmatter((root/result['document']).read_text(encoding='utf-8'))['data_source_name'],['법원도서관'])
                write_candidates(root, target='prec', 데이터출처명='민간업체')
                with self.assertRaises(ValueError):fetch_material.fetch('prec','1')

    def test_reconcile_only_unreviewed_automatic_citations(self):
        with fixture() as root:
            rows=[]
            for number,review,found in [('1','unreviewed',['cites-article']),('2','confirmed',['cites-article']),('3','unreviewed',['manual']),('4','unreviewed',['manual','cites-article'])]:
                row=common.relation('cites','case/대법원/1','law/009471@261727#a'+number)
                row.update(review=review,found_by=found);rows.append(row)
            common.add_relations(rows)
            common.add_relations([],replace_generated_for='case/대법원/1')
            actual=[json.loads(line) for line in (root/'relations/relations.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual({r['id'] for r in actual},{r['id'] for r in rows[1:]})

    def test_wrong_tab_links_fail(self):
        for target,link in [('prec','expcInfoP.do?expcSeq=1'),('prec','expcInfoP.do?precSeq=1'),('expc','precInfoP.do?precSeq=1')]:
            with patch.object(lawweb,'get',return_value='<a href="'+link+'">x</a>'):
                with self.assertRaises(ValueError):lawweb.linked(target,{})

    def test_relative_reading_commands(self):
        for command in ('python ./tools/fetch_case.py 1','./tools/fetch_case.py 1','python -I -B ./tools/fetch_case.py 1'):
            with fixture() as root:
                p=root/'rules/knowledge-reading-rules/SKILL.md'
                p.write_text(p.read_text(encoding='utf-8')+'\n```sh\n'+command+'\n```\n',encoding='utf-8')
                self.assertTrue(any('도구 명령' in e for e in validate.validate(root)[0]))

    def test_collection_dependency_failure_is_recorded(self):
        with fixture() as root, patch.object(collect_article,'ROOT',root), patch.object(collect_article,'load_index',side_effect=ValueError('missing pinned index')), patch.object(sys,'argv',['collect_article.py','law/009471@261727#a25']), patch.object(lawweb,'context') as context:
            self.assertEqual(collect_article.main(),1)
            context.assert_not_called()
            record=json.loads(next((root/'runs/article').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['tracks']['dependency']['status'],'failure')
            self.assertEqual(record['candidate_count'],0)

    def test_applied_version_and_replacement_documents(self):
        payload=dict(判例='unused',판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',side_effect=lambda *a,**kw: ({'PrecService':payload},'https://www.law.go.kr/DRF/lawService.do?target=prec&ID='+str(kw['ID']))):
            result=fetch_material.fetch('prec','1');p=root/result['document'];text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);body=text.split('\n---\n',1)[1]
            for value in ('current',True,'law/009471@261727#a25','law/009471@999999'):
                fm['applied_version']=value;write_doc(p,fm,body)
                self.assertTrue(validate.validate(root)[0])
            versions_file='sources/laws/test/versions/act.json'
            index={'schema':1,'laws':{'009471':{'name':'테스트법','current':{'lsiSeq':'261727'},'versions_file':versions_file}},'articles':{},'standards':{}}
            version_payload={'lsId':'009471','versions':[{'lsiSeq':'123'}]}
            (root/versions_file).parent.mkdir(parents=True)
            (root/versions_file).write_text(json.dumps(version_payload),encoding='utf-8')
            with patch.object(validate,'load_index',return_value=(index,root,'WORKTREE')):
                for value in ('unknown','law/009471@261727','law/009471@123'):
                    fm['applied_version']=value;write_doc(p,fm,body);self.assertEqual(validate.validate(root)[0],[])
            with patch.object(validate,'load_index',return_value=(index,root,'a'*40)), patch.object(validate.subprocess,'run') as run:
                run.return_value.stdout=json.dumps(version_payload).encode()
                fm['applied_version']='law/009471@123';write_doc(p,fm,body)
                self.assertEqual(validate.validate(root)[0],[])
                self.assertIn('a'*40+':'+versions_file,run.call_args.args[0])
            fm.update(applied_version='unknown',reference_status='overruled-confirmed',source_sha256=fm['source_sha256'],last_reviewed='2026-01-01T00:00:00Z');write_doc(p,fm,body)
            folder=root/'reviews/2026';folder.mkdir(parents=True)
            row=dict(id='review-1',target=fm['id'],reviewer_model='model',reviewed_at=fm['last_reviewed'],evidence={'source':'https://example.test','quote':'quote'},decision='accept',reference_status='overruled-confirmed',source_sha256=fm['source_sha256'],overruling_id='case/대법원/missing',change_quote='changed')
            rp=folder/'one.jsonl'
            for replacement in ('case/대법원/missing','interp/moleg/1',True,fm['id']):
                row['overruling_id']=replacement;rp.write_text(json.dumps(row),encoding='utf-8')
                self.assertTrue(any('대체/변경' in e for e in validate.validate(root)[0]))
            payload.update(판례정보일련번호='2',사건번호='2')
            fetch_material.fetch('prec','2');row['overruling_id']='case/대법원/2';rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])
            row['change_quote']=True;rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertTrue(any('대체/변경' in e for e in validate.validate(root)[0]))

    def test_superseding_id_must_be_existing_interpretation(self):
        payload=dict(법령해석례일련번호='1',안건번호='1',해석기관명='법제처',해석일자='20200101',안건명='title',이유='text')
        with fixture() as root, patch.object(lawapi,'request',side_effect=lambda *a,**kw: ({'ExpcService':payload},'https://www.law.go.kr/DRF/lawService.do?target=expc&ID='+str(kw['ID']))):
            result=fetch_material.fetch('expc','1');p=root/result['document'];text=p.read_text(encoding='utf-8');fm=common.frontmatter(text)
            fm.update(reference_status='superseded-confirmed',source_sha256=fm['source_sha256'],last_reviewed='2026-01-01T00:00:00Z');write_doc(p,fm,text.split('\n---\n',1)[1])
            folder=root/'reviews/2026';folder.mkdir(parents=True)
            row=dict(id='review-1',target=fm['id'],reviewer_model='model',reviewed_at=fm['last_reviewed'],evidence={'source':'https://example.test','quote':'quote'},decision='accept',reference_status='superseded-confirmed',source_sha256=fm['source_sha256'],superseding_id='interp/moleg/missing')
            rp=folder/'one.jsonl';rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertTrue(any('대체/변경' in e for e in validate.validate(root)[0]))
            payload.update(법령해석례일련번호='2',안건번호='2');fetch_material.fetch('expc','2')
            row['superseding_id']=fm['id'];rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertTrue(any('대체/변경' in e for e in validate.validate(root)[0]))
            row['superseding_id']='interp/moleg/2';rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])
            for field,value in [('evidence',True),('decision',True),('reviewed_at','not-a-date')]:
                bad=dict(row);bad[field]=value;rp.write_text(json.dumps(bad),encoding='utf-8')
                self.assertTrue(any('검토 필드 유형' in e for e in validate.validate(root)[0]))

    def test_typed_review_evidence(self):
        row=dict(id='review-1',target='case/대법원/1',reviewer_model='model',reviewed_at='2026-01-01T00:00:00Z',evidence={'source':'https://example.test','quote':'exact quote'},decision='accept')
        self.assertTrue(validate.review_valid(row))
        for key,value in [('evidence',True),('evidence',{'source':'https://example.test','quote':True}),('decision',True),('decision','arbitrary'),('reviewed_at','not-a-date'),('reviewed_at','2026-01-01')]:
            bad=dict(row);bad[key]=value;self.assertFalse(validate.review_valid(bad))

    def test_duplicate_frontmatter(self):
        with self.assertRaises(ValueError): common.frontmatter('---\nid: 1\nid: 2\n---\n')
    def test_duplicate_json(self):
        with self.assertRaises(ValueError): json.loads('{"x":1,"x":2}',object_pairs_hook=validate.unique)
    def test_secret_masking(self):
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): 'test-secret'}):
            self.assertEqual(lawapi.sanitize({'url':'https://x/?'+'O' + 'C=test-secret&x=1','text':'test-secret'}),{'url':'https://x/?O' + 'C=***&x=1','text':'***'})
    def test_relation_stable(self):
        a=common.relation('cites','case/대법원/1','law/009471@261727#a25')
        self.assertEqual(a,common.relation('cites','case/대법원/1','law/009471@261727#a25'))
        self.assertNotEqual(a['id'],common.relation('cites','case/대법원/1','law/009471@261727#a25','different')['id'])
    def test_relation_deduplication(self):
        scratch=Path(os.environ.get('KK_TEST_TMP', tempfile.gettempdir()))
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp, patch.object(common,'ROOT',Path(tmp)):
            row=common.relation('cites','case/대법원/1','law/009471@261727#a25')
            common.add_relations([row,row])
            common.add_relations([row])
            self.assertEqual(len((Path(tmp)/'relations/relations.jsonl').read_text(encoding='utf-8').splitlines()),1)
    def test_pagination(self):
        pages=['<h2>총<strong>11</strong>건(1/2)</h2>'+''.join(f'<a href="precInfoP.do?mode=0&precSeq={i}">x</a>' for i in range(10)), '<h2>총<strong>11</strong>건(2/2)</h2><a href="precInfoP.do?mode=0&precSeq=10">x</a>']
        with patch.object(lawweb,'get',side_effect=pages): self.assertEqual(len(lawweb.linked('prec',{})),11)
    def test_zero_vs_failure(self):
        with patch.object(lawweb,'get',return_value='<form id="precPageFrm">검색된 자료가 없습니다</form>'): self.assertEqual(lawweb.linked('prec',{}),[])
        with patch.object(lawweb,'get',return_value='<html>unexpected</html>'):
            with self.assertRaises(ValueError): lawweb.linked('prec',{})
    def test_agency_tab(self):
        with patch.object(lawweb,'get',return_value='<h2>총<strong>1</strong>건(1/1)</h2><a href="cgmExpcInfoP.do?mode=0&cgmExpcDatSeq=23852">x</a>'):
            rows=lawweb.linked('cgmexpc',{})
            self.assertEqual(rows[0]['target'],'cgmexpc')
    def test_validator_rejects_bad_relation(self):
        with fixture() as root:
            row=common.relation('overrules','case/대법원/1','case/대법원/2');row['review']='confirmed'
            (root/'relations/relations.jsonl').write_text(json.dumps(row),encoding='utf-8')
            with patch.object(validate,'load_index',return_value=({'schema':1,'laws':{},'articles':{},'standards':{}},root,'WORKTREE')):
                errors,_,_=validate.validate(root)
            self.assertTrue(any('증거/검토 누락' in e for e in errors))

class ReviewRegressionTests(unittest.TestCase):
    def test_structural_commands_and_sentences(self):
        sentences = ('Python libraries make parsing easier.', 'Git commits are immutable.',
                     'Python libraries make parsing easier', 'git commits are immutable.',
                     'Python 3.14 libraries make parsing easier.', 'Git reads config.json for settings.',
                     'Python code is used here', 'Python is useful.', 'Git is a version control system.',
                     'Bash scripts can be useful.', 'Curl is a transfer tool.', ' / ', './path',
                     'The references `a` / `b` are descriptive.',
                     'Python 표준 라이브러리를 사용한다.', 'git 이력은 보존한다')
        for sentence in sentences:
            self.assertFalse(validate.has_command(sentence), sentence)
            self.assertTrue(validate.has_command('    ' + sentence), sentence)
        commands = ('git checkout main', 'curl https://x', '/bin/sh -c "echo x"',
                    './x --help', '.\\x -m module', './tools/fetch_case.py 1',
                    'env bash -c "echo x"', 'env MODE=test /bin/sh -c x',
                    'sudo bash -c x', 'sudo -u root /bin/sh -c x', 'exec env bash -c x',
                    'python -m module', 'python script.py', '"C:/Python/python.exe" -c x')
        for command in commands:
            for prefix in ('', '- ', '* ', '+ ', '1. ', '$ ', '> ', '> - $ '):
                for context in (prefix+command, '```text\n'+prefix+command+'\n```',
                                '~~~json\n'+prefix+command+'\n~~~', '    '+prefix+command,
                                'Example `'+prefix+command+'` now.'):
                    self.assertTrue(validate.has_command(context), context)

    def test_markdown_code_and_reference_links(self):
        with fixture() as root:
            p=root/'links.md'
            code='[x](missing.md) [x][undefined]'
            for context in ('`'+code+'`', '``'+code+'``', '```text\n'+code+'\n```',
                            '~~~text\n'+code+'\n~~~', '    '+code, '\t'+code):
                p.write_text(context,encoding='utf-8')
                errors = validate.validate(root)[0]
                if context.startswith(('    ', '\t')):
                    self.assertTrue(any('도구 명령' in e for e in errors), context)
                else:
                    self.assertEqual(errors, [], context)
            for text in ('[text][LABEL]\n\n[label]: README.md "title"',
                         '[label][]\n\n[label]: <README.md>', '[label]\n\n[label]: README.md'):
                p.write_text(text,encoding='utf-8');self.assertEqual(validate.validate(root)[0],[])
            for text, message in (('[text][absent]', '정의 없는 참조'),
                                  ('[text][label]\n[label]: missing.md', '깨진 상대 링크')):
                p.write_text(text,encoding='utf-8')
                self.assertTrue(any(message in e for e in validate.validate(root)[0]))
            p.unlink()
            p=root/'docs/links.md'
            for target, valid in (('/README.md', True), ('../README.md', True),
                                  ('/../README.md', False), ('../../README.md', False),
                                  ('/%2e%2e/README.md', False), ('C:/Windows', True)):
                p.write_text('[link]('+target+')',encoding='utf-8')
                errors=validate.validate(root)[0]
                self.assertEqual(not errors, valid, (target,errors))

    def test_source_query_identity(self):
        for kind, paths in validate.SOURCE_PATHS.items():
            for path in paths:
                key='ID' if path.startswith('/DRF/') else {'prec':'precSeq','expc':'expcSeq','cgmexpc':'cgmExpcDatSeq'}[kind]
                prefix='target='+kind+'&' if path.startswith('/DRF/') else ''
                base='https://law.go.kr'+path+'?'+prefix
                self.assertTrue(validate.source_url_valid(base+key+'=123',kind,'123'))
                for suffix in ('', key+'=999', key+'=123&'+key+'=999', key+'=', key+'=abc'):
                    self.assertFalse(validate.source_url_valid(base+suffix,kind,'123'),base+suffix)
                if prefix:
                    self.assertFalse(validate.source_url_valid(base.replace('target='+kind,'target=law')+key+'=123',kind,'123'))
                    self.assertFalse(validate.source_url_valid(base+'target='+kind+'&ID=123',kind,'123'))
        self.assertTrue(validate.source_url_valid('https://law.go.kr/DRF/lawService.do?target=molitCgmExpc&ID=1','cgmexpc','1'))
        with fixture() as root:
            p=root/'sources/prec/1.json';p.parent.mkdir()
            payload = {'PrecService': {'판례정보일련번호': '1'}}
            valid=dict(target='prec',source_id='1',source_url='https://law.go.kr/DRF/lawService.do?target=prec&ID=1', fetched='2026-01-01T00:00:00Z', payload=payload, sha256=common.sha(common.canonical(payload)))
            common.save_json(p,valid);self.assertEqual(validate.validate(root)[0],[])
            for updates in ({'source_id':'2','source_url':'https://law.go.kr/DRF/lawService.do?target=prec&ID=2'}, {'target':'expc'}, {'source_url':'https://law.go.kr/DRF/lawService.do?target=prec&ID=2'}):
                common.save_json(p,dict(valid,**updates))
                self.assertTrue(any('원본 source_url' in e for e in validate.validate(root)[0]))

    def test_all_review_records_are_typed(self):
        record=dict(id='r1',target='case/대법원/1',reviewer_model='model',reviewed_at='2026-01-01T00:00:00Z',evidence={'source':'https://example.test','quote':'quote'},decision='accept')
        with fixture() as root:
            p=root/'reviews/2026/unused.jsonl';p.parent.mkdir()
            for key,values in {'target':['garbage','rel-short','law/123',True],
                               'reference_status':['typo',True,[],{}],
                               'relation_review':['typo',True,[],{}],
                               'decision':['typo',True,[],{}]}.items():
                for value in values:
                    row=dict(record);row[key]=value;p.write_text(json.dumps(row),encoding='utf-8')
                    self.assertTrue(any('검토 필드 유형' in e for e in validate.validate(root)[0]),(key,value))
            for target in ('law/009471','law/009471@1#a2-1','apps@1#code','skill/test','interp/moleg/1','issue/test','rel-'+'a'*20):
                row=dict(record,target=target)
                self.assertTrue(validate.review_valid(row),target)

    def test_relation_scope_and_evidence_binding(self):
        with fixture() as root:
            row=common.relation('cites','law/009471@261727#a25','law/009471')
            row.update(review='confirmed',evidence={'source':'https://example.test','quote':'quote'},reviewed_by='model',reviewed_at='2026-01-01T00:00:00Z')
            rp=root/'relations/relations.jsonl';rp.write_text(json.dumps(row),encoding='utf-8')
            record=dict(id='r1',target=row['id'],relation_review='confirmed',reviewer_model='model',reviewed_at=row['reviewed_at'],evidence=row['evidence'],decision='accept')
            p=root/'reviews/2026/one.jsonl';p.parent.mkdir();p.write_text(json.dumps(record),encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])
            for evidence in ({'source':'https://other.test','quote':'quote'},{'source':'https://example.test','quote':'different quote'}):
                record['evidence']=evidence;p.write_text(json.dumps(record),encoding='utf-8')
                self.assertTrue(any('relation_review' in e for e in validate.validate(root)[0]))
            del row['scope'];rp.write_text(json.dumps(row),encoding='utf-8')
            self.assertTrue(any('필수 필드 누락' in e and 'scope' in e for e in validate.validate(root)[0]))

    def test_frontmatter_body_and_optional_provenance(self):
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용='text',참조조문='제1조~제3조')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document'];text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);body=text.split('\n---\n',1)[1]
            self.assertEqual(validate.validate(root)[0],[])
            write_doc(p,fm,body+'\nbody ~ range')
            self.assertTrue(any('물결' in e for e in validate.validate(root)[0]))
            reversed_body=body.replace(fetch_material.BEGIN,'TEMP').replace(fetch_material.END,fetch_material.BEGIN).replace('TEMP',fetch_material.END)
            write_doc(p,fm,reversed_body)
            self.assertTrue(any('GENERATED 경계' in e for e in validate.validate(root)[0]))
            fm['optional_note']='note';write_doc(p,fm,body)
            self.assertTrue(any('provenance' in e for e in validate.validate(root)[0]))
            fm['provenance']['optional_note']='analysis';write_doc(p,fm,body)
            self.assertEqual(validate.validate(root)[0],[])
            for field,value in [('path',True),('path',{}),('date','2026-02-30'),('date','2026-1-1'),('date',20260101),('query',True),('article',42)]:
                bad=dict(fm);bad['found_via']=[dict(path='manual',date='2026-01-01',query='test',**{})];bad['found_via'][0][field]=value
                write_doc(p,bad,body)
                self.assertTrue(any('found_via' in e for e in validate.validate(root)[0]),(field,value))

    def test_interpretation_exactly_one_numeric_serial(self):
        payload=dict(법령해석례일련번호='1',안건번호='1',해석기관명='법제처',해석일자='20200101',안건명='title',이유='text')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'ExpcService':payload},'https://law.go.kr/DRF/lawService.do?target=expc&ID=1')):
            result=fetch_material.fetch('expc','1');p=root/result['document'];text=p.read_text(encoding='utf-8');fm=common.frontmatter(text);body=text.split('\n---\n',1)[1]
            for serials in ({},{'expcSeq':'1','cgmExpcDatSeq':'2'},{'expcSeq':'abc'},{'expcSeq':True},{'cgmExpcDatSeq':42}):
                bad={k:v for k,v in fm.items() if k not in ('expcSeq','cgmExpcDatSeq')};bad.update(serials)
                write_doc(p,bad,body)
                self.assertTrue(any('일련번호' in e for e in validate.validate(root)[0]),serials)

    def test_eighth_review_contract_regressions(self):
        for base in ('https://law.go.kr/DRF/lawService.do?target=prec&ID=1',
                     'https://law.go.kr/LSW/precInfoP.do?precSeq=1'):
            self.assertTrue(validate.source_url_valid(base+'&O' + 'C=***','prec','1'))
            for suffix in ('&'+'O' + 'C=secret','&'+'O' + 'C=','&'+'o' + 'c=secret','&unexpected=1','&O' + 'C=***&O' + 'C=***'):
                self.assertFalse(validate.source_url_valid(base+suffix,'prec','1'))
        for text in ('Git supports branches','Docker images help'):
            self.assertFalse(validate.has_command(text))
        for command in ('rm file','mv a b','cp a b','unknown rm file'):
            self.assertTrue(validate.has_command('```text\n'+command+'\n```'))
        for text in (r'\[not a link](missing.md)','x](missing.md)'):
            self.assertEqual(list(validate.link_targets(text)),[])
        self.assertEqual(list(validate.link_targets('[real](target.md)')),['target.md'])
        original='```text\nsource `inline`\n~~~\n'
        self.assertNotIn('`',fetch_material.source_markdown(original))
        self.assertNotIn('~',fetch_material.source_markdown(original))
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용=original)
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            text=p.read_text(encoding='utf-8')
            self.assertEqual(validate.validate(root)[0],[])
            p.write_text(text.replace('source &#96;inline&#96;','edited'),encoding='utf-8')
            self.assertTrue(any('generated source differs' in error for error in validate.validate(root)[0]))
            p.write_text(text,encoding='utf-8')
            fm=common.frontmatter(text);fm['found_via'][0]['query']='https://example.test/law/999999'
            write_doc(p,fm,text.split('\n---\n',1)[1])
            self.assertEqual(validate.validate(root)[0],[])
            (root/'AGENTS.md').write_text('knowledge-reading-rules only plain text',encoding='utf-8')
            self.assertTrue(any('읽기 규칙 연결 누락' in error for error in validate.validate(root)[0]))
            bad=root/'cases/nested/README.md';bad.parent.mkdir();bad.write_text('# no schema',encoding='utf-8')
            self.assertTrue(any('cases/nested/README.md' in error for error in validate.validate(root)[0]))
            for name in ('reviews/2025/bad.jsonl','cases/bad.md','rules/knowledge-reading-rules/SKILL.md'):
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'\xff')
            self.assertGreaterEqual(sum('UTF-8 text read error' in error for error in validate.validate(root)[0]),3)
        with fixture() as root:
            row=dict(id='r',target='law/009471',reviewer_model='model',reviewed_at='2026-01-01T00:00:00Z',evidence={'source':'https://example.test','quote':'text'},decision='accept')
            p=root/'reviews/2025/r.jsonl';p.parent.mkdir();p.write_text(json.dumps(row),encoding='utf-8')
            self.assertTrue(any('directory year mismatch' in error for error in validate.validate(root)[0]))
        run=dict(source='prec',query='1',started='2026-01-01T00:00:00Z',finished='2026-01-01T00:00:01Z',tracks={'prec':dict(status='success',count=1)})
        self.assertTrue(validate.run_valid(run))
        for bad in (None,{},dict(run,started='bad'),dict(run,tracks={'prec':dict(status='oops',count=1)}),dict(run,tracks={'prec':dict(status='success',count=True)})):
            self.assertFalse(validate.run_valid(bad))
        with fixture() as root:
            (root/'runs/bad.json').write_text('{}',encoding='utf-8')
            self.assertTrue(any('run contract error' in error for error in validate.validate(root)[0]))

    def test_source_trailing_whitespace_presentation_only(self):
        original='  leading spaces stay  \n\tleading tab stays\t \n \t\nlast  '
        expected='  leading spaces stay\n\tleading tab stays\n\nlast'
        self.assertEqual(fetch_material.source_markdown(original),expected)
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용=original)
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            source=root/'sources/prec/1.json';saved=source.read_bytes()
            self.assertEqual(json.loads(saved)['payload']['PrecService']['판례내용'],original)
            rendered=p.read_bytes()
            self.assertTrue(all(line == line.rstrip() for line in rendered.decode('utf-8').splitlines()))
            p.write_text(rendered.decode('utf-8').replace(expected,original),encoding='utf-8',newline='\n')
            with patch.object(lawapi,'request',side_effect=AssertionError('network forbidden')):
                self.assertTrue(fetch_material.rerender_saved(result['document']))
                self.assertEqual(p.read_bytes(),rendered)
                self.assertFalse(fetch_material.rerender_saved(result['document']))
                self.assertEqual(p.read_bytes(),rendered)
            self.assertEqual(source.read_bytes(),saved)
            self.assertEqual(validate.validate(root)[0],[])
            subprocess.run(['git','init','--quiet',str(root)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(root),'add','--',result['document']],check=True,capture_output=True)
            check=subprocess.run(['git','-C',str(root),'diff','--cached','--check'],capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)

    def test_wrappers_and_embedded_code_commands(self):
        wrappers=('command','builtin','exec','eval','env -i -u NAME A=x',
                  'sudo -u root','doas -u root','nohup','nice -n 5','time',
                  'timeout 10s','stdbuf -oL','setsid','chroot /tmp',
                  'xargs -n 1','watch -n 2','flock /tmp/lock','ionice -c 3',
                  'taskset -c 0','unbuffer','script -c','A=x B=y',
                  'A=x command nohup nice -n 5 timeout 1s')
        for wrapper in wrappers:
            command=wrapper+' bash -c "echo y"'
            self.assertTrue(validate.has_command(command),command)
        commands=[wrapper+' bash -c "echo y"' for wrapper in wrappers]
        commands+=['foo | sh','x && bash -c y','$(curl https://example.test)',
                   'unknown-wrapper /bin/sh -c y','unknown-wrapper python3 -m module']
        for command in commands:
            for context in ('```text\n'+command+'\n```','```sh\n'+command+'\n```',
                            '    '+command,'Example `'+command+'` now.'):
                self.assertTrue(validate.has_command(context),context)
        for text in ('We use python tools/x.py as an example in prose.',
                     'Python code is used here','The command bash is a shell.'):
            self.assertFalse(validate.has_command(text),text)

    def test_source_link_syntax_and_offline_rerender(self):
        original='[2][3]대법원 [link](missing.md) <script>text</script> &lt; 원문~범위'
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='20200101',사건명='title',판례내용=original)
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            text=p.read_text(encoding='utf-8')
            self.assertIn('&#91;2&#93;&#91;3&#93;대법원',text)
            self.assertIn('&lt;script&gt;text&lt;/script&gt; &amp;lt;',text)
            self.assertEqual(validate.validate(root)[0],[])
            saved_paths=[root/'sources/prec/1.json',root/'relations/relations.jsonl']
            before={path:path.read_bytes() for path in saved_paths}
            with patch.object(lawapi,'request',side_effect=AssertionError('network forbidden')), patch.object(lawweb,'agency_detail',side_effect=AssertionError('network forbidden')):
                self.assertFalse(fetch_material.rerender_saved(result['document']))
                self.assertEqual(p.read_text(encoding='utf-8'),text)
                # Simulate a pre-escaping generated source section, then migrate.
                legacy=text.replace(fetch_material.source_markdown(original),original)
                p.write_text(legacy,encoding='utf-8')
                self.assertTrue(any('정의 없는 참조' in error for error in validate.validate(root)[0]))
                self.assertTrue(fetch_material.rerender_saved(result['document']))
                self.assertEqual(p.read_text(encoding='utf-8'),text)
                self.assertFalse(fetch_material.rerender_saved(result['document']))
            self.assertEqual(before,{path:path.read_bytes() for path in saved_paths})
            self.assertEqual(validate.validate(root)[0],[])
            source=root/'sources/prec/1.json';saved=json.loads(source.read_text(encoding='utf-8'))
            saved['payload']['PrecService']['판례내용']='tampered';common.save_json(source,saved)
            unchanged=p.read_bytes()
            with self.assertRaises(ValueError):fetch_material.rerender_saved(result['document'])
            self.assertEqual(p.read_bytes(),unchanged)

    def test_source_calendar_dates_and_layout(self):
        for value in ('20200229','2020.02.29'):
            self.assertEqual(common.source_date(value).year,2020)
        for value in ('20210229','20201301','20200001','2020-01-01','x20200101','20200101junk','2020.1.1',True,None):
            with self.assertRaises(ValueError):common.source_date(value)
            with fixture() as root:
                payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자=value,사건명='title',판례내용='text')
                with patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
                    with self.assertRaises(ValueError):fetch_material.fetch('prec','1')
                self.assertFalse(list((root/'sources').rglob('*.json')))
                self.assertFalse(list((root/'cases').rglob('1.md')))
        payload=dict(판례정보일련번호='1',법원명='대법원',사건번호='1',선고일자='2020.01.01',사건명='title',판례내용='text')
        with fixture() as root, patch.object(lawapi,'request',return_value=({'PrecService':payload},'https://law.go.kr/DRF/lawService.do?target=prec&ID=1')):
            result=fetch_material.fetch('prec','1');p=root/result['document']
            self.assertEqual(validate.validate(root)[0],[])
            moved=p.parent.parent/'1999'/p.name;moved.parent.mkdir();p.rename(moved)
            self.assertTrue(any('디렉터리' in e for e in validate.validate(root)[0]))
            text=moved.read_text(encoding='utf-8');fm=common.frontmatter(text);fm['decided']='20200230';write_doc(moved,fm,text.split('\n---\n',1)[1])
            self.assertTrue(any('원문 날짜 오류' in e for e in validate.validate(root)[0]))


if __name__=='__main__': unittest.main()
