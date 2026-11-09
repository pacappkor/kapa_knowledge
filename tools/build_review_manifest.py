# SPDX-License-Identifier: GPL-3.0-only
"""Build legacy review IDs and canonical content hashes from a pinned local commit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_read import run_git
from common import readjson, canonical, sha, check_output_path, safe_write_text, run_cli


def resolve_commit(repository, commit):
    return run_git(repository, ['rev-parse', '--verify', commit + '^{commit}'], text=True).stdout.strip()


def build(repository, commit, *, relations=False):
    revision = resolve_commit(repository, commit)
    paths = run_git(repository, ['ls-tree', '-r', '--name-only', revision, '--', 'reviews/2026/'], text=True).stdout.splitlines()
    sources = {}
    if relations:
        raw = run_git(repository, ['cat-file', '-p', revision + ':relations/relations.jsonl']).stdout.decode('utf-8')
        for line in raw.splitlines():
            if line.strip():
                edge = readjson(line)
                sources[edge['id']] = edge['src']
    entries = []
    for path in paths:
        if not path.endswith('.jsonl'):
            continue
        text = run_git(repository, ['cat-file', '-p', revision + ':' + path]).stdout.decode('utf-8')
        for line in text.splitlines():
            if not line.strip():
                continue
            row = readjson(line)
            if relations:
                owner = sources.get(row.get('target'), row.get('relation_snapshot', {}).get('src', ''))
                selected = row.get('relation_review') == 'confirmed' and owner.startswith(('case/', 'interp/'))
            else:
                selected = 'reference_status' in row and row.get('target', '').startswith(('case/', 'interp/'))
            if selected and 'source_sha256' not in row:
                entries.append(dict(id=row['id'], review_sha256=sha(canonical(row, reject_masked=True))))
    if len({entry['id'] for entry in entries}) != len(entries):
        raise ValueError('duplicate review IDs')
    return sorted(entries, key=lambda entry: entry['id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--relations', action='store_true', help='select source-backed confirmed relation reviews instead of document status reviews')
    args = parser.parse_args(argv)
    check_output_path(args.output)
    entries = build(args.repository, args.commit, relations=args.relations)
    safe_write_text(args.output, json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
    print('manifest reviews:', len(entries))
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
