# 변경 이력 (CHANGELOG)

Keep a Changelog와 유의적 버전을 따른다. [버전 규칙](docs/RELEASING.md).

## [Unreleased]

### Secret-free CI hardening

- Address scanner review findings with quote-aware object RHS boundaries, comparison/JS-arrow exclusion, union/generic annotations, intact bracketed config words, and independent JS-template/Python f-string static chunks (including rf/fr). Acquire trusted main only through pinned checkout, retain main-only absence skip and fail-closed extraction, align security documentation and refresh the snapshot. Add runtime-built positive/negative regressions; no runs or catalogs changes.

- Resolve every PR's trusted pattern scanner from freshly fetched, validated default main instead of an arbitrary PR base; retain validated blob extraction, main-only absence notice, and fail-closed errors. Skip balanced JS/TS template interpolation expressions while inspecting static chunks, and preserve punctuation in bare shell/config values. Add runtime-built positive/negative and non-main-base regressions; no runs or catalog changes.

- Address three scanner findings: keep trailing possessive apostrophes out of quote bounds, preserve inner equals signs in bare assignment candidates, and recognize TOML dotted credential keys with quoted prefixes. Add runtime-built positive and negative regressions; no runs or catalog changes.

- Address six scanner findings: extract trusted blobs with validated object IDs and cat-file, bound assignment RHS at quote-aware shell separators, include non-ignored untracked files, preserve padded colon values, distinguish source references from literals, and restrict placeholder markers to whole allowlisted shapes. Add runtime-built scanner and extracted-CI regressions; no research data changes.

- Remove the untrusted PR-scanner bootstrap gate: when the immutable base lacks tools/pattern_scan.py, preparation succeeds with an explicit activation notice and the blocking step is skipped, never executing the PR copy. Keep ordinary scanner unit tests and fail-closed handling for every other extraction error; add hostile-copy and credential-gate regressions.

- Close #7: preserve and unescape shell words with escaped whitespace, share enclosing lexer candidates for provider environment-reference exemptions, restrict masking/example markers to whole placeholder shapes, and keep prose apostrophes out of statement quote bounds. Add runtime-built positive and negative regressions for all four scanner findings.

- Run the blocking PR pattern scan from immutable base tooling and its embedded allowlist outside the worktree, with a notice-only skip (never the PR copy) when the scanner is absent at base and fail-closed extraction otherwise. Keep PR scanner unit tests, add explicit worktree root support and trusted-extraction regressions, and document that scanner/allowlist changes apply after merge.

- Address seven scanner review gaps with shared escape/doubled-quote handling, quoted shell operands, shell word-boundary comments, literal subscript targets, compound assignments, conventional secret-key names and enclosing provider placeholders. Add runtime-built positive/negative regressions; two exact path/rule/line-hash exceptions cover existing runtime-variable subscript fixtures, not literal credentials.

- Scan strict UTF-16LE and UTF-16BE decodings independently whenever NUL-containing bytes have even length, in addition to the existing decoding. Union findings by line and rule so Korean-heavy BOM-less text cannot hide credentials; add runtime-built CLI detection, masking and clean-text regressions for both byte orders.

- Default-inspect all single-line assignment candidates, with segmented credential names, prefixed/template literals and shell fallback operands. Add runtime-built regressions and document heuristic limits and the authoritative trusted LAW_OC control. Keep the exact-hash allowlist unchanged.

- Address scanner review gaps: inspect typed assignment literals, exempt only whole environment references instead of arbitrary dollar-prefixed values, and recognize plausible BOM-less UTF-16LE/BE text. Add runtime-built positive/negative fixtures, including binary safety; keep masked diagnostics and the existing exact-line allowlist unchanged.
- Add a blocking tracked-file credential-shape scan for all PRs, including forks and Dependabot, with masked diagnostics and synthetic regression tests. Four exact-line exceptions cover existing runtime expressions and masking fixtures; no research data changes.
- Add CODEOWNERS and pin checkout v4.4.0 / setup-python v5.6.0 to release commit SHAs; retain the pinned central traffic workflow.

### 공개 여부와 독립적인 CI 준비

- 공개 배포에 대비해 조직 템플릿의 일일 traffic workflow와 방문·clone 배지를 추가한다. 모든 PR·푸시의 secret-free 검사와 main 푸시·수동 실행·main 대상 same-repo PR(작성자와 실행 actor 모두 Dependabot이 아닌 경우)의 필수 실제 키 검사를 분리했다. 신뢰된 base scanner 추출과 최소 읽기 권한을 유지한다.
- Codex 검토 반영: 비-main 대상 PR과 Dependabot 작성·실행 PR은 fork PR처럼 offline-checks만 실행하도록 job 조건을 좁히고 기존 fail-closed 준비 검사는 유지한다. 공개 전환 시 비공개 취약점 신고 활성화와 상세 없는 Security contact request 공개 이슈에서 비공개 채널로 전환하는 fallback을 명시했다.
- 비공개에 의존하지 않는 신뢰 경계·vendor 메타데이터의 배포 권리 확인·비공개 보안 신고 절차를 문서화했다. runs와 FAQ·동일성 보류 자료는 변경하지 않았다.

### 저장소 이력 재생성에 따른 의존성 고정 갱신

