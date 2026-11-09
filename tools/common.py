# SPDX-License-Identifier: GPL-3.0-only
"""경로, 비밀 제거, JSON 및 계약 색인 공용 함수."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from credentials import selected_key
from git_read import run_git


def source_date(value):
    """Accept only a real calendar date in the two source wire formats."""
    if not isinstance(value, str) or not re.fullmatch(r'(?:\d{8}|\d{4}\.\d{2}\.\d{2})', value):
        raise ValueError('원문 날짜 형식/달력 오류: 보류')
    try:
        return datetime.strptime(value, '%Y.%m.%d' if '.' in value else '%Y%m%d').date()
    except ValueError:
        raise ValueError('원문 날짜 형식/달력 오류: 보류') from None

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('KK_ROOT', CODE_ROOT)).resolve()

def run_cli(main):
    """Redact complete CLI output and uncaught failures before emitting anything.

    Buffering also protects split writes and argparse's SystemExit diagnostics.
    Child processes must capture/discard BOTH output streams (enforced by the
    safety regression); captured text is redacted here if emitted, not before
    parsing. Python stream redirection does not intercept inherited child FDs.
    Only already selected credentials are reused; no credential file is opened.
    """
    from secret_scan import redact_diagnostic
    destinations = (sys.stdout, sys.stderr)
    for stream in destinations:
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    buffers = (io.StringIO(), io.StringIO())
    with redirect_stdout(buffers[0]), redirect_stderr(buffers[1]):
        try:
            status = main()
        except SystemExit as exc:
            status = exc.code
        except KeyboardInterrupt:
            print('ERROR: interrupted', file=sys.stderr)
            status = 130
        except Exception as exc:
            # Do not render a traceback: its frames can contain input paths too.
            try:
                message = str(exc)
            except Exception:
                message = 'command failed'
            print('ERROR:', message, file=sys.stderr)
            status = 1
        if status is not None and not isinstance(status, int):
            print(status, file=sys.stderr)
            status = 1
    for destination, buffer in zip(destinations, buffers):
        try:
            diagnostic = redact_diagnostic(buffer.getvalue())
        except Exception:
            diagnostic = '[redacted]'  # Redaction failure must never expose input.
        try:
            print(diagnostic, end='', file=destination)
        except (OSError, ValueError):
            status = 1  # Output failure must not rerun or rewrite completed work.
    return status


def now():
    return datetime.now(timezone.utc).isoformat()

def mask(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            masked_key = mask(key)
            if masked_key in result:
                raise ValueError('masked mapping keys collide')
            result[masked_key] = ('***' if isinstance(key, str) and key.lower() == 'oc' else mask(item))
        return result
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'''(?i)([?&](?:amp;)?\x4fC=)[^&#\s"'<>`\)\]]+''', r'\1***', value)
        secret = selected_key()
        if secret:
            from secret_scan import ScanError, matching_encodings, value_needles
            value = value.replace(secret, '***')
            try:
                needles = value_needles(secret)
            except ScanError:
                raise ValueError('Cannot safely mask selected credential.') from None
            # Preserve raw-value replacement; suppress the complete remaining
            # string on encoded matches, avoiding normalized-offset reconstruction.
            if next(matching_encodings(value.encode('utf-8', errors='surrogatepass'), needles), None):
                value = '***'
    return value

def canonical(data, reject_masked=False):
    if reject_masked and data != mask(data):
        raise ValueError('stored payload contains unmasked secret')
    return (json.dumps(mask(data), ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')

def save_json(path, data):
    safe_write_bytes(path, canonical(data))


def safe_write_bytes(path, data):
    """All tool writes use this checked, repository-local byte sink."""
    path = Path(path)
    check_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_output_path(path)
    return path.write_bytes(data)


def safe_write_text(path, text):
    """Write UTF-8 without platform newline translation through the byte sink."""
    return safe_write_bytes(path, text.encode('utf-8'))

def check_output_path(target, *, root=None, directory=False, require_exists=False):
    """Reject linked/escaped paths; metadata-only options also guard snapshot reads."""
    try:
        target = Path(target)
        if '..' in target.parts:
            raise ValueError
        root, target = (ROOT if root is None else Path(root)).absolute(), target.absolute()
        relative = target.relative_to(root)
        if (not relative.parts and not (directory and require_exists)) or '..' in relative.parts:
            raise ValueError
        current = root
        for part in (None, *relative.parts[:-1]):
            if part is not None:
                current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISDIR(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                raise ValueError
        try:
            info = target.lstat()
        except FileNotFoundError:
            if require_exists:
                raise ValueError from None
            info = None
        regular = stat.S_ISDIR if directory else stat.S_ISREG
        if info is not None and (not regular(info.st_mode)
                or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise ValueError
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise ValueError('Unsafe output path; repository-local real directories required.') from None


def check_tracked_links(root=ROOT):
    """Cheap read-only Git policy check, usable before any maintenance writes."""
    try:
        entries = run_git(root, ['ls-files', '-s', '-z']).stdout.split(b'\0')
    except (OSError, subprocess.CalledProcessError):
        raise ValueError('Cannot inspect tracked symlink modes.') from None
    modes = {entry.partition(b' ')[0] for entry in entries}
    if b'120000' in modes:
        raise ValueError('repository: tracked symlinks are not allowed')
    if b'160000' in modes:
        raise ValueError('repository: tracked gitlinks are not allowed')


@contextmanager
def staged_files(targets):
    """Prepare repository-local outputs, then replace or roll back the unit."""
    targets = tuple(targets)
    for target in targets:
        check_output_path(target)
    staged, backups, replaced = {}, {}, []
    try:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            check_output_path(target)
            for table in (staged, backups):
                fd, name = tempfile.mkstemp(prefix='.' + target.name + '-', dir=target.parent)
                os.close(fd)
                table[target] = Path(name)
            if target.exists():
                safe_write_bytes(backups[target], target.read_bytes())
            else:
                backups[target].unlink()
        yield staged
        for target, temporary in staged.items():
            check_output_path(target)
            os.replace(temporary, target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            try:
                check_output_path(target)
            except ValueError:
                continue  # Never restore through a parent that became unsafe.
            if backups[target].exists():
                os.replace(backups[target], target)
            else:
                target.unlink()
        raise
    finally:
        for temporary in (*staged.values(), *backups.values()):
            try:
                check_output_path(temporary)
            except ValueError:
                continue  # Never clean up through a substituted parent.
            temporary.unlink(missing_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()

def load_index(root=ROOT, *, read_text=None, inspect_bytes=None):
    read_text = read_text or (lambda path: path.read_text(encoding='utf-8'))
    lock = readjson(read_text(root / 'deps.lock'))['kapa_skills']
    sibling = Path(os.environ.get('KK_SKILLS_ROOT', CODE_ROOT.parent / 'kapa_skills')).resolve()
    if not sibling.is_dir():
        raise ValueError('검증 불가: kapa_skills 형제 체크아웃 없음')
    commit = lock['commit']
    try:
        if commit == 'WORKTREE':
            text = read_text(sibling / 'docs/law-index.json')
        else:
            if not re.fullmatch(r'[0-9a-f]{40}', commit):
                raise ValueError('commit은 40자리 sha 또는 WORKTREE')
            raw = run_git(sibling, ['cat-file', '-p', commit + ':docs/law-index.json']).stdout
            if inspect_bytes is not None:
                inspect_bytes(sibling / 'docs/law-index.json', raw)
            text = raw.decode('utf-8')
        data = readjson(text)
        if data.get('schema') != 1:
            raise ValueError('지원하지 않는 색인 schema')
        return data, sibling, commit
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise ValueError('검증 불가: 잠금 판본 law-index를 읽지 못함') from exc

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('중복 JSON 키: ' + key)
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError('비유한 JSON 상수 금지: ' + value)


def readjson(text):
    """Parse strict JSON text, including nested values."""
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


def frontmatter(text):
    """제한 YAML: 각 값은 JSON 스칼라/배열/객체 또는 한 줄 문자열."""
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError('frontmatter 없음')
    result = {}
    for line in text.split('\n---\n', 1)[0][4:].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition(':')
        if not sep or key in result:
            raise ValueError('frontmatter 중복 키 또는 지원하지 않는 형식: ' + key)
        try:
            result[key] = readjson(value.strip())
        except json.JSONDecodeError:
            result[key] = value.strip()
    return result

def court_slug(value):
    """Normalize court names only for IDs and directories, never source fields."""
    return re.sub(r'\s+', '', value)


def relation(kind, src, dst, scope='', found_by='cites-article', evidence=''):
    rid = 'rel-' + sha(json.dumps([kind, src, dst, scope], ensure_ascii=False, separators=(',', ':')).encode())[:20]
    return dict(id=rid, type=kind, src=src, dst=dst, scope=scope, found_by=[found_by], review='unreviewed', evidence=evidence, reviewed_by=None, reviewed_at=None)

def add_relations(rows, replace_generated_for=None, path=None):
    path = path if path is not None else ROOT / 'relations/relations.jsonl'
    old = [readjson(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()] if path.exists() else []
    # Only exclusively automatic, unreviewed citations are replaceable.
    if replace_generated_for:
        old = [x for x in old if not (x.get('src') == replace_generated_for
               and x.get('type') == 'cites' and x.get('review') == 'unreviewed'
               and x.get('found_by') == ['cites-article'])]
    unique_old = {x['id']: x for x in old}
    for row in rows:
        unique_old.setdefault(row['id'], row)
    old = list(unique_old.values())
    safe_write_text(path, ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in sorted(old, key=lambda x: x['id'])))
