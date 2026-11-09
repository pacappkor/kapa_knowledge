# SPDX-License-Identifier: GPL-3.0-only
"""Restore verbatim source court names without changing normalized IDs/paths."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, frontmatter, readjson, court_slug, canonical, sha, safe_write_text, run_cli


def restore(root=ROOT):
    updates = {}
    for path in (root / 'cases').rglob('*.md'):
        if path.name == 'README.md':
            continue
        text = path.read_text(encoding='utf-8')
        fm = frontmatter(text)
        if fm.get('provenance', {}).get('court') != 'source':
            continue
        saved = readjson((root / 'sources/prec' / (fm['precSeq'] + '.json')).read_text(encoding='utf-8'))
        data = saved['payload']
        court = data['PrecService']['법원명']
        if (set(data) != {'PrecService'} or str(data['PrecService']['판례정보일련번호']) != fm['precSeq']
                or saved['target'] != 'prec' or str(saved['source_id']) != fm['precSeq']
                or sha(canonical(data, reject_masked=True)) != fm['source_sha256']
                or saved['sha256'] != fm['source_sha256']
                or court_slug(court) != court_slug(fm['court'])):
            raise ValueError('court restoration identity/digest mismatch')
        if court != fm['court']:
            fm['court'] = court
            header = '---\n' + ''.join(k + ': ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fm.items()) + '---\n'
            updates[path] = header + text.split('\n---\n', 1)[1]
    for path, text in updates.items():
        safe_write_text(path, text)
        print(path.relative_to(root).as_posix())
    return len(updates)


def main():
    print('restored court fields:', restore())
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
