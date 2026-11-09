# SPDX-License-Identifier: GPL-3.0-only
"""Small Markdown context scanner shared by command and link validation.

This is not a renderer: it separates code from prose, preserving newlines so
consumers never interpret examples as links or frontmatter as body prose.
"""
import csv
import io
import json
import re
from html import unescape

LAUNCHER = re.compile(r'(?:python(?:\d+(?:\.\d+)*)?|py|git|curl|wget|bash|sh|zsh|pwsh|powershell|cmd|npm|npx|pip|pip3|gh|rm|mv|cp|node|ruby|perl|docker|podman|make|uv|ssh|scp|sftp|rsync|telnet|nc|ncat|netcat|socat|ftp|tftp|rsh|rcp|mosh|plink|pscp|psftp)(?:\.exe)?', re.I)
SUBCOMMAND_CLI = {'git', 'npm', 'npx', 'pip', 'pip3', 'gh', 'docker', 'podman', 'uv'}
TOKEN = re.compile(r'''"[^"\n]*"|'[^'\n]*'|[^\s]+''')
MARKER = re.compile(r'^(?:[-*+]\s+|\d+[.)]\s+|[>$]\s*)')


def body(text):
    if text.startswith('---\n') and '\n---\n' in text[4:]:
        return text.split('\n---\n', 1)[1]
    return text


def strip_markers(line):
    line = line.lstrip()
    while match := MARKER.match(line):
        line = line[match.end():].lstrip()
    return line


def executable(token):
    return bool(LAUNCHER.fullmatch(token) or re.match(r'^(?:/|\./|\.\\|\.\./|\.\.\\|[A-Za-z]:[/\\]|tools/)\S+', token))


def argument(token):
    # Options, source IDs, paths, URLs, filenames and shell operators have
    # syntactic meaning independent of any natural-language phrase list.
    return bool(re.match(r'^[-/\\.$~]|^\d+$|^[A-Za-z][A-Za-z0-9+.-]*://|^[|&;<>]', token)
                or re.search(r'[/\\]|\w\.\w|^[A-Za-z0-9_@.-]+:[^\s]+$', token))


WRAPPERS = {
    'command', 'builtin', 'exec', 'eval', 'env', 'sudo', 'doas', 'nohup',
    'nice', 'time', 'timeout', 'stdbuf', 'setsid', 'chroot', 'xargs',
    'watch', 'flock', 'ionice', 'taskset', 'unbuffer', 'script',
}
WRAPPER_OPTION_ARGS = {
    'env': {'-u', '--unset', '-C', '--chdir', '-S', '--split-string'},
    'sudo': {'-u', '-g', '-h', '-p', '-C', '-T'}, 'doas': {'-u', '-C'},
    'nice': {'-n', '--adjustment'}, 'time': {'-f', '-o', '--format', '--output'},
    'timeout': {'-s', '--signal', '-k', '--kill-after'},
    'stdbuf': {'-i', '-o', '-e'}, 'chroot': {'--userspec', '--groups'},
    'xargs': {'-a', '-d', '-E', '-I', '-L', '-n', '-P', '-s'},
    'watch': {'-n', '--interval'}, 'flock': {'-w', '--wait', '-E'},
    'ionice': {'-c', '-n', '-p', '-P', '-u'}, 'taskset': {'-p'},
    'script': {'-O', '-I', '-B', '-T'},
}
ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')


def command_line(line, code=False):
    prompted = bool(re.match(r'^\s*(?:\$|>)\s+', line))
    tokens = [t.strip('\"\'') for t in TOKEN.findall(strip_markers(line))]
    while tokens:
        if ASSIGNMENT.match(tokens[0]):
            tokens.pop(0)
            continue
        if tokens[0].lower() not in WRAPPERS:
            break
        wrapper = tokens.pop(0).lower()
        while tokens and tokens[0].startswith('-'):
            option = tokens.pop(0)
            if option == '--':
                break
            if option in WRAPPER_OPTION_ARGS.get(wrapper, set()) and tokens:
                tokens.pop(0)
        if wrapper in {'timeout', 'chroot', 'flock', 'taskset'} and tokens:
            tokens.pop(0)  # duration, directory, lock file, or CPU mask/list
        if wrapper in {'eval', 'script'} and len(tokens) == 1:
            tokens = [t.strip('\"\'') for t in TOKEN.findall(tokens[0])]
    if not tokens or not executable(tokens[0]):
        return False
    launcher, args = tokens[0], tokens[1:]
    if not args:
        return False
    # Sentence punctuation plus several bare words is prose, even when a
    # version number or filename occurs in the sentence. Explicit shell
    # options/paths/URLs remain commands, including quoted -c programs.
    if (len(args) >= 3 and args[-1].endswith('.')
            and not any(re.match(r'^[-/\\\\.$~]|^[A-Za-z][A-Za-z0-9+.-]*://', t) for t in args)):
        return False
    if any(argument(t) for t in args):
        return True
    # Subcommand CLIs accept bare subcommands and operands, unlike language
    # runtimes. A sentence's punctuation/capitalization is not CLI syntax.
    return ((code or prompted) and launcher.lower().removesuffix('.exe') in
            (SUBCOMMAND_CLI | {'rm', 'mv', 'cp', 'ssh', 'scp', 'sftp', 'rsync', 'telnet', 'nc', 'ncat', 'netcat', 'socat', 'ftp', 'tftp', 'rsh', 'rcp', 'mosh', 'plink', 'pscp', 'psftp'}) and len(args) <= 2
            and all(re.fullmatch(r'[a-z0-9_@:+-]+', t) for t in args))


