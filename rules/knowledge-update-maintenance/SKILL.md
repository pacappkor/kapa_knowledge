---
name: knowledge-update-maintenance
description: 명시적 요청에 따라 법령 연계·판례·해석·재검토를 수집하고 근거 검토·검증·CHANGELOG·PR로 반영하는 1–6단계 절차.
---

# 지식 지도 갱신 절차

사용자가 명시적으로 요청했을 때만 실행한다. 정기 갱신·스케줄은 없다. 읽고 답하기는 범위 밖이며 [knowledge-reading-rules](../knowledge-reading-rules/SKILL.md)에 있다.

## 1. 범위와 기준 확인

쟁점·조문·기관·기간·적용 시점과 기존 검토 상태를 정한다. 초기 역사 조사인지 추가 조사인지 구별한다. 키는 LAW_OC, 없으면 LAW_OC_FILE 경로, 없으면 저장소 부모의 law_oc.txt에서 읽는다. 키를 출력하지 않는다. 모든 URL의 OC를 가린다. 실패를 변동 없음으로 보고하지 않는다.

## 2. 작업 브랜치와 조사 계획

작업 브랜치에서 수행한다. 사용자 권한 범위 밖 저장소는 수정하지 않는다. 초기 조사에는 쟁점별 `issues/<slug>/coverage.md`에 P1–P7별 질의·기간·페이지·실행 기록·제외 이유·빈틈을 적는다.

| 경로 | 역사 조사 범위 |
|---|---|
| P1 | 현행 조문 연결 판례·해석 목록 전 페이지 |
| P2 | 연혁·구법·전신법과 개정 전 조문 번호 연결 |
| P3 | 사건명·쟁점 키워드와 동의어 API 검색 |
| P4 | 참조판례·인용 판례를 거슬러 찾기 |
| P5 | 후속 인용·변경·구별 판결 찾기 |
| P6 | 법제처·소관 기관·국토교통부 해석 찾기 |
| P7 | 실무기준·업무 스킬·인접 쟁점에서 교차 탐색 |

포화 기준: 계획한 P1–P7과 전 페이지를 조사하고 서로 다른 질의·인용 확장 2회 연속 새 고유 자료가 없으면 잠정 포화로 적는다. 접근 실패·제외 기간·기관은 별도로 남긴다. 포화는 완전성 보장이 아니다.

## 3. 수집 트랙 L·P·I·R

- L: kapa_skills의 `rules/skill-update-maintenance/SKILL.md`를 호출한다. 그 저장소에서 승인된 개정 절차가 끝난 뒤 변경 조문 목록 전체를 받아 관련 문서·관계의 재검토 후보로 삼는다. 법령을 여기 복제하지 않는다.
- P: 조문 연결 목록 전 페이지와 DRF prec 검색을 함께 사용한다. 검색 결과의 `데이터출처명`을 보존하고 법원 출처인지 확인한다. precSeq와 공백 정규화 사건번호로 중복을 확인한다.
- I: 법제처·law.go.kr expc와 국토교통부 molitCgmExpc를 조사한다. 기관과 안건번호로 중복을 확인한다. 소관·질의 사실·회신 범위를 보존한다.
- R: 변경 조문, 새 인용·후속 판결, 참조 판본 불명, 충돌 후보를 recheck 트리거로 기록한다. 뒤의 결정이라는 이유로 변경 확정 상태를 붙이지 않는다.

쓰기 작업 전 추적 링크 검사부터 실행하고 곧바로 필수 credential 검사를 worktree 모드로 실행한다. LAW_OC는 뒤의 credential 절차대로 셸에 설정하며 미설정·노출·검사 실패 시 수집·이관 전에 즉시 중단한다. 링크 검사는 의존성·원문·인증정보 파일을 읽지 않고 Git index mode만 확인한다. 검사 후에도 각 쓰기 함수가 출력 경로를 별도로 확인하므로 미추적 링크·junction·reparse point도 열기 전에 거부한다. 저장소 JSON을 읽는 CLI는 공용 실행 래퍼로 표준 출력·오류를 모아 공유 redactor를 적용하며 처리되지 않은 예외도 traceback 대신 가려진 진단과 실패 종료로 바꾼다.

