# SPDX-License-Identifier: GPL-3.0-only
"""Whole-file documentation inventory; no Markdown or command interpretation."""
import hashlib
import json
from pathlib import Path
import re
import stat

import common
from secret_scan import redact_diagnostic

SNAPSHOT = 'tools/doc_command_snapshot.json'
ROOT_PREFIXES = ('readme', 'agents', 'claude', 'skill')


class SnapshotError(ValueError):
    """Only fixed/redacted diagnostics may leave the snapshot reader."""


def checked_path(path, root, *, directory=False):
    try:
        common.check_output_path(path, root=root, directory=directory, require_exists=True)
    except (OSError, RuntimeError, ValueError):
        raise SnapshotError(redact_diagnostic('Unsafe documentation snapshot input path.')) from None


def check_index(root):
    try:
        common.check_tracked_links(root)
    except (OSError, RuntimeError, ValueError):
        raise SnapshotError(redact_diagnostic('Documentation snapshot refuses tracked links or unreadable Git modes.')) from None


def checked_documents(root):
    """Validate the complete read set, including every extension and hidden file."""
    root = Path(root)
    paths = []
    def visit(directory):
        checked_path(directory, root, directory=True)
        for path in directory.iterdir():
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                visit(path)  # Check reparse/junction metadata before traversal.
            else:
                checked_path(path, root)
                paths.append(path)
    try:
        # Check governed tree roots before any root directory enumeration.
        for name in ('rules', 'docs'):
            directory = root / name
            try:
                directory.lstat()
            except FileNotFoundError:
                continue  # Optional trees in small offline fixtures.
            visit(directory)
        checked_path(root, root, directory=True)
        for path in root.iterdir():
            if path.name.casefold().startswith(ROOT_PREFIXES):
                checked_path(path, root)
                paths.append(path)
    except (OSError, RuntimeError):
        raise SnapshotError(redact_diagnostic('Cannot inspect documentation snapshot inputs.')) from None
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def read_snapshot_input(path, root):
    checked_path(path, root)
    try:
        return path.read_bytes()
    except OSError:
        raise SnapshotError(redact_diagnostic('Cannot read documentation snapshot input.')) from None


def document_snapshot(root):
    root = Path(root)
    check_index(root)
    paths = checked_documents(root)
    records = []
    for path in paths:
        data = read_snapshot_input(path, root)
        records.append({'file': path.relative_to(root).as_posix(),
                        'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)})
    return records


def valid_records(records):
    if not isinstance(records, list):
        return False
    names = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {'file', 'sha256', 'size'}:
            return False
        if (not isinstance(record['file'], str) or not record['file']
                or not isinstance(record['sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])
                or type(record['size']) is not int or record['size'] < 0):
            return False
        names.append(record['file'])
    return names == sorted(set(names))


def load_snapshot(root):
    check_index(root)
    try:
        records = json.loads(read_snapshot_input(Path(root) / SNAPSHOT, root).decode('utf-8'))
    except (json.JSONDecodeError, UnicodeError):
        raise SnapshotError(redact_diagnostic('Invalid documentation snapshot JSON.')) from None
    if not valid_records(records):
        raise SnapshotError(redact_diagnostic('Invalid documentation snapshot inventory.')) from None
    return records


def snapshot_difference(actual, expected):
    """Render only validated paths/hashes/sizes, never source or arbitrary fields."""
    if not valid_records(actual) or not valid_records(expected):
        return redact_diagnostic('Invalid documentation snapshot inventory.')
    differences = []
    for index in range(max(len(actual), len(expected))):
        left = actual[index] if index < len(actual) else None
        right = expected[index] if index < len(expected) else None
        if left == right:
            continue
        for record in (left, right):
            if record is not None:
                path = ascii(redact_diagnostic(record['file']))
                differences.append(f"{path} sha256={record['sha256']} size={record['size']}")
    return redact_diagnostic('\n'.join(differences))
