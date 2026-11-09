# SPDX-License-Identifier: GPL-3.0-only
"""조문 연결 세 탭의 후보와 성공/zero/failure 실행 기록 수집."""
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_index, now, save_json, staged_files, safe_write_text, run_cli
from secret_scan import redact_diagnostic
import lawweb

def main():
    article = sys.argv[1]
    m = re.fullmatch(r'law/(\d{6})@(\d+)#a(\d+)(?:-(\d+))?', article)
    if not m:
        raise ValueError('article ID 형식 오류')
    law, seq, no, branch = m.groups()
    started = now()
    day = started[:10]
    folder = ROOT / 'runs/article'
    n = 1
    while (folder / f'{day}-{n}.json').exists():
        n += 1
    runid = f'article-{day}-{n}'
    record = dict(id=runid, article=article, started=started, tracks={}, candidate_count=0)
    candidates = {}
    existing = set()
    try:
        try:
            for base in ('cases', 'interpretations'):
                for path in (ROOT / base).rglob('*.md'):
                    from common import frontmatter
                    if path != ROOT / base / 'README.md':
                        fm = frontmatter(path.read_text(encoding='utf-8'))
                        target = 'prec' if base == 'cases' else ('cgmexpc' if 'cgmExpcDatSeq' in fm else 'expc')
                        source_id = fm.get('precSeq', fm.get('cgmExpcDatSeq', fm.get('expcSeq', '')))
                        existing.add((target, str(source_id)))
        except Exception as exc:
            record['tracks']['preflight'] = dict(status='failure', count=0, error=redact_diagnostic(str(exc)))
            raise
        try:
            index, _, _ = load_index()
            if article not in index['articles']:
                raise ValueError('잠금 색인에 조문 없음')
        except Exception as exc:
            record['tracks']['dependency'] = dict(status='failure', count=0, error=redact_diagnostic(str(exc)))
            raise
        ctx = lawweb.context(seq, no.zfill(4), (branch or '0').zfill(2), index['laws'][law]['name'])
        for target in lawweb.ENDPOINTS:
            try:
                rows = lawweb.linked(target, ctx)
                record['tracks'][target] = dict(status='success' if rows else 'zero', count=len(rows))
                for row in rows:
                    ident = (row['target'], row['source_id'])
                    if ident in existing:
                        continue
                    if ident not in candidates:
                        candidates[ident] = dict(row, article=article, found_via=[dict(path='article-linked', article=article, date=day)], source_tabs=[])
                    candidates[ident]['source_tabs'].append(target)
            except Exception as exc:
                record['tracks'][target] = dict(status='failure', count=0, error=redact_diagnostic(str(exc)))
    except Exception as exc:
        if not ({'dependency', 'preflight'} & record['tracks'].keys()):
            record['tracks']['context'] = dict(status='failure', count=0, error=redact_diagnostic(str(exc)))
    dest = ROOT / 'sources/candidates' / (runid + '.jsonl')
    record.update(finished=now(), candidate_count=len(candidates), candidates=dest.relative_to(ROOT).as_posix())
    run_path = folder / f'{day}-{n}.json'
    with staged_files([dest, run_path]) as staged:
        safe_write_text(staged[dest], ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for _, x in sorted(candidates.items())))
        save_json(staged[run_path], record)
    print(redact_diagnostic(json.dumps(record, ensure_ascii=False)))
    return int(any(x['status'] == 'failure' for x in record['tracks'].values()))

if __name__ == '__main__':
    sys.exit(run_cli(main))
