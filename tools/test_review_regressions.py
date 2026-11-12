# SPDX-License-Identifier: GPL-3.0-only
"""Regression coverage for the thirteen outstanding skeleton review comments."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from tools.test_tools import fixture, write_doc, write_candidates
import common
import collect_article
import fetch_material
import lawapi
import lawweb
import validate
from candidates import candidate_file


def payload(ident='1', **extra):
    return dict(판례정보일련번호=ident, 법원명='대법원', 사건번호=ident,
                선고일자='20200101', 사건명='title', 판례내용='source quotation', **extra)


def response(_endpoint, _kind, ID):
    return {'PrecService': payload(ID)}, 'https://law.go.kr/DRF/lawService.do?target=prec&ID=' + ID


def edit_frontmatter(path, **values):
    text = path.read_text(encoding='utf-8')
    fm = common.frontmatter(text)
    fm.update(values)
    fm['provenance'].update({key: 'machine' for key in values})
    write_doc(path, fm, text.split('\n---\n', 1)[1])
    return fm


def accept_edge(root, edge):
    edge.update(review='confirmed', reviewed_by='model', reviewed_at='2026-01-01T00:00:00Z',
                evidence=dict(source='https://example.test', quote='source quotation'))
    record = dict(id='review-' + edge['id'], target=edge['id'], relation_review='confirmed',
                  reviewer_model=edge['reviewed_by'], reviewed_at=edge['reviewed_at'],
                  evidence=edge['evidence'], decision='accept',
                  relation_snapshot={key: edge[key] for key in ('type', 'src', 'dst', 'scope')})
    if edge['src'].startswith(('case/', 'interp/')):
        for base in ('cases', 'interpretations'):
            for document in (root / base).rglob('*.md'):
                if document == root / base / 'README.md':
                    continue
                fm = common.frontmatter(document.read_text(encoding='utf-8'))
                if fm['id'] == edge['src']:
                    record['source_sha256'] = fm['source_sha256']
    path = root / 'reviews/2026/relations.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + '\n', encoding='utf-8')
    return path, record


class ReviewRegressions(unittest.TestCase):
    def test_4507392889_removed_relation_bound_to_original_source(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            first = root / fetch_material.fetch('prec', '1')['document']
            second = root / fetch_material.fetch('prec', '2')['document']
            source_id = common.frontmatter(first.read_text(encoding='utf-8'))['id']
            edge = common.relation('cites', source_id, 'law/009471@261727#a25')
            review_path, review = accept_edge(root, edge)
            edit_frontmatter(first, progress='published')
            edit_frontmatter(second, relation_recheck=[edge['id']])
            errors = validate.validate(root)[0]
            self.assertTrue(any('without recheck on source document' in error for error in errors))
            self.assertTrue(any('another source document' in error for error in errors))
            text = second.read_text(encoding='utf-8'); fm = common.frontmatter(text)
            fm.pop('relation_recheck'); fm['provenance'].pop('relation_recheck')
            write_doc(second, fm, text.split('\n---\n', 1)[1])
            edit_frontmatter(first, progress='source-verified', relation_recheck=[edge['id']])
            self.assertEqual(validate.validate(root)[0], [])
            review.pop('relation_snapshot')
            review_path.write_text(json.dumps(review), encoding='utf-8')
            self.assertTrue(any('relation_snapshot' in error for error in validate.validate(root)[0]))

    def test_4507392891_collector_deduplicates_nested_readme(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            path = root / fetch_material.fetch('prec', '1')['document']
            path.rename(path.parent / 'README.md')
            interp = root / 'interpretations/moleg/2020/README.md'
            interp.parent.mkdir(parents=True)
            write_doc(interp, dict(id='interp/moleg/1', expcSeq='1'), '\n')
            index = {'laws': {'009471': {'name': '테스트법'}}, 'articles': {'law/009471@261727#a25': {}}}
            def linked(target, _ctx):
                return [dict(target=target, source_tab=target, source_id=ident, found_by=['linked-by-center'])
                        for ident in ('1', '2')] if target != 'cgmexpc' else []
            with patch.object(collect_article, 'ROOT', root), patch.object(collect_article, 'load_index', return_value=(index, root, 'WORKTREE')), patch.object(lawweb, 'context', return_value={}), patch.object(lawweb, 'linked', side_effect=linked), patch.object(sys, 'argv', ['collect_article.py', 'law/009471@261727#a25']):
                self.assertEqual(collect_article.main(), 0)
            rows = candidate_file(root, next((root / 'sources/candidates').glob('*.jsonl')))
            self.assertEqual({(row['target'], row['source_id']) for row in rows}, {('prec', '2'), ('expc', '2')})

    def test_4507392894_quoted_data_fences_preserve_data_indentation(self):
        for fence in ('json\n{\n  "a": "> value"\n}', 'jsonl\n{"a":1}\n{"a":2}',
                      'yaml\nkey:\n  child: "value"', 'csv\na,b\n1,2', 'tsv\na\tb\n1\t2'):
            for prefix in ('> ', '> > '):
                content = '\n'.join(prefix + line for line in ('```' + fence + '\n```').splitlines())
                self.assertFalse(validate.has_command(content), content)
        self.assertTrue(validate.has_command('> ```text\n> systemctl reboot\n> ```'))
        self.assertTrue(validate.has_command('> ```json\n> {broken}\n> ```'))

    def test_4507392897_malformed_relation_reports_and_continues(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            path = root / fetch_material.fetch('prec', '1')['document']
            ident = common.frontmatter(path.read_text(encoding='utf-8'))['id']
            edge = common.relation('cites', ident, 'law/009471@261727#a25')
            edge.pop('id')
            (root / 'relations/relations.jsonl').write_text(json.dumps(edge), encoding='utf-8')
            (root / 'cases/README.md').write_text('systemctl reboot', encoding='utf-8')
            errors = validate.validate(root)[0]
            self.assertTrue(any('relations: 필수 필드 누락' in error for error in errors))
            self.assertTrue(any('cases/README.md: 도구 명령' in error for error in errors))

    def test_4507392904_candidates_require_matching_machine_run(self):
        with fixture() as root:
            path, run_path, row, run = write_candidates(root)
            self.assertEqual(fetch_material.candidate_provenance('expc', '1'), row['found_via'])
            self.assertEqual(validate.validate(root)[0], [])
            for changes in ({'source_id': True}, {'target': 'unknown'}, {'found_via': []},
                            {'found_via': [dict(path='article-linked', article=row['article'], date='2026-02-30')]},
                            {'article': 'law/009471@261727#a26'}, {'source_tabs': ['prec']},
                            {'found_by': ['manual']}, {'데이터출처명': []}):
                path.write_text(json.dumps(dict(row, **changes)), encoding='utf-8')
                with self.assertRaises(ValueError):
                    fetch_material.candidate_provenance('expc', '1')
                self.assertTrue(any('candidate contract' in error for error in validate.validate(root)[0]), changes)
            path.write_text(json.dumps(row), encoding='utf-8')
            for changes in ({'id': 'other'}, {'candidate_count': 2}, {'candidates': 'sources/candidates/other.jsonl'},
                            {'tracks': {'expc': dict(status='zero', count=0)}}, {'article': 'law/009471@261727#a26'}):
                common.save_json(run_path, dict(run, **changes))
                with self.assertRaises(ValueError):
                    fetch_material.candidate_rows('expc', '1')
            run_path.unlink()
            self.assertTrue(any('candidate contract' in error for error in validate.validate(root)[0]))

    def test_4507401836_visible_markdown_commands(self):
        for command in ('**systemctl reboot**', '## systemctl reboot', '[systemctl reboot](README.md)',
                        'systemctl&#32;reboot', '<strong>systemctl reboot</strong>',
                        '<div>systemctl&nbsp;reboot</div>', '*systemctl reboot*',
                        '[systemctl reboot][ref]\n\n[ref]: README.md'):
            self.assertTrue(validate.has_command(command), command)
            with fixture() as root:
                (root / 'cases/README.md').write_text(command, encoding='utf-8')
                self.assertTrue(any('도구 명령' in error for error in validate.validate(root)[0]), command)
        self.assertFalse(validate.has_command('**법률 자료**를 검토한다.'))

    def test_4507401838_non_utf8_and_nul_files_rejected(self):
        value = '$env:' + 'LAW_O' + 'C' + ' = "fixture-secret"'
        with fixture() as root:
            for encoding in ('utf-16', 'utf-16-le', 'utf-32-le'):
                (root / 'windows-env.txt').write_bytes(value.encode(encoding))
                self.assertTrue(any('windows-env.txt: UTF-8' in error for error in validate.validate(root)[0]), encoding)
            (root / 'windows-env.txt').write_bytes(b'\xff\xfe\x80')
            self.assertTrue(any('UTF-8' in error for error in validate.validate(root)[0]))

    def test_4507401842_changed_payload_invalidates_manual_confirmed_relation(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            path = root / fetch_material.fetch('prec', '1')['document']
            fetch_material.fetch('prec', '2')
            ident = common.frontmatter(path.read_text(encoding='utf-8'))['id']
            edge = common.relation('overrules', ident, 'case/대법원/2', found_by='manual')
            review_path, record = accept_edge(root, edge)
            before_review = review_path.read_bytes()
            common.add_relations([edge])
            edit_frontmatter(path, progress='published')
            self.assertEqual(validate.validate(root)[0], [])
            changed = payload(); changed['판례내용'] = 'quotation removed'
            with patch.object(lawapi, 'request', return_value=({'PrecService': changed}, response('', '', '1')[1])):
                for _ in range(2):
                    fetch_material.fetch('prec', '1')
                    fm = common.frontmatter(path.read_text(encoding='utf-8'))
                    self.assertEqual(fm['progress'], 'source-verified')
                    self.assertEqual(fm['relation_recheck'], [edge['id']])
                    rows = [json.loads(line) for line in (root / 'relations/relations.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertEqual(rows[0]['review'], 'needs-review')
                    self.assertEqual(validate.validate(root)[0], [])
                self.assertEqual(review_path.read_bytes(), before_review)
                edge['evidence'] = dict(source='https://example.test', quote='new evidence')
                record['evidence'] = edge['evidence']
                record['source_sha256'] = fm['source_sha256']
                review_path.write_text(json.dumps(record), encoding='utf-8')
                (root / 'relations/relations.jsonl').write_text(json.dumps(edge), encoding='utf-8')
                fetch_material.fetch('prec', '1')
                self.assertNotIn('relation_recheck', common.frontmatter(path.read_text(encoding='utf-8')))
                self.assertEqual(validate.validate(root)[0], [])


    def test_4507451304_refetch_preserves_pending_removed_accept(self):
        with fixture() as root, patch.object(lawapi, 'request', side_effect=response):
            path = root / fetch_material.fetch('prec', '1')['document']
            ident = common.frontmatter(path.read_text(encoding='utf-8'))['id']
            edge = common.relation('cites', ident, 'law/009471@261727#a25')
            accept_edge(root, edge)
            edit_frontmatter(path, relation_recheck=[edge['id']])
            for _ in range(2):
                fetch_material.fetch('prec', '1')
                self.assertEqual(common.frontmatter(path.read_text(encoding='utf-8'))['relation_recheck'], [edge['id']])
                self.assertEqual(validate.validate(root)[0], [])

    def test_4507451306_multiline_inline_spans(self):
        for text in ('`git\nstatus`', '``systemctl\nreboot``', '설명 `git\r\nstatus` 설명',
                     '`git\n status`'):
            self.assertTrue(validate.has_command(text), text)
        for text in ('`law/009471@261727#a25`', '`tools/validate.py`', '`git\n\nstatus`',
                     '```json\n{"command":"git status"}\n```'):
            self.assertFalse(validate.has_command(text), text)
        with fixture() as root:
            (root / 'cases/README.md').write_text('`git\nstatus`', encoding='utf-8')
            self.assertTrue(any('도구 명령' in error for error in validate.validate(root)[0]))

    def test_4507451309_complete_indexed_law_names_with_digits(self):
        names = ('119구조법', '5·18민주화운동법', '법률(특례)법', 'A&B법')
        index = dict(laws={f'{number:06d}': dict(name=name) for number, name in enumerate(names, 1)},
                     articles={f'law/{number:06d}@1#a2': {} for number in range(1, 5)})
        for number, name in enumerate(names, 1):
            unmapped, rows = fetch_material.generated_relations('case/대법원/1', name + ' 제2조', index)
            self.assertEqual(unmapped, [], name)
            self.assertEqual([row['dst'] for row in rows], [f'law/{number:06d}@1#a2'])
        for name in ('구조법', '18민주화운동법', '가짜119구조법'):
            _, rows = fetch_material.generated_relations('case/대법원/1', name + ' 제2조', index)
            self.assertEqual(rows, [], name)
        duplicate = copy.deepcopy(index); duplicate['laws']['000005'] = dict(name=names[0])
        self.assertEqual(fetch_material.generated_relations('case/대법원/1', names[0] + ' 제2조', duplicate)[1], [])

    def test_4507460663_only_canonical_source_blocks_exempt_commands(self):
        block = fetch_material.BEGIN + '\nsystemctl reboot\n' + fetch_material.END
        with fixture() as root:
            for name in ('cases/README.md', 'interpretations/README.md', 'cases/extra.md'):
                path = root / name
                path.write_text(block, encoding='utf-8')
                self.assertTrue(any(name + ': 도구 명령' in error for error in validate.validate(root)[0]), name)
                path.unlink()
        with fixture() as root, patch.object(lawapi, 'request', return_value=({'PrecService': dict(payload(), 판례내용='systemctl reboot')}, response('', '', '1')[1])):
            path = root / fetch_material.fetch('prec', '1')['document']
            self.assertEqual(validate.validate(root)[0], [])
            original = path.read_text(encoding='utf-8')
            path.write_text(original + '\nsystemctl reboot\n', encoding='utf-8')
            self.assertTrue(any('도구 명령' in error for error in validate.validate(root)[0]))
            path.write_text(original.replace('systemctl reboot', 'systemctl poweroff'), encoding='utf-8')
            errors = validate.validate(root)[0]
            self.assertTrue(any('generated source differs' in error for error in errors))
            self.assertTrue(any('도구 명령' in error for error in errors))