모든 운영 Git 호출은 공용 git_read.run_git helper를 사용한다. helper는 core.fsmonitor=false와 core.untrackedCache=false를 명시하고 LAW_OC·LAW_OC_FILE 및 모든 GIT_* 변수를 제거한 환경 사본으로만 실행하여 저장소 fsmonitor hook이나 환경 재지정에 credential을 상속하지 않는다. 부모의 credential 환경은 유지하며 helper 밖의 직접 자식 실행은 거부한다.

모든 도구 실행은 격리 옵션 `-I`와 바이트코드 쓰기 금지 옵션 `-B`를 함께 사용한다. 사전 검사도 도구 import 전에 캐시 쓰기를 차단해야 하므로 예외가 없다. 비격리 실행의 `PYTHONDONTWRITEBYTECODE=1`도 바이트코드 쓰기를 막지만 `-I`는 Python 환경변수를 무시하므로 이 절차에서는 환경변수만으로 대체하지 않고 반드시 `-B`를 명시한다.

rules/·docs/ 아래 모든 일반 파일(확장자·대소문자·숨김 여부 무관)과 루트 README*·AGENTS*·CLAUDE*·SKILL* 파일(접두사 대소문자 무관)의 전체 바이트를 상대 경로·SHA-256·크기로 tools/doc_command_snapshot.json에 고정한다. 코드 영역이나 실행기 토큰을 추출하지 않으며 일반 문장·HTML·바이너리·새 확장자도 예외가 아니다. 내용·추가·삭제·이름 변경은 snapshot을 명시적으로 재생성하기 전 실패한다. 변경한 문서와 snapshot diff는 같은 PR에서 함께 검토하며 시험 중 자동 재생성·자동 승인하지 않는다. 문서와 snapshot 자체를 읽기 전에 Git index mode 120000·160000을 거부하고 공용 lstat·resolve 경로 검사로 링크·junction·reparse point·비정규 파일·저장소 밖 경로를 차단한다. 문서 트리도 안전한 디렉터리만 순회한다. 불일치는 본문 없이 경로·SHA-256·바이트 크기만 공용 redactor를 거쳐 보고한다. 검증과 unittest도 셸 실패 종료 접미사 또는 PowerShell 다음 줄 종료 검사를 붙여 실패 후 뒤 절차를 실행하지 않는다. rules/**/SKILL.md의 아래 정규 형식과 사전 검사 쌍은 보조 sanity 검사일 뿐 셸 의미 해석이나 주된 강제 수단이 아니다.

문서 수정 후 아래 작은 명령으로 snapshot만 명시적으로 재생성한다. 도구는 위의 안전 읽기와 공용 안전 쓰기를 사용하며 링크 입력·출력을 거부한다. 재생성 뒤 문서와 해시 목록 diff를 PR에서 함께 검토한다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
python -I -B tools/update_doc_snapshot.py
```

문서의 fence 안 Python 명령은 아래 정규 형식만 허용한다. 환경변수는 별도로 설정하고 실행기 앞 대입·wrapper·따옴표·옵션 재정렬·도움말·셸 연산자·치환·리다이렉션을 붙이지 않는다. 일반 도구 명령과 정확히 고정된 unittest 명령 외에는 쓰기 전 링크·credential 사전 검사 쌍만 예외로 허용한다. 사전 검사 두 줄은 셸에서는 각각 실패 시 종료 접미사를, PowerShell에서는 각각 바로 다음 줄의 고정 종료 검사를 사용하고 첫 쓰기 전에 같은 블록에 연속해서 둔다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
python -I -B tools/collect_article.py 'law/009471@261727#a25'
python -I -B tools/fetch_case.py 136387
python -I -B tools/fetch_interp.py 326371
python -I -B tools/fetch_interp.py 23852 cgmexpc
python -I -B tools/fetch_interp.py 225338 cgmexpc
```

