# SPDX-License-Identifier: GPL-3.0-only
"""원문 보존 및 문서 생성. 기존 수동 영역과 검토 결과는 보존한다."""
import json
import os
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, CODE_ROOT, now, sha, canonical, save_json, frontmatter, load_index, relation, add_relations, readjson, source_date, court_slug, staged_files, check_output_path, safe_write_text, safe_write_bytes
import lawapi
import lawweb
from secret_scan import redact_diagnostic

AGENCIES = {'국토교통부': 'molit', '국세청': 'nts'}

def candidate_rows(kind, ident):
    rows = []
    from candidates import candidate_file
    for path in sorted((ROOT / 'sources/candidates').glob('*.jsonl')):
        for row in candidate_file(ROOT, path):
            if row['target'] == kind and row['source_id'] == ident:
                rows.append(row)
    return rows

def candidate_provenance(kind, ident):
    found = []
    for row in candidate_rows(kind, ident):
        for via in row.get('found_via', []):
            if via not in found: found.append(via)
    return found

BEGIN = '<!-- BEGIN GENERATED:source -->'
END = '<!-- END GENERATED:source -->'

SOURCE_HEADING = '\n### 수집 원문 [source]\n\n'
SOURCE_FIELDS = {'판례내용', '해석이유', '이유', '판시사항', '판결요지', '질의요지', '회답', '참조조문', '참조판례'}


def source_markdown(value):
    """Render untrusted source text literally, not as Markdown links or HTML."""
    text = str(value)
    for char, entity in (('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'),
                         ('[', '&#91;'), (']', '&#93;'), ('~', '&#126;'), ('`', '&#96;')):
        text = text.replace(char, entity)
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def render_source(payload):
    return SOURCE_HEADING + ''.join(
        f'#### {key}\n\n' + source_markdown(value) + '\n\n'
        for key, value in sorted(payload.items()) if key in SOURCE_FIELDS)


def generated_relations(mid, rawrefs, index=None):
    unmapped, rels = [], []
    try:
        index, _, _ = load_index() if index is None else (index, None, None)
        # Prefer complete pinned names, including digits and punctuation; an
        # unknown/abbreviated prefix must never match a shorter indexed suffix.
        names = sorted({re.sub(r'\s+', '', law['name']) for law in index['laws'].values()}, key=len, reverse=True)
        name_pattern = '|'.join(r'\s*'.join(re.escape(c) for c in name) for name in names)
        pattern = r'(?<![가-힣A-Za-z0-9·])(' + (name_pattern or r'(?!)') + r'|[가-힣A-Za-z0-9·()ㆍ「」]+(?:\s+[가-힣A-Za-z0-9·()ㆍ「」]+)*?)\s*제(\d+)조(?:의(\d+))?'
        for match in re.finditer(pattern, rawrefs):
            name, no, sub = match.groups()
            name = re.sub(r'\s+', '', name)
            laws = [lid for lid, law in index['laws'].items() if re.sub(r'\s+', '', law['name']) == name]
            matches = [aid for aid in index['articles'] if len(laws) == 1 and aid.startswith('law/' + laws[0] + '@') and aid.endswith('#a' + no + ('-' + sub if sub else ''))]
            if len(matches) == 1:
                rels.append(relation('cites', mid, matches[0], evidence=match.group(0)))
            else:
                unmapped.append(dict(text=match.group(0), reason='법령명/판본/조문 대응 불확실'))
        if rawrefs and not rels and not unmapped:
            unmapped.append(dict(text=rawrefs, reason='명시적 조문 파싱 불가'))
    except ValueError:
        unmapped.append(dict(reason='검증 불가: 잠금 색인 없음'))
    rels = list({row['id']: row for row in rels}.values())
    return unmapped, rels


