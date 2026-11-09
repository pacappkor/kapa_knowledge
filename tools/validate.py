# SPDX-License-Identifier: GPL-3.0-only
"""계약·출처·검토·관계·규칙 분리 검증. 오류가 있으면 종료 코드 1."""
import ipaddress
import json
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
from html import unescape
from urllib.parse import unquote, urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, frontmatter, load_index, canonical, sha, relation, readjson as strict_json, source_date, court_slug, check_tracked_links, run_cli, dependency_bytes
import secret_scan
from markdown_context import body, prose as markdown_prose, has_command, command_line
from material_contracts import (CATALOG, EVIDENCE, CATALOG_INPUTS, IDENTITY_DOCUMENTS,
                                build_catalog, version_reference)

PROGRESS = {'candidate', 'source-verified', 'relations-reviewed', 'published'}
STATUS = {'unreviewed', 'current-usable', 'recheck-amendment', 'recheck-relation', 'overruled-confirmed', 'superseded-confirmed', 'historical-only', 'indeterminate'}
TYPES = {'cites', 'interprets', 'applies', 'special-rule-of', 'cites-case', 'overrules', 'distinguishes', 'conflict-candidate', 'recheck-due-to', 'same-provision'}
PATTERN = r'(?:law/\d{6}(?:@\d+(?:#a\d+(?:-\d+)?)?)?|apps@\d+#[\w.\-]+|skill/[a-z0-9-]+|case/[^/\s]+/[^\s`"<>]+|interp/[a-z0-9-]+/[^\s`"<>]+|issue/[a-z0-9-]+)'
def inline_link_targets(text):
    """Read inline link/image destinations with CommonMark destination syntax."""
    # Match balanced label brackets (including images and escaped brackets).
    openings, destinations = [], []
    pos = 0
    while pos < len(text):
        if text[pos] == '\\':
            pos += 2
            continue
        if text[pos] == '[':
            openings.append(pos)
        elif text[pos] == ']' and openings:
            openings.pop()
            if text[pos + 1:pos + 2] == '(':
                destinations.append(pos + 2)
        pos += 1
    for offset in destinations:
        start = pos = offset
        while pos < len(text) and text[pos].isspace():
            pos += 1
        start = pos
        if pos >= len(text): continue
        if text[pos] == '<':
            start = pos = pos + 1
            while pos < len(text):
                if text[pos] == '\\' and pos + 1 < len(text):
                    pos += 2
                    continue
                if text[pos] in '<\n\r': break
                if text[pos] == '>': break
                pos += 1
            if pos >= len(text) or text[pos] != '>': continue
            end = pos
            pos += 1
        else:
            depth = 0
            while pos < len(text):
                char = text[pos]
                if char == '\\' and pos + 1 < len(text) and text[pos + 1] in r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~':
                    pos += 2
                    continue
                if char.isspace() or ord(char) < 32: break
                if char == '(':
                    depth += 1
                elif char == ')':
                    if not depth: break
                    depth -= 1
                pos += 1
            if depth: continue
            end = pos
        # A destination must end at the link's closing delimiter, optionally
        # followed by whitespace and a CommonMark title.
        tail = text[pos:]
        if not re.match(r'''^(?:\s+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^()\\])*\)))?\s*\)''', tail):
            continue
        destination = re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', text[start:end])
        yield unescape(destination)


def link_targets(text, undefined=None):
    """Scan prose links and reference definitions, never code examples."""
    text = markdown_prose(text)
    definitions = {}
    normalize = lambda label: ' '.join(label.split()).casefold()
    definition = re.compile(r'^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$', re.M)
    for match in definition.finditer(text):
        targets = list(inline_link_targets('[ref](' + match[2] + ')'))
        if targets:
            definitions.setdefault(normalize(match[1]), targets[0])
            yield targets[0]
    text = definition.sub('', text)
    yield from inline_link_targets(text)
    for match in re.finditer(r'(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]|!\[([^\]\n]*)\]\[([^\]\n]+)\]', text):
        label = normalize((match[2] or match[1]) if match[1] is not None else match[4])
        if label not in definitions and undefined is not None:
            undefined.append(label)
    # Collapsed and shortcut references whose labels are defined are links too;
    # definitions have already had their destinations validated above.


def local_link_valid(root, path, target):
    local = unquote(target.split('#', 1)[0].split('?', 1)[0]).replace('\\', '/')
    base = root if local.startswith('/') else path.parent
    candidate = (base / local.lstrip('/') if local.startswith('/') else base / local).resolve()
    return candidate.is_relative_to(root.resolve()) and candidate.exists()


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('중복 JSON 키: ' + k)
        result[k] = v
    return result

def nonempty(value):
    return isinstance(value, str) and bool(value.strip())

def iso_timestamp(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}T', value): return False
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError: return False

def https_url(value):
    if not nonempty(value) or re.search(r'\s|[\\\x00-\x1f\x7f]', value): return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        parsed.port  # Force validation of malformed and out-of-range ports.
        if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None:
            return False
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            labels = host.split('.')
            return (len(host) <= 253 and len(labels) >= 2 and all(
                re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                for label in labels))
    except ValueError: return False

SOURCE_PATHS = {
    'prec': {'/DRF/lawService.do', '/DRF/lawSearch.do', '/LSW/precInfoP.do'},
    'expc': {'/DRF/lawService.do', '/DRF/lawSearch.do', '/LSW/expcInfoP.do'},
    'cgmexpc': {'/DRF/lawService.do', '/DRF/lawSearch.do', '/LSW/cgmExpcInfoP.do', '/LSW/cgmExpcInfoR.do'},
}


