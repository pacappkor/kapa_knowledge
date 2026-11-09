# SPDX-License-Identifier: GPL-3.0-only
"""Pure historical membership and unpublished pilot evidence contracts."""
import re
from pathlib import PurePosixPath

from common import readjson, sha, source_date, frontmatter, court_slug

CATALOG = 'catalogs/materials.json'
EVIDENCE = 'runs/pilot/held-items-research.json'
HISTORY = 'runs/pilot/predecessor-versions-research.json'
IDENTITY_SOURCES = {
    '토지정책과-1730': {'23932': '37643', '40580': '37950'},
    '토지정책과-308': {'40786': '37805', '40696': '37808'},
}
IDENTITY_DOCUMENTS = frozenset('interp/molit/' + key for key in IDENTITY_SOURCES)
CATALOG_INPUTS = frozenset((CATALOG, EVIDENCE, HISTORY))


def historical_case(case_id, case, read_bytes):
    """Bind research identity to a bounded, existing local case document."""
    name = case.get('case_file')
    if not isinstance(name, str):
        raise ValueError('Historical case path missing.')
    path = PurePosixPath(name)
    if (path.as_posix() != name or '\\' in name or ':' in name
            or len(path.parts) != 4 or path.parts[0] != 'cases'
            or any(part in ('.', '..') for part in path.parts)
            or not re.fullmatch(r'\d{4}', path.parts[2]) or path.suffix != '.md'):
        raise ValueError('Unsafe historical case path.')
    if case_id != case.get('case_id'):
        raise ValueError('Historical case key/identity mismatch.')
    fm = frontmatter(read_bytes(name).decode('utf-8'))
    normalized = re.sub(r'\s+', '', fm.get('case_no', ''))
    court = court_slug(fm.get('court', ''))
    year = str(source_date(fm.get('decided')).year).zfill(4)
    expected_id = 'case/' + court + '/' + normalized
    expected_path = 'cases/' + court + '/' + year + '/' + normalized + '.md'
    if (not normalized or case_id != fm.get('id') or case_id != expected_id
            or name != expected_path or case.get('decision_date') != fm.get('decided')
            or case.get('case_source_url') !=
            'https://www.law.go.kr/LSW/precInfoP.do?precSeq=' + str(fm.get('precSeq'))):
        raise ValueError('Historical case document identity/path mismatch.')
    return fm


def version_reference(ident, index, read_versions):
    """Resolve catalog identity only; never infer articles or applicability."""
    if not isinstance(ident, str) or not re.fullmatch(r'law/\d{6}@\d+', ident):
        raise ValueError('Expected a complete version ID, without an article.')
    lid, seq = ident[4:].split('@')
    law = index.get('laws', {}).get(lid)
    result = dict(id=ident, catalog_status='unavailable', versions_file=None,
                  metadata_sha256=None, entries=[], article_text_status='unavailable',
                  applicability_status='unverified',
                  unavailable_reason='law-id-absent-from-pinned-index')
    if not law:
        return result
    name = law.get('versions_file')
    result['versions_file'] = name
    if not name:
        result['unavailable_reason'] = 'versions-file-absent-from-pinned-index'
        if str(law.get('current', {}).get('lsiSeq')) == seq:
            result['catalog_status'] = 'verified-current-index'
            result['unavailable_reason'] = None
        return result
    if (not isinstance(name, str) or not re.fullmatch(
            r'sources/laws/[a-z0-9-]+/versions/[a-zA-Z0-9_-]+\.json', name)):
        raise ValueError('Unsafe versions metadata path.')
    raw = read_versions(name)
    metadata = readjson(raw)
    if not isinstance(metadata, dict) or not isinstance(metadata.get('versions'), list):
        raise ValueError('Invalid versions metadata.')
    if str(metadata.get('lsId')) != lid:
        raise ValueError('Versions metadata law identity mismatch.')
    rows = metadata['versions']
    if any(not isinstance(row, dict) or not re.fullmatch(r'\d+', str(row.get('lsiSeq', '')))
           for row in rows):
        raise ValueError('Invalid version identity.')
    result['metadata_sha256'] = sha(raw)
    # Multiple effective dates for one lsiSeq must all survive.
    result['entries'] = [{key: row[key] for key in
                          ('lsiSeq', 'efYd', 'ancYd', 'ancNo', 'name', 'kind', 'status')
                          if key in row} for row in rows if str(row['lsiSeq']) == seq]
    if result['entries']:
        result['catalog_status'] = 'verified-version-list'
    elif str(law.get('current', {}).get('lsiSeq')) == seq:
        result['catalog_status'] = 'verified-current-index'
    result['unavailable_reason'] = (None if result['catalog_status'] != 'unavailable'
                                    else 'sequence-absent-from-pinned-version-list')
    return result


