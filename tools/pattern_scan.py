# SPDX-License-Identifier: GPL-3.0-only
"""Blocking, secret-free credential shapes in tracked working files (not history)."""
import hashlib
import math
from pathlib import Path
import re
import stat
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_scan import ScanError, repository_files

# Exact path/rule/whole-line SHA-256 only: edits invalidate each exception.
# No path-wide exclusions or inline suppression directives.
ALLOWLIST = {
    # Runtime function call, not a literal credential.
    ('tools/lawapi.py', 'law-oc', 'acc7471c4a3039774577221742693dfe27341f130607ff4c6dd81967cb46e1d7'),
    # Synthetic KEY variable in a masking regression fixture.
    ('tools/test_review_round6.py', 'law-oc', '5f389a44337cb5688c946171460f430ed1ea23e712c2d4b8e51939679f8af114'),
    # Deliberate ordinary word in a recursive masking regression fixture.
    ('tools/test_review_round7.py', 'law-oc', '15aef1191dcf0221d3f67420efd375774f18e9265f76fe0ab72c7347770056a2'),
    # Runtime concatenation of the example-not-a-real-key placeholder.
    ('tools/test_secret_scan.py', 'law-oc', '04e3a24f5e3c1e2f0d977063b6218f9e960beadc7c970161bfd53b70f45577e2'),
}
TOKEN_RULES = (
    ('github-token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})')),
    ('huggingface-token', re.compile(r'\bhf_[A-Za-z0-9]{30,}')),
    ('aws-access-key', re.compile(r'\bAKIA[A-Z0-9]{16}\b')),
    ('private-key', re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')),
)
# Capture quoted values including spaces, or a bare URL/config value. Boundary
# excludes identifiers such as protocol while allowing OC query parameters.
ASSIGNMENT = re.compile(
    r'''(?ix)(?<![\w-]) ["']?
    (?P<name>oc|(?:[\w]+[_-])?(?:api[_-]?key|service[_-]?key|secret|token|password))
    ["']? \s* [=:] \s*
    (?: "(?P<double>[^"\r\n]*)" | '(?P<single>[^'\r\n]*)' |
        (?P<bare>[^\s&;,\}\]\)"'`]+))'''
)
PLACEHOLDER = re.compile(
    r'(?ix)^(?:\*+|<[^>]*>|example(?:[_-].*)?|fake(?:[_-].*)?|'
    r'not[-_]a[-_]real(?:[-_].*)?|your[_-].*|\$.*|%[A-Z_][A-Z0-9_]*%|'
    r'\{.*\}|(?:os\.)?(?:getenv|environ)(?:\b.*)|process\.env\..*)$'
)


def placeholder(value):
    return not value or bool(PLACEHOLDER.fullmatch(value))


def high_entropy(value):
    if len(value) < 20:
        return False
    counts = Counter(value)
    entropy = -sum((n / len(value)) * math.log2(n / len(value)) for n in counts.values())
    return entropy >= 3.5


def findings(text):
    """Yield only (line number, rule id); never return matched values."""
    for number, line in enumerate(text.splitlines(), 1):
        rules = set()
        for rule, pattern in TOKEN_RULES:
            for match in pattern.finditer(line):
                if not placeholder(match[0]):
                    rules.add(rule)
        for match in ASSIGNMENT.finditer(line):
            value = next(v for v in (match['double'], match['single'], match['bare']) if v is not None)
            if placeholder(value):
                continue
            if match['name'].lower() == 'oc':
                rules.add('law-oc')
            elif high_entropy(value):
                rules.add('generic-secret')
        for rule in sorted(rules):
            yield number, rule


def scan(root):
    root, paths = repository_files(root)
    matches = []
    for relative in paths:
        # A credential-shaped filename must not leak through diagnostics either.
        safe_path = '[redacted path]' if list(findings(relative)) else ascii(relative)
        path = root / relative
        try:
            # Refuse links/reparse points in any component before opening a file.
            current = root
            for part in Path(relative).parts:
                current = current / part
                info = current.lstat()
                if current.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ScanError(f'{safe_path}: unsafe path [masked]')
            if not stat.S_ISREG(info.st_mode):
                raise ScanError(f'{safe_path}: unsupported file type [masked]')
            data = path.read_bytes()
        except FileNotFoundError:
            continue  # Tracked deletion.
        except OSError:
            raise ScanError(f'{safe_path}: cannot read file [masked]') from None
        # Decode UTF-16 BOM files too; no extension or binary-file exclusions.
        encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'
        text = data.decode(encoding, errors='replace')
        lines = text.splitlines()
        for line, rule in findings(text):
            digest = hashlib.sha256(lines[line - 1].encode('utf-8')).hexdigest()
            if (relative, rule, digest) not in ALLOWLIST:
                matches.append((safe_path, line, rule))
    return matches


def main():
    try:
        matches = scan(Path.cwd())
    except ScanError as exc:
        print(f'ERROR: {exc}')
        return 2
    for path, line, rule in matches:
        print(f'{path}:{line}: {rule} [masked]')
    print(f'Pattern scan: {len(matches)} finding(s).')
    return 1 if matches else 0


if __name__ == '__main__':
    raise SystemExit(main())