def source_url_valid(value, kind, source_id):
    if not https_url(value) or not re.fullmatch(r'\d+', str(source_id)): return False
    parsed = urlsplit(value)
    if not (parsed.netloc in {'law.go.kr', 'www.law.go.kr'}
            and parsed.path in SOURCE_PATHS.get(kind, set()) and not parsed.fragment):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(key.lower() == 'oc' and (key != 'OC' or values != ['***']) for key, values in query.items()):
        return False
    if any(len(values) != 1 for values in query.values()): return False
    if parsed.path.startswith('/DRF/'):
        if set(query) - {'target', 'ID', 'type', 'OC'}: return False
        targets = {'prec': {'prec'}, 'expc': {'expc'}, 'cgmexpc': {'cgmexpc', 'molitCgmExpc'}}
        return (len(query.get('target', [])) == 1 and query['target'][0] in targets[kind]
                and query.get('ID') == [str(source_id)])
    key = {'prec': 'precSeq', 'expc': 'expcSeq', 'cgmexpc': 'cgmExpcDatSeq'}[kind]
    return not (set(query) - {key, 'mode', 'ofiClsCd', 'efYd', 'OC'}) and query.get(key) == [str(source_id)]


def source_envelope_valid(saved, kind, source_id):
    if (not isinstance(saved, dict) or saved.get('target') != kind
            or str(saved.get('source_id')) != str(source_id)
            or not source_url_valid(saved.get('source_url'), kind, source_id)
            or not iso_timestamp(saved.get('fetched'))):
        return False
    service, serial = {'prec': ('PrecService', '판례정보일련번호'), 'expc': ('ExpcService', '법령해석례일련번호'), 'cgmexpc': ('CgmExpcService', '법령해석일련번호')}[kind]
    data = saved.get('payload')
    if (not isinstance(data, dict) or set(data) != {service}
            or not isinstance(data[service], dict) or str(data[service].get(serial)) != str(source_id)):
        return False
    try:
        return saved.get('sha256') == sha(canonical(data, reject_masked=True))
    except (ValueError, TypeError):
        return False


def endpoint_kind(value):
    if re.fullmatch(r'law/\d{6}@\d+#a\d+(?:-\d+)?', value): return 'article'
    if value.startswith('law/'): return 'law'
    if value.startswith('apps@'): return 'standard'
    return value.split('/', 1)[0]


LEGAL = {'article', 'standard'}
MATERIAL = {'case', 'interp'}
ALL_KINDS = LEGAL | MATERIAL | {'law', 'issue', 'skill'}
ENDPOINTS = {
    'cites': {(src, dst) for src in ALL_KINDS for dst in ALL_KINDS},
    'interprets': {('interp', 'article')},
    'applies': {('case', 'article')},
    'special-rule-of': {(src, dst) for src in LEGAL for dst in LEGAL},
    'cites-case': {('case', 'case')},
    'overrules': {('case', 'case')},
    'distinguishes': {('case', 'case')},
    'conflict-candidate': {(src, dst) for src in MATERIAL | LEGAL for dst in MATERIAL | LEGAL},
    'recheck-due-to': {(src, dst) for src in MATERIAL | {'issue'} for dst in MATERIAL | LEGAL | {'law'}},
    'same-provision': {('article', 'article')},
}

def evidence_valid(value):
    return (isinstance(value, dict) and https_url(value.get('source'))
            and nonempty(value.get('quote')))

RELATION_REVIEW = {'unreviewed', 'confirmed', 'rejected', 'needs-review'}


def relation_snapshot_valid(snapshot, target):
    return (isinstance(snapshot, dict)
            and all(isinstance(snapshot.get(key), str) for key in ('type', 'src', 'dst', 'scope'))
            and snapshot['type'] in TYPES
            and bool(re.fullmatch(PATTERN, snapshot['src']))
            and bool(re.fullmatch(PATTERN, snapshot['dst']))
            and relation(snapshot['type'], snapshot['src'], snapshot['dst'], snapshot['scope'])['id'] == target)


def review_valid(row):
    return (all(nonempty(row.get(k)) for k in ('id', 'target', 'reviewer_model'))
            and bool(re.fullmatch(PATTERN + r'|rel-[0-9a-f]{20}', row['target']))
            and iso_timestamp(row.get('reviewed_at')) and evidence_valid(row.get('evidence'))
            and row.get('decision') in ('accept', 'reject', 'needs-review')
            and ('reference_status' not in row or isinstance(row['reference_status'], str) and row['reference_status'] in STATUS)
            and ('reference_status' not in row or row['target'].startswith('issue/') or isinstance(row.get('source_sha256'), str) and bool(re.fullmatch(r'[0-9a-f]{64}', row['source_sha256'])))
            and ('source_sha256' not in row or isinstance(row['source_sha256'], str) and bool(re.fullmatch(r'[0-9a-f]{64}', row['source_sha256'])))
            and ('source_sha256_basis' not in row or nonempty(row['source_sha256_basis']))
            and ('relation_snapshot' not in row or relation_snapshot_valid(row['relation_snapshot'], row['target']))
            and ('relation_review' not in row or isinstance(row['relation_review'], str) and row['relation_review'] in RELATION_REVIEW))


def found_via_valid(value):
    if not isinstance(value, list) or not value: return False
    for entry in value:
        if not isinstance(entry, dict) or not nonempty(entry.get('path')): return False
        day = entry.get('date')
        if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day): return False
        try: datetime.strptime(day, '%Y-%m-%d')
        except ValueError: return False
        if not any(key in entry for key in ('query', 'article')): return False
        if any(not nonempty(entry[key]) for key in ('query', 'article') if key in entry): return False
    return True

