# SPDX-License-Identifier: GPL-3.0-only
"""One-time offline pilot baseline: bind legacy reviews to current verified payloads.

This explicitly cannot establish which payload existed at historical review time.
Existing digests are never overwritten; all files are preflighted before writes.
"""
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, frontmatter, readjson, canonical, sha, safe_write_text, run_cli
from build_review_manifest import build, resolve_commit

PILOT_COMMIT = '0f90463b34127b71af14c7046f7b27660ed9adf7'


def migrate(root=ROOT, *, manifest, repository, commit, relations=False, _expected_commit=PILOT_COMMIT):
    revision = resolve_commit(repository, commit)
    if revision != _expected_commit:
        raise ValueError('migration requires the fixed pilot commit')
    entries = readjson(Path(manifest).read_text(encoding='utf-8'))
    if (not isinstance(entries, list) or not entries
            or any(not isinstance(item, dict) or set(item) != {'id', 'review_sha256'}
                   or not isinstance(item['id'], str) or not item['id'].strip()
                   or not isinstance(item['review_sha256'], str)
                   or not re.fullmatch(r'[0-9a-f]{64}', item['review_sha256']) for item in entries)
            or len({item['id'] for item in entries}) != len(entries)):
        raise ValueError('manifest must contain unique review IDs and pinned content hashes')
    allowed = {item['id']: item['review_sha256'] for item in entries}
    pinned = {item['id']: item['review_sha256'] for item in build(repository, revision, relations=relations)}
    if allowed != pinned:
        raise ValueError('manifest differs from pinned commit reviews')
    seen = set()
    documents = {}
    for base in ('cases', 'interpretations'):
        for path in (root / base).rglob('*.md'):
            if path == root / base / 'README.md':
                continue
            fm = frontmatter(path.read_text(encoding='utf-8'))
            key = next(k for k in ('precSeq', 'expcSeq', 'cgmExpcDatSeq') if k in fm)
            kind = {'precSeq': 'prec', 'expcSeq': 'expc', 'cgmExpcDatSeq': 'cgmexpc'}[key]
            saved = readjson((root / 'sources' / kind / (fm[key] + '.json')).read_text(encoding='utf-8'))
            from validate import source_url_valid
            payload_key, serial = {'prec': ('PrecService', '판례정보일련번호'), 'expc': ('ExpcService', '법령해석례일련번호'), 'cgmexpc': ('CgmExpcService', '법령해석일련번호')}[kind]
            data = saved.get('payload')
            if (saved.get('target') != kind or str(saved.get('source_id')) != fm[key]
                    or saved.get('source_url') != fm.get('source_url')
                    or not source_url_valid(saved.get('source_url'), kind, fm[key])
                    or not isinstance(data, dict) or set(data) != {payload_key}
                    or not isinstance(data[payload_key], dict) or str(data[payload_key].get(serial)) != fm[key]):
                raise ValueError('migration source identity mismatch')
            digest = sha(canonical(data, reject_masked=True))
            if digest != fm['source_sha256'] or digest != saved['sha256']:
                raise ValueError('migration source digest mismatch')
            documents[fm['id']] = digest
    relations_path = root / 'relations/relations.jsonl'
    relations = {}
    if relations_path.exists():
        for line in relations_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            edge = readjson(line)
            from validate import relation_snapshot_valid
            if not relation_snapshot_valid(edge, edge.get('id')) or edge['id'] in relations:
                raise ValueError('migration relation identity mismatch')
            relations[edge['id']] = edge
    updates, count = {}, 0
    for path in sorted((root / 'reviews').glob('[0-9][0-9][0-9][0-9]/*.jsonl')):
        rows = [readjson(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        changed = False
        for row in rows:
            if row.get('id') not in allowed:
                continue
            if row['id'] in seen:
                raise ValueError('duplicate manifest review')
            seen.add(row['id'])
            original = dict(row)
            # Only our own two additive migration fields are excluded on reruns.
            if 'source_sha256' in original and original.get('source_sha256_basis') == 'migrated-baseline':
                original.pop('source_sha256')
                original.pop('source_sha256_basis')
            if sha(canonical(original, reject_masked=True)) != allowed[row['id']]:
                raise ValueError('manifest review content differs from pinned commit')
            owner = row.get('target') if 'reference_status' in row else None
            if row.get('relation_review') == 'confirmed':
                edge = relations.get(row.get('target'), row.get('relation_snapshot'))
                from validate import relation_snapshot_valid
                if not relation_snapshot_valid(edge, row.get('target')):
                    raise ValueError('manifest relation review has no valid source snapshot')
                owner = edge['src']
            if owner not in documents:
                raise ValueError('manifest record is not a source-backed document or confirmed relation review')
            if 'source_sha256' not in row:
                row['source_sha256'] = documents[owner]
                row['source_sha256_basis'] = 'migrated-baseline'
                count += 1
                changed = True
        if changed:
            updates[path] = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows)
    if seen != set(allowed):
        raise ValueError('manifest review missing from export')
    for path, text in updates.items():
        safe_write_text(path, text)
    return count


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--relations', action='store_true')
    args = parser.parse_args(argv)
    print('migrated reviews:', migrate(manifest=args.manifest, repository=args.repository,
                                      commit=args.commit, relations=args.relations))
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
