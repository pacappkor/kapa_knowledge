# SPDX-License-Identifier: GPL-3.0-only
"""Populate legacy missing derived fields; never overwrite present source values."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, frontmatter, readjson, canonical, sha, safe_write_text, run_cli
from fetch_material import extract_source_fields


def migrate(root=ROOT):
    updates = {}
    for base in ('cases', 'interpretations'):
        for path in (root / base).rglob('*.md'):
            if path.name == 'README.md':
                continue
            text = path.read_text(encoding='utf-8'); fm = frontmatter(text)
            key = next(key for key in ('precSeq', 'expcSeq', 'cgmExpcDatSeq') if key in fm)
            kind, service = {'precSeq': ('prec', 'PrecService'), 'expcSeq': ('expc', 'ExpcService'), 'cgmExpcDatSeq': ('cgmexpc', 'CgmExpcService')}[key]
            saved = readjson((root / 'sources' / kind / (fm[key] + '.json')).read_text(encoding='utf-8'))
            from validate import source_url_valid
            serial = {'prec': '판례정보일련번호', 'expc': '법령해석례일련번호', 'cgmexpc': '법령해석일련번호'}[kind]
            data = saved['payload']
            if (not isinstance(data, dict) or set(data) != {service} or not isinstance(data[service], dict)
                    or str(data[service].get(serial)) != fm[key] or saved.get('target') != kind
                    or str(saved.get('source_id')) != fm[key] or saved.get('source_url') != fm.get('source_url')
                    or not source_url_valid(saved.get('source_url'), kind, fm[key])
                    or sha(canonical(data, reject_masked=True)) != fm['source_sha256'] or saved['sha256'] != fm['source_sha256']):
                raise ValueError('source migration identity/digest mismatch')
            providers = []
            for candidate_file in (root / 'sources/candidates').glob('*.jsonl'):
                for line in candidate_file.read_text(encoding='utf-8').splitlines():
                    if line.strip():
                        row = readjson(line)
                        if row.get('target') == kind and str(row.get('source_id')) == fm[key]:
                            providers.append(row.get('데이터출처명'))
            expected, _ = extract_source_fields(kind, fm[key], saved['payload'][service], providers)
            changed = False
            for field in ('ref_articles_raw', 'data_source_name'):
                if field in expected and field not in fm:
                    fm[field] = expected[field]
                    fm['provenance'][field] = 'source'
                    changed = True
            if changed:
                updates[path] = '---\n' + ''.join(k + ': ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fm.items()) + '---\n' + text.split('\n---\n', 1)[1]
    for path, text in updates.items():
        safe_write_text(path, text)
    return len(updates)


def main():
    print('missing source fields populated:', migrate())
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
