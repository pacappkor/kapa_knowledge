# SPDX-License-Identifier: GPL-3.0-only
"""Validate article-linked candidates against their machine collection run."""
import re
from common import readjson


def candidate_file(root, path, *, read_text=None):
    read_text = read_text or (lambda path: path.read_text(encoding='utf-8'))
    # Imported lazily so validation and fetching share the same contracts.
    from validate import run_valid, run_path_valid, found_via_valid, nonempty
    match = re.fullmatch(r'article-(\d{4}-\d{2}-\d{2})-(\d+)\.jsonl', path.name)
    if not match:
        raise ValueError('candidate contract: article run filename required')
    day, number = match.groups()
    run_path = root / 'runs/article' / f'{day}-{number}.json'
    run = readjson(read_text(run_path))
    if (not run_valid(run) or not run_path_valid(run_path.relative_to(root), run)
            or run.get('id') != path.stem
            or run.get('candidates') != path.relative_to(root).as_posix()
            or run['started'][:10] != day):
        raise ValueError('candidate contract: associated article run mismatch')
    rows = [readjson(line) for line in read_text(path).splitlines() if line.strip()]
    if len(rows) != run['candidate_count']:
        raise ValueError('candidate contract: run candidate_count mismatch')
    seen, counts = set(), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('candidate contract: object required')
        target, ident = row.get('target'), row.get('source_id')
        tabs = row.get('source_tabs')
        via = row.get('found_via')
        if (target not in {'prec', 'expc', 'cgmexpc'}
                or not isinstance(ident, str) or not re.fullmatch(r'\d+', ident)
                or (target, ident) in seen or row.get('article') != run['article']
                or row.get('found_by') != ['linked-by-center']
                or not isinstance(tabs, list) or tabs != [target]
                or row.get('source_tab', target) != target
                or not found_via_valid(via)
                or via != [dict(path='article-linked', article=run['article'], date=day)]
                or ('데이터출처명' in row and not nonempty(row['데이터출처명']))):
            raise ValueError('candidate contract: identity/discovery fields invalid')
        track = run['tracks'].get(target, {})
        counts[target] = counts.get(target, 0) + 1
        if track.get('status') != 'success' or track.get('count', 0) < counts[target]:
            raise ValueError('candidate contract: successful source track required')
        seen.add((target, ident))
    return rows