def inline_contexts(text):
    """CommonMark code spans may cross physical lines, but not block boundaries."""
    pos = 0
    for span in re.finditer(r'(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)', text, re.S):
        yield 'prose', text[pos:span.start()]
        yield 'inline', span[2].replace('\n', ' ')
        # Preserve line boundaries for link and prose consumers.
        yield 'prose', re.sub(r'[^\n]', ' ', span[0])
        pos = span.end()
    yield 'prose', text[pos:]


def contexts(text):
    """Yield (kind, content), where kind is prose, code or inline.

    Fence delimiters are excluded. Nested quote/list prefixes and indented
    blocks are recognized before inline backtick spans are split.
    """
    fence_char, fence_size = '', 0
    pending = []
    for line in body(text).splitlines(keepends=True):
        clean = strip_markers(line)
        marker = re.match(r'^(`{3,}|~{3,})(.*)$', clean.rstrip('\r\n'))
        indented = line.startswith(('    ', '\t')) or re.match(r'^(?: {0,3}> ?)+(?: {4}|\t)', line)
        if fence_char or marker or indented or not clean.strip():
            yield from inline_contexts(''.join(pending))
            pending = []
        if fence_char:
            if marker and marker[1][0] == fence_char and len(marker[1]) >= fence_size and not marker[2].strip():
                fence_char, fence_size = '', 0
            else:
                yield 'code', line
            yield 'prose', '\n'
            continue
        if marker:
            fence_char, fence_size = marker[1][0], len(marker[1])
            # An executable fence info string can itself conceal a command.
            yield 'code', marker[2]
            yield 'prose', '\n'
            continue
        if line.startswith(('    ', '\t')) or re.match(r'^(?: {0,3}> ?)+(?: {4}|\t)', line):
            yield 'code', line
            yield 'prose', '\n'
            continue
        pending.append(line)
    yield from inline_contexts(''.join(pending))


def prose(text):
    return ''.join(content for kind, content in contexts(text) if kind == 'prose')


def code_command(line):
    if command_line(line, code=True):
        return True
    # In code, inspect every shell segment, including substitutions and unknown
    # wrappers. Unlike prose, a launcher need not be the first token.
    tokens = re.findall(r'[^\s\"\';&|`(){}]+|[;&|]', line)
    for index, token in enumerate(tokens):
        if not executable(token):
            continue
        args = []
        for following in tokens[index + 1:]:
            if following in {';', '&', '|'}:
                break
            args.append(following)
        if index and tokens[index - 1] in {'&', '|'}:
            return True  # A piped interpreter can execute stdin without flags.
        if command_line(' '.join([token] + args), code=True):
            return True
    return False


def generic_command(text):
    """Inline code is data only when it is an identifier/path, not a command."""
    tokens = TOKEN.findall(text.strip())
    if len(tokens) < 2:
        return bool(re.search(r'\$\(|\|\||&&|;', text))
    # Multiword ASCII verb/operand sequences are command-shaped even when all
    # arguments are bare words (for example an unfamiliar CLI subcommand).
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', tokens[0]):
        return (any(argument(token) or '=' in token for token in tokens[1:])
                or all(re.fullmatch(r'[A-Za-z0-9_.:@+-]+', token) for token in tokens[1:]))
    return bool(re.search(r'\$\(|[|;]|&&', text))


