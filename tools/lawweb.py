# SPDX-License-Identifier: GPL-3.0-only
"""국가법령정보센터 조문 연결 목록. 검증 불가능한 빈 응답은 실패다."""
import html
from html.parser import HTMLParser
import re
import time
import urllib.parse
import urllib.request

BASE = 'https://www.law.go.kr'
ENDPOINTS = {'prec': 'lsStmdConPrecListR.do', 'expc': 'lsStmdConExpcListR.do', 'cgmexpc': 'lsStmdConCgmExpcListR.do'}

class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input':
            self.values[a.get('id', a.get('name', ''))] = a.get('value', '')

def get(path, form=None):
    for attempt in range(3):
        try:
            time.sleep(.5)
            req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(form).encode() if form else None, headers={'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/LSW/lsInfoP.do'})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
            for encoding in ('utf-8', 'cp949'):
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    pass
            raise ValueError('응답 인코딩 오류')
        except Exception:
            if attempt == 2:
                raise RuntimeError('law.go.kr 웹 통신/디코딩 실패') from None
            time.sleep(attempt + 1)

class AgencyDetail(HTMLParser):
    """Extract visible detail sections; never treat script text as source content."""
    def __init__(self):
        super().__init__()
        self.values, self.sections = {}, {}
        self.section, self.skip, self.heading = None, False, False
        self.subtitle, self.in_subtitle = '', False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {'script', 'style'}: self.skip = True
        if tag == 'input': self.values[a.get('id', '')] = a.get('value', '')
        if tag == 'div' and a.get('class') == 'subtit1': self.in_subtitle = True
        if tag == 'h4':
            self.section = a.get('id')
            self.heading = True
            self.sections.setdefault(self.section, [])
        if tag in {'p', 'br'} and self.section: self.sections[self.section].append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style'}: self.skip = False
        if tag == 'h4': self.heading = False
        if tag == 'div': self.in_subtitle = False
    def handle_data(self, data):
        if self.skip: return
        if self.in_subtitle: self.subtitle += data
        if self.section and not self.heading: self.sections[self.section].append(data)

def agency_detail(ident):
    url = '/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=' + ident
    parser = AgencyDetail()
    parser.feed(get(url))
    vals = parser.values
    if vals.get('cgmExpcDatSeq') != ident:
        raise ValueError('중앙부처 해석 상세 ID 불일치')
    case_no = vals.get('cgmExpcNo', '')
    subtitle = re.sub(r'\s+', ' ', parser.subtitle).strip().lstrip('[')
    if not case_no or case_no not in subtitle:
        raise ValueError('중앙부처 해석 기관/안건번호 확인 불가')
    payload = dict(안건번호=case_no, 해석기관명=subtitle.split(case_no, 1)[0].strip(),
                   해석일자=vals.get('cgmExpcYd', ''), 안건명=vals.get('cgmExpcNm', ''),
                   법령해석일련번호=ident)
    for section, key in {'inqGst': '질의요지', 'rpl': '회답', 'rsn': '이유', 'conLs': '참조조문'}.items():
        payload[key] = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parser.sections.get(section, []))).strip()
    return {'CgmExpcService': payload}, BASE + url

def context(seq, no, branch='00', expected_name=None):
    text = get('/LSW/joStmdInfoP.do?' + urllib.parse.urlencode(dict(lsiSeq=seq, joNo=no, joBrNo=branch)))
    parser = Inputs()
    parser.feed(text)
    vals = parser.values
    if not vals.get('lsNmKo') or not vals.get('lsKndCdCls'):
        raise ValueError('법령명/종류 확인 불가')
    for key, requested in {'lsiSeq': seq, 'joNo': no, 'joBrNo': branch}.items():
        returned = vals.get(key, '')
        if not returned.isdigit() or int(returned) != int(requested):
            raise ValueError('응답 판본/조문 식별자 불일치: ' + key)
    norm = lambda s: re.sub(r'\s+', '', s)
    expected_article = '제' + str(int(no)) + '조' + ('의' + str(int(branch)) if int(branch) else '')
    actual = norm(vals['lsNmKo'])
    if expected_name and actual not in {norm(expected_name), norm(expected_name) + expected_article}:
        raise ValueError('응답 법령명/조문 불일치')
    return dict(unLsEmpSeq='0', lsiSeq=seq, joNo=no, joBrNo=branch, lsNmKo=vals['lsNmKo'], lsKndCdCls=vals['lsKndCdCls'])

