#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run stock unittest discovery and verify its stderr completion summary.

Test code is trusted: this is an accidental early-exit check, not a sandbox.
"""
import codecs
import locale
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


def completion_errors(returncode, output):
    """Return every failed completion condition from unittest's stderr."""
    output = output.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))
    errors = []
    if returncode != 0:
        errors.append(f'Test runner failed (exit {returncode})')
    summaries = list(re.finditer(r'^Ran (\d+) tests? in [^\r\n]+$', output, re.MULTILINE))
    # Only the status belonging to the last summary decides completion. Later
    # stderr output (for example, atexit diagnostics) is not a runner status.
    lines = output[summaries[-1].end():].splitlines() if summaries else []
    final = next((line.strip() for line in lines if line.strip()), '')
    success = re.fullmatch(r'OK(?: \([^\r\n]*\))?', final)
    if not summaries:
        errors.append('Test completion failed: missing unittest summary (Ran N tests)')
    elif int(summaries[-1].group(1)) == 0:
        skipped = re.search(r'\bskipped=(\d+)\b', final) if success else None
        if skipped is None or int(skipped.group(1)) == 0:
            errors.append('Test completion failed: ran zero tests and reported no skips')
    if not success:
        errors.append('Test completion failed: missing final OK / OK (...) line')
    return errors


def output_encoding():
    getencoding = getattr(locale, 'getencoding', None)
    return (getencoding() if getencoding else locale.getpreferredencoding(False)) or 'utf-8'


def set_nonblocking(pipe):
    # os.set_blocking gained Windows pipe support in Python 3.12.
    if os.name == 'nt' and sys.version_info < (3, 12):
        import ctypes
        from ctypes import wintypes
        import msvcrt

        set_state = ctypes.WinDLL('kernel32', use_last_error=True).SetNamedPipeHandleState
        set_state.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                              ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD))
        set_state.restype = wintypes.BOOL
        mode = wintypes.DWORD(1)  # PIPE_NOWAIT
        if not set_state(msvcrt.get_osfhandle(pipe.fileno()), ctypes.byref(mode), None, None):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.set_blocking(pipe.fileno(), False)


def read_pipe(pipe, size):
    if os.name == 'nt' and sys.version_info < (3, 12):
        # Older CRT reads do not consistently map PIPE_NOWAIT's ERROR_NO_DATA
        # to BlockingIOError. ReadFile keeps that case distinct from EOF.
        import ctypes
        from ctypes import wintypes
        import msvcrt

        read = ctypes.WinDLL('kernel32', use_last_error=True).ReadFile
        read.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                         ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID)
        read.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(size)
        count = wintypes.DWORD()
        if not read(msvcrt.get_osfhandle(pipe.fileno()), buffer, size,
                    ctypes.byref(count), None):
            error = ctypes.get_last_error()
            if error == 232:  # ERROR_NO_DATA: writer is still alive
                raise BlockingIOError()
            if error == 109:  # ERROR_BROKEN_PIPE: all writers closed
                return b''
            raise ctypes.WinError(error)
        return buffer.raw[:count.value]
    return os.read(pipe.fileno(), size)


def buffered_bytes(pipe):
    """Snapshot the finite queued byte count, without consuming pipe data."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt

        peek = ctypes.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
        peek.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                         ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                         ctypes.POINTER(wintypes.DWORD))
        peek.restype = wintypes.BOOL
        available = wintypes.DWORD()
        if not peek(msvcrt.get_osfhandle(pipe.fileno()), None, 0, None,
                    ctypes.byref(available), None):
            error = ctypes.get_last_error()
            if error == 109:  # ERROR_BROKEN_PIPE: no buffered bytes remain
                return 0
            raise ctypes.WinError(error)
        return available.value
    import array
    import fcntl
    import termios

    available = array.array('i', [0])
    fcntl.ioctl(pipe.fileno(), termios.FIONREAD, available, True)
    return available[0]


class Stream:
    def __init__(self, pipe, destination, stop_reading, *, capture=False):
        self.pipe = pipe
        self.destination = destination
        self.stop_reading = stop_reading
        self.decoder = codecs.getincrementaldecoder(output_encoding())(errors='replace')
        self.lock = threading.Lock()
        self.captured = []
        self.capture = capture
        self.closed = False

    def drain(self):
        # Caller holds the lock. Read only the bytes already queued, not an
        # unbounded stream supplied by a busy descendant. The one-byte probe
        # on an empty pipe distinguishes EOF from a still-open writer.
        if self.closed:
            return
        remaining = max(1, buffered_bytes(self.pipe))
        while remaining and not self.closed:
            try:
                chunk = read_pipe(self.pipe, min(65536, remaining))
            except BlockingIOError:
                break
            remaining -= len(chunk)
            text = self.decoder.decode(chunk, final=not chunk)
            if self.capture:
                self.captured.append(text)
            self.destination.write(text)
            self.destination.flush()
            if not chunk:
                self.closed = True
                self.pipe.close()

    def snapshot(self):
        with self.lock:
            self.drain()
            self.capture = False

    def echo(self):
        while not self.stop_reading.is_set():
            with self.lock:
                self.drain()
                if self.closed:
                    return
            self.stop_reading.wait(0.05)
        with self.lock:
            if not self.closed:
                self.pipe.close()
                self.closed = True


def main():
    root = Path(__file__).resolve().parents[2]
    layout = subprocess.run(
        [sys.executable, '-I', '-B', str(root / '.github/ci/ci_layout_check.py')], cwd=root, capture_output=True)
    sys.stdout.buffer.write(layout.stdout)
    sys.stderr.buffer.write(layout.stderr)
    if layout.returncode:
        print('Test runner not started: layout check failed', file=sys.stderr)
        return 1
    command = [sys.executable, '-I', '-B', '-m', 'unittest', 'discover',
               '-s', 'tools', '-t', '.', '-p', 'test_*.py', '-v']
    # Keep stdout separate: trusted tests may print there, while the stock
    # TextTestRunner writes its summary to stderr. Drain both pipes concurrently.
    stop_reading = threading.Event()

    # Nonblocking raw pipes let readers stop even while descendants retain a
    # write handle. Closing a TextIOWrapper from another thread can block.
    with subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, bufsize=0) as process:
        for pipe in (process.stdout, process.stderr):
            set_nonblocking(pipe)
        streams = [Stream(process.stdout, sys.stdout, stop_reading),
                   Stream(process.stderr, sys.stderr, stop_reading, capture=True)]
        threads = [threading.Thread(target=stream.echo) for stream in streams]
        for thread in threads:
            thread.start()
        returncode = process.wait()
        deadline = time.monotonic() + 10
        # Include stderr already buffered at outer exit, then stop retaining it.
        # A fixed queued-byte snapshot cannot chase a continuously writing child.
        streams[1].snapshot()
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            stop_reading.set()
            for thread in threads:
                thread.join()
            print('Warning: output readers cut off after runner exit; '
                  'a descendant may still hold a pipe', file=sys.stderr)
    stderr = streams[1]
    errors = completion_errors(returncode, ''.join(stderr.captured))
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print('Test completion verified: stock unittest summary and final OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