API 보조 검색은 lawapi의 search(target, query, page, display, **kw), 상세는 service(target, ID, **kw)를 사용한다. prec·expc·molitCgmExpc·lsJoHstInf는 실제 응답 필드를 확인한다. 자동 조문 수집은 세 웹 탭만 담당하므로 키워드·역사 조사와 기관 API는 별도로 수행한다. cgmexpc 후보는 cgmExpcInfoR.do의 cgmExpcDatSeq 상세를 사용한다. 23852는 국토교통부(molitCgmExpc API로도 확인 가능), 225338은 국세청으로 같은 기관 API에 넣지 않는다. 미등록 기관은 보류한다. 후보 JSONL의 target/source_id가 일치하는 found_via를 문서에 합쳐 조사 조문·경로를 보존한다. 해석의 참조조문·관련법령도 조문 연결과 미대응 진단에 사용한다. 미검토 문서 재수집은 source 필드를 갱신하되 수동 필드는 보존하고, 검토된 원문이 바뀌면 보류한다.

모든 실행은 runs에 success/zero/failure와 질의·페이지·건수·실패 이유를 구별해 기록한다. 수집 오류 진단과 payload 속성명·값의 가림은 API가 실제로 선택한 정규 키를 공유하여 파일 fallback도 보호한다. 파일은 API만 명시적으로 읽고 가림 함수는 선택 값을 재사용하며 scanner는 환경변수 전용으로 유지한다. 실행 날짜는 한 번 읽은 started에서 정하고 상세 tracks는 source 하나만 사용한다. 조문 후보 파일과 실행 기록도 공용 준비·교체·롤백 단위로 저장하므로 기록 실패 시 후보만 남기지 않는다. manifest·전체 이관·법원 복원·오프라인 재생성·JSON 및 관계 저장을 포함한 모든 도구 파일 쓰기는 공용 안전 쓰기 함수를 사용한다. 공용 staging은 출력 경로 전체를 부작용 전에 검사하여 저장소 밖 경로와 symlink·junction·reparse point 부모 또는 최종 링크 파일을 거부하고 교체 전에도 재검사한다. 상세 수집 실패 기록에도 같은 경로 검사를 적용한다. 일반 검증과 쓰기 전 링크 검사는 Git index의 추적 symlink(mode 120000)와 gitlink(mode 160000)를 허용하지 않는다. zero는 정상 빈 결과가 확인된 경우만 쓴다. sources는 생성물이며 직접 편집하지 않는다. 중복 재실행은 자료를 중복 추가하지 않는다. 시험은 KK_ROOT로 스크래치 경로를 지정한다. 잠금 저장소·색인 실패도 dependency failure로 기록하고 다른 탭의 상세 링크는 실패로 처리한다. DRF 서비스 root·일련번호를 대조하며 같은 목적지의 다른 원문 ID도 충돌로 보류한다. 판례의 데이터출처명은 응답과 후보 모두 확인하고 법원도서관·대법원·헌법재판소 외 명시적 출처는 보류한다. 출처명이 제공되지 않은 경우 추정하지 않고 원문 URL과 법원명 확인 범위를 적는다. 재수집은 문서 참조 상태와 무관하게 미검토 cites-article 단독 자동 관계를 새 집합으로 교체하며 제거도 progress 하향 사유다. 수동·검토·혼합 경로 관계는 보존한다. 검토 자동 관계의 근거가 사라지면 relation_recheck에 ID를 기록하고 source-verified로 내리며 재검토 완료 전 게시하지 않는다. 기존 자료 스캔 오류는 preflight failure로 남긴다. 빈 목록도 탭 고유 form ID와 0건 표식을 함께 확인하며 응답 조문 문맥의 판본·조·가지 번호를 요청과 대조한다. 원본 교체 전 기존 문서의 frontmatter·GENERATED 경계와 순서를 검증하고 렌더링을 완료한다. 문서 출처 URL·종류·ID는 저장 원본 메타데이터와 일치해야 한다.

## 4. 원문과 관계 검토

