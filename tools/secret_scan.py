# SPDX-License-Identifier: GPL-3.0-only
"""Find the LAW_OC environment value in Git working files, without disclosing it."""
import argparse
import base64
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credentials import selected_key
from git_read import run_git


class ScanError(Exception):
    """A safe-to-display error; never include key material or raw exceptions."""


def environment_needles():
    """Return environment-only needles; never load or use a fallback file."""
    return value_needles(selected_key(env_only=True))


def value_needles(value):
    """Derive shared byte needles from an explicitly selected credential."""
    if value is None:
        return None
    if len(value) < 4 or value == '***':
        raise ScanError('LAW_OC is invalid (expected an unmasked value of 4+ characters).')
    try:
        raw = value.encode('utf-8')
        needles = [
            ('utf-8', raw),
            ('url-quote', quote(value, safe='').encode('ascii')),
            ('url-quote-plus', quote_plus(value, safe='').encode('ascii')),
            ('utf-16-le', value.encode('utf-16-le')),
            ('utf-16-be', value.encode('utf-16-be')),
            ('hex-lower', raw.hex().encode('ascii')),
            ('hex-upper', raw.hex().upper().encode('ascii')),
        ]
    except UnicodeError:
        raise ScanError('LAW_OC cannot be encoded.') from None
    for name, encode in (('base64', base64.b64encode), ('base64url', base64.urlsafe_b64encode)):
        full = encode(raw)
        needles.append((f'{name}-full', full))
        needles.append((f'{name}-full-unpadded', full.rstrip(b'=')))
        for offset in range(3):
            # Keep only sextets wholly contained in the key. The first/last
            # sextet may also encode neighbouring bytes in a larger blob.
            start = (offset * 8 + 5) // 6
            end = ((offset + len(raw)) * 8) // 6
            needle = encode(b'\0' * offset + raw)[start:end]
            if len(needle) >= 8:
                needles.append((f'{name}-offset-{offset}', needle))
    return needles


def repository_files(root, *, worktree=False):
    """Tracked files always count; only literal, read-only Git commands run."""
    try:
        top = run_git(root, ['rev-parse', '--show-toplevel']).stdout
        root = Path(os.fsdecode(top).rstrip('\r\n'))
        tracked = run_git(root, ['ls-files', '-z', '--cached']).stdout
        if worktree:
            tracked += run_git(root, ['ls-files', '-z', '--others', '--exclude-standard']).stdout
    except (OSError, subprocess.CalledProcessError):
        raise ScanError('Cannot enumerate Git working files.') from None
    return root, sorted(set(os.fsdecode(item) for item in tracked.split(b'\0') if item))


def matching_encodings(data, needles):
    """Normalize encoding syntax only; credential characters stay case-sensitive."""
    url_data = base64_data = hex_data = None
    for encoding, needle in needles:
        haystack = data
        if encoding.startswith('url-'):
            if url_data is None:
                url_data = re.sub(rb'%[0-9a-fA-F]{2}', lambda match: match[0].upper(), data)
            haystack = url_data
        elif encoding.startswith('base64'):
            if base64_data is None:
                base64_data = data.translate(None, b'\r\n \t')
            haystack = base64_data
        elif encoding.startswith('hex-'):
            if hex_data is None:
                hex_data = data.lower()
            haystack, needle = hex_data, needle.lower()
        if needle in haystack:
            yield encoding


def redact_diagnostic(message, needles=None):
    """Suppress diagnostics containing any documented credential representation.

    Callers may reuse needles, or use the credential selected by the API.
    Invalid credentials fail closed without echoing either input or diagnostics.
    Full suppression avoids reconstructing normalized string offsets.
    """
    if needles is None:
        try:
            needles = value_needles(selected_key())
        except ScanError:
            return '[redacted]'
    data = message.encode('utf-8', errors='surrogatepass')
    return '[redacted]' if needles and next(matching_encodings(data, needles), None) else message


def scan(root, *, worktree=False, needles=None):
    """Return (safe path, encoding) matches, or None if LAW_OC is absent.

    Read current working-file and relative-pathname bytes (not Git history).
    Symlinks contribute link text, never the contents of an external target.
    """
    if needles is None:
        needles = environment_needles()
    if needles is None:
        return None
    root, paths = repository_files(root, worktree=worktree)
    matches = []
    for relative in paths:
        pathname_encodings = list(matching_encodings(os.fsencode(relative), needles))
        safe_path = '[redacted path]' if pathname_encodings else ascii(relative)
        matches.extend((safe_path, f'{encoding} (pathname)') for encoding in pathname_encodings)
        path = root / relative
        try:
            if path.is_symlink():
                data = os.fsencode(os.readlink(path))
            elif path.is_dir():
                continue  # Gitlinks belong to separate repositories.
            else:
                data = path.read_bytes()
        except FileNotFoundError:
            continue  # Tracked deletion in this working tree.
        except OSError:
            raise ScanError(f'{safe_path}: cannot read file.') from None
        matches.extend((safe_path, encoding) for encoding in matching_encodings(data, needles))
    return matches


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require', action='store_true', help='fail if LAW_OC is unavailable')
    parser.add_argument('--worktree', action='store_true', help='include untracked, non-ignored files')
    args = parser.parse_args(argv)
    try:
        matches = scan(Path.cwd(), worktree=args.worktree)
    except ScanError as exc:
        print(f'ERROR: {exc}')
        return 2
    if matches is None:
        print('NOTICE: LAW_OC is unset or empty; credential scan skipped.')
        return 2 if args.require else 0
    for path, encoding in matches:
        print(f'{path}: {encoding}')
    return 1 if matches else 0


if __name__ == '__main__':
    raise SystemExit(main())