- 새 관리자 계정으로 저장소 이력을 재생성했다. 각 commit의 tree 내용은 동일하며 kapa_skills 잠금 commit과 vendor commit을 747dc72에서 b8d9d8d로 옮겼다(동일 tree). vendor 메타데이터 165개 파일의 원본 바이트·SHA-256은 모두 동일하고 보류 자료 카탈로그는 dependency_commit만 변경했다. 새 원문 수집·검토·관계·상태 변경은 없다.
- 이전 기록의 SHA를 새 이력에 맞췄다: 536356823d43e867d426ba5eb5c6407ca64199cd → e5d7d2c4fda6d19cdf7813e88445debd217c558b, 747dc72b5a0fa5b1298f72751f11ac535e32a6e0 → b8d9d8d93e59d0a7da29d0fe120177ea9b0d1b02.

### kapa_skills 의존성 갱신

- kapa_skills 잠금 commit과 vendor commit을 e5d7d2c에서 b8d9d8d로 갱신했다. 색인·과거 판본 메타데이터 165개 파일의 원본 바이트와 SHA-256은 모두 동일하다. 보류 자료 카탈로그를 오프라인 재생성했으며 `catalogs/materials.json`은 dependency_commit만 변경했다.
- 상위 5개 commit은 미래 시행 법령 판본 snapshot 추가, 86824 규칙 부칙 정리(조문 불변), 별표 Markdown 줄바꿈 서식, 문서·도구·CI 변경이다. 기존 저장 인용·해시 영향은 0건이며 source_sha256·검토 이력·관계·역사 조사 기록·보류 상태는 변경하지 않았다. 새 원문 수집이나 참조 상태 승인은 없다.

### 과거 판본·회신 동일성·FAQ 계약 (#2·#3·#4)

- PR7 검토 반영: 입력·카탈로그 동시 삭제로 동일성 게시 보류를 우회하지 못하도록 독립 검사한다. law.go.kr–LAIIS 출처 ID 쌍과 실제 판례 문서·경로를 주석 생성 전에 대조하며, FAQ 빈 번호·조사 판단·중첩 assertion 해시의 provenance를 실제 출처에 맞게 구분한다.

- 저장 연구에서 `catalogs/materials.json`을 오프라인 생성한다. 과거 판본 주장 48건 중 토지수용법 시기 009295 연혁 10건은 기존 잠금 versions_file로 확인하고, 색인에 없는 공특법 계열 001826·002258·006297의 38건은 정확한 미확인 사유로 보류한다. 판례 8건의 조문명·판본·적용 기준일 주장은 별도 주석에 보존한다. 법령 본문을 복제하지 않으며 과거 조문 ID·적용 판본을 추정 승인하지 않는다.
- 토지정책과-308·1730의 각각 두 원문 ID와 상이한 날짜 주장을 동일성 미확정으로 연결한다. 기존 문서·검토·GENERATED는 보존하며 unresolved 보류 중 published 진행은 거부한다. 원 회신문과 기관 정정은 미확보다.
- 안건번호 없는 국토교통부 FAQ 11건은 별도 faq ID·행정 FAQ 종류·law.go.kr/국민신문고 식별자·저장 연구 해시로 연결한다. 정식 해석으로 수록하지 않으며 원본 봉투 미확보·공식 안건번호 미확인·목록 접근 실패를 표시한다. 신규 API 호출·원문 인용·상태 승인은 없다.
- 검증기는 카탈로그와 실제 입력에서 재계산한 전체 결과를 비교하고 판본의 법령 ID를 대조한다. 스키마·오프라인 회귀 시험을 추가했다. 출처 조사와 승인·본문 수록은 완료로 주장하지 않는다.

### 시범 쟁점: 미지급용지

- 선별 1,683행의 `screened_text_sha256`를 SRI `sha256-<Base64 digest>` 표기로 통일했다. SHA-256 digest 32바이트의 패딩 포함 RFC 4648 표준 Base64이며, 캐시 원문 checksum과 대조하여 기존 hex 표기와 digest 바이트가 동일함을 확인했다. 원문·계산 대상·matcher·판정·선별시각은 변경하지 않았다.

