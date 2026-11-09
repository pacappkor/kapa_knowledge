# SPDX-License-Identifier: GPL-3.0-only
"""Refresh only pinned law-index and historical-version metadata, never law text."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ROOT, CODE_ROOT, check_tracked_links, readjson, run_cli,
                    safe_write_bytes, safe_write_text, sha)
from git_read import run_git

INDEX_PATH = 'docs/law-index.json'
VENDOR_PATH = 'vendor/kapa_skills'


def metadata_paths(index):
    paths = {INDEX_PATH}
    for law in index.get('laws', {}).values():
        name = law.get('versions_file')
        if name:
            if not isinstance(name, str):
                raise ValueError('Unsafe dependency metadata path.')
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts
                    or '\\' in name or ':' in name
                    or not name.startswith('sources/laws/') or '/versions/' not in name
                    or not name.endswith('.json') or path.as_posix() != name):
                raise ValueError('Unsafe dependency metadata path.')
            paths.add(name)
    return sorted(paths)


def refresh(root=ROOT, sibling=None):
    check_tracked_links(root)
    lock = readjson((root / 'deps.lock').read_text(encoding='utf-8'))
    dependency = lock['kapa_skills']
    commit = dependency['commit']
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Vendoring requires a full pinned commit, not WORKTREE.')
    sibling = Path(sibling or os.environ.get('KK_SKILLS_ROOT', CODE_ROOT.parent / 'kapa_skills'))
    # cat-file reads exactly the requested object, without checkout/filter effects.
    index = run_git(sibling, ['cat-file', '-p', commit + ':' + INDEX_PATH]).stdout
    parsed = readjson(index)
    if parsed.get('schema') != 1:
        raise ValueError('Unsupported law-index schema.')
    blobs = {INDEX_PATH: index}
    for name in metadata_paths(parsed):
        if name != INDEX_PATH:
            blobs[name] = run_git(sibling, ['cat-file', '-p', commit + ':' + name]).stdout
            data = readjson(blobs[name])
            if not isinstance(data.get('versions'), list):
                raise ValueError('Unsupported historical-version metadata.')
    # Read every pinned object before writing. These are metadata, not sources
    # collected by this repo. Safe sinks reject linked/escaped output paths.
    for name, raw in sorted(blobs.items()):
        safe_write_bytes(root / VENDOR_PATH / name, raw)
    dependency['vendor'] = {'commit': commit,
                            'files': {name: sha(raw) for name, raw in sorted(blobs.items())}}
    safe_write_text(root / 'deps.lock', json.dumps(lock, ensure_ascii=False, indent=2) + '\n')
    return len(blobs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills-root', type=Path)
    args = parser.parse_args()
    print(f'Vendored {refresh(sibling=args.skills_root)} pinned metadata files.')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