def render_generated(payload, mid, url, source_path, digest, index=None):
    rawrefs = str(payload.get('참조조문') or payload.get('관련법령') or '').strip()
    unmapped, rels = generated_relations(mid, rawrefs, index)
    generated = BEGIN + '\n## 원문 메타데이터와 연결 [machine]\n\n' + f'- 원문: {url}\n- 원문 파일: `{source_path}`\n- SHA256: `{digest}`\n'
    for row in rels:
        generated += '- 참조 조문: `' + row['dst'] + '` [machine; 적용 판본 미확인]\n'
    if unmapped:
        generated += '- 미대응: ' + source_markdown(json.dumps(unmapped, ensure_ascii=False)) + '\n'
    generated += render_source(payload)
    # Fetched content is data, never a generated-block delimiter.
    generated = BEGIN + re.sub(r'<!-- (?=(?:BEGIN|END) GENERATED:)', '&lt;!-- ', generated[len(BEGIN):]).replace('~', '&#126;') + END
    return generated


def rerender_saved(document):
    """Offline full generated-block migration; preserve metadata, manual text and JSON.

    Reuse the fetch renderer directly. No API calls, state transitions, relation
    regeneration or found_via changes occur during this formatting migration.
    """
    path = Path(document)
    path = ROOT / path if not path.is_absolute() else path
    check_output_path(path)
    path = path.resolve()
    text = path.read_text(encoding='utf-8')
    fm = frontmatter(text)
    keys = [key for key in ('precSeq', 'expcSeq', 'cgmExpcDatSeq') if key in fm]
    if len(keys) != 1 or not isinstance(fm[keys[0]], str) or not re.fullmatch(r'\d+', fm[keys[0]]):
        raise ValueError('재생성 원문 식별자 오류')
    kind = {'precSeq': 'prec', 'expcSeq': 'expc', 'cgmExpcDatSeq': 'cgmexpc'}[keys[0]]
    ident = fm[keys[0]]
    saved = readjson((ROOT / 'sources' / kind / (ident + '.json')).read_text(encoding='utf-8'))
    from validate import source_url_valid
    if (saved.get('target') != kind or str(saved.get('source_id')) != ident
            or saved.get('source_url') != fm.get('source_url')
            or not source_url_valid(saved.get('source_url'), kind, ident)):
        raise ValueError('재생성 원문 메타데이터 불일치')
    data = saved['payload']
    expected_root, serial_key = {'prec': ('PrecService', '판례정보일련번호'), 'expc': ('ExpcService', '법령해석례일련번호'), 'cgmexpc': ('CgmExpcService', '법령해석일련번호')}[kind]
    if (not isinstance(data, dict) or set(data) != {expected_root}
            or not isinstance(data[expected_root], dict)
            or str(data[expected_root].get(serial_key)) != ident):
        raise ValueError('재생성 원문 종류/일련번호 불일치')
    digest = sha(canonical(data, reject_masked=True))
    if digest != saved.get('sha256') or digest != fm.get('source_sha256'):
        raise ValueError('재생성 원문 해시 불일치')
    header, body = text.split('\n---\n', 1)
    if body.count(BEGIN) != 1 or body.count(END) != 1 or body.index(BEGIN) >= body.index(END):
        raise ValueError('GENERATED 경계 오류: 보류')
    start, end = body.index(BEGIN), body.index(END)
    block = body[start:end]
    if block.count(SOURCE_HEADING) != 1:
        raise ValueError('재생성 원문 절 경계 오류')
    replacement = render_generated(data[expected_root], fm['id'], fm['source_url'],
                                   'sources/' + kind + '/' + ident + '.json', digest)[:-len(END)]
    result = header + '\n---\n' + body[:start] + replacement + body[end:]
    if result != text:
        with staged_files([path]) as staged:
            safe_write_text(staged[path], result)
    return result != text


def clean_filename(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).rstrip('. ')

def case_source_valid(court, providers):
    # Official court abbreviations used by the center: 지법/고법 as well as 법원.
    pattern = r'(?:대법원|헌법재판소|[가-힣]+(?:지방법원|고등법원|가정법원|행정법원|특허법원|회생법원|지법|고법)(?: [가-힣]+지원)?)'
    return (isinstance(court, str) and bool(re.fullmatch(pattern, court))
            and isinstance(providers, list)
            and all(provider in {'법원도서관', '대법원', '헌법재판소'} for provider in providers))


