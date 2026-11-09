# SPDX-License-Identifier: GPL-3.0-only
"""Explicit offline generation of the held pilot material catalog."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ROOT, check_output_path, check_tracked_links, dependency_bytes,
                    load_index, run_cli, save_json)
from material_contracts import CATALOG, build_catalog


def main():
    check_tracked_links(ROOT)
    index, sibling, commit = load_index(ROOT)
    if commit == 'WORKTREE':
        raise ValueError('Catalog generation requires a pinned dependency commit.')
    def read(name):
        path = ROOT / name
        check_output_path(path, require_exists=True)
        return path.read_bytes()
    def versions(name):
        return dependency_bytes(ROOT, sibling, commit, name)
    catalog = build_catalog(read, index, commit, versions)
    save_json(ROOT / CATALOG, catalog)
    print('Generated unpublished catalog:', len(catalog['records']), 'material records;',
          len(catalog['historical_versions']), 'historical version assertions')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