def linked(target, ctx):
    rows, seen, signatures = [], set(), set()
    for page in range(1, 10001):
        text = get('/LSW/' + ENDPOINTS[target], dict(ctx, pageIndex=page))
        if re.search(r'<title>[^<]*(?:오류|에러)|시스템\s*오류', text):
            raise ValueError('목록 오류 페이지')
        matches = re.findall(r'(precInfoP|expcInfoP|cgmExpcInfoP)\.do\?[^\s\"\'<>]*?(precSeq|expcSeq|cgmExpcDatSeq)=(\d+)', html.unescape(text))
        expected = {'prec': ('precInfoP', 'precSeq'), 'expc': ('expcInfoP', 'expcSeq'), 'cgmexpc': ('cgmExpcInfoP', 'cgmExpcDatSeq')}[target]
        if any((handler, param) != expected for handler, param, _ in matches):
            raise ValueError('목록 탭/상세 링크 종류 불일치')
        ids = {(target, ident) for _, _, ident in matches}
        signature = tuple(sorted(ids))
        if signature in signatures and ids:
            raise ValueError('페이지 반복: 수집 완료로 간주하지 않음')
        signatures.add(signature)
        if not ids:
            # Empty pages have no detail links; require the real tab form identity.
            forms = re.findall(r'<form\b[^>]*\bid=[\"\']([^\"\']+)', text, re.I)
            expected_form = {'prec': 'precPageFrm', 'expc': 'expcPageFrm', 'cgmexpc': 'cgmExpcResultPageFrm'}[target]
            known_forms = {'precPageFrm', 'expcPageFrm', 'cgmExpcResultPageFrm'}
            if expected_form not in forms or (set(forms) & known_forms) != {expected_form}:
                raise ValueError('빈 목록 탭 식별 불가/불일치')
            # 알려진 빈 목록 표식만 zero로 인정한다.
            if re.search(r'검색된.*없|조회된.*없|검색 결과.*없|검색결과.*없|등록된.*없|자료가.*없|총\s*(?:<[^>]*>\s*)*0\s*건', re.sub(r'<[^>]+>', ' ', text)):
                return rows
            raise ValueError('빈 목록인지 확인 불가')
        for kind, ident in sorted(ids):
            if (kind, ident) not in seen:
                rows.append(dict(target=kind, source_tab=target, source_id=ident, found_by=['linked-by-center']))
                seen.add((kind, ident))
        # 서버의 총 건수와 페이지 수를 우선 사용한다.
        plain = re.sub(r'<[^>]+>', '', text)
        total = re.search(r'총\s*([\d,]+)\s*건\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)', plain)
        if total:
            count, current, pages = (int(x.replace(',', '')) for x in total.groups())
            if current != page:
                raise ValueError('서버 페이지 번호 불일치')
            if page >= pages:
                if len(rows) != count:
                    raise ValueError('총 건수와 수집 건수 불일치')
                return rows
            continue
        # explicit pagination: no next page link and fewer than 10 entries means last.
        page_numbers = [int(x) for x in re.findall(r'(?:goPage|fn_goPage|fn_search|pageIndex|searchPage)\s*\(?[=\s\"\']*(\d+)', text)]
        if len(ids) < 10 and not any(n > page for n in page_numbers):
            return rows
    raise ValueError('페이지 상한 초과')