def extract_source_fields(kind, ident, payload, providers_extra=()):
    """Shared source-to-frontmatter extraction for fetching and validation."""
    pick = lambda *keys: next((str(payload[k]).strip() for k in keys if payload.get(k)), '')
    if kind == 'prec':
        court, case_no = str(payload.get('법원명', '')), pick('사건번호')
        date, title = pick('선고일자'), pick('사건명')
        fulltext = pick('판례내용')
        if not all((court, case_no, date, title, fulltext)):
            raise ValueError('판례 핵심 필드 누락: 보류')
        providers = {pick('데이터출처명')} - {''}
        providers.update(str(value).strip() for value in providers_extra if value)
        normalized_case = re.sub(r'\s+', '', case_no)
        mid = f'case/{court_slug(court)}/{normalized_case}'
        fm = dict(id=mid, court=court, case_no=case_no, decided=date, title=title, kind=pick('판결유형', '사건종류명') or 'unknown', precSeq=ident, ref_articles_raw=pick('참조조문'))
        fm['data_source_name'] = sorted(providers)
        dest = ROOT / 'cases' / clean_filename(court_slug(court)) / str(source_date(date).year).zfill(4) / (clean_filename(case_no) + '.md')
    else:
        case_no = pick('안건번호')
        if kind == 'expc':
            agency = 'moleg'
            if pick('해석기관명') not in {'법제처', '법제처 법령해석국'}:
                raise ValueError('법제처 외 해석기관: 기관 코드 확인 후 수록 필요')
        else:
            agency = AGENCIES.get(pick('해석기관명'))
            if not agency:
                raise ValueError('중앙부처 해석 기관 코드 미등록: 보류')
        date, title = pick('회신일자', '해석일자'), pick('안건명', '제목')
        fulltext = pick('해석이유', '이유', '회답')
        if not all((case_no, date, title, fulltext)):
            raise ValueError('해석 핵심 필드 누락: 보류')
        mid = f'interp/{agency}/{case_no}'
        fm = dict(id=mid, agency=agency, case_no=case_no, replied=date, requester=pick('질의기관명', '질의기관', '요청기관') or 'unknown', title=title, ref_articles_raw=pick('참조조문', '관련법령'), facts_summary='unknown')
        fm['cgmExpcDatSeq' if kind == 'cgmexpc' else 'expcSeq'] = ident
        dest = ROOT / 'interpretations' / agency / str(source_date(date).year).zfill(4) / (clean_filename(case_no) + '.md')
    return fm, dest