- 골격(#1) 도구로 시범 데이터를 이관했다. 쟁점 절·법원 표기·원문 필드를 갱신하고 원문 문서 38건을 재생성했다(24건 변경). 원본 시범 commit 0f90463 의 고정 manifest 로 문서 검토 38건과 확정 관계 검토 48건에 source_sha256 과 migrated-baseline 표시를 채웠다. 이 86건은 이관 시점 원문에 대한 기준선이며 과거 검토 당시 원문을 입증하지 않는다.
- 자동 인용 관계 2건(rel-c28108d3118dfcd63527, rel-f4df573f22916e0c1bb4)의 근거 문자열 앞 공백을 제거해 재생성 값과 일치시켰다. 2023다295442 의 수동 참조조문 줄 끝 공백을 제거했다. 관계 66건과 원문 payload·참조 상태는 그대로다.
- 미지급용지 초기 역사 조사: 판례 21건, 법제처 4건, 국토교통부 13건의 공개 원문과 쟁점 골격·범위·실행 기록. 수집 당시에는 모두 참조 미검토였으며 현재 개별 상태는 문서와 검토 기록을 따른다. 전신법 계약·일부 판본 확인 등 조사는 미완료다.
- 미지급용지 잔여 법원 ID 1,683건을 공백 무관 9개 신호의 단일 완전 matcher로 전수 재선별했다. 적중 0건·문구 없음 제외 1,683건·실패 0건·해당 큐 미선별 0건이며 행별 공식 URL·정규화 전 원문 문자열 UTF-8 SHA-256·바이트 크기·선별시각을 기록했다. 과거 배치 취득 정보와 이전 1,500건의 역사적 방법은 구별해 보존했다. 실체적 무관 또는 전체 조사 포화를 선언하지 않는다.
- PR #5 관계 증거 재검토: 정확한 저장 원문으로 관계 4건의 인용을 교체하고 rel-a097900d33e0e1faf96b는 needs-review로 내렸다. 기존 승인을 보존하고 GPT-6 에이전트 재검토 5건을 추가했다. 총 66건(confirmed 47 / needs-review 12 / unreviewed 7)이며, 출발 문서 토지정책과-1948은 relation_recheck를 남기고 progress만 source-verified로 내렸다. reference_status와 GENERATED 영역은 유지했다. 자료 38건의 관계 메모와 사례·읽기 지도·조사 범위의 낡은 선별 설명을 현재 데이터에 맞췄다.
- 미지급용지 판례·해석 검토 제안 관계 59건을 병합했다(confirmed 48, needs-review 11). 기존 미검토 인용 7건을 유지하여 총 66건이며 확인 관계의 accept 검토 기록을 대조했다. 참조 상태를 높이지 않고 38개 자료의 하위 쟁점 읽기 지도를 작성했다. 공특법 전신 판본 ID·회신일 충돌·후속 결과 등 미확인은 [조사 범위](issues/unpaid-land/coverage.md) 및 지도에 표시했다.

### CI

- PR6 4512191338: credential 검사 PR base를 기본 브랜치 main으로 제한한다. trigger 필터와 blob 접근 전 런타임 ref 확인을 함께 적용해 악성 scanner가 있는 비기본 base를 거부한다. main의 신뢰된 리뷰를 전제로 하며 branch protection 설정 자체를 보장하지 않는다.

- PR6 4511991421: 실제 LAW_OC를 받는 CI scanner와 두 의존모듈을 trusted base의 Git 객체에서 작업 트리 밖으로 추출한다. 준비는 인라인 표준 라이브러리만 실행하고 PR 코드는 import하지 않는다. PR 전체 worktree 필수 검사는 유지하며, workflow YAML 자체를 바꿀 수 있는 same-repo 작성자의 잔여 신뢰 경계는 문서화했다.

- 기본 CI: 단일 Ubuntu·Python 3.12 작업에서 첫 저장소 코드 실행 단계의 필수 LAW_OC 검사, 추적 링크 거부, 경로별 검증·표준 unittest 감독, 무시 파일 포함 작업 트리 불변성과 diff 공백을 확인한다. secret은 전용 단계에만 전달하며 fork의 secret 부재는 실패한다. 예약 실행·외부 자료 수집은 없다.
- deps.lock의 kapa_skills commit에서 색인과 과거 판본 메타데이터만 vendor하고 원본별 SHA-256·vendor commit을 고정했다. 형제 checkout 부재 시 해시 검증 후 사용하며 불일치·누락은 실패한다. 명시적 갱신 도구와 회귀 시험·문서 snapshot을 함께 추가했고 법령 본문·수집 자료·게시 상태는 바꾸지 않았다.

- PR 1 추가 검토 4510448438: GIT_ALLOW_PROTOCOL 에 이름을 두면 같은 이름의 git-remote-<name> helper 가 허용될 수 있으므로 빈 값으로 고정해 어떤 transport·remote helper 도 허용하지 않는다. PATH 에 둔 합성 remote helper 를 promisor URL 로 지정한 저장소에서 보호된 읽기가 helper 를 실행하지 않음을 회귀 시험으로 확인한다.
- PR 1 추가 검토 4510368675: protocol.allow 는 protocol.<name>.allow 설정에 덮이므로, 자식 Git 환경에 실제 프로토콜을 하나도 허용하지 않는 GIT_ALLOW_PROTOCOL 을 고정해 저장소·사용자 설정과 무관하게 모든 transport 를 거부한다. 저장소 로컬 protocol.file.allow=always·protocol.ext.allow=always 를 둔 partial clone 회귀 시험을 추가했다.
- PR 1 추가 검토 4510295690: GIT_NO_LAZY_FETCH 를 모르는 이전 Git 에서도 지연 fetch 가 실행되지 않도록 공용 Git helper 에 protocol.allow=never 를 고정했다. partial clone 의 누락 객체를 환경변수 없이 읽어도 실패하고 객체가 받아지지 않음을 실제 저장소 회귀 시험으로 확인한다.
- PR 1 추가 검토 4510183676: 정리한 자식 Git 환경에 GIT_NO_LAZY_FETCH=1 과 GIT_TERMINAL_PROMPT=0 을 다시 고정해 partial clone 의 누락 객체 지연 fetch(설정된 upload-pack 실행)와 자격 증명 프롬프트를 막고 누락 객체는 실패로 처리한다. 부모가 다른 값을 줘도 덮어쓰는 회귀 시험을 추가했다.
- PR 1 추가 검토 4510066563: 모든 운영 Git 실행을 공용 helper 하나로 통일하고 core.fsmonitor=false·core.untrackedCache=false를 고정했다. 자식 환경 사본에서 LAW_OC·LAW_OC_FILE 및 모든 GIT_* 설정·저장소 재지정 변수를 제거하며 부모 scanner 환경은 유지한다. 운영 subprocess 직접 호출은 helper의 고정 prefix·캡처·환경 형태 외에는 거부하고, helper 인수도 plumbing allowlist로 검사한다. 임시 저장소의 실제 독성 fsmonitor hook 억제와 자식 환경·정적 우회 거부 회귀 시험을 추가했다.

- PR 1 추가 검토 4509827699·4509827708·4509827716: 영역 추출 snapshot을 제거하고 rules/·docs/의 모든 파일 및 루트 README*·AGENTS*·CLAUDE*·SKILL*의 전체 바이트를 경로·SHA-256·크기로 고정한다. 확장자·대소문자·실행기 인식과 무관하게 변경·추가·삭제·이름 변경을 거부하며 안전 읽기·쓰기를 사용하는 명시적 재생성 도구와 같은 PR의 snapshot 검토 절차를 추가했다. rules/**/SKILL.md의 정규 사전 검사 쌍은 보조 sanity 검사로 유지한다. 운영 Git 명령은 ls-files·ls-tree·rev-parse·cat-file plumbing만 허용하고 show·diff·log 및 textconv·filter 옵션을 거부하며 기존 객체 읽기를 cat-file -p로 전환했다. 전체 파일·바이너리·경로와 updater 안전성 및 변환 없는 Git 객체 읽기 회귀 시험을 추가했다.

- PR 1 추가 검토 4509651096·4509655620·4509655623·4509655628·4509655635: 문서와 golden snapshot은 내용 읽기 전 Git 링크 mode와 공용 lstat·resolve 경로 검사로 링크·junction·reparse point·비정규 파일·경로 이탈을 거부하고 안전한 디렉터리만 순회한다. 불일치는 본문 대신 경로·블록 번호·SHA-256·길이만 공용 redactor를 거쳐 진단하고 문서의 검증·unittest 명령을 fail-stop으로 바꿨다. Git status는 허용 목록에서 제거하고 임의 객체의 이벤트 루프 자식 실행 메서드도 거부한다. raw HTML pre·code·script·textarea 전체를 snapshot에 포함하며 fixture 쓰기 면제는 실제 discovery 대상이자 production import 경로에서 도달하지 않는 시험 모듈에만 적용한다. 합성 index·mock 링크 및 reparse·실제 unittest 실패 출력·HTML 영역·import 경로 회귀 시험을 추가했다.

- PR 1 추가 검토 4509500778·4509500782·4509500784·4509500790·4509500793·4509500799: 문서 코드 전체의 파일·순서·원문을 검토된 golden snapshot과 비교하여 Python 외 명령·줄 연속·인용 및 목록 안 fence 변경도 같은 PR의 명시적 snapshot 검토를 요구한다. 정규 명령·사전 검사 쌍 검사는 보조 sanity 검사로 유지한다. 대체 자식 실행 API는 기본 거부하고 production subprocess는 출력 캡처와 literal git의 고정 읽기 전용 명령·옵션만 허용하며 scanner의 동적 Git 호출을 제거했다. 가벼운 링크 검사와 일반 검증은 추적 gitlink mode 160000도 거부한다. 오프라인 snapshot 변경·프로세스 정책·합성 Git index 회귀 시험을 추가했다.

- PR 1 추가 검토 4509424163·4509424167·4509424172: 문서 fence의 Python 명령은 셸 의미 추정 대신 정규 형식 allowlist로 검사한다. 환경변수 접두사·wrapper·연산자·치환·도움말·따옴표 실행기·옵션 재정렬을 거부하고, 쓰기 전 두 사전 검사와 셸 실패 접미사 또는 PowerShell 다음 줄 종료 검사를 정확한 문자열 쌍으로 요구한다. rules·README·AGENTS·docs 전체에 적용하고 이관·CI 명령 예시를 정규 형식으로 맞췄다. 시험 subprocess 실행기 검사는 유지하며 3건의 보고 변형과 허용·거부 표를 회귀 시험한다.

- PR 1 추가 검토 4509310479: 문서 실행기를 정규식의 뒤 공백으로 찾는 대신 명령을 먼저 token화하고 일치하는 따옴표·PowerShell 호출 연산자를 제거한 실행 파일 basename으로 판별한다. 따옴표를 쓴 Python·py 버전 실행기, 공백을 포함한 Windows·POSIX 경로, pythonw·exe 변형에도 격리·바이트코드 금지 옵션 및 쓰기 전 사전 검사 규칙을 적용한다. 문서와 시험 인수 목록이 같은 실행기 분류를 공유하며 표 기반 회귀 시험을 추가했다.

- PR 1 추가 검토 5건: 저장 payload의 문자열 값·속성명에 scanner의 공용 matcher를 적용하여 선택된 키의 문서화한 인코딩까지 가리고 엄격한 정규 저장에서는 거부한다. 문서 작업 블록의 backtick·tilde fence와 3자 이상 길이를 인식하고, 도구 이름 대신 AST의 공용 쓰기 함수 및 도구 간 호출 관계로 쓰기 여부를 판정한다. 시험의 Python·python3·py·sys.executable 인수 목록에도 문서와 같은 필수 옵션 검사를 적용하고, 시험 fixture 쓰기는 허용하되 자식 출력 캡처 검사는 시험 모듈에도 적용한다. 합성 키·임시 도구 호출 그래프·fence·실행기·시험 자식 출력의 표 기반 회귀 시험을 추가했다.

- PR 1 추가 검토 4건: 문서 회귀 검사는 사전 검사 유무가 아니라 쓰기 가능한 도구로 작업 블록을 식별하여 링크·credential 검사 누락과 실패 후 계속 진행을 거부한다. Python·python3·py 버전 실행기를 먼저 찾고 옵션 순서와 무관하게 격리·바이트코드 쓰기 금지 옵션을 각각 확인한다. 자식 프로세스의 표준 출력·오류 캡처 또는 폐기를 tools 재귀 회귀 검사로 강제하고 캡처 결과의 공용 진단 가림을 실제 자식 실행으로 시험한다. 직접 호출 회귀 도구는 import 별칭까지만 다루며 의도적 재결속·우회는 신뢰된 저장소 코드의 PR 검토 범위임을 주석으로 명시했다.

- PR 1 추가 보안 검토 4건: 추적 링크 검사 직후 worktree 필수 credential 검사를 수행하여 수집·이관 전 실패를 차단하고, 저장소 JSON CLI의 출력·오류·예외를 공용 실행 래퍼에서 공유 redactor로 가린다. 직접 쓰기 회귀 방지는 표준 삭제·절단·이름 변경·링크 생성·복사 API를 포함하고 tools 하위 패키지도 재귀 검사한다. 모든 문서·시험 도구 실행에 격리와 바이트코드 쓰기 금지 옵션을 함께 적용하여 검사 전 캐시 쓰기도 막는다. 합성 키·CLI·문서 옵션·하위 도구 회귀 시험을 추가했다.

- PR 1 보안 검토 4508981672: manifest 생성·전체 이관·법원 복원·오프라인 재생성·JSON 및 관계 저장 등 모든 도구 파일 쓰기를 공용 경로 검사와 안전 쓰기 함수로 통일하여 저장소 밖 경로와 symlink·junction·reparse point를 열기 전에 거부한다. 갱신 절차는 쓰기 전에 가벼운 추적 링크 검사를 실행하고 실패하면 중단한다. manifest 링크·공용 저장·이관·재생성 회귀 시험과 tools 전체의 미검사 직접 쓰기 호출을 탐지하는 AST 회귀 시험을 추가했다.

- PR 1 보안 검토: 공용 staging은 모든 출력 경로를 부작용 전에 검사하여 저장소 밖 경로, 부모 경로의 symlink·junction·reparse point와 비디렉터리, 링크인 최종 파일을 거부한다. 교체 전에도 재검사하고 안전하지 않은 부모를 통한 롤백·정리를 막으며 상세 수집의 실패 기록에도 같은 경로 검사를 적용한다. 일반 검증은 Git index mode 120000인 추적 symlink를 거부한다. 실제 링크 시험은 생성 권한이 없으면 건너뛰되 권한 없는 환경에서도 mock reparse·경로 이탈·index mode 회귀 시험을 수행한다.

- PR 1 추가 검토 3건: API가 실제로 선택한 환경변수 또는 파일 fallback 키를 공용 selected_key에서 관리하여 payload 가림과 인코딩 진단 가림이 공유한다. 파일 읽기는 API만 명시적으로 수행하고 scanner는 환경변수 전용 정책을 유지한다. payload 속성명에 포함된 키도 가리고 가림 후 속성명 충돌은 안전하게 거부한다. 추가 입력 검사에서 저장소 상대 경로만 검사하고 외부 입력은 내용 바이트만 검사한다. 합성 LAW_OC_FILE·속성명·checkout 부모 경로 회귀 시험을 추가했다.

- PR 1 추가 검토 4건: 환경변수 키 정규화 함수를 공용 payload 가림·API·값 기반 검사에 공유한다. 짧은 키의 base64 오탐을 줄이기 위해 내부 정렬 조각은 8자 이상만 사용하고 전체 인코딩은 유지한다. 조문·상세 수집의 실패 진단은 저장·출력 전에 공용 인코딩 가림을 적용한다. 시각이 있는 실행 기록은 시간대를 반영하여 종료가 시작보다 빠르면 거부한다. 각 항목의 합성 키·오프라인 회귀 시험을 추가했다.

- PR 1 추가 검토 2건: 일반 검증의 credential 사전 검사와 실제 읽기 집합을 추적·미추적 비무시 파일로 통일하고, 별도 의존성 색인·지정 snapshot·참조 파일도 파싱 전에 검사한다. 문서화한 모든 검색 바이트와 percent·hex 대소문자 및 base64 공백 변형이 진단에 있으면 진단 전체를 가린다. 기본 수집·후보 계약은 유지하면서 검증용 읽기 콜백만 연결했다.
- LAW_OC는 수집 API와 동일하게 앞뒤 공백·탭 등을 strip한 정규 값으로 검색 바이트를 한 번 만들고 검사·진단 가림에 공유한다. 미추적 인코딩 중복 JSON 키, 외부 의존성, 무시된 스킬, 정규화된 환경변수의 합성 키 회귀 시험을 추가했다.

- PR 1 값 기반 검사 검토 4건: base64의 CR·LF·공백·탭 및 MIME 줄바꿈, URL percent escape의 hex 대소문자를 처리하고 파일 내용뿐 아니라 추적 상대 경로명의 키도 가려 보고한다. 키 자체의 대소문자는 유지한다. 일반 검증은 의존성 파싱 전 credential 검사를 수행하여 노출·검사 오류 시 즉시 중단하고 진단 문자열의 실제 키도 방어적으로 가린다. 합성 키 회귀 시험을 추가했으며 다른 계약과 CI workflow는 변경하지 않았다.

- credential 구문/AST/정규식 스캐너·상수 folding·캐시와 전용 회귀 시험을 실제 환경변수 LAW_OC의 값 기반 검사로 교체했다. 아래 과거 구문 스캐너 개선 기록은 이 설계로 대체된다. Git 추적 바이트와 선택적 미추적·비무시 파일에서 UTF-8·URL quote/quote_plus·UTF-16-LE/BE·hex 소문자/대문자·표준/URL-safe base64(내부 세 정렬)를 검사하며 바이너리도 포함한다. 키·검색 바이트는 출력하지 않는다.
- 유효한 실제 키를 제공한 성공 검사만 문서화한 인코딩의 해당 키 부재를 보장한다. 난독화·암호화 등은 범위 밖이며 비공개·PR 검토를 유지한다. 로컬은 셸 LAW_OC를 사용하고, GitHub secret LAW_OC를 전달하는 CI 전용 필수 단계는 별도 CI PR에서 추가한다. 일반 검증에 같은 검사를 연결하고 긴 직접 literal 대입은 비실패 경고만 남겼다. 합성 키·임시 Git 저장소 회귀 시험을 추가했으며 관계 근거·이관·수집 계약은 유지했다.

- PR 1 credential 검토 8건: 환경 API의 positional·keyword 인수와 import 별칭을 결속하고 mapping union·상수 dict 표현식·Python 문자열 안 shell 대입을 검사한다. 값 없는 annotation과 비 Python 비교식의 오탐을 제거하고 비 Python 우변 전체를 검사해 마스크 뒤 접미사를 놓치지 않는다.
- 실제 literal·상수 연결·상수 f-string·bytes와 동적 표현식의 마스크 외 문자열 조각을 탐지하되 런타임 credential 조회·호출·매개변수는 허용한다. 비 Python에서는 정확한 단일 변수·secret 참조만 추가로 허용하고 명령 치환·기본값·연결은 거부한다. README와 SCHEMA에 비공개·PR 검토 및 의도적 난독화 제외라는 검사 범위를 명시하고 회귀 시험을 추가했다. 반복 검증은 경로·mtime 대신 원문 텍스트와 언어 모드를 키로 하는 유한 캐시를 사용해 변경 탐지는 유지하면서 동일 Python 파일의 재파싱을 줄인다.

- PR 1 다음 검토 4건: Python credential key·value는 환경변수 API를 인식하는 AST 검사로 읽어 그룹 괄호 우회와 일반 호출·동적 key 접미사 오탐을 함께 막는다. 비 Python·파싱 실패의 정규식 경로도 인식한 API로 제한한다.
- baseline 이관은 원본 파일럿 전체 commit 0f90463b34127b71af14c7046f7b27660ed9adf7의 실제 Git 객체만 허용하며 CLI에서 다른 원본으로 바꿀 수 없다. 상세 수집의 커밋 후 출력을 예외 처리 밖으로 옮겨 stdout 실패가 success 실행을 failure로 덮어쓰지 않게 했다. 조문 수집도 출력 실패 시 후보·실행 보존을 시험했다.
- 4건별 오프라인 회귀 시험을 추가했으며 관계 근거 비교·실제 수집·파일럿 checkout·게시 상태는 변경하지 않았다.

- PR 1 다음 검토 7건: 이관 manifest를 고정 commit 검토 행 전체의 정규 해시에 결속하고 이관 시 원본 저장소·commit·관계 모드로 재계산한다. ID 전용 manifest는 재생성이 필요하며 기존 파일럿 38개 문서 검토·48개 관계 검토와 baseline 제한은 유지한다.
- 상세 실행 tracks를 source 하나에 결속하고 자동 관계의 evidence·미검토 필드를 payload 재생성과 대조한다. 실행 날짜는 한 번 읽은 started에서 정하며 조문 후보와 실행 기록을 상세 수집과 같은 공용 준비·교체·롤백 단위로 저장한다.
- credential key의 Python escape·인접 문자열도 해제 후 검사한다. 7건별 오프라인 회귀 시험과 이관 명령 문서를 갱신했으며 실제 수집·파일럿 checkout·게시 상태는 변경하지 않았다.

- PR 1 다음 검토 9건: 원문 출발 confirmed 관계 승인을 검토 source_sha256에 결속하고 파일럿 관계 검토 48개의 명시적 manifest baseline 이관을 기존 도구에 추가했다. 외부 계약 ID 출발 삭제 관계는 원래 snapshot을 가진 후속 needs-review 검토 기록으로 보류할 수 있다.
- 조문 실행에서 후보 파일 존재·행 수를 역검사하고 기계 실행의 경로·source·날짜·순번·후보 ID 및 success 양수 건수를 검증한다. 상세 수집의 success 실행 기록을 원본·문서·관계와 함께 준비·교체하며 실패 시 롤백한다.
- 접두사 literal·중괄호 환경변수 인증정보와 균형 대괄호 Markdown 링크를 검사한다. 9건별 오프라인 회귀 시험을 추가했으며 실제 수집·파일럿 checkout·게시 상태는 변경하지 않았다.

- PR 1 미해결 13건: 삭제 승인 관계를 원래 출발 문서와 snapshot으로 결속하고 재수집 때 보류 표시를 보존한다. 원문 변경은 수동·혼합 확정 관계도 needs-review로 내린다. 잘못된 관계 행은 오류로 보고하고 나머지를 계속 검사한다.
- 조문 후보의 중첩 README 중복 제외, 후보·발견 경로와 실제 실행 기록 대조, 숫자·기호를 포함한 잠금 색인의 완전한 법령명 대응을 추가했다.
- Markdown 표시 정규화·다중 행 inline 명령·인용 데이터 fence를 처리하고 GENERATED 명령 면제를 원본과 정규 대조한 문서에만 적용한다. 그룹화 literal 인증정보를 해제 후 검사하며 UTF-8 실패·NUL 파일을 거부한다. 13건별 회귀 시험과 unittest discovery용 패키지 표지를 추가했다. 실제 자료 수집·게시 상태 변경은 없다.

- Codex 13차: credential 할당·첨자·설정 호출·JSON/YAML key의 구분자 사이 모든 공백(탭·CR·LF 포함)을 허용해 줄바꿈 우회를 차단하고 원문 행 번호로 비밀 위치를 보고한다. 다중 행 비밀·마스크 회귀 시험과 파일럿 export 재검증을 추가했다.

- Codex 12차: 환경변수 문자열 첨자 할당·설정 호출의 literal 비밀을 검사하고 YAML 부분집합의 값·따옴표·flow 문법을 검증한다.
- 법원명 전체 고정 패턴을 fetch/validate에 공유하고 문서 참조 여부와 무관하게 모든 저장 원본의 URL·해시·fetched·서비스 root·일련번호 봉투를 검증한다.
- 수집 중복 검사에 중첩 README 문서를 포함하고 두 token 산문 명령도 실행기 이름과 무관하게 차단한다.
- accept 관계 검토의 대상 삭제 시 relation_recheck 기록과 source-verified 진행 상태를 요구한다. 파일럿은 기존 이관 단계로 새 문제 없이 검증한다.

- Codex 11차: 실행기 이름과 무관한 산문 명령 모양 및 데이터 fence 문법을 검사한다. 데이터 내부 문자열은 명령으로 취급하지 않는다.
- 원문 추출 필드의 값과 정확한 provenance를 표지 변경과 무관하게 결속하고 누락된 legacy 원문 필드만 채우는 이관을 제공한다.
- 환경변수·shell·JSON key·bare OC 할당의 비밀을 검사하고 relation_recheck·진행 상태·자동 관계를 payload/잠금 색인에서 재계산한다.
- fetch/validate에 동일한 판례 출처 정책을 적용한다. 공식 법원 약칭 지법·고법을 명시 허용하며 명시적 데이터출처명 허용 목록은 유지한다.
- canonical 생성기가 없는 쟁점의 GENERATED 표지를 수동 절로 이관한다. 파일럿 checkout을 수정하지 않고 export에서 표지·법원명·누락 필드·digest 이관과 전체 검증을 수행한다.

- 추가 보안 검토: source frontmatter를 공유 원문 추출 결과에 결속하고 court 원문/ID 정규화를 분리한다. 읽기 경로는 데이터 fence allowlist·일반 명령 모양 inline 검사로 제한하며 파일럿의 법원명 복원 도구를 제공한다.
- Codex 10차: JSON Unicode 및 중복 percent encoding OC 이름을 전수 검사하고 fragment·구분자에서 마스크 값을 종료한다.
- 검토 문서도 교체 가능한 자동 관계의 제거·추가를 반영해 진행 상태를 내리고, 근거가 사라진 검토 관계는 보존하며 relation_recheck로 표시한다.
- 저장 payload 자체의 서비스 root·종류별 일련번호를 문서·source_id와 해시/렌더링 전에 대조한다.
- baseline digest 이관은 고정 commit에서 추출한 명시적 review ID manifest만 허용하며 migrated-baseline marker를 남긴다. 파일럿 원본 checkout을 수정하지 않고 export에서 재생성·38개 이관·전체 검증한다.

- Codex 9차: raw 저장 텍스트 OC 전수 검사 및 저장 payload 마스킹 차이 거부, 공통 renderer로 GENERATED 전체 대조·오프라인 재생성.
- 문서 상태 검토를 source_sha256으로 원본 판본에 결속하고 파일럿 1회 baseline 이관 도구·제한·명령을 문서화.
- 색인 재대응으로 자동 관계 집합이 바뀌어도 진행 상태 하향, 조문 수집 실패 count=0 보완, 필드별 provenance category 검사.
- 읽기 경로의 SSH·SCP·SFTP·rsync·telnet·netcat 등 원격 실행/전송 launcher 탐지와 회귀 시험 추가. 파일럿 committed 자료 38개·검토 86개를 스크래치에서 검증(문서 검토 38개 이관, 관계 검토 48개 제외).


### 수정
- Codex 8차 검토: source_url query 허용 목록·OC 마스크, 저장 payload와 생성 원문 일치, 백틱 이스케이프·안정적 필드 순서를 검증한다. 코드/산문의 명령 판별, 실제 링크 opener·읽기 규칙 링크, 자료 README 예외 범위, 검토 연도, 실행 기록 계약, UTF-8 오류 지속 검사, 참조 필드의 완전한 ID 검사를 강화했다. 파일럿 보조 실행 기록과 기계 수집 기록의 계약을 구별한다.
- 원문 renderer가 줄 끝 공백·탭을 표시 전용으로 제거한다. 저장 JSON·해시 보존, 재생성 바이트 안정성과 생성 문서의 Git 공백 검사를 회귀 시험한다.
- 명령 탐지에서 환경 변수 접두사와 중첩 셸 wrapper를 구조적으로 벗기고, 코드 문맥의 임의 위치 launcher·파이프·명령 치환도 검사한다. 일반 산문의 문맥 구분은 보존한다.
- 생성 영역 원문의 대괄호·꺾쇠·앰퍼샌드·물결을 공통 renderer에서 HTML entity로 보존해 원문 인용 번호가 링크로 해석되지 않게 했다. 저장 원문의 메타데이터·해시를 대조한 오프라인 원문 절 재생성을 추가하며 수동 절·frontmatter·원본·관계는 보존한다. 신규·기존 문서의 재생성 일치와 멱등성 회귀 시험을 추가했다.
- Codex 6·7차 검토: Markdown 문맥 스캐너로 명령·링크·산문 본문을 분리하고 자연어 허용 목록을 제거했다. 목록·prompt·인용 표지, wrapper·절대/상대 실행 경로, 모든 fence의 명령을 검사하며 tools Markdown도 포함한다. 참조형 링크와 저장소 루트 기준·경계 이탈 링크를 검증한다.
- 출처 URL query의 종류·일련번호와 저장 자료를 결속하고 confirmed 관계의 인라인 증거를 승인 검토의 URL·인용문과 일치시킨다. 모든 검토의 target·enum, 관계 scope 필수, 해석 단일 숫자 일련번호, 발견 경로 유형·달력 날짜, 선택 필드를 포함한 provenance, GENERATED 순서를 엄격히 검사한다.
- 수집 전 원문 달력 날짜를 검증하고 문서의 기관·연도 디렉터리와 대조한다. 원문 진단의 물결도 entity로 보존한다. 시험 기본 임시 경로를 운영체제의 쓰기 가능한 temp로 바꾸고 회귀 시험을 추가했다. 실제 파일럿 자료는 수정하지 않았다.
- 시험 fixture는 도구·규칙·양식·계약 파일만 명시적으로 복사하고 자료 디렉터리는 합성 안내문 외 빈 상태로 만들어 실데이터 충돌·검증 오염을 차단한다. 균형 괄호·꺾쇠 목적지·꺾쇠 안 공백·퍼센트 인코딩 상대 링크를 파일 경로로 검증하고 회귀 시험을 추가했다. 실제 수집·자료 상태 변경은 없다.
- 관계 끝점 계약·필수 문자열 유형·국가법령정보센터 자료별 출처 URL을 검증하고 읽기 경로의 스크립트 fence와 실행 명령을 차단한다. 비유한 JSON 상수를 거부하며 원문 해시 변경 시 관계 검토 진행 상태를 source-verified로 초기화한다. 회귀 시험을 추가했으며 실제 수집·자료 상태 변경은 없다.
- 확정 자기참조 관계·잘못된 증거 URL·중첩 규칙 경로를 거부하고 명령 탐지를 실행 문맥으로 제한했다. 원본·문서·관계를 모두 임시 준비한 뒤 교체하며 실패 시 보존하고, 수집 원문의 GENERATED 표지를 이스케이프한다. 실제 수집·상태 변경은 없다.
- 검토 URL 호스트·연도 경로·자기 대체 금지, 모든 Python 실행 형식 분리, 빈 탭·조문 문맥 식별 검사를 강화했다.
- 기존 자료 스캔 실패를 기록하고 문서·원본 메타데이터 일치 및 원본 교체 전 문서 검증을 보장한다.
- 상세 응답 ID·출처·중복 충돌과 탭 일치 검사를 강화하고 오래된 자동 관계를 재수집 시 정리한다.
- 적용 판본·대체 문서·검토 증거 유형과 시각·중첩 JSON 키·읽기 파일 상대 명령을 검증하고 의존성 실패 실행 기록을 보존한다.
- 중앙부처 1차해석 상세 수집과 기관 구분, 후보 발견 경로 보존, 해석 참조조문 연결을 보완했다.
- 미검토 자료 재수집의 원문 필드를 갱신하고 검토된 원문 변경 보류를 유지했다.
- confirmed 관계의 일치 검토 이력과 쟁점 계약 ID 배열을 검증하고 회귀 시험을 추가했다.

### 추가
- 지식 지도 입구와 읽기·갱신 규칙 두 스킬
- 판례·해석·쟁점 양식, 두 상태 축과 근거 기반 검토·관계 스키마
- DRF API, 조문 연결 목록, 후보 수집, 판례·해석 문서 생성 및 검증 도구
- 의존성 잠금 계약과 스크래치 수집 지원. 실제 자료는 아직 수록하지 않았다.
