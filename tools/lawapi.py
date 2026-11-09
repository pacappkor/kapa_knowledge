# SPDX-License-Identifier: GPL-3.0-only
"""DRF Open API JSON client. 비밀 및 서버 응답은 예외에 출력하지 않는다."""
from pathlib import Path
import time
import urllib.parse
import urllib.request
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import mask, readjson
from credentials import selected_key

BASE = 'https://www.law.go.kr/DRF/'
_LAST = 0.0

def key():
    return selected_key(load_file=True)

def sanitize(value):
    return mask(value)

def request(endpoint, target, **params):
    global _LAST
    params.update({'OC': key(), 'target': target, 'type': 'JSON'})
    url = BASE + endpoint + '?' + urllib.parse.urlencode(params)
    for attempt in range(3):
        time.sleep(max(0, .5 - (time.monotonic() - _LAST)))
        try:
            _LAST = time.monotonic()
            req = urllib.request.Request(url, headers={'User-Agent': 'kapa-knowledge/0.1 (legal research)'})
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read()
            text = raw.decode('utf-8-sig')
            data = readjson(text)
            if not isinstance(data, dict) or not data:
                raise ValueError('empty or non-object')
            if any(k.lower() in {'error', 'errormsg', 'errorcode'} for k in data):
                raise ValueError('API error')
            root = next(iter(data.values()))
            if not isinstance(root, (dict, list)) or not root:
                raise ValueError('unexpected response root')
            return sanitize(data), sanitize(url)
        except Exception:
            if attempt == 2:
                raise RuntimeError(f'DRF {endpoint} target={target}: 응답 검증/통신 실패 (3회)') from None
            time.sleep(attempt + 1)

def search(target, query, page=1, display=100, **kw):
    return request('lawSearch.do', target, query=query, page=page, display=display, **kw)[0]

def service(target, ID, **kw):
    return request('lawService.do', target, ID=ID, **kw)[0]