원문·sha256·출처·적용 판본을 대조하고 수동 요약·분석을 작성한다. GENERATED 블록만 도구로 갱신한다. source/summary/analysis/machine 출처를 표시한다. 에이전트 모델 ID, 검토 시각, 대상, 인용 증거, 판단을 reviews에 기록한다.

진행 상태는 candidate → source-verified → relations-reviewed → published다. 참조 상태는 별도다. unreviewed 이외에는 증거가 있는 검토 기록이 필요하다. overruled-confirmed는 판례만, 변경 판결 ID와 변경 선언 인용문이 필요하다. superseded-confirmed는 해석만이며 대체 자료와 근거를 적는다. historical-only는 나이가 아니라 사용 범위에 대한 판단이다. 변경·대체 ID는 각각 실제 존재하는 case·interp 문서로 확인한다. applied_version은 unknown 또는 완전한 판본 ID만 사용하고, 과거 판본은 잠금 commit의 versions_file에서 검증한다. 원문 문서 상태 검토에는 검토 당시 source_sha256도 기록하며 현재 문서 해시와 같은 accept만 승인한다. 검토 evidence는 source(HTTPS 원문 URL)·quote(정확한 인용) 문자열 객체로 적고, decision은 accept / reject / needs-review로 제한한다. 상태·관계 확정에는 accept만 사용한다. reviewed_at은 시간대 포함 ISO 8601 시각이고 change_quote는 인용 문자열이다. 단순 boolean이나 진릿값을 근거로 사용하지 않는다. 변경·대체 ID는 검토 대상 자신이 아니어야 한다. 검토 기록은 4자리 연도 바로 아래의 JSONL만 승인 근거로 사용한다. 증거 URL의 HTTPS scheme·호스트·인증정보 부재를 확인한다. 읽기 파일에는 Markdown 문맥과 인수 구문으로 판별한 실행 명령을 두지 않는다. tools의 Markdown도 같은 규칙을 따르며 명령은 이 스킬에만 둔다.

