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
# Recognize names independently of value syntax. Once an assignment is found,
# inspect the entire remaining line, rather than accepting one blessed RHS form.
ASSIGNMENT = re.compile(
    r"""(?<![\w.-]) ["']? (?P<name>[A-Za-z_][\w.-]*) ["']? \s*
    (?P<operator>:=|=>|->|\?=|=|:)""", re.X
)
SEGMENTS = re.compile(r'[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+')
PLACEHOLDER = re.compile(
    r'(?ix)^(?:\*+|<[^>]*>|example(?:[_-].*)?|fake(?:[_-].*)?|'
    r'not[-_]a[-_]real(?:[-_].*)?|your[_-].*)$'
)
ENV_REFERENCE = re.compile(
    r"""(?ix)(?:\$[A-Z_][A-Z0-9_]*|\$env:[A-Z_][A-Z0-9_]*|
    % [A-Z_][A-Z0-9_]* %|\$\{[A-Z_][A-Z0-9_]*\}|
    \$\{\{\s*(?:secrets|env)\.[A-Z_][A-Z0-9_]*\s*\}\}|
    (?:os\.)?getenv\(\s*["'][A-Z_][A-Z0-9_]*["']\s*\)|
    (?:os\.)?environ\[\s*["'][A-Z_][A-Z0-9_]*["']\s*\]|
    process\.env\.[A-Z_][A-Z0-9_]*)"""
)
SHELL_OPERAND = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?P<op>:-|:=|:\+|:\?|[-=+?])')
TYPE_ANNOTATION = re.compile(r'\s*[A-Za-z_][\w.]*\s*(?:\[[^=]*?\]\s*)?=(?!>)')


def credential_rule(name):
    # Split delimiters first, then camel humps (including acronym boundaries).
    words = []
    for part in re.split(r'[_ .-]+', name):
        words.extend(word.lower() for word in SEGMENTS.findall(part))
    if words and words[-1] == 'oc':
        return 'law-oc'
    if words and words[-1] in ('secret', 'token', 'password', 'passwd'):
        return 'generic-secret'
    pairs = set(zip(words, words[1:]))
    if pairs & {('api', 'key'), ('service', 'key'), ('private', 'key')}:
        return 'generic-secret'
    # Preserve conventional all-lower/all-upper spellings as whole segments.
    if any(word in ('apikey', 'servicekey', 'privatekey') for word in words):
        return 'generic-secret'
    return None


def placeholder(value):
    return not value or bool(PLACEHOLDER.fullmatch(value) or ENV_REFERENCE.fullmatch(value))


def braced_end(text, start):
    """Find a balanced shell expansion without mistaking nested refs for literals."""
    depth = 1
    for index in range(start + 2, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if not depth:
                return index + 1
    return len(text)


def literal_candidates(value):
    """Inspect expansion operands and template static parts, not reference names."""
    if placeholder(value):
        return
    if value.startswith('${') and braced_end(value, 0) == len(value):
        operand = SHELL_OPERAND.match(value, 2)
        if operand:
            yield from literal_candidates(value[operand.end():-1])
            return
    # A mixed reference/literal is not exempt. Also inspect operands separately
    # so a long fallback cannot hide behind low-entropy surrounding syntax.
    index = 0
    while index < len(value):
        start = value.find('${', index)
        if start < 0:
            break
        end = braced_end(value, start)
        operand = SHELL_OPERAND.match(value, start + 2)
        if operand:
            yield from literal_candidates(value[operand.end():end - 1])
        index = end
    yield value


def candidates(text):
    """Small single-line lexer: every literal or bare token is inspected.

    Python literal prefixes are syntax, not values. Backtick interpolations are
    omitted while their static chunks are retained. This is not a language parser.
    """
    index = 0
    while index < len(text):
        if text[index].isspace() or text[index] in '=,:;()[]&':
            index += 1
            continue
        if text[index] == '#':
            break
        env = ENV_REFERENCE.match(text, index)
        if env and (env.end() == len(text) or text[env.end()] in ' 	,;)]}\"\''):
            index = env.end()
            continue
        prefix = re.match(r"(?i:[bruf]*)['\"`]", text[index:])
        if prefix:
            quote_index = index + prefix.end() - 1
            quote = text[quote_index]
            end = quote_index + 1
            chunks = []
            start = end
            while end < len(text) and text[end] != quote:
                if text[end] == '\\':
                    end += 2
                    continue
                if quote == '`' and text.startswith('${', end):
                    chunks.append(text[start:end])
                    # Shell-style fallbacks are inspected even in templates.
                    stop = braced_end(text, end)
                    yield from literal_candidates(text[end:stop])
                    end = stop
                    start = end
                    continue
                end += 1
            chunks.append(text[start:end])
            yield from literal_candidates(''.join(chunks))
            index = end + 1
            continue
        start = index
        while index < len(text):
            if text.startswith('${', index):
                index = braced_end(text, index)
            elif text[index].isspace() or text[index] in ',;)]}\"\'`&':
                break
            else:
                index += 1
        if index == start:
            index += 1
        else:
            yield from literal_candidates(text[start:index])


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
            rule = credential_rule(match['name'])
            if rule is None:
                continue
            rest = line[match.end():]
            # Embedded URL assignments end at the next query parameter. A name
            # inside a surrounding string cannot consume code after that string.
            if '?' in line[:match.start()] and rule == 'law-oc':
                rest = rest.split('&', 1)[0]
            before = line[:match.start()]
            for quote in ('"', "'"):
                if before.count(quote) % 2 and quote in rest:
                    rest = rest.split(quote, 1)[0]
                    break
            if match['operator'] == ':':
                annotation = TYPE_ANNOTATION.match(rest)
                if annotation:
                    rest = rest[annotation.end():]
            for value in candidates(rest):
                if not placeholder(value) and (rule == 'law-oc' or high_entropy(value)):
                    rules.add(rule)
        for rule in sorted(rules):
            yield number, rule


def decode_text(data):
    """Recognize BOM-less UTF-16 text without interpreting arbitrary binary as it."""
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16', errors='replace')
    if len(data) >= 4 and len(data) % 2 == 0:
        even, odd = data[::2], data[1::2]
        for encoding, high, low in (('utf-16-le', odd, even), ('utf-16-be', even, odd)):
            # ASCII-heavy UTF-16 has NULs predominantly in its high-byte lane.
            if high.count(0) / len(high) < 0.6 or low.count(0) / len(low) > 0.1:
                continue
            try:
                text = data.decode(encoding)
            except UnicodeError:
                continue
            if sum(c.isprintable() or c in '\r\n\t' for c in text) / len(text) >= 0.95:
                return text
    return data.decode('utf-8', errors='replace')


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
        # Keep the original decoding, but do not let ASCII-lane heuristics hide
        # credentials surrounded by non-ASCII UTF-16 text. Strict decoding rejects
        # malformed binary data; each byte order is attempted independently.
        texts = [decode_text(data)]
        if b'\0' in data and len(data) % 2 == 0:
            for encoding in ('utf-16-le', 'utf-16-be'):
                try:
                    texts.append(data.decode(encoding, errors='strict'))
                except UnicodeError:
                    continue
        file_matches = set()
        for text in texts:
            lines = text.splitlines()
            for line, rule in findings(text):
                digest = hashlib.sha256(lines[line - 1].encode('utf-8')).hexdigest()
                if (relative, rule, digest) not in ALLOWLIST:
                    file_matches.add((line, rule))
        matches.extend((safe_path, line, rule) for line, rule in sorted(file_matches))
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