def fetch(kind, ident, *, run_path=None, started=None):
    if not re.fullmatch(r'\d+', ident):
        raise ValueError('API ID는 숫자여야 함')
    if kind not in {'prec', 'expc', 'cgmexpc'}:
        raise ValueError('지원하지 않는 자료 종류')
    data, url = lawweb.agency_detail(ident) if kind == 'cgmexpc' else lawapi.request('lawService.do', kind, ID=ident)
    expected_root, serial_key = {'prec': ('PrecService', '판례정보일련번호'), 'expc': ('ExpcService', '법령해석례일련번호'), 'cgmexpc': ('CgmExpcService', '법령해석일련번호')}[kind]
    if set(data) != {expected_root}:
        raise ValueError('상세 응답 종류 불일치: 보류')
    payload = data[expected_root]
    if not isinstance(payload, dict):
        raise ValueError('본문 객체가 아님')
    if str(payload.get(serial_key, '')) != ident:
        raise ValueError('상세 응답 원문 ID 불일치: 보류')
    fm, dest = extract_source_fields(kind, ident, payload, [row.get('데이터출처명') for row in candidate_rows(kind, ident)])
    mid = fm['id']
    if kind == 'prec':
        if not case_source_valid(fm['court'], fm['data_source_name']):
            raise ValueError('비법원 출처/데이터출처명: 판례 수록 보류')
    # 동일 원문 ID 또는 논리 키가 다른 경로에 있으면 중복 생성 대신 보류한다.
    for base in ('cases', 'interpretations'):
        for existing in (ROOT / base).rglob('*.md'):
            if existing == ROOT / base / 'README.md':
                continue
            old = frontmatter(existing.read_text(encoding='utf-8'))
            source_key = {'prec': 'precSeq', 'expc': 'expcSeq', 'cgmexpc': 'cgmExpcDatSeq'}[kind]
            same_source = str(old.get(source_key)) == ident
            if existing == dest:
                if not same_source or old.get('id') != mid:
                    raise ValueError('동일 목적지 원문 ID 충돌: 보류')
                continue
            same_key = old.get('id') == mid
            if same_source or same_key:
                raise ValueError('중복 식별 키가 다른 경로에 존재: 보류')
    # 검색 원문은 비밀을 제거한 정규 JSON 바이트를 해시한다.
    digest = sha(canonical(data))
    source = ROOT / 'sources' / kind / (ident + '.json')
    if dest.exists():
        prior = frontmatter(dest.read_text(encoding='utf-8'))
        if prior.get('source_sha256') != digest and prior.get('reference_status') != 'unreviewed':
            raise ValueError('검토된 문서 원문 변경: 기존 검토를 유지한 자동 덮어쓰기 보류')
    fm.update(source_url=url, source_sha256=digest, applied_version='unknown', progress='source-verified', reference_status='unreviewed', last_reviewed=None,
              found_via=candidate_provenance(kind, ident) + [dict(path='web-detail' if kind == 'cgmexpc' else 'api-service', query=ident, date=now()[:10])])
    fields = {k: ('machine' if k in {'id', 'source_sha256', 'progress', 'reference_status', 'last_reviewed', 'found_via', 'source_url', 'applied_version'} else 'source') for k in fm}
    if kind != 'prec':
        fields['facts_summary'] = 'summary'
    fm['provenance'] = fields
    unmapped, rels = generated_relations(mid, fm.get('ref_articles_raw', ''))
    generated = render_generated(payload, mid, url, source.relative_to(ROOT).as_posix(), digest)
    reconciled_rows = None
    if dest.exists():
        text = dest.read_text(encoding='utf-8')
        old = frontmatter(text)
        if old['id'] != mid:
            raise ValueError('문서 식별자 충돌')
        # 미검토 자료의 source 필드만 새 응답으로 갱신하고 수동 판단은 보존한다.
        if old.get('reference_status') == 'unreviewed':
            for key, value in fm.items():
                if fields.get(key) == 'source' and old.get('provenance', {}).get(key, 'source') == 'source':
                    old[key] = value
                    old.setdefault('provenance', {})[key] = 'source'
        relations_path = ROOT / 'relations/relations.jsonl'
        existing_rows = [readjson(line) for line in relations_path.read_text(encoding='utf-8').splitlines() if line.strip()] if relations_path.exists() else []
        old_edges = {row['id'] for row in existing_rows if row.get('src') == mid}
        retained_edges = {row['id'] for row in existing_rows if row.get('src') == mid
                          and not (row.get('type') == 'cites' and row.get('review') == 'unreviewed'
                                   and row.get('found_by') == ['cites-article'])}
        regenerated_edges = {row['id'] for row in rels}
        # Compare replaceable automatic candidates independently of document review.
        old_automatic = old_edges - retained_edges
        next_automatic = regenerated_edges - retained_edges
        stale_reviewed = {row['id'] for row in existing_rows if row.get('src') == mid
                          and row.get('type') == 'cites' and row.get('found_by') == ['cites-article']
                          and row.get('review') != 'unreviewed' and row['id'] not in regenerated_edges}
        # Never discard an unresolved removal, even when its edge is absent.
        existing_by_id = {row['id']: row for row in existing_rows}
        stale_reviewed.update(rid for rid in old.get('relation_recheck', [])
                              if rid not in existing_by_id or existing_by_id[rid].get('review') == 'needs-review')
        if old.get('source_sha256') != digest:
            for row in existing_rows:
                if row.get('src') == mid and row.get('review') == 'confirmed':
                    row['review'] = 'needs-review'
                    stale_reviewed.add(row['id'])
            reconciled_rows = existing_rows
        if stale_reviewed:
            old['relation_recheck'] = sorted(stale_reviewed)
            old.setdefault('provenance', {})['relation_recheck'] = 'machine'
        elif 'relation_recheck' in old:
            old.pop('relation_recheck')
            old.get('provenance', {}).pop('relation_recheck', None)
        edges_changed = old_automatic != next_automatic or bool(stale_reviewed)
        if (old.get('source_sha256') != digest or edges_changed) and old.get('progress') in {'relations-reviewed', 'published'}:
            old['progress'] = 'source-verified'
        old.update({k: fm[k] for k in ('source_url', 'source_sha256')})
        for via in fm['found_via']:
            if via not in old['found_via']: old['found_via'].append(via)
        fm = old
        body = text.split('\n---\n', 1)[1]
        if body.count(BEGIN) != 1 or body.count(END) != 1 or body.index(BEGIN) >= body.index(END):
            raise ValueError('GENERATED 경계 오류: 보류')
        body = body[:body.index(BEGIN)] + generated + body[body.index(END) + len(END):]
    else:
        template = (CODE_ROOT / 'templates' / ('case.md' if kind == 'prec' else 'interp.md')).read_text(encoding='utf-8')
        body = template.split('\n---\n', 1)[1]
        body = body[:body.index(BEGIN)] + generated + body[body.index(END) + len(END):]
    header = '---\n' + ''.join(k + ': ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fm.items()) + '---\n'
    if body.count(BEGIN) != 1 or body.count(END) != 1 or body.index(BEGIN) >= body.index(END):
        raise ValueError('GENERATED 경계 오류: 보류')
    frontmatter(header + body)
    # Prepare every artifact on its destination filesystem before any replacement.
    relations_path = ROOT / 'relations/relations.jsonl'
    result = dict(document=dest.relative_to(ROOT).as_posix(), relations=len(rels), unmapped=unmapped)
    targets = [source, dest, relations_path]
    if run_path is not None:
        targets.append(run_path)
    with staged_files(targets) as staged:
        save_json(staged[source], dict(target=kind, source_id=ident, fetched=now(), source_url=url, sha256=digest, payload=data))
        readjson(staged[source].read_text(encoding='utf-8'))
        safe_write_text(staged[dest], header + body)
        frontmatter(staged[dest].read_text(encoding='utf-8'))
        if reconciled_rows is None:
            safe_write_bytes(staged[relations_path], relations_path.read_bytes() if relations_path.exists() else b'')
        else:
            safe_write_text(staged[relations_path], ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in reconciled_rows))
        add_relations(rels, replace_generated_for=mid,
                      path=staged[relations_path])
        for line in staged[relations_path].read_text(encoding='utf-8').splitlines():
            readjson(line)
        if run_path is not None:
            save_json(staged[run_path], dict(source=kind, query=ident, started=started,
                      finished=now(), tracks={kind: dict(status='success', count=1)}, **result))
            readjson(staged[run_path].read_text(encoding='utf-8'))
    return result


def run_fetch(kind, ident):
    started = now()
    day = started[:10]
    folder = ROOT / 'runs' / kind
    n = 1
    while (folder / f'{day}-{n}.json').exists():
        n += 1
    record = dict(source=kind, query=ident, started=started, tracks={})
    try:
        # The success audit record is committed with the source/doc/relations.
        result = fetch(kind, ident, run_path=folder / f'{day}-{n}.json', started=record['started'])
    except Exception as exc:
        record['tracks'][kind] = dict(status='failure', count=0, error=redact_diagnostic(lawapi.sanitize(str(exc))))
        record['finished'] = now()
        run_path = folder / f'{day}-{n}.json'
        check_output_path(run_path)
        save_json(run_path, record)
        print('ERROR', record['tracks'][kind]['error'])
        return 1
    # Output is not part of collection: a closed pipe must not rewrite success.
    print(redact_diagnostic(json.dumps(result, ensure_ascii=False)))
    return 0