def run_valid(row, supplemental=False):
    if not isinstance(row, dict) or not row:
        return False
    timed = all(iso_timestamp(row.get(key)) for key in ('started', 'finished'))
    if timed and (datetime.fromisoformat(row['finished'].replace('Z', '+00:00'))
                  < datetime.fromisoformat(row['started'].replace('Z', '+00:00'))):
        return False
    if not timed:
        if not supplemental or any(key in row for key in ('started', 'finished')):
            return False
        # Supplemental research/validation snapshots are not collection runs.
        dated = nonempty(row.get('date', row.get('integrated_on')))
        if not (dated or {'laws', 'cases', 'method', 'unresolved'} <= row.keys()
                or all(re.fullmatch(r'\d+', key) and isinstance(value, dict)
                       and nonempty(value.get('decision')) and nonempty(value.get('reason'))
                       for key, value in row.items())):
            return False
    if 'status' in row and row['status'] not in ('success', 'zero', 'failure'):
        return False
    if 'counts' in row and (not isinstance(row['counts'], dict) or
            any(type(value) is not int or value < 0 for value in row['counts'].values())):
        return False
    tracks = row.get('tracks', {} if supplemental else None)
    if supplemental and isinstance(tracks, list):
        if not all(isinstance(track, dict) and nonempty(track.get('query'))
                   and track.get('status') in ('success', 'zero', 'failure')
                   and ('count' not in track or type(track['count']) is int and track['count'] >= 0)
                   for track in tracks):
            return False
        tracks = {}
    if not isinstance(tracks, dict) or not tracks and not supplemental:
        return False
    for name, track in tracks.items():
        if (not nonempty(name) or not isinstance(track, dict)
                or track.get('status') not in ('success', 'zero', 'failure')
                or type(track.get('count')) is not int or track['count'] < 0):
            return False
        if (track['status'] == 'zero' and track['count'] != 0
                or not supplemental and track['status'] == 'success' and track['count'] == 0):
            return False
        # Historical research tracks count attempted versions even on failure;
        # detailed errors can be recorded in the versions array.
        if not supplemental and track['status'] == 'failure' and not nonempty(track.get('error')):
            return False
    if any(type(row[key]) is not int or row[key] < 0 for key in ('candidate_count', 'relations') if key in row):
        return False
    if 'article' in row:
        return (nonempty(row.get('id')) and isinstance(row['article'], str)
                and bool(re.fullmatch(r'law/\d{6}@\d+#a\d+(?:-\d+)?', row['article']))
                and 'candidate_count' in row and nonempty(row.get('candidates')))
    if supplemental:
        return True
    return (row.get('source') in (set(SOURCE_PATHS) | {'molitCgmExpc'})
            and set(tracks) == {row['source']} and nonempty(row.get('query')))


def run_path_valid(path, row):
    """Bind machine run identity to its source directory and started day."""
    if path.parts[:2] == ('runs', 'pilot'):
        return True  # Supplemental records deliberately have legacy names.
    if len(path.parts) != 3 or path.parts[0] != 'runs':
        return False
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})-([1-9]\d*)\.json', path.name)
    if not match or match[1] != row.get('started', '')[:10]:
        return False
    source = 'article' if 'article' in row else row.get('source')
    if path.parts[1] != source:
        return False
    if source == 'article':
        stem = 'article-' + path.stem
        return (row.get('id') == stem
                and row.get('candidates') == 'sources/candidates/' + stem + '.jsonl')
    return True


# Field-specific categories; unspecified optional fields retain the four-category enum.
SOURCE_FIELDS = {'court', 'case_no', 'decided', 'kind', 'precSeq', 'agency', 'replied',
                 'requester', 'expcSeq', 'cgmExpcDatSeq', 'title', 'source_url',
                 'source_sha256', 'ref_articles_raw', 'data_source_name', 'change_quote'}
SUMMARY_FIELDS = {'facts_summary', 'summary', 'holding_summary', 'question_summary',
                  'issue_summary', 'analysis'}


