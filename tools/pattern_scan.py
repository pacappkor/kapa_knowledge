# SPDX-License-Identifier: GPL-3.0-only
"""Blocking, secret-free credential shapes in non-ignored worktree files (not history)."""
import argparse
from bisect import bisect_right
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
    # Runtime variables, not literal credentials, assigned to subscript targets.
    ('tools/test_ci_trusted_scanner.py', 'law-oc', 'd26dec3ebec8d25cb4e2e7de04700eeef3ba835562b3fcf827c854ee2917a0a4'),
    ('tools/test_secret_scan.py', 'law-oc', '8f0a9fcb537ccb47e2c0bea9c6db3f82406d7ed62823b856c55b01563b9c1397'),
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
NAME_TOKEN = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_][\w.-]*''')
OPERATOR = re.compile(r'\?\?=|\|\|=|&&=|\+=|:=|=>|->|\?=|=(?!=|>)|:(?!=)')
SPACE = re.compile(r'\s*')


class Assignment:
    """Small match-compatible record produced by the forward-only name scan."""

    def __init__(self, start, end, name, operator, key=None, option=False):
        self.start_at, self.end_at = start, end
        self.fields = {'name': name, 'key': key, 'operator': operator, 'option': option}

    def start(self):
        return self.start_at

    def end(self):
        return self.end_at

    def span(self):
        return self.start_at, self.end_at

    def __getitem__(self, key):
        return self.fields[key]


def bracket_pairs(text, angles=False):
    """Index balanced groups once so chained lookups never rescan suffixes."""
    pairs, stack = {}, []
    index = 0
    while index < len(text):
        char = text[index]
        if char in '\"\'`':
            index = quoted_end(text, index) + 1
            continue
        if char in '([{' or (angles and char == '<'):
            stack.append((char, index))
        elif char in ')]}>':
            if char == '>' and index and text[index - 1] in '=-':
                index += 1
                continue
            if stack and stack[-1][0] == {')': '(', ']': '[', '}': '{', '>': '<'}[char]:
                _, opening = stack.pop()
                pairs[opening] = index
        index += 1
    return pairs


DECLARATOR_SUFFIX = re.compile(
    r'(?:\[[A-Za-z_0-9\s]*+\]\s*+)*+(?:const\s++)*+'
    r'(?:\*+(?:const\s++)*+)?'
    r'(?:[A-Za-z_][\w.]*+(?:\s*\[[A-Za-z_0-9\s]*+\])*+(?:\s+const)*+\s*+)?'
    r'=(?!=|>)')


def assignments_in(text, kind='unknown'):
    """Consume dotted/indexed chains and bounded declarators in one forward pass."""
    pairs = bracket_pairs(text) if '[' in text else {}
    cursor = 0
    while cursor < len(text):
        if text[cursor] == '\\':
            cursor += 2
            continue
        token = NAME_TOKEN.match(text, cursor)
        if token is None:
            cursor += 1
            continue
        start, end = token.span()
        if text[start:end].endswith('.') and text[end:end + 1] in ('"', "'"):
            end -= 1
        cursor = end
        if text[start] in '\"\'' and not re.fullmatch(r'[A-Za-z_][\w. -]*', text[start + 1:end - 1]):
            # Still recognize embedded examples inside ordinary strings/prose.
            if text.startswith('.', SPACE.match(text, end).end()):
                pass  # Quoted namespace.
            else:
                cursor = start + 1
                continue
        if text[start:end].endswith('-') and text[end:end + 1] == '>':
            end -= 1
        option_start = start
        while option_start and text[option_start - 1] == '-':
            option_start -= 1
        option = (start - option_start in (1, 2)
                  and (not option_start or text[option_start - 1].isspace()))
        if start and (text[start - 1].isalnum() or text[start - 1] in '_.-') and not option:
            continue
        key = 'password' if option and text[start:end] == 'p' else None
        after = SPACE.match(text, end).end()
        if kind == 'c-family' and credential_rule(text[start:end]):
            # Bound each lookahead independently of the line length. Only a
            # completed initializer is a declaration; bare declarations stay clean.
            declarator = DECLARATOR_SUFFIX.match(text, after, min(len(text), after + 4096))
            if declarator:
                yield Assignment(start, declarator.end(), text[start:end], '=')
                cursor = declarator.end()
                continue
        if text[start] in '\"\'' and text[after:after + 1] == ']':
            key = text[start + 1:end - 1]
            after = SPACE.match(text, after + 1).end()
        else:
            indexed_chain = False
            while True:
                if text[after:after + 1] == '[' and after in pairs:
                    indexed_chain = True
                    closing = pairs[after]
                    indexed = text[after + 1:closing].strip()
                    key = indexed[1:-1] if indexed[:1] in ('\"', "'") else '[dynamic]'
                    end = closing + 1
                    after = SPACE.match(text, end).end()
                elif text[after:after + 1] == '.':
                    following = NAME_TOKEN.match(text, SPACE.match(text, after + 1).end())
                    if following is None:
                        break
                    if indexed_chain:
                        key = following[0].strip('\"\'')
                    end = following.end()
                    after = SPACE.match(text, end).end()
                else:
                    break
            cursor = max(cursor, after)
        operator = OPERATOR.match(text, after)
        if operator:
            yield Assignment(start, operator.end(), text[start:end], operator[0], key, option)
            cursor = operator.end()
        elif option and after > end and after < len(text):
            yield Assignment(option_start, after, text[start:end], 'option', key, True)
SEGMENTS = re.compile(r'[A-Za-z]+|[0-9]+')


def name_segments(part):
    """Split camel/acronym boundaries without uppercase-run backtracking."""
    for match in SEGMENTS.finditer(part):
        word = match[0]
        start = 0
        for index in range(1, len(word)):
            if (word[index].isupper() and
                    (word[index - 1].islower() or
                     (index + 1 < len(word) and word[index + 1].islower()))):
                yield word[start:index].lower()
                start = index
        yield word[start:].lower()
PLACEHOLDER = re.compile(r'(?:[*•●]+|<[^>]*>)')
MARKER_WORDS = frozenset(('example', 'fake', 'not', 'a', 'real', 'your',
                          'api', 'key', 'here', 'token', 'secret', 'password',
                          'value', 'placeholder', 'test', 'dummy', 'sample'))
PROVIDER_PREFIXES = frozenset(('hf', 'ghp', 'gho', 'ghu', 'ghs', 'ghr', 'sk'))
PLACEHOLDER_MARKERS = frozenset(('example', 'fake', 'your', 'placeholder',
                                'test', 'dummy', 'sample'))
ENV_REFERENCE = re.compile(
    r"""(?ix)(?:\$env:[A-Z_][A-Z0-9_]*|\$[A-Z_][A-Z0-9_]*|
    \$[0-9@*#?$!\-]|\$\{[0-9]+\}|
    % [A-Z_][A-Z0-9_]* %|\$\{[A-Z_][A-Z0-9_]*\}|
    \$\{\{\s*(?:secrets|env)\.[A-Z_][A-Z0-9_]*\s*\}\}|
    (?:os\.)?getenv\(\s*["'][A-Z_][A-Z0-9_]*["']\s*\)|
    (?:os\.)?environ\[\s*["'][A-Z_][A-Z0-9_]*["']\s*\]|
    process\.env\.[A-Z_][A-Z0-9_]*)"""
)
SHELL_OPERAND = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?P<op>:-|:=|:\+|:\?|[-=+?])')
TYPE_ANNOTATION = re.compile(
    r'''\s*+(?:[A-Za-z_]|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
    (?:[\w.\s\[\]<>,|?]|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')*+=(?!=|>)''', re.X)
LITERAL_PREFIX = re.compile(r"(?i:([bruf]*))(['\"`])")
# Deterministic work limits, not a best-effort timeout. Exceeding any limit
# raises ScanError (CLI exit 2); no file is silently skipped.
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_LINE_CHARS = 256 * 1024
MAX_LINE_WORK = 4 * 1024 * 1024
MAX_FILE_WORK = 64 * 1024 * 1024
MAX_NESTING = 64

# (line markers, block marker pairs). Unknown files retain prose/config handling,
# but only balanced same-line block comments may act as assignment trivia.
COMMENT_SYNTAX = {
    'javascript': (('//',), (('/*', '*/'),)),
    'c-family': (('//',), (('/*', '*/'),)),
    'css': ((), (('/*', '*/'),)),
    'php': (('//', '#'), (('/*', '*/'),)),
    'python': (('#',), ()),
    'shell': (('#',), ()),
    'hash-config': (('#',), ()),
    'ini': (('#', ';'), ()),
    'sql': (('--',), (('/*', '*/'),)),
    'lua': (('--',), (('--[[', ']]'),)),
    'markup': ((), (('<!--', '-->'),)),
    'json': ((), ()),
    'unknown': (('#', '//'), (('/*', '*/'),)),
}
FILE_TYPES = {
    'javascript': ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'),
    'c-family': ('.c', '.h', '.cc', '.cpp', '.cxx', '.hpp', '.hh', '.hxx',
                 '.cs', '.java', '.go', '.rs', '.kt', '.kts', '.swift',
                 '.m', '.mm', '.scala', '.sc', '.dart', '.groovy', '.gradle'),
    'css': ('.css', '.scss', '.less'),
    'php': ('.php', '.phtml'),
    'python': ('.py', '.pyw'),
    'shell': ('.sh', '.bash', '.zsh', '.dash', '.ksh', '.env'),
    'hash-config': ('.yaml', '.yml', '.toml'),
    'ini': ('.ini', '.cfg'),
    'sql': ('.sql',),
    'lua': ('.lua',),
    'markup': ('.html', '.htm', '.xml', '.svg'),
    'json': ('.json', '.jsonl'),
}
SUFFIX_TYPES = {suffix: kind for kind, suffixes in FILE_TYPES.items() for suffix in suffixes}
SOURCE_TYPES = frozenset(('python', 'javascript', 'c-family', 'php'))
SHELL_TYPES = frozenset(('shell', 'ini'))
SHEBANG = re.compile(
    r'^#!\s*(?:/[^\s]*/)?(?P<command>[\w.+-]+)(?:\s|$)')


def file_type(text, path=None):
    """Classify once per file; an interpreter shebang takes precedence over suffix."""
    first_line = text[:min(len(text), MAX_LINE_CHARS + 1)].split('\n', 1)[0]
    match = SHEBANG.match(first_line)
    if match:
        command = match['command']
        if command == 'env':
            # Support env options (notably -S) and leading NAME=value arguments.
            words = first_line[match.end():].split()
            command = next((word for word in words
                            if not word.startswith('-') and '=' not in word), '')
        if command in ('sh', 'bash', 'zsh', 'dash', 'ksh'):
            return 'shell'
        if re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', command):
            return 'python'
        if command in ('node', 'nodejs'):
            return 'javascript'
    if path is None:
        return 'unknown'
    name = Path(path)
    if name.name == '.env':
        return 'shell'
    return SUFFIX_TYPES.get(name.suffix.lower(), 'unknown')


def literal_prefix(text, index):
    start = index
    while start and text[start - 1].isalpha():
        start -= 1
    prefix = text[start:index]
    return prefix if (not start or not (text[start - 1].isalnum() or text[start - 1] == '_')) and all(c.lower() in 'bruf' for c in prefix) else ''


def credential_rule(name):
    # Split delimiters first, then camel humps (including acronym boundaries).
    words = []
    for part in re.split(r'[_ .-]+', name):
        words.extend(name_segments(part))
    if words and words[-1] == 'oc':
        return 'law-oc'
    if words and words[-1] in ('secret', 'token', 'password', 'passwd'):
        return 'generic-secret'
    if words and words[-1] == 'key' and 'secret' in words[:-1]:
        return 'generic-secret'
    pairs = set(zip(words, words[1:]))
    if pairs & {('api', 'key'), ('service', 'key'), ('private', 'key'),
                ('access', 'key'), ('secret', 'key')}:
        return 'generic-secret'
    # Preserve conventional all-lower/all-upper spellings as whole segments.
    if any(word in ('apikey', 'servicekey', 'privatekey', 'accesskey', 'secretkey')
           for word in words):
        return 'generic-secret'
    return None


def placeholder(value):
    if not value or PLACEHOLDER.fullmatch(value) or ENV_REFERENCE.fullmatch(value):
        return True
    words = re.split(r'[_-]', value.lower())
    if words[0] in PROVIDER_PREFIXES:
        words = words[1:]
    return bool(words and all(word in MARKER_WORDS for word in words)
                and (set(words) & PLACEHOLDER_MARKERS
                     or words[:4] == ['not', 'a', 'real', 'token']
                     or words == ['not', 'a', 'real']))


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


def interpolation_end(text, start, opening=2, python=False):
    """Skip a balanced interpolation, including nested objects and strings."""
    depth = 1
    index = start + opening
    while index < len(text):
        if text[index] == '\\':
            index += 2
        elif text[index] in '\"\'`':
            index = quoted_end(text, index) + 1
        elif not python and text.startswith('//', index):
            return len(text)  # Single-line scanner: the rest is a comment.
        elif not python and text.startswith('/*', index):
            stop = text.find('*/', index + 2)
            index = len(text) if stop < 0 else stop + 2
        elif text[index] == '{':
            depth += 1
            index += 1
        elif text[index] == '}':
            depth -= 1
            index += 1
            if not depth:
                return index
        else:
            index += 1
    return len(text)


def quoted_end(text, start):
    """Return the closing quote offset, respecting escapes and doubled quotes."""
    quote = text[start]
    formatted = quote != '`' and 'f' in literal_prefix(text, start).lower()
    index = start + 1
    while index < len(text):
        if text[index] == '\\':
            index += 1 if formatted and text[index + 1:index + 2] in ('{', '}') else 2
        elif formatted and text[index:index + 2] in ('{{', '}}'):
            index += 2
        elif formatted and text[index] == '{':
            index = interpolation_end(text, index, opening=1, python=True)
        elif text.startswith('$(', index) and quote == '"':
            index = command_end(text, index)
        elif text.startswith('${', index):
            index = (interpolation_end(text, index) if quote == '`'
                     else braced_end(text, index))
        elif text[index] == quote:
            if index + 1 < len(text) and text[index + 1] == quote:
                index += 2
            else:
                return index
        else:
            index += 1
    return len(text)


class QuoteIndex:
    """Cache prose-elision lookahead once, without copying per-quote suffixes."""

    def __init__(self, text):
        self.boundaries = [m.start() for m in re.finditer(
            r'[;\n]|(?<![\w.-])[A-Za-z_][\w.-]*\s*[:=]', text)] + [len(text)]
        self.single_end = [len(text)] * (len(text) + 2)
        self.previous = [''] * len(text)
        previous = ''
        for index, char in enumerate(text):
            self.previous[index] = previous
            if not char.isspace():
                previous = char
        for index in range(len(text) - 1, -1, -1):
            char = text[index]
            if char == '\\':
                self.single_end[index] = self.single_end[index + 2]
            elif char == "'":
                self.single_end[index] = (self.single_end[index + 2]
                                          if text.startswith("''", index) else index)
            else:
                self.single_end[index] = self.single_end[index + 1]


def quote_start(text, index, quotes=None):
    # Word-internal and trailing possessive apostrophes are prose. Only a
    # recognized literal prefix at a token boundary can open a quote after a word.
    if text[index] == "'" and index > 0 and re.match(r'\w', text[index - 1]):
        return bool(literal_prefix(text, index))
    if (text[index] == "'" and re.match(r'\w', text[index + 1:index + 2])
            and (not index or text[index - 1].isspace())):
        quotes = quotes if quotes is not None else QuoteIndex(text)
        if quotes.previous[index] not in '=(:,[{+' or not quotes.previous[index]:
            stop = quotes.boundaries[bisect_right(quotes.boundaries, index)]
            if quotes.single_end[index + 1] >= stop:
                return False
    return text[index] in '\"\'`'


def quote_spans(text):
    quotes = QuoteIndex(text)
    index = 0
    while index < len(text):
        if text[index] == '\\':
            index += 2
        elif quote_start(text, index, quotes):
            end = quoted_end(text, index)
            yield index, end
            index = end + 1
        else:
            index += 1


def command_end(text, start):
    """Consume nested $(...) with shell quotes; never inspect command bodies."""
    stack = [(')', None)]
    index = start + 2
    while index < len(text):
        closing, quote = stack[-1]
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if quote == "'":
            if char == quote:
                stack[-1] = (closing, None)
        elif text.startswith('$(', index) and quote != '`':
            if len(stack) >= MAX_NESTING:
                raise ScanError('pattern scan nesting work limit exceeded [masked]')
            stack.append((')', None))
            index += 2
            continue
        elif quote:
            if char == quote:
                stack[-1] = (closing, None)
        elif char in '\"\'`':
            stack[-1] = (closing, char)
        elif char == '(':
            if len(stack) >= MAX_NESTING:
                raise ScanError('pattern scan nesting work limit exceeded [masked]')
            stack.append((')', None))
        elif char == closing:
            stack.pop()
            if not stack:
                return index + 1
        index += 1
    return len(text)


def shell_static(text):
    """Separate literal chunks around runtime command substitutions."""
    index = start = 0
    while index < len(text):
        if text[index] == '\\':
            index += 2
        elif text.startswith('$(', index) or text[index] == '`':
            yield text[start:index]
            index = (command_end(text, index) if text[index] == '$'
                     else quoted_end(text, index) + 1)
            start = index
        else:
            index += 1
    yield text[start:]


def literal_candidates(value):
    """Inspect expansion operands and template static parts, not reference names."""
    if value and value[0] in '\"\'`' and quoted_end(value, 0) == len(value) - 1:
        value = value[1:-1]
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


def lexemes(text, comment_at_start=True, separators=False, bare_equals=False, quotes=None):
    """Yield source bounds and values for single-line literals, refs and words.

    Python literal prefixes are syntax, not values. Source bounds let provider
    rules reuse the generic lexer's whole-reference test. Not a language parser.
    """
    quotes = quotes if quotes is not None else QuoteIndex(text)
    index = 0
    while index < len(text):
        if separators and text[index] in ';|&\n':
            stop = index + (2 if text[index:index + 2] in ('&&', '||') else 1)
            if text[index] != '&' or stop == index + 2:
                yield index, stop, None
            index = stop
            continue
        if (text[index].isspace() or text[index] in '=,:;()&'
                or (not bare_equals and text[index] in '[]')):
            index += 1
            continue
        if text[index] == '#' and ((index == 0 and comment_at_start)
                                   or (index > 0 and (text[index - 1].isspace()
                                                      or text[index - 1] in ';(&|'))):
            break
        env = ENV_REFERENCE.match(text, index)
        if env and (env.end() == len(text) or text[env.end()] in ' 	,;)]}\"\''):
            yield index, env.end(), env[0]
            index = env.end()
            continue
        prefix = LITERAL_PREFIX.match(text, index)
        if prefix:
            quote_index = prefix.end() - 1
            end = quoted_end(text, quote_index)
            value = text[quote_index + 1:end]
            yield index, end + 1, value
            index = end + 1
            continue
        start = index
        while index < len(text):
            if text[index] == '\\':
                index += 2
            elif text.startswith('$(', index):
                index = command_end(text, index)
            elif text.startswith('${', index):
                index = braced_end(text, index)
            elif (text[index].isspace() or text[index] in ';&'
                  or (text[index] in ',:=()[]}' and not bare_equals)
                  or (separators and text[index] == '|')
                  or quote_start(text, index, quotes)):
                break
            else:
                index += 1
        if index == start:
            index += 1
        else:
            # Escaped whitespace and delimiters belong to the same shell word.
            yield start, index, re.sub(r'\\(.)', r'\1', text[start:index])


def shell_word_candidates(text, comment_at_start=True):
    """Join static shell word parts, flushing at operators and runtime expansions."""
    parts = []
    quote = None
    index = 0
    while index < len(text):
        char = text[index]
        if char == '\\' and quote != "'" and index + 1 < len(text):
            parts.append(text[index + 1])
            index += 2
            continue
        if quote == "'":
            if char == quote:
                quote = None
            else:
                parts.append(char)
            index += 1
            continue
        if char == quote:
            quote = None
            index += 1
            continue
        if char in '\"\'' and quote is None:
            quote = char
            index += 1
            continue
        if char == '`' or text.startswith('$(', index) or text.startswith('${', index):
            yield from literal_candidates(''.join(parts))
            parts = []
            if char == '`':
                index = quoted_end(text, index) + 1
            elif text.startswith('$(', index):
                index = command_end(text, index)
            else:
                end = braced_end(text, index)
                operand = SHELL_OPERAND.match(text, index + 2)
                if operand:
                    yield from shell_word_candidates(text[operand.end():end - 1], False)
                index = end
            continue
        reference = ENV_REFERENCE.match(text, index) if char == '$' else None
        if reference:
            yield from literal_candidates(''.join(parts))
            parts = []
            # Preserve legacy dollar-prefixed credential-shape detection without
            # joining either adjacent static run across the runtime reference.
            if reference.end() < len(text) and text[reference.end()] in '!/':
                yield reference[0] + text[reference.end()]
            index = reference.end()
            continue
        if quote is None and (char.isspace() or char in ';|&()'):
            yield from literal_candidates(''.join(parts))
            parts = []
        elif (quote is None and char == '#'
              and ((index == 0 and comment_at_start)
                   or (index > 0 and (text[index - 1].isspace() or text[index - 1] in ';(&|')))):
            break
        else:
            parts.append(char)
        index += 1
    yield from literal_candidates(''.join(parts))


def candidates(text, comment_at_start=True, source=False, shell=False):
    # Source literals retain the existing per-token semantics (including Python
    # implicit concatenation, which this heuristic deliberately does not fold).
    # Unknown/config contexts keep template and prefixed-source literal handling.
    if shell or (not source and not text.lstrip().startswith('`')
                 and not re.search(r"(?:^|\s)[brufBRUF]+['\"]", text)):
        yield from shell_word_candidates(text, comment_at_start)
        return
    # Only brackets can enclose quoted keys; bare member chains have no
    # literals to exclude. Do not retry a repeated chain at every member.
    references = []
    if source:
        cursor = 0
        while cursor < len(text):
            reference = re.compile(r'\b[A-Za-z_$][\w$]*\[').search(text, cursor)
            if reference is None:
                break
            closing = text.find(']', reference.end())
            if closing < 0:
                break
            references.append((reference.start(), closing + 1))
            cursor = closing + 1
    spans = list(quote_spans(text)) if source else []
    # Getter first arguments are names, like bracketed lookup keys. Defaults
    # remain separate literals and are deliberately not excluded.
    getters = []
    if source:
        for call in re.finditer(r'\b(?:get|getenv)\s*\(\s*', text):
            argument = LITERAL_PREFIX.match(text, call.end())
            if argument:
                closing = quoted_end(text, argument.end() - 1)
                getters.append((argument.start(), closing + 1))
    span_starts = [a for a, _ in spans]
    lookups = []
    for start, end in references:
        position = bisect_right(span_starts, start) - 1
        if position < 0 or not spans[position][0] < start < spans[position][1]:
            lookups.append((start, end))
    lookup_starts = [a for a, _ in lookups]
    # The assignment operator has already been consumed; inner equals signs
    # (including base64 padding) belong to the bare shell/config word.
    for start, end, value in lexemes(text, comment_at_start, bare_equals=True):
        if source:
            if any(a <= start and end <= b for a, b in getters):
                continue
            # A quoted subscript is a lookup key, not a credential literal.
            lookup = bisect_right(lookup_starts, start) - 1
            if lookup >= 0 and end <= lookups[lookup][1]:
                continue
            literal = LITERAL_PREFIX.match(text, start)
            if not literal:
                continue
        literal = LITERAL_PREFIX.match(text, start)
        if literal and literal[2] == '`' and shell:
            continue
        if shell and literal and literal[2] == "'":
            yield from literal_candidates(value)
        elif shell or '$(' in value:
            for chunk in shell_static(value):
                yield from literal_candidates(chunk)
        elif literal and (literal[2] == '`' or 'f' in literal[1].lower()):
            for chunk in static_chunks(value, formatted=literal[2] != '`'):
                yield from literal_candidates(chunk)
        else:
            yield from literal_candidates(value)


def static_chunks(value, formatted=False):
    """Keep noncontiguous template text separate; doubled f-braces are literal."""
    chunk = []
    cursor = 0
    while cursor < len(value):
        if value[cursor] == '\\':
            width = 1 if formatted and value[cursor + 1:cursor + 2] in ('{', '}') else 2
            chunk.append(value[cursor:cursor + width])
            cursor += width
        elif formatted and value[cursor:cursor + 2] in ('{{', '}}'):
            chunk.append(value[cursor])
            cursor += 2
        elif ((formatted and value[cursor] == '{')
              or (not formatted and value.startswith('${', cursor))):
            yield ''.join(chunk)
            chunk = []
            cursor = interpolation_end(value, cursor, opening=1 if formatted else 2,
                                       python=formatted)
        else:
            chunk.append(value[cursor])
            cursor += 1
    yield ''.join(chunk)


REGEX_KEYWORDS = frozenset(('else', 'do', 'return', 'throw', 'case', 'delete', 'void',
                            'typeof', 'instanceof', 'in', 'of', 'yield', 'await', 'new'))


def regex_end(text, start):
    index = start + 1
    character_class = False
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == '[':
            character_class = True
        elif char == ']':
            character_class = False
        elif char == '/' and not character_class:
            index += 1
            while index < len(text) and text[index].isalpha():
                index += 1
            return index
        index += 1
    return None


class LineState:
    """One quote-aware structural pass; RHS queries are O(log n), not rescans."""

    def __init__(self, line, kind='unknown'):
        line_comments, block_comments = COMMENT_SYNTAX[kind]
        last_closings = {closing: line.rfind(closing) for _, closing in block_comments}
        self.owner = [-1] * (len(line) + 1)
        self.context = [0] * (len(line) + 1)
        self.braces = [0] * (len(line) + 1)
        self.question = [False] * (len(line) + 1)
        self.bounds = {0: []}
        self.statements = []
        self.comments = []
        self.parameters = set()
        self.regex_spans = []
        self.formatted_spans = []
        self.ternary_colons = set()
        ternaries = Counter()
        self.quotes = quotes = QuoteIndex(line)
        openings = {}
        signatures = {m.end() - 1 for m in re.finditer(
            r'\b(?:def\s+[A-Za-z_$][\w$]*\s*+|function\s*+(?:\*\s*+)?(?:[A-Za-z_$][\w$]*\s*+)?)[(]', line)}
        methods = {m.end() - 1 for m in re.finditer(
            r'(?:^|[;,{}])\s*(?:(?:async|static|get|set)\s+)*[A-Za-z_$][\w$]*\s*\(', line)}
        type_pairs = bracket_pairs(line, angles=True) if kind == 'javascript' else {}
        annotation_cache = {}

        def signature_tail(position):
            position = SPACE.match(line, position).end()
            if line[position:position + 1] != ':':
                return position
            position = SPACE.match(line, position + 1).end()
            visited = []
            while position < len(line):
                if position in annotation_cache:
                    position = annotation_cache[position]
                    break
                if line.startswith('=>', position) or line[position] in ';=':
                    break
                if line[position] == '{' and visited and line[visited[-1]] not in '|&':
                    break  # Method body after a return type, not a type literal.
                visited.append(position)
                if position in type_pairs:
                    function_type = line[position] == '('
                    position = SPACE.match(line, type_pairs[position] + 1).end()
                    if function_type and line.startswith('=>', position):
                        position += 2
                elif line[position] == '{':
                    break
                else:
                    position += 1
                position = SPACE.match(line, position).end()
            for offset in visited:
                annotation_cache[offset] = position
            return position

        regex_allowed = True
        stack = [0]
        brace_depth = 0
        question = False
        index = 0
        while index < len(line):
            self.context[index] = stack[-1]
            self.braces[index] = brace_depth
            self.question[index] = question
            if (kind == 'javascript' and line[index] == '/' and regex_allowed
                    and not line.startswith(('//', '/*'), index)):
                # ECMAScript's expression-start heuristic: escaped slashes and
                # character classes do not terminate a regular expression.
                end = regex_end(line, index)
                if end is not None:
                    self.regex_spans.append((index, end))
                    index = end
                    regex_allowed = False
                    continue
            if kind == 'javascript' and (line[index].isalpha() or line[index] in '_$'):
                word = re.compile(r'[\w$]+').match(line, index)
                regex_allowed = word[0] in REGEX_KEYWORDS
                # Keep structural arrays populated at every offset.
                for offset in range(index, word.end()):
                    self.context[offset] = stack[-1]
                    self.braces[offset] = brace_depth
                    self.question[offset] = question
                index = word.end()
                continue
            if quote_start(line, index, quotes):
                end = min(quoted_end(line, index), len(line))
                formatted = 'f' in literal_prefix(line, index).lower()
                if formatted or line[index] == '`':
                    self.formatted_spans.append((index, end, formatted))
                regex_allowed = False
                query = False
                expansion_end = index
                for offset in range(index, min(end + 1, len(line))):
                    self.owner[offset] = end
                    self.context[offset] = stack[-1]
                    self.braces[offset] = brace_depth
                    if offset >= expansion_end and (line[offset].isspace() or line[offset] in ';|'):
                        query = False
                    self.question[offset] = query
                    if line.startswith('${', offset) and offset >= expansion_end:
                        expansion_end = braced_end(line, offset)
                    if (line[offset] == '?' and offset >= expansion_end
                            and (not offset or line[offset - 1] != '\\')):
                        query = True
                question = False
                index = end + 1
                continue
            # Comments contain no source nesting. Credential matching still
            # examines their text below; only structural accounting stops here.
            block = next(((opening, closing) for opening, closing in block_comments
                          if line.startswith(opening, index)), None)
            if block:
                opening, closing_marker = block
                closing = (line.find(closing_marker, index + len(opening))
                           if last_closings[closing_marker] >= index + len(opening) else -1)
                if closing >= 0 or kind != 'unknown':
                    end = len(line) if closing < 0 else closing + len(closing_marker)
                    self.comments.append((index, end))
                    index = end
                    continue
            if (any(line.startswith(marker, index) for marker in line_comments)
                    and (kind not in ('shell', 'unknown', 'ini')
                         or not index or line[index - 1].isspace()
                         or line[index - 1] in ';(&|')):
                self.comments.append((index, len(line)))
                break
            char = line[index]
            if kind == 'javascript' and not char.isspace():
                if line.startswith(('++', '--'), index):
                    # Preserve expression-start for prefix operators, but a
                    # postfix operator ends an expression just like its operand.
                    # Consume both characters so the second cannot reset state.
                    for offset in (index, index + 1):
                        self.context[offset] = stack[-1]
                        self.braces[offset] = brace_depth
                        self.question[offset] = question
                    index += 2
                    continue
                regex_allowed = char in '=(:,[!&|?;{}~+-*%/^<>'
            if char.isspace() or char in ';|':
                question = False
            if char == '\\':
                index += 2
                continue
            if char == '?':
                question = True
                if (not line.startswith(('??', '?.', '?='), index)
                        and not re.compile(r'\s*:').match(line, index + 1)
                        and (not index or line[index - 1] != '?')):
                    ternaries[stack[-1]] += 1
            elif char == ':' and ternaries[stack[-1]] and not line.startswith(':=', index):
                self.ternary_colons.add(index)
                ternaries[stack[-1]] -= 1
            elif char == ';':
                ternaries[stack[-1]] = 0
            if char in '([{':
                if len(stack) > MAX_NESTING:
                    raise ScanError('pattern scan nesting work limit exceeded [masked]')
                context = len(self.bounds)
                self.bounds[context] = []
                if char == '(':
                    openings[context] = index
                    if index in signatures:
                        self.parameters.add(context)
                stack.append(context)
                brace_depth += char in '{['
            elif char in ')]}':
                context = stack[-1]
                if char == ')' and context in openings:
                    tail = signature_tail(index + 1)
                    if (line.startswith('=>', tail)
                            or (openings[context] in methods and line[tail:tail + 1] == '{')):
                        self.parameters.add(context)
                self.bounds[stack[-1]].append(index)
                if len(stack) > 1:
                    stack.pop()
                brace_depth -= char in '}]'
            elif char in ',;':
                self.bounds[stack[-1]].append(index)
            if char in ';|' or (char == '&' and (not question or line.startswith('&&', index))):
                self.statements.append(index)
            index += 1
        self.context[len(line)] = stack[-1]
        self.length = len(line)
        for boundaries in self.bounds.values():
            boundaries.append(len(line))
        self.statements.append(len(line))

    def without_comments(self, line):
        """Replace tracked trivia once, keeping all match offsets unchanged."""
        parts = []
        start = 0
        for opening, end in self.comments:
            parts.extend((line[start:opening], ' ' * (end - opening)))
            start = end
        parts.append(line[start:])
        return ''.join(parts)

    def rhs_end(self, start, delimiters=False):
        boundaries = self.bounds[self.context[start]] if delimiters else self.statements
        return boundaries[bisect_right(boundaries, start - 1)]


def shell_word_boundaries(line):
    """Index unquoted word endings once; quotes and expansions may contain spaces."""
    boundaries = []
    index = 0
    while index < len(line):
        if line[index] == '\\':
            index += 2
        elif line[index] in '\"\'`':
            index = quoted_end(line, index) + 1
        elif line.startswith('$(', index):
            index = command_end(line, index)
        elif line.startswith('${', index):
            index = braced_end(line, index)
        else:
            if line[index].isspace():
                boundaries.append(index)
            index += 1
    boundaries.append(len(line))
    return boundaries


def high_entropy(value):
    # Public URL scheme syntax does not contribute credential entropy/length.
    value = re.sub(r'^https?://', '', value)
    if len(value) < 20:
        return False
    counts = Counter(value)
    entropy = -sum((n / len(value)) * math.log2(n / len(value)) for n in counts.values())
    return entropy >= 3.5


def findings(text, path=None, budget=None):
    """Yield only (line number, rule id); never return matched values."""
    if budget is None:
        budget = [MAX_FILE_WORK]
    kind = file_type(text, path)
    shell = kind in SHELL_TYPES
    source_file = kind in SOURCE_TYPES
    typed_source = kind in ('python', 'javascript')
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > MAX_LINE_CHARS:
            raise ScanError('pattern scan line work limit exceeded [masked]')
        rules = set()
        work = len(line)
        value_end = len(line.rstrip(' \t='))
        raw_assignments = list(assignments_in(line, kind))
        provider_matches = [(rule, match) for rule, pattern in TOKEN_RULES
                            for match in pattern.finditer(line)]
        # Most repository lines contain no credential-shaped name or provider.
        # Avoid all quote/structure/token passes on those lines. Keep structural
        # work-limit enforcement for potentially deeply nested input.
        if (not provider_matches and not any(credential_rule(m['key'] or m['name'])
                                            for m in raw_assignments)
                and not any(marker in line for marker in ('/*', '<!--', '--[['))
                and sum(line.count(c) for c in '([{') <= MAX_NESTING):
            budget[0] -= work
            if budget[0] < 0:
                raise ScanError('pattern scan file work limit exceeded [masked]')
            continue
        state = LineState(line, kind)
        assignment_text = state.without_comments(line)
        # Only rescan when comment elision actually changed the line.
        assignments = raw_assignments
        if assignment_text != line:
            assignments = sorted({m.span(): m for m in
                                  raw_assignments + list(assignments_in(assignment_text, kind))}.values(),
                                 key=lambda item: item.end())
        word_ends = shell_word_boundaries(line) if shell or any(m['option'] for m in assignments) else []
        tokens = (list(lexemes(line, comment_at_start=False, quotes=state.quotes))
                  if provider_matches else [])
        token_starts = [start for start, _, _ in tokens]
        assignment_ranges = []
        for item in assignments:
            end = min(state.rhs_end(item.end(), True), state.rhs_end(item.end()))
            if shell:
                end = min(end, word_ends[bisect_right(word_ends, item.end() - 1)])
            owner = state.owner[item.start()]
            if owner >= 0 and item.end() <= owner:
                end = min(end, owner)
            assignment_ranges.append((item.end(), end))
        range_starts = [start for start, _ in assignment_ranges]
        range_ends = []
        furthest = -1
        for _, end in assignment_ranges:
            furthest = max(furthest, end)
            range_ends.append(furthest)
        for rule, pattern in TOKEN_RULES:
            for match in pattern.finditer(line):
                # Pure reference names are not credentials. Other placeholder
                # wrappers are exempt only in assignments; bare prose still reports.
                token_index = bisect_right(token_starts, match.start()) - 1
                enclosing = match[0]
                if token_index >= 0 and tokens[token_index][1] >= match.end():
                    enclosing = tokens[token_index][2]
                if ENV_REFERENCE.fullmatch(enclosing):
                    continue
                assignment_index = bisect_right(range_starts, match.start()) - 1
                in_assignment = (assignment_index >= 0
                                 and range_ends[assignment_index] >= match.end())
                if not (in_assignment and placeholder(enclosing)):
                    rules.add(rule)
        for match in assignments:
            # Quoted TOML prefixes are namespaces, not credential names. Keep
            # bare dotted segments for conventional names such as prefix.api.key.
            name = re.sub(r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*\.\s*''',
                          '', match['key'] or match['name'])
            rule = credential_rule(name)
            if rule is None:
                continue
            if (match['operator'] == '=>' and
                    (path is None or kind == 'javascript')):
                continue
            if match['operator'] == '->' and kind in ('c-family', 'php'):
                continue
            if (match['operator'] == ':' and match.end() - 1 in state.ternary_colons
                    and kind == 'javascript'):
                continue
            start = match.end()
            typed = (TYPE_ANNOTATION.match(assignment_text, start, min(len(line), start + 4096))
                     if match['operator'] == ':' else None)
            if typed and not (
                    typed.end() < value_end
                    and (typed_source or re.search(r'\s=|=\s', typed[0]))):
                typed = None
            if typed:
                work += typed.end() - start
                if work > MAX_LINE_WORK:
                    raise ScanError('pattern scan line work limit exceeded [masked]')
                start = typed.end()
            stop = state.rhs_end(start)
            if source_file and state.context[start]:
                stop = min(stop, state.rhs_end(start, True))
            if shell or match['option']:
                word_start = SPACE.match(line, start).end()
                stop = min(stop, word_ends[bisect_right(word_ends, word_start)])
            owner = state.owner[match.start()]
            embedded = owner >= match.end() and line[match.start()] not in '\"\''
            if owner >= match.end():
                stop = min(stop, owner)
            # Bound flow values before copying/lexing the suffix. Bare config
            # words retain commas and other punctuation as literal characters.
            if match['operator'] == ':' and state.braces[match.start()] > 0:
                stop = min(stop, state.rhs_end(start, True))
            work += stop - start
            if work > MAX_LINE_WORK:
                raise ScanError('pattern scan line work limit exceeded [masked]')
            rest = line[start:stop]
            # Only bare config nulls are sentinels. Quoted "null" is a string
            # (and remains reportable for OC); source literals are unchanged.
            if rest.strip() in ('', '~', 'null', 'Null', 'NULL'):
                continue
            if (match['operator'] == ':' and not typed
                    and typed_source
                    and state.context[match.start()] in state.parameters):
                # Typed function parameters are declarations, not values.
                # A literal default above still follows the assignment path.
                continue
            if state.question[match.start()] and rule == 'law-oc':
                rest = rest.split('&', 1)[0]
            if any(a <= match.start() < b for a, b in state.regex_spans):
                continue
            embedded_chunks = None
            if embedded:
                formatted_owner = next(((a, b, f) for a, b, f in state.formatted_spans
                                        if a <= match.start() < b), None)
                if formatted_owner:
                    # Preserve the enclosing template's interpolation mode even
                    # though the embedded query RHS has no opening quote.
                    embedded_chunks = static_chunks(rest, formatted=formatted_owner[2])
            source = not embedded and source_file
            # Calls and access chains are references even without a source suffix;
            # bare config/shell words otherwise remain literal values.
            expression = re.match(r'\s*[A-Za-z_$][\w$]*(?:\s*\(|\.[A-Za-z_$]|\[)', rest)
            if embedded_chunks is not None:
                values = (value for chunk in embedded_chunks
                          for value in literal_candidates(chunk))
            else:
                values = candidates(rest, comment_at_start=False,
                                    source=source or (path is None and bool(expression)),
                                    shell=shell)
            for value in values:
                if not placeholder(value) and (rule == 'law-oc' or high_entropy(value)):
                    rules.add(rule)
        budget[0] -= work
        if budget[0] < 0:
            raise ScanError('pattern scan file work limit exceeded [masked]')
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
    root, paths = repository_files(root, worktree=True)
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
            if info.st_size > MAX_FILE_BYTES:
                raise ScanError('pattern scan file work limit exceeded [masked]')
            with path.open('rb') as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ScanError('pattern scan file work limit exceeded [masked]')
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
        budget = [MAX_FILE_WORK]
        for text in texts:
            lines = text.splitlines()
            for line, rule in findings(text, relative, budget):
                digest = hashlib.sha256(lines[line - 1].encode('utf-8')).hexdigest()
                if (relative, rule, digest) not in ALLOWLIST:
                    file_matches.add((line, rule))
        matches.extend((safe_path, line, rule) for line, rule in sorted(file_matches))
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd(),
                        help='Git worktree to scan (default: current working directory)')
    args = parser.parse_args()
    try:
        matches = scan(args.root)
    except RecursionError:
        print('ERROR: pattern scan nesting work limit exceeded [masked]')
        return 2
    except ScanError as exc:
        print(f'ERROR: {exc}')
        return 2
    for path, line, rule in matches:
        print(f'{path}:{line}: {rule} [masked]')
    print(f'Pattern scan: {len(matches)} finding(s).')
    return 1 if matches else 0


if __name__ == '__main__':
    raise SystemExit(main())
