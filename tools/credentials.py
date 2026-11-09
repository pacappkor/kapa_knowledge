# SPDX-License-Identifier: GPL-3.0-only
"""Canonical credential selection shared by API use, masking and diagnostics."""
import os
from pathlib import Path

_file_selection = None


def environment_key():
    """Return stripped LAW_OC, or None only when it is unset or empty."""
    value = os.environ.get('LAW_OC')
    return value.strip() if value else None


def selected_key(*, env_only=False, load_file=False):
    """Use LAW_OC, or the fallback credential already selected by the API.

    Only the API opts into loading a credential file. Masking and diagnostics
    reuse that selected value without opening a file, even if it later changes.
    The scanner uses env_only=True and never consumes the fallback cache.
    Whitespace-only environment values are invalid, not fallback requests.
    """
    global _file_selection
    value = environment_key()
    if env_only:
        return value
    if value is None:
        filename = os.environ.get('LAW_OC_FILE') or str(Path(__file__).resolve().parents[2] / 'law_oc.txt')
        if _file_selection is not None and _file_selection[0] == filename:
            value = _file_selection[1]
        elif load_file:
            try:
                value = Path(filename).read_text(encoding='utf-8-sig').strip()
            except (OSError, UnicodeError):
                raise RuntimeError('LAW_OC 인증정보를 읽지 못함') from None
            if not value or '\n' in value:
                raise RuntimeError('LAW_OC 인증정보 형식 오류')
            _file_selection = (filename, value)
    if load_file and (not value or '\n' in value):
        raise RuntimeError('LAW_OC 인증정보 형식 오류')
    return value