def validate(root=ROOT):
    errors, warnings = [], []
    try:
        secret_needles = secret_scan.environment_needles()
    except secret_scan.ScanError as exc:
        return [str(exc)], [], 0
    def diagnostic(msg):
        return secret_scan.redact_diagnostic(msg, secret_needles) if secret_needles else msg
    def err(msg): errors.append(diagnostic(msg))
    # Match the later read set, including non-ignored untracked inputs.
    if secret_needles:
        try:
            for path, encoding in secret_scan.scan(root, worktree=True, needles=secret_needles) or []:
                err(f'{path}: LAW_OC exposure ({encoding})')
        except secret_scan.ScanError as exc:
            err(str(exc))
        if errors:
            return errors, warnings, 0
    try:
        git_root, tracked = secret_scan.repository_files(root)
        tracked = set(tracked) if git_root.resolve() == root.resolve() else set()
        _, selected = secret_scan.repository_files(root, worktree=True)
        selected = set(selected) if git_root.resolve() == root.resolve() else None
    except secret_scan.ScanError:
        tracked, selected = set(), None  # Non-Git contract fixtures.
    if selected is not None:
        try:
            check_tracked_links(root)
        except ValueError as exc:
            err(str(exc))
        if errors:
            return errors, warnings, 0
    validation_paths = ([root / name for name in sorted(selected)] if selected is not None
                        else list(root.rglob('*')))
    secret_exposure = False
    def inspect_input(path, data):
        nonlocal secret_exposure
        if not secret_needles:
            return
        relative = path.relative_to(root) if path.is_relative_to(root) else None
        path_encodings = (list(secret_scan.matching_encodings(os.fsencode(relative), secret_needles))
                          if relative is not None else [])
        encodings = path_encodings + list(secret_scan.matching_encodings(data, secret_needles))
        if encodings:
            safe_path = ('[redacted path]' if path_encodings else
                         ascii(relative.as_posix()) if relative is not None else '[external input]')
            err(f'{safe_path}: LAW_OC exposure ({encodings[0]})')
            secret_exposure = True
            raise secret_scan.ScanError('Credential-bearing input was not parsed.')
    def read_input_bytes(path):
        if path.is_relative_to(root):
            rel = path.relative_to(root).as_posix()
            if (selected is not None and rel not in selected
                    or path.is_symlink() or not path.resolve().is_relative_to(root.resolve())):
                raise ValueError('Input outside validation file selection; not read.')
        data = path.read_bytes()
        inspect_input(path, data)
        return data
    def readtext(path):
        try:
            return read_input_bytes(path).decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
        except secret_scan.ScanError:
            return ''  # inspect_input already recorded a safe exposure error.
        except (UnicodeError, OSError):
            err(f'{path.relative_to(root) if path.is_relative_to(root) else path.name}: UTF-8 text read error')
            return ''
        except ValueError as exc:
            err(str(exc))
            return ''
    def readjson(path):
        return strict_json(readtext(path))
    def candidate_text(path):
        before = len(errors)
        text = readtext(path)
        if len(errors) != before:
            raise ValueError('candidate contract: input read error')
        return text
    index, sibling, commit = {}, None, None
    try:
        index, sibling, commit = load_index(root, read_text=readtext, inspect_bytes=inspect_input,
                                            read_bytes=read_input_bytes)
        if commit == 'WORKTREE': warnings.append('deps.lock: WORKTREE 개발 상태; PR 전에 실제 SHA 고정 필요')
    except Exception as exc: err(str(exc))
    if secret_exposure:
        return errors, [], 0
    literal_warning = False
    docs, reviews, rels = {}, [], []
    source_relation_sets = {}
    material_records = []
    selected_names = {path.relative_to(root).as_posix() for path in validation_paths}
    def require_material_catalog():
        missing = CATALOG_INPUTS - selected_names
        if missing:
            err('catalogs/materials.json: affected material requires its held material catalog and inputs: '
                + ', '.join(sorted(missing)))
    if CATALOG_INPUTS & selected_names:
        require_material_catalog()
    command_checks, canonical_sources = [], set()
    for path in validation_paths:
        if '.git' in path.parts or '__pycache__' in path.parts or path.is_symlink() or not path.is_file(): continue
        rel = path.relative_to(root).as_posix()
        raw_text = readtext(path)
        if secret_exposure:
            return errors, [], 0
        if '\x00' in raw_text:
            err(f'{rel}: UTF-8 text contains NUL bytes')
        if not literal_warning and rel in tracked and re.search(
                r'''(?m)^\s*["']?(?:OC|LAW_OC)["']?\s*[:=]\s*(["'])[^"'\r\n]{8,}\1''', raw_text):
            warnings.append(f'{rel}: quoted OC/LAW_OC literal; run value-based credential scan')
            literal_warning = True
        parts = path.relative_to(root).parts
        source_kind = parts[1] if len(parts) >= 3 and parts[0] == 'sources' and parts[1] in SOURCE_PATHS else None
        if source_kind and (len(parts) != 3 or path.suffix != '.json' or not re.fullmatch(r'\d+', path.stem)):
            err(f'{rel}: source envelope path error')
        if path.suffix == '.json' or path.name == 'deps.lock':
            try:
                saved = readjson(path)
                if rel == CATALOG:
                    def catalog_read(name):
                        from common import check_output_path
                        check_output_path(root / name, root=root, require_exists=True)
                        return read_input_bytes(root / name)
                    def catalog_versions(name):
                        return dependency_bytes(root, sibling, commit, name,
                                                inspect_bytes=inspect_input, read_bytes=read_input_bytes)
                    if commit == 'WORKTREE':
                        raise ValueError('Material catalog requires a pinned dependency commit.')
                    expected = build_catalog(catalog_read, index, commit, catalog_versions)
                    material_records = expected['records']
                    if saved != expected:
                        err('catalogs/materials.json: derived catalog mismatch; identity/provenance/hold changed')
                if rel.startswith('runs/'):
                    if (not run_valid(saved, supplemental=rel.startswith('runs/pilot/'))
                            or not run_path_valid(Path(rel), saved)):
                        err(f'{rel}: run contract error (path/source/date/identity)')
                    elif not rel.startswith('runs/pilot/') and 'article' in saved:
                        from candidates import candidate_file
                        try:
                            # Canonical path is already bound above; even zero
                            # runs must retain their empty candidate artifact.
                            candidate_file(root, root / saved['candidates'], read_text=candidate_text)
                        except Exception as exc:
                            err(f'{rel}: candidate contract error: {exc}')
                if source_kind and not source_envelope_valid(saved, source_kind, path.stem):
                    err(f'{rel}: source envelope contract error (원본 source_url/identity/digest/fetched)')
            except Exception as exc: err(f'{rel}: {exc}')
        if path.suffix == '.jsonl':
            if rel.startswith('sources/candidates/'):
                try:
                    from candidates import candidate_file
                    candidates = candidate_file(root, path, read_text=candidate_text)
                    if index and any(row['article'] not in index.get('articles', {}) for row in candidates):
                        err(f'{rel}: candidate article missing from pinned index')
                except Exception as exc:
                    err(f'{rel}: candidate contract error: {exc}')
            for n, line in enumerate(readtext(path).splitlines(), 1):
                if not line.strip(): continue
                try:
                    row = strict_json(line)
                    if not isinstance(row, dict): raise ValueError('객체 아님')
                    if rel.startswith('reviews/'):
                        if not re.fullmatch(r'reviews/\d{4}/[^/]+\.jsonl', rel):
                            err(f'{rel}: 검토 기록은 reviews/YYYY/*.jsonl만 허용')
                        elif not iso_timestamp(row.get('reviewed_at')) or row['reviewed_at'][:4] != path.parent.name:
                            err(f'{rel}: 검토 필드 유형/ISO 시각 또는 review directory year mismatch')
                        else:
                            reviews.append(row)
                    elif rel == 'relations/relations.jsonl': rels.append(row)
                except Exception as exc: err(f'{rel}:{n}: {exc}')
        if path.suffix != '.md': continue
        text = readtext(path)
        prose = markdown_prose(text)
        if '~' in prose: err(f'{rel}: 산문 물결 기호; 범위는 – 사용')
        undefined = []
        for target in link_targets(text, undefined):
            if re.match(r'[a-z][a-z0-9+.-]*:', target, re.I) or target.startswith(('#', '//')): continue
            if not local_link_valid(root, path, target): err(f'{rel}: 깨진 상대 링크 {target}')
        for label in undefined: err(f'{rel}: 정의 없는 참조 링크 {label}')
        command_checks.append((rel, text))
        if (rel.startswith(('cases/', 'interpretations/', 'issues/'))
                and rel not in {'cases/README.md', 'interpretations/README.md', 'issues/README.md'}
                and not (rel.startswith('issues/') and path.name == 'coverage.md')):
            try:
                fm = frontmatter(text)
                required = {'id','title','progress','reference_status','last_reviewed','found_via','provenance'}
                if rel.startswith('cases/'):
                    required |= {'court','case_no','decided','kind','precSeq','source_url','source_sha256','ref_articles_raw','applied_version'}
                    prefix = 'case/'
                elif rel.startswith('interpretations/'):
                    required |= {'agency','case_no','replied','requester','source_url','source_sha256','applied_version','facts_summary'}
                    prefix = 'interp/'
                else:
                    prefix = 'issue/'
                    required |= {'articles', 'standards', 'skills'}
                    for key, pattern in {'articles': r'law/\d{6}@\d+#a\d+(?:-\d+)?', 'standards': r'apps@\d+#[\w.\-]+', 'skills': r'skill/[a-z0-9-]+'}.items():
                        value = fm.get(key)
                        if not isinstance(value, list) or any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in value):
                            err(f'{rel}: {key} 계약 ID 배열 오류')
                if missing := required - fm.keys(): err(f'{rel}: 필수 필드 누락 {sorted(missing)}')
                string_fields = required - {'last_reviewed', 'found_via', 'provenance', 'articles', 'standards', 'skills'}
                if not all(isinstance(fm.get(k), str) for k in string_fields):
                    err(f'{rel}: 필수 문자열 필드 유형 오류');continue
                if fm.get('last_reviewed') is not None and not iso_timestamp(fm['last_reviewed']):
                    err(f'{rel}: last_reviewed 유형/시각 오류')
                ident = fm.get('id', '')
                if not isinstance(ident,str) or not ident.startswith(prefix) or not re.fullmatch(PATTERN, ident): err(f'{rel}: ID 형식 오류')
                if ident in docs: err(f'{rel}: 문서 ID 중복 {ident}')
                docs[ident] = (fm,path,text)
                if fm.get('progress') not in PROGRESS: err(f'{rel}: progress 오류')
                if 'relation_recheck' in fm:
                    pending = fm['relation_recheck']
                    if (not isinstance(pending, list) or not pending or any(not isinstance(item, str) or not re.fullmatch(r'rel-[0-9a-f]{20}', item) for item in pending)
                            or fm.get('progress') in {'relations-reviewed', 'published'}):
                        err(f'{rel}: relation_recheck requires pending relation IDs and downgraded progress')
                if fm.get('reference_status') not in STATUS: err(f'{rel}: reference_status 오류')
                if fm.get('reference_status') == 'overruled-confirmed' and prefix != 'case/': err(f'{rel}: overruled-confirmed 판례 전용')
                if fm.get('reference_status') == 'superseded-confirmed' and prefix != 'interp/': err(f'{rel}: superseded-confirmed 해석 전용')
                via = fm.get('found_via')
                if not found_via_valid(via): err(f'{rel}: found_via 형식 오류')
                provenance=fm.get('provenance',{})
                if not isinstance(provenance,dict) or any(not isinstance(v, str) or v not in {'source','summary','analysis','machine'} for v in provenance.values()) or fm.keys() - {'provenance'} - provenance.keys(): err(f'{rel}: 필드 provenance 누락/오류')
                if isinstance(provenance, dict):
                    for field in fm.keys() - {'provenance'}:
                        allowed = {'source', 'machine'} if field in SOURCE_FIELDS else {'summary', 'analysis'} if field in SUMMARY_FIELDS or field.endswith('_summary') else None
                        if allowed and provenance.get(field) not in allowed:
                            err(f'{rel}: field provenance category error: {field}')
                generated_body = body(text)
                begin, end = '<!-- BEGIN GENERATED:source -->', '<!-- END GENERATED:source -->'
                if prefix == 'issue/':
                    if begin in generated_body or end in generated_body:
                        err(f'{rel}: issue sections are manual; GENERATED markers forbidden')
                elif generated_body.count(begin) != 1 or generated_body.count(end) != 1 or generated_body.index(begin) >= generated_body.index(end): err(f'{rel}: GENERATED 경계 오류')
                if prefix=='case/' and ident != 'case/'+court_slug(str(fm.get('court')))+'/'+re.sub(r'\s+','',str(fm.get('case_no'))): err(f'{rel}: 판례 ID와 사건정보 불일치')
                if prefix=='interp/' and ident != 'interp/'+str(fm.get('agency'))+'/'+str(fm.get('case_no')): err(f'{rel}: 해석 ID와 사건정보 불일치')
                if prefix!='issue/':
                    date_key = 'decided' if prefix == 'case/' else 'replied'
                    try:
                        year = str(source_date(fm.get(date_key)).year).zfill(4)
                        owner = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', '_', str(fm.get('court' if prefix == 'case/' else 'agency'))).rstrip('. ')
                        if prefix == 'case/': owner = court_slug(owner)
                        if path.relative_to(root).parts[:-1] != (('cases' if prefix == 'case/' else 'interpretations'), owner, year):
                            err(f'{rel}: 자료 디렉터리와 기관/원문 날짜 불일치')
                    except ValueError: err(f'{rel}: {date_key} 원문 날짜 오류')
                    if prefix == 'interp/' and (sum(key in fm for key in ('expcSeq', 'cgmExpcDatSeq')) != 1 or any(not isinstance(fm[key], str) or not re.fullmatch(r'\d+', fm[key]) for key in ('expcSeq', 'cgmExpcDatSeq') if key in fm)):
                        err(f'{rel}: 해석 일련번호는 숫자 문자열 expcSeq/cgmExpcDatSeq 중 정확히 하나 필요')
                        continue
                    if not re.fullmatch(r'[0-9a-f]{64}', str(fm.get('source_sha256',''))): err(f'{rel}: source_sha256 형식 오류')
                    sourcekind = 'prec' if prefix=='case/' else ('cgmexpc' if 'cgmExpcDatSeq' in fm else 'expc')
                    sourceid = fm.get({'prec': 'precSeq', 'expc': 'expcSeq', 'cgmexpc': 'cgmExpcDatSeq'}[sourcekind])
                    if not source_url_valid(fm.get('source_url'), sourcekind, sourceid): err(f'{rel}: source_url 오류')
                    source = root/'sources'/sourcekind/(str(sourceid)+'.json')
                    if not source.exists(): err(f'{rel}: 원본 없음')
                    else:
                        saved=readjson(source)
                        if saved.get('source_url') != fm.get('source_url') or saved.get('target') != sourcekind or str(saved.get('source_id')) != str(sourceid):
                            err(f'{rel}: 문서와 원본 출처 URL/target/ID 불일치')
                        if not source_url_valid(saved.get('source_url'), sourcekind, sourceid): err(f'{rel}: 원본 source_url 오류')
                        payload_key, serial_key = {'prec': ('PrecService', '판례정보일련번호'), 'expc': ('ExpcService', '법령해석례일련번호'), 'cgmexpc': ('CgmExpcService', '법령해석일련번호')}[sourcekind]
                        data = saved.get('payload')
                        if (not isinstance(data, dict) or set(data) != {payload_key}
                                or not isinstance(data[payload_key], dict)
                                or str(data[payload_key].get(serial_key)) != str(sourceid)
                                or str(data[payload_key].get(serial_key)) != str(saved.get('source_id'))):
                            err(f'{rel}: payload kind/serial identity mismatch')
                            continue
                        digest=sha(canonical(data, reject_masked=True))
                        if digest != fm.get('source_sha256') or digest != saved.get('sha256'): err(f'{rel}: source sha256 mismatch')
                        from fetch_material import render_generated, extract_source_fields, case_source_valid, generated_relations
                        providers = []
                        from candidates import candidate_file
                        for candidate_path in (root / 'sources/candidates').glob('*.jsonl'):
                            if selected is not None and candidate_path.relative_to(root).as_posix() not in selected:
                                continue
                            for candidate in candidate_file(root, candidate_path, read_text=candidate_text):
                                if candidate['target'] == sourcekind and candidate['source_id'] == str(sourceid):
                                    providers.append(candidate.get('데이터출처명'))
                        expected_fields, _ = extract_source_fields(sourcekind, str(sourceid), data[payload_key], providers)
                        expected_fields.update(source_url=saved['source_url'], source_sha256=digest)
                        if sourcekind == 'prec' and not case_source_valid(expected_fields['court'], expected_fields['data_source_name']):
                            err(f'{rel}: case source acceptance policy error')
                        _, regenerated = generated_relations(ident, expected_fields.get('ref_articles_raw', ''), index)
                        # Relations are fully loaded only after the repository scan.
                        source_relation_sets[ident] = {edge['id']: edge for edge in regenerated}
                        for field, expected_value in expected_fields.items():
                            # Match fetch's exact categories; a label change cannot
                            # exempt payload-derived fields from value binding.
                            if field == 'facts_summary':
                                continue  # Manual summary placeholder, not source.
                            category = 'machine' if field in {'id', 'source_url', 'source_sha256'} else 'source'
                            if fm.get(field) != expected_value or fm.get('provenance', {}).get(field) != category:
                                err(f'{rel}: source provenance differs from payload: {field}')
                        payload_key = {'prec': 'PrecService', 'expc': 'ExpcService', 'cgmexpc': 'CgmExpcService'}[sourcekind]
                        block = begin + generated_body.split(begin, 1)[1].split(end, 1)[0] + end
                        expected = render_generated(saved['payload'][payload_key], ident, saved['source_url'],
                                                    source.relative_to(root).as_posix(), digest, index)
                        if block != expected:
                            err(f'{rel}: generated source differs from saved payload (entire block)')
                        elif (source_envelope_valid(saved, sourcekind, sourceid)
                              and digest == fm.get('source_sha256')
                              and generated_body.count(begin) == generated_body.count(end) == 1):
                            canonical_sources.add(rel)
            except Exception as exc: err(f'{rel}: {exc}')
    for rel, text in command_checks:
        if rel in canonical_sources:
            text = re.sub(r'<!-- BEGIN GENERATED:source -->.*?<!-- END GENERATED:source -->', '', text, flags=re.S)
        if rel != 'rules/knowledge-update-maintenance/SKILL.md' and has_command(text):
            err(f'{rel}: 도구 명령은 갱신 스킬에만 둔다')
    skill_paths = [path for path in validation_paths if path.name == 'SKILL.md'
                   and not path.is_symlink() and path.is_file()]
    rule_skills = [path for path in skill_paths if path.relative_to(root).parts[0] == 'rules']
    rule_paths = [p.relative_to(root).as_posix() for p in rule_skills]
    if len(rule_paths) != 2 or set(rule_paths) != {'rules/knowledge-reading-rules/SKILL.md', 'rules/knowledge-update-maintenance/SKILL.md'}:
        err('rules/: 두 스킬 분리 위반')
    for entry in ('AGENTS.md','CLAUDE.md','00-knowledge-start/SKILL.md'):
        entry_path = root / entry
        reading = (root / 'rules/knowledge-reading-rules/SKILL.md').resolve()
        targets = link_targets(readtext(entry_path)) if entry_path.exists() else []
        if not any(not urlsplit(target).scheme and not target.startswith('//') and
                   ((root if target.startswith('/') else entry_path.parent) / unquote(target.split('#', 1)[0]).lstrip('/')).resolve() == reading
                   for target in targets): err(entry+': 읽기 규칙 연결 누락')
    for path in skill_paths:
        try:
            fm=frontmatter(readtext(path))
            if fm.get('name')!=path.parent.name or not 0<len(fm.get('description',''))<=140: err(str(path)+': 스킬 이름/설명 오류')
        except Exception as exc: err(str(path)+': '+str(exc))
    for skill in rule_skills:
        if skill.parent.name == 'knowledge-reading-rules' and re.search(r'^##.*(?:재생성|수집 트랙|검증|기록과 반영)', readtext(skill), re.M):
            err('읽기 규칙에 갱신 작업 절이 있음')
        if skill.parent.name == 'knowledge-update-maintenance':
            text = readtext(skill)
            if 'knowledge-reading-rules/SKILL.md' not in text:
                err('갱신 스킬: 읽기 규칙 범위 밖 연결 누락')
            if re.search(r'^##.*(?:시점과 원문|발견 메모|인용 형식)', text, re.M):
                err('갱신 스킬에 읽기 규칙 절이 있음')
    review_ids=set()
    for row in reviews:
        if not review_valid(row): err('reviews: 검토 필드 유형/증거/판단/ISO 시각 오류')
        if not review_valid(row): continue
        if row.get('id') in review_ids: err('reviews: ID 중복')
        review_ids.add(row.get('id'))
    # Exclude malformed rows before reconciliation; report them without aborting.
    valid_rels = []
    for row in rels:
        missing = {'id','type','src','dst','scope','found_by','review','evidence','reviewed_by','reviewed_at'} - row.keys()
        if missing:
            err('relations: 필수 필드 누락 ' + str(sorted(missing)))
        elif not all(nonempty(row.get(k)) for k in ('id','type','src','dst','review')) or not isinstance(row['scope'], str):
            err('relations: 필수 문자열 필드 유형 오류')
        else:
            valid_rels.append(row)
    rels = valid_rels
    relation_ids = {row['id'] for row in rels}
    accepted_reviews = [row for row in reviews if review_valid(row)
                        and row.get('decision') == 'accept' and 'relation_review' in row]
    missing_reviewed = {row['target'] for row in accepted_reviews} - relation_ids
    removed_by_source = {}
    for rid in missing_reviewed:
        snapshots = [row.get('relation_snapshot') for row in accepted_reviews if row['target'] == rid]
        owners = set()
        for snapshot in snapshots:
            if relation_snapshot_valid(snapshot, rid):
                owners.add(snapshot['src'])
        if len(owners) != 1:
            err(rid + ': missing relation requires original relation_snapshot')
            continue
        owner = owners.pop()
        removed_by_source.setdefault(owner, set()).add(rid)
        if endpoint_kind(owner) not in {'case', 'interp', 'issue'}:
            # External IDs have no local frontmatter. Keep the pending deletion
            # with its original owner in a later explicit review tombstone.
            approvals = [row for row in accepted_reviews if row['target'] == rid]
            latest = max(datetime.fromisoformat(row['reviewed_at'].replace('Z', '+00:00')) for row in approvals)
            if not any(review_valid(row) and row.get('target') == rid
                       and row.get('decision') == row.get('relation_review') == 'needs-review'
                       and relation_snapshot_valid(row.get('relation_snapshot'), rid)
                       and row['relation_snapshot']['src'] == owner
                       and datetime.fromisoformat(row['reviewed_at'].replace('Z', '+00:00')) > latest
                       for row in reviews):
                err(rid + ': missing external relation requires later needs-review tombstone with original relation_snapshot')
        elif owner not in docs or rid not in docs[owner][0].get('relation_recheck', []):
            err(rid + ': accepted relation review targets missing relation without recheck on source document')
        elif docs[owner][0].get('progress') != 'source-verified':
            err(owner + ': removed relations require source-verified progress')
    for ident, (fm, _, _) in docs.items():
        for rid in fm.get('relation_recheck', []):
            if rid in missing_reviewed and rid not in removed_by_source.get(ident, set()):
                err(ident + ': removed relation recheck belongs to another source document')
    for ident, regenerated in source_relation_sets.items():
        fm = docs[ident][0]
        outgoing = [row for row in rels if row.get('src') == ident]
        automatic_rows = {row['id']: row for row in outgoing if row.get('type') == 'cites'
                          and row.get('found_by') == ['cites-article'] and row.get('review') == 'unreviewed'}
        automatic = set(automatic_rows)
        retained = {row['id'] for row in outgoing if row['id'] not in automatic}
        stale = sorted(row['id'] for row in outgoing if row.get('type') == 'cites'
                       and row.get('found_by') == ['cites-article'] and row.get('review') != 'unreviewed'
                       and row['id'] not in regenerated)
        # A documented pending removal may retain a missing accepted relation
        # ID. Existing stale edges must still match regenerated evidence exactly.
        recorded = fm.get('relation_recheck', [])
        recorded_missing = removed_by_source.get(ident, set())
        invalidated = {row['id'] for row in outgoing if row.get('review') == 'needs-review'
                       and any(review['target'] == row['id'] and review.get('relation_review') == 'confirmed'
                               for review in accepted_reviews)}
        expected_pending = sorted(set(stale) | recorded_missing | invalidated)
        if recorded != expected_pending:
            err(ident + ': relation_recheck differs from regenerated evidence')
        expected_automatic = {rid: edge for rid, edge in regenerated.items() if rid not in retained}
        automatic_changed = (automatic != set(expected_automatic)
                             or any(any(row.get(key) != value or key not in row for key, value in expected_automatic[rid].items())
                                    for rid, row in automatic_rows.items() if rid in expected_automatic))
        if automatic_changed:
            err(ident + ': automatic relations differ from regenerated payload/index')
        if (expected_pending or automatic_changed) and fm.get('progress') != 'source-verified':
            err(ident + ': changed automatic relations require source-verified progress')
    seen_prec, seen_case, seen_interp = set(),set(),set()
    for ident,(fm,path,text) in docs.items():
        if ident.startswith('case/'):
            p=str(fm.get('precSeq')); c=(fm.get('court'),re.sub(r'\s+','',str(fm.get('case_no'))))
            if p in seen_prec or c in seen_case: err(ident+': 판례 중복 키')
            seen_prec.add(p);seen_case.add(c)
        if ident.startswith('interp/'):
            k=(fm.get('agency'),fm.get('case_no'))
            if k in seen_interp: err(ident+': 해석 중복 키')
            seen_interp.add(k)
        status=fm.get('reference_status')
        if status != 'unreviewed':
            matches=[r for r in reviews if r.get('target')==ident and r.get('reference_status')==status and r.get('reviewed_at')==fm.get('last_reviewed') and review_valid(r) and r.get('decision') == 'accept' and (ident.startswith('issue/') or r.get('source_sha256') == fm.get('source_sha256'))]
            if not matches: err(ident+': confirmed reference_status에 근거 검토 기록 없음')
            if status in {'overruled-confirmed', 'superseded-confirmed'}:
                key, prefix = ('overruling_id', 'case/') if status == 'overruled-confirmed' else ('superseding_id', 'interp/')
                valid = [r for r in matches if isinstance(r.get(key), str) and r[key].startswith(prefix)
                         and re.fullmatch(PATTERN, r[key]) and r[key] in docs and r[key] != ident
                         and (status != 'overruled-confirmed' or nonempty(r.get('change_quote')))]
                if not valid: err(ident+': 대체/변경 자료 ID 유형·존재·근거 확인 불가')
    if IDENTITY_DOCUMENTS & docs.keys():
        require_material_catalog()
    # This guard survives deletion of both research and generated catalog.
    for ident in IDENTITY_DOCUMENTS & docs.keys():
        if docs[ident][0].get('progress') == 'published':
            err('identity hold: unresolved source identity prevents publication ' + ident)
    for held in material_records:
        if held['kind'] == 'identity-hold':
            ident = held['existing_document_id']
            if ident not in docs:
                err('identity hold: existing document missing ' + ident)
    def reference(ident):
        if not isinstance(ident, str) or not re.fullmatch(PATTERN,ident): err('참조 ID 형식 오류: '+str(ident));return
        if ident.startswith(('case/','interp/','issue/')):
            if ident not in docs: err('대상 문서 없음: '+ident)
        elif index:
            if ident.startswith('law/'):
                if '#a' in ident: ok=ident in index.get('articles',{})
                elif '@' not in ident: ok=ident[4:] in index.get('laws',{})
                else:
                    def read_versions(name):
                        if commit == 'WORKTREE':
                            return read_input_bytes(sibling / name)
                        return dependency_bytes(root, sibling, commit, name,
                                                inspect_bytes=inspect_input, read_bytes=read_input_bytes)
                    try:
                        ok = version_reference(ident, index, read_versions)['catalog_status'] != 'unavailable'
                    except Exception:
                        ok = False
                if not ok: err('검증 불가: 색인/판본에 참조 없음 '+ident)
            elif ident.startswith('apps@') and ident not in index.get('standards',{}): err('실무기준 참조 없음: '+ident)
            elif ident.startswith('skill/'):
                name=ident[6:]
                # 계약 색인에 수록된 skill 경로에서 이름을 확인한다.
                skills={Path(v.get('skill','')).parent.name for table in ('articles','standards') for v in index.get(table,{}).values()}
                if name not in skills: err('검증 불가: 색인에 skill 없음 '+ident)
    for ident,(fm,path,text) in docs.items():
        if ident.startswith(('case/', 'interp/')):
            version = fm.get('applied_version')
            if not isinstance(version, str) or (version != 'unknown' and not re.fullmatch(r'law/\d{6}@\d+', version)):
                err(ident+': applied_version 형식 오류')
        for key in ('articles', 'standards', 'skills', 'applied_version', 'overruling_id', 'superseding_id'):
            value = fm.get(key, [])
            for ref in value if isinstance(value, list) else [value]:
                if ref != 'unknown': reference(ref)
        for via in fm.get('found_via', []):
            if isinstance(via, dict) and 'article' in via: reference(via['article'])
        for ref in re.findall(r'`('+PATTERN+r')`',text): reference(ref)
    ids=set()
    for row in rels:
        if row['id'] in ids: err('relations: ID 중복')
        ids.add(row['id'])
        if row['type'] not in TYPES: err('relations: type 오류')
        if row['id']!=relation(row['type'],row['src'],row['dst'],row['scope'])['id']: err('relations: 결정적 ID 불일치')
        if row['review'] not in {'unreviewed','confirmed','rejected','needs-review'}: err('relations: review 오류')
        if row['review'] == 'confirmed' and row['src'] == row['dst']:
            err('relations: confirmed 자기참조 관계 금지')
        if not isinstance(row['found_by'],list) or not row['found_by'] or any(not isinstance(v, str) for v in row['found_by']) or set(row['found_by'])-{'linked-by-center','cites-article','cites-case','manual'}: err('relations: found_by 오류')
        if row['review']=='confirmed' and not (evidence_valid(row['evidence']) and nonempty(row['reviewed_by']) and iso_timestamp(row['reviewed_at'])): err('relations: confirmed 관계 증거/검토 누락 (overrules/distinguishes 포함)')
        if row['review'] == 'confirmed' and not any(
            r.get('target') == row['id'] and r.get('relation_review') == 'confirmed'
            and r.get('reviewer_model') == row['reviewed_by'] and r.get('reviewed_at') == row['reviewed_at']
            and review_valid(r) and r.get('decision') == 'accept'
            and r.get('evidence') == row['evidence']
            and (endpoint_kind(row['src']) not in MATERIAL
                 or row['src'] in docs and r.get('source_sha256') == docs[row['src']][0].get('source_sha256'))
            for r in reviews):
            err('relations: confirmed 관계에 일치하는 relation_review 기록 없음 (source_sha256 포함)')
        if row['type'] in ENDPOINTS and (endpoint_kind(row['src']), endpoint_kind(row['dst'])) not in ENDPOINTS[row['type']]:
            err('relations: 끝점 계약 오류 '+row['type'])
        reference(row['src']);reference(row['dst'])
    return errors, [diagnostic(msg) for msg in warnings], len(docs)

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-links', action='store_true', help='only inspect tracked symlink and gitlink modes before maintenance writes')
    args = parser.parse_args()
    if args.check_links:
        try:
            check_tracked_links(ROOT)
        except ValueError as exc:
            print('ERROR', exc)
            return 1
        print('tracked symlinks: 0; tracked gitlinks: 0')
        return 0
    errors,warnings,count=validate()
    for w in warnings:print('WARNING',w)
    for e in errors:print('ERROR',e)
    print(f'documents: {count}  errors: {len(errors)}  warnings: {len(warnings)}')
    return int(bool(errors))

if __name__=='__main__':sys.exit(run_cli(main))