def visible_prose(text):
    """Normalize presentation syntax without treating inert data as instructions."""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'</?(?:p|div|li|h[1-6]|br|blockquote)\b[^>]*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!?\[([^\]\n]*)\]\([^\n]*?\)', r'\1', text)
    text = re.sub(r'\[([^\]\n]+)\]\[[^\]\n]*\]', r'\1', text)
    text = re.sub(r'^ {0,3}#{1,6}\s+|\s+#+\s*$', '', text, flags=re.M)
    text = re.sub(r'(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1', r'\2', text)
    return re.sub(r'[^\S\r\n]', ' ', unescape(text))


def prose_command(line):
    clean = strip_markers(line).strip()
    if command_line(line):
        return True
    tokens = TOKEN.findall(clean)
    if not tokens or not re.fullmatch(r'[a-z][a-z0-9._-]*', tokens[0]):
        return False
    if not clean.isascii() or clean.endswith(('.', '?')):
        return False
    return len(tokens) >= 2


def yaml_scalar_valid(value):
    value = value.strip()
    if not value or value.startswith('#'):
        return True
    try:
        if value.startswith(('"', '[', '{')):
            parsed = json.loads(value)
            return isinstance(parsed, (str, list, dict))
        if value.startswith("'"):
            return bool(re.fullmatch(r"'(?:[^']|'')*'", value))
    except ValueError:
        return False
    # Plain scalars intentionally exclude quote/collection syntax, tags,
    # anchors, block scalars and other YAML features outside this subset.
    return not any(char in value for char in '[]{}\"\'') and not value.startswith(('!', '&', '*', '|', '>'))


def yaml_line_valid(line):
    clean = line.strip()
    if not clean or clean.startswith('#') or clean in {'---', '...'}:
        return True
    if clean.startswith('- '):
        clean = clean[2:].strip()
        if not clean:
            return False
    match = re.fullmatch(r'([A-Za-z_가-힣][A-Za-z0-9_가-힣 .-]*):(?:[ \t]+(.*)|[ \t]*)', clean)
    if match:
        return yaml_scalar_valid(match[2] or '')
    return line.strip().startswith('- ') and yaml_scalar_valid(clean)


def data_fence_valid(info, lines):
    content = '\n'.join(lines)
    try:
        if info == 'json':
            json.loads(content)
        elif info == 'jsonl':
            for line in lines:
                if line.strip():
                    json.loads(line)
        elif info in {'yaml', 'yml'}:
            # Deliberately limited safe subset; no dependency or object loading.
            if not all(yaml_line_valid(line) for line in lines):
                return False
        elif info in {'csv', 'tsv'}:
            rows = list(csv.reader(io.StringIO(content), delimiter=',' if info == 'csv' else '\t', strict=True))
            widths = {len(row) for row in rows if row}
            if len(widths) != 1 or next(iter(widths), 0) < 2:
                return False
        elif info == 'text':
            return not any(generic_command(strip_markers(line)) or prose_command(line) or code_command(line) for line in lines)
        else:
            return False
    except (ValueError, csv.Error):
        return False
    return True


def unsafe_code(text):
    """Read-path fences are allowlisted data, never executable languages."""
    fence_char, fence_size, info = '', 0, ''
    quote_depth = 0
    lines = []
    for line in body(text).splitlines():
        clean = strip_markers(line)
        marker = re.match(r'^(`{3,}|~{3,})(.*)$', clean)
        if fence_char:
            if marker and marker[1][0] == fence_char and len(marker[1]) >= fence_size and not marker[2].strip():
                if not data_fence_valid(info, lines):
                    return True
                fence_char = ''
                continue
            content = line
            for _ in range(quote_depth):
                prefix = re.match(r'^ {0,3}>[ \t]?', content)
                if not prefix:
                    return True  # A quoted fence cannot consume outside prose.
                content = content[prefix.end():]
            lines.append(content)
            continue
        if marker:
            quote = re.match(r'^(?: {0,3}>[ \t]?)+', line)
            quote_depth = quote[0].count('>') if quote else 0
            fence_char, fence_size, info = marker[1][0], len(marker[1]), marker[2].strip().lower()
            lines = []
            if info not in {'json', 'jsonl', 'yaml', 'yml', 'csv', 'tsv', 'text'}:
                return True
        elif line.startswith(('    ', '\t')) or re.match(r'^(?: {0,3}> ?)+(?: {4}|\t)', line):
            return True
    return bool(fence_char)


def has_command(text):
    spans = list(contexts(text))
    return (unsafe_code(text)
            or any(prose_command(line) for line in visible_prose(''.join(
                content if kind == 'prose' else ' INLINE ' if kind == 'inline' else '\n'
                for kind, content in spans)).splitlines())
            or any(generic_command(content) or code_command(content)
                   for kind, content in spans if kind == 'inline'))