def build_catalog(read_bytes, index, commit, read_versions):
    """Derive a non-publication catalog from stored research, without network."""
    raw = read_bytes(EVIDENCE)
    research = readjson(raw)
    records = []
    for item in research['items']:
        key = item['item']
        if key.startswith('faq/'):
            sid = key.split('/')[1]
            if not re.fullmatch(r'\d+', sid):
                raise ValueError('Invalid FAQ source identity.')
            source_date(item['replied'])
            detail = 'https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=' + sid
            links = [e for e in item['evidence'] if e.get('epUnionSn')]
            if len(links) != 1 or not item.get('full_reply'):
                raise ValueError('FAQ evidence incomplete.')
            link = links[0]
            ep = link['epUnionSn']
            expected_link = ('https://www.epeople.go.kr/nep/pttn/gnrlPttn/'
                             'pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=' + ep)
            if (not re.fullmatch(r'\d+', ep) or link['url'] != detail
                    or link['source_link'] != expected_link):
                raise ValueError('FAQ source link mismatch.')
            record = dict(id='faq/molit/lawgo/' + sid, kind='faq', agency='molit',
                          material_type='administrative-faq', case_no='',
                          source_id=sid, source_url=detail, upstream_url=expected_link,
                          source_identifiers={'lawgo': sid, 'epUnionSn': ep},
                          title=item['source_title'], asserted_replied=item['replied'],
                          progress='candidate', reference_status='unreviewed',
                          publication_hold=True, source_envelope_status='unavailable',
                          reply_sha256=sha(item['full_reply'].encode('utf-8')),
                          limitations=research['limitations'][1:])
        elif key.startswith('토지정책과-'):
            if key not in IDENTITY_SOURCES:
                raise ValueError('Unknown held identity.')
            assertions = []
            for e in item['evidence']:
                source_date(e['date'])
                if e['case_no'] != key or not re.fullmatch(r'\d+', e['source_id']):
                    raise ValueError('Identity assertion mismatch.')
                upstream_id = IDENTITY_SOURCES[key].get(e['source_id'])
                expected_law = ('https://www.law.go.kr/LSW/cgmExpcInfoR.do?'
                                'cgmExpcDatSeq=' + e['source_id'])
                expected_upstream = ('https://www.laiis.go.kr/lips/nya/lrn/'
                                     'localRegulationDetail.do?nttNo=' + str(upstream_id))
                if (upstream_id is None or e['law_url'] != expected_law
                        or e['upstream_url'] != expected_upstream):
                    raise ValueError('Identity source/upstream link mismatch.')
                assertions.append(dict(source_id=e['source_id'], asserted_replied=e['date'],
                                       source_url=e['law_url'], upstream_url=e['upstream_url'],
                                       citation=e['exact_citation'], title=e['title'],
                                       reply_sha256=sha(e['reply'].encode('utf-8'))))
                assertions[-1]['provenance'] = {field: ('machine' if field == 'reply_sha256'
                                                       else 'source') for field in assertions[-1]}
            if len(assertions) != 2 or len({e['source_id'] for e in assertions}) != 2:
                raise ValueError('Identity hold requires two distinct source assertions.')
            record = dict(id='identity-hold/molit/' + key, kind='identity-hold',
                          agency='molit', case_no=key, identity_status='unresolved',
                          existing_document_id='interp/molit/' + key,
                          publication_hold=True, assertions=assertions,
                          limitations=research['limitations'][:1])
        else:
            continue
        record.update(evidence_file=EVIDENCE, evidence_sha256=sha(raw),
                      evidence_item=key, evidence_basis='stored-pilot-research')
        record['provenance'] = {field: ('analysis' if field == 'limitations' else
            'source' if field in {'title', 'asserted_replied', 'upstream_url'}
            or field == 'case_no' and record['kind'] == 'identity-hold'
            else 'machine') for field in record}
        records.append(record)
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Duplicate material identity.')
    if {r['case_no'] for r in records if r['kind'] == 'identity-hold'} != set(IDENTITY_SOURCES):
        raise ValueError('Required held identity research items missing.')
    historical_raw = read_bytes(HISTORY)
    historical = readjson(historical_raw)
    versions = []
    sequence_laws = {}
    for law in historical['laws'].values():
        for assertion in law['versions']:
            ident = 'law/' + law['lsId'] + '@' + assertion['lsiSeq']
            sequence_laws.setdefault(assertion['lsiSeq'], set()).add(law['lsId'])
            resolved = version_reference(ident, index, read_versions)
            resolved.update(source_assertion={k: assertion[k] for k in
                            ('lsiSeq', 'efYd', 'ancYd', 'ancNo', 'kind', 'source_url')
                            if k in assertion}, evidence_file=HISTORY,
                            evidence_sha256=sha(historical_raw))
            versions.append(resolved)
    annotations = []
    for case_id, case in historical['cases'].items():
        historical_case(case_id, case, read_bytes)
        provisions = [case] + case.get('additional_provisions', [])
        for provision in provisions:
            seq = provision.get('lsiSeq')
            lids = sequence_laws.get(seq, set())
            version_id = 'law/' + next(iter(lids)) + '@' + seq if len(lids) == 1 else None
            annotations.append(dict(case_id=case_id,
                provision_label=provision['provision'], asserted_lsiSeq=seq,
                asserted_version_id=version_id, asserted_effective_date=provision.get('efYd'),
                applicable_date=provision.get('date_used'), date_basis=provision.get('date_basis'),
                source_url=provision.get('source_url'),
                article_id=None, article_text_status='unavailable',
                applicability_status='unverified', publication_hold=True,
                evidence_file=HISTORY, evidence_sha256=sha(historical_raw)))
    return dict(schema=1, catalog_type='unpublished-evidence', dependency_commit=commit,
                records=sorted(records, key=lambda r: r['id']),
                historical_versions=versions, historical_case_annotations=annotations,
                historical_gaps=historical['unresolved'])