관계는 found_by와 review를 분리한다. overrules·distinguishes는 confirmed와 증거가 있어야 판단에 사용한다. 자동 추정 관계는 unreviewed로 둔다. confirmed 관계는 해당 관계 ID를 target으로 한 relation_review=confirmed 검토 이력을 reviews/YYYY/*.jsonl에 남기며 모델·시각을 인라인 필드와 일치시킨다. case/interp 출발 관계의 승인 기록에는 검토 당시 source_sha256도 남기고 현재 출발 원문과 대조한다. 쟁점의 articles·standards·skills는 각 계약 ID 배열을 빠짐없이 두고 잠금 색인으로 검증한다.

보류: 원문 열람 불가, 비법원 판례 출처, 판본·사건 동일성 불확실, API 오류·이상 응답, 해석 기관 불명, 변경 문구 미확인, 개인정보·권리 불명. 보류 이유를 실행 기록·coverage에 남기고 게시하지 않는다.

## 5. 검증

CI credential 검사 PR의 허용 base는 기본 브랜치 main뿐이다. pull_request branches 필터와 인라인 준비의 base ref == main == repository default branch 검사를 함께 적용하고, 일치 확인 뒤에만 이벤트의 immutable base SHA와 scanner blob을 읽는다. 비기본 브랜치에 있는 regular scanner도 신뢰하지 않는다. main은 신뢰된 리뷰로 관리한다는 운영 전제이며 실제 branch protection 설정이 있다고 가정하지 않는다. 기본 브랜치 변경은 이 허용 정책과 workflow를 함께 검토해야 한다.

기존 자료의 원문 링크 문법 이스케이프 이관은 저장 JSON으로 오프라인 재생성한다. 문서 경로를 인수로 받으며 원문 메타데이터·해시를 대조한 뒤 GENERATED 블록 전체를 교체한다. 네트워크·상태 변경·발견 경로 추가·관계 재생성은 하지 않는다. 예시는 파일럿의 원문 인용 번호 문서다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
python -I -B tools/rerender_source.py 'cases/서울고법/2011/2010나47706.md'
```

파일럿 0f90463의 1회 baseline 이관은 최신 도구·스키마를 반영한 파일럿 작업 브랜치에서 모든 원문 문서를 먼저 재생성한 뒤 수행한다. 먼저 쟁점의 비정규 GENERATED 표지를 제거해 수동 절로 바꾸고, 법원 원문 표기를 복원하며 누락된 참조조문·출처명 필드만 payload에서 채운다. 원문 JSON·관계·상태는 바꾸지 않는다. 별도 manifest에 명시된 누락 문서 검토 38개와 원문 출발 confirmed 관계 검토 48개만 현재 해시와 migrated-baseline marker로 채우며 과거 판본 보증이 아니라는 SCHEMA의 이관 제한을 PR에 명시한다. manifest는 현재 reviews를 임의 승인하지 않고 원본 파일럿 저장소의 고정 commit 0f90463에서 만든다. 최신 manifest는 ID와 고정 commit 검토 행 전체의 정규 내용 해시를 가진 객체 배열이므로 ID 목록만 가진 기존 파일은 다시 생성한다. 이관 명령에도 같은 원본 저장소·commit과 관계 모드를 전달하며 도구가 manifest를 재계산하고 현재 검토 행의 내용까지 대조한다. 이관 도구 자체도 원본을 전체 commit 0f90463b34127b71af14c7046f7b27660ed9adf7로 고정하고 그 객체가 없는 저장소나 다른 revision을 거부한다. 아래 짧은 revision도 반드시 이 전체 SHA로 해석되어야 하며 CLI 우회 옵션은 없다. PR에서는 이 고정 commit과 migrated-baseline 제한도 검토한다. 아래 repository 인수의 고정 경로 예시는 그 commit을 보유한 로컬 저장소를 가리키며 실제 보관 위치가 다르면 따옴표 안 경로만 바꾼다. 원본 checkout은 읽기만 하며 이 명령들은 별도 export 또는 작업 브랜치에서 실행한다.

```powershell
python -I -B tools/validate.py --check-links
if ($LASTEXITCODE -ne 0) { exit 1 }
python -I -B tools/secret_scan.py --require --worktree
if ($LASTEXITCODE -ne 0) { exit 1 }
python -I -B tools/migrate_issue_sections.py
python -I -B tools/restore_source_court.py
python -I -B tools/migrate_source_fields.py
$docs = Get-ChildItem cases,interpretations -Recurse -Filter *.md | Where-Object { $_.Name -ne 'README.md' } | ForEach-Object { $_.FullName }
python -I -B tools/rerender_source.py @docs
python -I -B tools/build_review_manifest.py --repository '../kapa_knowledge-pilot' --commit 0f90463 --output pilot-review-manifest.json
if ((Get-Content pilot-review-manifest.json -Raw | ConvertFrom-Json).Count -ne 38) { throw 'pilot manifest count mismatch' }
python -I -B tools/migrate_review_digest.py --manifest pilot-review-manifest.json --repository '../kapa_knowledge-pilot' --commit 0f90463
python -I -B tools/build_review_manifest.py --repository '../kapa_knowledge-pilot' --commit 0f90463 --relations --output pilot-relation-review-manifest.json
if ((Get-Content pilot-relation-review-manifest.json -Raw | ConvertFrom-Json).Count -ne 48) { throw 'pilot relation manifest count mismatch' }
python -I -B tools/migrate_review_digest.py --manifest pilot-relation-review-manifest.json --repository '../kapa_knowledge-pilot' --commit 0f90463 --relations
python -I -B tools/validate.py
if ($LASTEXITCODE -ne 0) { exit 1 }
```

```sh
python -I -B tools/validate.py || exit 1
python -I -B -m unittest discover -s tools -t . -p "test_*.py" || exit 1
python -I -B tools/secret_scan.py
python -I -B tools/secret_scan.py --worktree
```

credential 검사는 위 수집기의 파일 fallback과 달리 셸 환경변수 LAW_OC에서만 실제 키를 읽는다. 로컬에서는 개발자가 LAW_OC를 셸에 설정한 뒤 실행한다. 수집 API와 같이 앞뒤 공백·탭 등을 strip한 정규 값으로 검색 바이트를 한 번 만들고 진단 가림에도 공유한다. UTF-8 원문, URL quote(safe 빈 문자열)·quote_plus, UTF-16-LE/BE, UTF-8 바이트의 hex(소문자/대문자/혼합 표기), 표준/URL-safe base64를 대소문자 구분하여 검사한다. base64 전체 키의 독립 인코딩은 padding 유무와 무관하게 검사하고, 큰 blob 내부의 세 정렬 조각은 8자 이상일 때만 검사한다. URL percent escape의 hex 대소문자만 정규화하고 base64는 CR·LF·공백·탭을 제거한 사본에서도 검사하여 MIME 줄바꿈을 허용하되 키 자체의 대소문자는 유지한다. 추적 파일의 현재 바이트 전체(바이너리 포함)와 상대 경로명을 검사하며 경로명에만 키가 있어도 경로를 가려 보고한다. worktree 모드는 미추적·비무시 파일도 포함한다. 무시된 미추적 파일은 읽지 않고, 강제로 추적한 파일은 검사한다. 심볼릭 링크는 링크 문자열만, 하위 모듈은 별도 검사한다. index·과거 이력 검사가 아니므로 커밋 내용과 같은 clean checkout에서 확인한다.

유효한 실제 LAW_OC로 성공하면 문서화한 인코딩의 그 키가 검사 파일에 없음을 보장한다. 다른 키·문자열 조립·escape·난독화·암호화·미문서 인코딩은 범위 밖이며 비공개·PR 검토가 전제다. 값·파생 검색 바이트·일치 내용은 출력하지 않는다. 일치는 종료 1, 실행 오류·잘못된 값은 종료 2다. 미설정·빈 값은 기본 안내와 종료 0이며 필수 모드는 종료 2다. 일반 검증기는 LAW_OC가 있으면 의존성 등 다른 계약을 읽기 전에 worktree 모드로 추적·미추적 비무시 파일을 검사하고 같은 집합만 순회한다. 별도로 여는 의존성 색인·지정 snapshot·참조 파일도 파싱 전에 바이트를 검사하고 무시 파일과 로컬 링크 대상은 읽지 않는다. 노출이나 검사 오류가 있으면 중단하며 진단에 문서화한 키 인코딩이 있으면 percent·hex 대소문자와 base64 공백 정규화 변형까지 포함하여 진단 전체를 가린다. 명백한 quoted literal 대입의 참고 경고는 검증을 실패시키지 않는다.

GitHub 저장소 secret LAW_OC는 등록되어 있다. CI는 전용 단계에서만 secret을 환경변수 LAW_OC로 노출하여 필수 검사를 실행한다. 다른 단계나 job 전체에는 전달하지 않고 echo하지 않는다. GitHub 로그 마스킹도 적용되지만 도구 자체도 키·검색 바이트를 출력하지 않는다. checkout·Python 준비 뒤에는 workflow 인라인 표준 라이브러리만 실행하여 PR base SHA(main push는 해당 SHA, 수동 실행은 기본 브랜치 ref를 commit으로 고정)의 tools/secret_scan.py·credentials.py·git_read.py 일반 blob 세 개를 작업 트리 밖의 새 runner 임시 디렉터리에 추출한다. PR 코드나 helper를 실행·import하지 않고 누락·비정규 객체에는 실패한다. 첫 저장소 코드 실행은 이 trusted scanner이며 경로와 무관하게 실행한다. cwd는 PR checkout이고 추적·미추적 비무시 파일 전체를 --require·--worktree로 검사한다. fork PR 등 secret이 없는 실행은 필수 모드에서 실패한다.

전용 단계의 환경변수 LAW_OC에 GitHub secret LAW_OC를 연결한다. 단계 이름은 Scan actual LAW_OC value로 두고 workflow의 TRUSTED_SCANNER 디렉터리에 추출한 scanner를 격리 실행한다. 아래는 로컬 검사 정규 명령이며 CI에서는 PR 작업 트리의 tools 스크립트를 실행하지 않는다. same-repo PR은 workflow YAML 자체도 제안할 수 있으므로 trusted base scanner만으로 악성 workflow 변경까지 막지는 못한다. workflow 작성 권한·PR 리뷰가 잔여 신뢰 경계이며, 별도 environment 승인·secret 설정이나 PR에서 수정할 수 없는 실행 출처는 이번 변경에 포함하지 않는다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
```

오류가 0이어야 한다. 형제 체크아웃이 없으면 deps.lock에 고정한 vendor 메타데이터로 검증한다. 형제 저장소가 있지만 잠금 객체가 없으면 실패하며 vendor로 숨기지 않는다. 개발 WORKTREE는 형제 체크아웃에서만 허용하는 경고 상태이고 PR에서는 실제 SHA로 고정한다. 링크·출처 해시·검토·관계와 읽기/갱신 분리를 함께 확인한다.

### 저장 조사에서 보류 카탈로그 생성

과거 판본·FAQ·회신 동일성 주장은 저장된 파일럿 조사에서만 가져온다. 카탈로그는 정식 해석 수록이나 검토 승인이 아니다. 출처 바이트가 바뀌면 해시와 생성 결과가 달라져 검증이 실패한다. 변경된 출처와 결과를 함께 검토하고 명시적으로 재생성한다. 이 명령은 네트워크·OC 없이 기존 잠금 메타데이터만 사용한다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
python -I -B tools/build_material_catalog.py
```

### 의존성 메타데이터의 명시적 갱신

kapa_skills의 승인된 새 commit을 deps.lock의 commit에 먼저 고정한다. 로컬 형제 체크아웃 또는 KK_SKILLS_ROOT가 그 객체를 보유해야 한다. vendor_skills 도구는 작업 사본이 아니라 그 commit의 Git 객체에서 docs/law-index.json과 색인이 지정한 sources/laws 아래 versions 메타데이터만 읽는다. 법령 본문·다른 저장소 코드는 복제하지 않으며 네트워크 접근은 없다. 아래 명령은 공용 안전 쓰기로 vendor 원본 바이트와 deps.lock의 vendor.commit·파일별 SHA-256을 함께 갱신한다.

```sh
python -I -B tools/validate.py --check-links || exit 1
python -I -B tools/secret_scan.py --require --worktree || exit 1
python -I -B tools/vendor_skills.py
```

형제 위치가 다르면 KK_SKILLS_ROOT를 셸에 별도로 설정하거나 도구의 --skills-root 인수로 지정한다. 새 색인에서 사라진 메타데이터 파일은 PR에서 확인하고 Git으로 명시적으로 삭제한다. 도구는 임의 파일 삭제를 하지 않으며 시험은 vendor 파일 집합과 잠금 목록의 일치도 확인한다. 같은 PR에서 deps.lock의 upstream commit·vendor commit·모든 해시 및 vendor diff를 함께 검토한다. commit만 바꾸고 vendor를 갱신하지 않거나 원본 바이트가 해시와 다르면 fallback은 실패한다. CI는 vendor를 다시 생성하거나 자동 승인하지 않고 검증만 한다. 형제 체크아웃 없이도 과거 applied_version을 검증하도록 versions 메타데이터까지 포함한다.

위 표준 unittest 명령은 저장소 루트에서 실행한다. CI 전용 .github/ci/ci_tests_supervise.py는 같은 명령에 -v만 추가하여 별도 프로세스로 실행하고, .github/ci/ci_layout_check.py의 패키지 구조 검사와 stderr 완료 요약 검사를 더한다. 감독기는 운영 tools의 subprocess 예외가 아니라 별도 CI 진입점이며 운영 코드에서 import하지 않는다.

## 6. 기록과 반영

CHANGELOG의 Unreleased에 조사 범위·자료 수·상태 변경·관계 변경·미확인을 적는다. coverage와 실행 기록을 연결한다. [릴리스 규칙](../../docs/RELEASING.md)에 따라 PR을 열고 검토 모델·증거·검증 결과를 포함한다. 사용자에게 성공/0건/실패와 미완료 사항을 구별해 보고한다.
