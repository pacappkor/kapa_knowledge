# kapa_knowledge

[![visitors](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pacappkor/kapa_knowledge/traffic/.traffic/badge-views.json)](https://github.com/pacappkor/kapa_knowledge)
[![clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pacappkor/kapa_knowledge/traffic/.traffic/badge-clones.json)](https://github.com/pacappkor/kapa_knowledge)

감정평가 법률 지식 지도. 공개 가능한 저장소로 운영하며 판례·법령해석·유권해석과 실무 쟁점을 kapa_skills의 조문·실무기준·업무 스킬에 연결한다. 법령은 복제하지 않는다.

## 시작

- [00-knowledge-start](00-knowledge-start/SKILL.md): 쟁점 또는 업무에서 자료를 찾는다.
- [knowledge-reading-rules](rules/knowledge-reading-rules/SKILL.md): 읽기·답변만 한다.
- [knowledge-update-maintenance](rules/knowledge-update-maintenance/SKILL.md): 명시적 요청에만 갱신한다. 도구 명령은 이곳에만 있다.

## 구조

| 경로 | 내용 |
|---|---|
| [issues](issues/README.md) | 쟁점과 조사 범위 |
| [cases](cases/README.md) | 판례와 전문 |
| [interpretations](interpretations/README.md) | 법제처·기관 해석 |
| relations/relations.jsonl | 자료 간 관계 |
| [reviews](reviews/README.md) | 모델·근거를 갖춘 검토 이력 |
| [sources](sources/README.md) | 기계 수집 원본 |
| [runs](runs/README.md) | 성공·0건·실패를 구별하는 수집 기록 |
| templates/ | 판례·해석·쟁점 양식 |
| [docs/SCHEMA.md](docs/SCHEMA.md) | ID·필드·상태·관계 계약 |
| tools/ | 수집·문서 생성·검증 도구 |

진행 상태는 자동으로 올릴 수 있지만 참조 상태는 검토 근거가 필요하다. 요약은 원문을 대신하지 않는다. 검토자는 에이전트이며 모델과 증거를 기록한다. 초깃값에는 실제 수집 자료가 없다.

`deps.lock`의 kapa_skills commit과 형제 체크아웃의 `docs/law-index.json`으로 참조를 검증한다. 개발 중 WORKTREE는 경고이며 PR에서는 실제 SHA를 고정한다. 형제 체크아웃이 없으면 `vendor/kapa_skills/`의 고정 색인·과거 판본 메타데이터를 사용한다. 법령 본문은 복제하지 않는다. vendor commit과 각 원본 바이트의 SHA-256을 deps.lock에 함께 기록하며, commit 불일치·파일 누락·해시 불일치에는 실패한다. 존재하는 형제 저장소의 잠금 객체를 읽지 못한 경우에는 vendor로 숨기지 않고 실패한다.

## credential 검사 범위

`tools/secret_scan.py`는 실제 키를 환경변수 LAW_OC에서만 읽는 값 기반 검사다. 수집 API와 같이 앞뒤 공백·탭 등을 strip한 값을 기준으로 검색 바이트를 한 번 만들고 진단 가림에도 같은 바이트를 사용한다. 대소문자를 구분하여 UTF-8 원문, URL quote(safe 빈 문자열)·quote_plus, UTF-16-LE·BE, UTF-8 바이트의 hex(소문자·대문자·혼합 표기), 표준·URL-safe base64를 찾는다. base64는 전체 키의 독립 인코딩을 padding 유무와 무관하게 검사하고, 더 큰 blob 안의 세 바이트 정렬 조각은 8자 이상일 때만 검사하여 짧은 키의 오탐을 줄인다. CR·LF·공백·탭을 제거한 사본에서 MIME 줄바꿈도 탐지한다. URL의 percent escape는 hex 숫자의 대소문자만 정규화하며 키 자체는 대소문자를 구분한다. 값·파생 검색 바이트·일치 내용은 출력하지 않고 경로와 인코딩만 보고한다. API의 payload 가림과 수집 오류 진단 가림은 공용 선택 함수에서 API가 실제로 선택한 키를 사용하며 파일 fallback도 포함한다. 파일은 API만 명시적으로 읽고 다른 가림 함수는 선택된 값을 재사용한다. 저장 payload의 문자열 값과 속성명도 scanner의 같은 matcher로 위 인코딩·정규화 표현을 검사한다. 원문 키는 기존처럼 치환하고 남은 인코딩 일치가 있으면 그 문자열 전체를 가리며, 가림이 필요한 payload의 엄격한 정규 저장과 속성명 가림 후 충돌은 거부한다. scanner는 이와 별도로 환경변수 전용 정책을 유지한다.

범위는 Git 추적 파일의 현재 작업 사본 바이트 전체(바이너리 포함)와 상대 경로명의 바이트이며, 경로명에만 키가 있어도 경로를 가려 노출로 보고한다. 선택한 worktree 모드에서는 미추적·비무시 파일도 포함한다. Git이 무시하는 미추적 로컬 파일은 읽지 않는다. 강제로 추적한 파일은 ignore 패턴과 무관하게 검사한다. 심볼릭 링크는 링크 문자열만 읽으며 하위 모듈은 별도 저장소에서 검사한다. Git 이력이나 아직 작업 사본에 반영하지 않은 index 내용은 검사하지 않으므로 커밋할 내용과 같은 clean checkout에서 실행해야 한다.

유효한 실제 LAW_OC가 주어지고 검사에 성공하면 문서화한 인코딩의 그 키가 검사한 파일에 없음을 보장한다. 다른 키·문자열 조립·escape·난독화·암호화 및 문서화하지 않은 인코딩의 탐지는 보장하지 않는다. 저장소의 공개 여부를 보안 경계로 삼지 않는다. 모든 변경은 PR로 검토하고 실제 값은 GitHub Actions secret LAW_OC 또는 로컬 셸 환경변수로만 전달한다. 키 미설정·빈 값은 기본적으로 건너뛰지만 필수 모드에서는 실패한다. 일반 검증기와 쓰기 전 링크 검사는 Git index의 추적 symlink(mode 120000)와 gitlink(mode 160000)를 모두 거부한다. 하위 모듈 내부로 쓰는 별도 절차는 이 저장소의 갱신 범위가 아니다. manifest·이관·법원 복원·오프라인 재생성·JSON 및 관계 저장을 포함한 모든 도구 파일 쓰기는 공용 경로 검사와 안전 쓰기 함수를 거친다. 출력 경로가 저장소 안에 있고 기존 부모가 링크·junction·reparse point가 아닌 실제 디렉터리인지 확인하며 최종 링크 파일과 안전하지 않은 경로는 열기 전에 거부한다. 갱신 절차는 쓰기 전 가벼운 추적 링크 검사 직후 worktree 필수 credential 검사를 수행하고 미설정·노출·실패 시 수집·이관 전에 중단한다. 저장소 JSON을 읽는 CLI의 출력·오류와 처리되지 않은 예외는 공용 실행 래퍼에서 모아 같은 redactor를 적용하므로 traceback으로 원문 키가 새지 않는다. 자식 프로세스는 표준 출력과 오류를 모두 명시적으로 캡처하거나 버려야 하며, 캡처 결과를 출력할 때도 공용 redactor를 거친다. Python 스트림 래퍼만으로 자식의 상속 파일 디스크립터를 가릴 수 없으므로 tools 전체 회귀 검사가 캡처 없는 subprocess 호출을 거부한다. production 자식 실행은 literal git 실행기와 고정된 읽기 전용 하위 명령·옵션 allowlist만 허용하며 shell 실행·동적 argv 확장·다른 실행 파일·Git 설정 쓰기는 거부한다. Git 허용 목록은 ls-files·ls-tree·rev-parse·cat-file(-e·-t·-s·-p·--batch) plumbing으로 한정한다. show·diff·log·status·config·check-ignore 및 textconv·외부 diff·filter 옵션은 거부하며 객체 원문은 cat-file -p로 읽는다. 모든 운영 Git은 공용 git_read.run_git helper만 사용하여 core.fsmonitor=false·core.untrackedCache=false를 고정하고, LAW_OC·LAW_OC_FILE 및 모든 GIT_* 설정·저장소 재지정 변수를 제거한 환경 사본을 넘긴다. 부모 scanner의 환경은 바꾸지 않으며 helper 밖의 직접 자식 실행은 회귀 검사에서 거부한다. os·asyncio·pty와 임의 객체의 이벤트 루프 subprocess_exec·subprocess_shell 등 대체 자식 실행 API도 현재 허용하지 않는다. 시험 fixture 쓰기 면제는 실제 unittest discovery 대상 중 production import 경로에서 도달하지 않는 모듈에만 적용하며 production이 test_ 이름 모듈을 import하면 실패한다. 문서 snapshot은 rules/·docs/ 아래 모든 파일(확장자·대소문자 무관)과 루트 README*·AGENTS*·CLAUDE*·SKILL* 파일(접두사 대소문자 무관)의 전체 바이트를 경로·SHA-256·크기로 고정한다. 내용·추가·삭제·이름 변경은 명시적 재생성 전 실패하며 snapshot diff를 같은 PR에서 검토한다. 읽기 전에 index mode 및 공용 경로 검사로 링크·junction·reparse point·비정규 파일·저장소 이탈을 거부하고 불일치 진단은 본문 없이 가려진 경로·해시·크기로 제한한다. 문서 영역 추출은 하지 않고 rules/**/SKILL.md의 정규 사전 검사 쌍만 보조 sanity 검사로 유지한다. 이 AST 검사는 import 별칭과 직접 호출을 다루는 회귀 방지 수단이며 임의 재결속·데이터 흐름·Git 환경 설정까지 격리하는 sandbox는 아니므로 신뢰된 코드와 PR 검토가 전제다. 일반 검증기는 LAW_OC가 있으면 다른 계약을 읽기 전에 추적·미추적 비무시 파일을 worktree 모드로 검사하고 같은 파일 집합만 순회한다. 별도로 여는 의존성 색인·지정 snapshot·참조 파일도 파싱 전에 바이트를 검사하고 무시 파일과 로컬 링크 대상은 읽지 않는다. 노출이나 검사 오류가 있으면 내용이 진단으로 새지 않도록 중단하며, 진단에 문서화한 키 인코딩이 있으면 진단 전체를 가린다. 명백한 긴 quoted literal 대입은 실패하지 않는 참고 경고만 낸다.

도구 실행은 `-I -B`를 함께 사용하여 import 전부터 바이트코드 캐시 쓰기를 막는다. 비격리 실행의 `PYTHONDONTWRITEBYTECODE=1`도 같은 효과지만 `-I`는 Python 환경변수를 무시하므로 이 절차에서는 명시적 `-B`가 필수다.

로컬에서는 개발자가 셸 환경변수 LAW_OC를 설정하여 실행한다. CI는 GitHub secret LAW_OC를 전용 필수 검사 단계에만 전달한다. 실행 명령과 종료 코드는 [갱신 절차](rules/knowledge-update-maintenance/SKILL.md)에 둔다.

## CI

credential 검사를 받는 PR의 허용 base는 기본 브랜치 `main`뿐이다. secret-free 검사는 모든 PR에서 실행하지만 실제 값 검사 준비는 base ref == main == repository default branch를 확인하며, ref 확인 후에만 이벤트의 immutable base SHA를 읽고 blob을 추출한다. 임의 브랜치의 regular scanner는 신뢰하지 않는다. `main`이 신뢰된 리뷰로 관리된다는 운영 전제이며 branch protection이 실제 설정되어 있다고 가정하거나 보장하지 않는다. 기본 브랜치 변경은 허용 정책·workflow의 명시적 검토를 요구한다.

GitHub Actions는 모든 PR·푸시·수동 실행에 secret-free `offline-checks` 작업을 실행한다. 별도의 `credential-scan`은 main 푸시·수동 실행·same-repo PR에서만 실행하고 fork PR에서는 건너뛴다. 두 작업은 ubuntu-latest와 Python 3.12를 사용한다. 예약 실행·행렬·외부 자료 수집·다른 저장소 checkout은 없다. 권한은 contents: read이며 checkout 인증정보는 남기지 않는다.

- credential-scan 작업의 checkout·Python 준비 뒤 인라인 표준 라이브러리 코드만으로 trusted scanner를 준비한다. PR은 이벤트의 base SHA, main push는 해당 SHA, 수동 실행은 기본 브랜치의 원격 추적 ref를 commit으로 고정한다. 그 Git 객체의 tools/secret_scan.py·credentials.py·git_read.py 일반 blob 세 개만 작업 트리 밖의 새 runner 임시 디렉터리에 추출한다. 준비 단계는 PR 코드·helper를 import하거나 실행하지 않으며 객체·모듈 누락이나 비정규 파일에는 실패하고 PR 코드로 fallback하지 않는다.
- credential-scan 작업의 첫 저장소 코드 실행은 Scan actual LAW_OC value 단계의 추출된 trusted scanner다. 격리 실행으로 PR의 scanner·의존모듈·동명 shadow 모듈을 import하지 않으며 cwd는 PR checkout을 유지해 추적 파일과 미추적·비무시 파일 전체의 현재 바이트·경로를 필수 검사한다. 경로와 무관하게 실행하며 secret은 이 단계에만 노출하고 출력하지 않는다. 이 작업이 실행될 때 secret이 없으면 실패 폐쇄(fail closed)한다. fork PR에는 secret을 전달하지 않으며 offline-checks만 실행한다.
- 이 분리는 scanner나 의존모듈을 바꾼 PR이 검사 중 secret을 실행 코드로 받는 경로를 막는다. same-repo PR이 workflow YAML 자체를 바꾸어 secret을 직접 사용하는 경로까지 차단하지는 않는다. trusted base만으로 workflow의 실행 출처를 고정했다고 주장하지 않으며, workflow 작성 권한과 PR 리뷰는 여전히 신뢰 경계다. 악성 workflow 변경까지 승인 전에 차단하려면 별도 environment secret·승인 규칙 또는 PR이 수정할 수 없는 workflow 실행 경계가 필요하다. 이 PR은 저장소 설정·리뷰어·environment를 변경하지 않는다.
- 추적 symlink·gitlink를 기존 검증기의 가벼운 링크 검사로 거부한다.
- offline-checks는 secret 없이 scanner를 --require 없이 호출하고 일반 검증·문서 snapshot·전체 회귀 시험을 항상 실행한다. 현재 scanner는 LAW_OC 미설정 시 값 검사를 건너뛰며 pattern/shape 검사기가 아니다. 검증기의 literal-shape 경고는 참고용이며 실제 키 부재를 보장하지 않는다. 변경 경로 계산은 비교 기준과 실행 요약에 사용한다.
- PR은 base SHA와의 세 점 비교, 일반 푸시는 조상 before와의 두 점 비교를 사용한다. 강제 푸시는 공통 조상을 기준으로 전체 검사하며 수동 실행·기준 누락·공통 조상 없음·diff 실패도 전체 검사한다. rename 탐지를 끄므로 이전 도구 경로 삭제가 숨겨지지 않는다.
- 문서 전체 바이트 snapshot은 항상 별도의 읽기 전용 검사로 대조한다. snapshot 미갱신은 실패하며 CI에서 자동 재생성하지 않는다.
- 시험 감독기는 import 없이 패키지 구조를 확인한 뒤 표준 unittest discovery를 그대로 실행한다. 종료 코드 0과 stderr의 마지막 Ran N tests 요약·그 직후 OK 또는 OK (...)를 요구한다. 0건은 실제 skip 보고가 있어야 허용한다. 종료 직후 대기 바이트까지만 판정에 포함하고 하위 프로세스가 파이프를 계속 잡아도 출력 대기는 10초로 제한한다. 신뢰된 시험 코드의 우발적 조기 종료 검사이며 sandbox·파일별 실행 증명·악성 출력 위조 방어는 아니다.
- 마지막으로 무시 파일을 포함한 작업 트리 불변성과 diff 공백을 검사한다. 공백 기준은 변경 선택과 공유하며 기준이 없으면 빈 트리, 수동 실행은 부모가 있으면 HEAD^, rewind는 새 commit이 없어 공백만 건너뛴다. 현재 sources에는 보존할 공백 오류가 없어 sources/**도 제외하지 않는다.

모든 Python 실행은 격리·바이트코드 쓰기 금지를 함께 사용하고 작업 환경에도 PYTHONDONTWRITEBYTECODE를 설정한다. `.github/ci/`는 Git 비교·Actions 출력 파일·시험 자식 실행을 담당하는 CI 전용 감독 영역이다. tools의 운영 import 경로에서 사용하지 않으며 운영 도구의 공용 안전 쓰기·git_read plumbing 제한을 완화하지 않는다. 이 경계와 신뢰된 workflow·시험 코드는 PR에서 함께 검토한다. 의존성 갱신은 [갱신 절차](rules/knowledge-update-maintenance/SKILL.md)의 명시적 vendor 갱신을 따른다.

별도 Daily traffic workflow는 조직 템플릿을 사용하여 매일 03:17 UTC 또는 수동 실행으로 방문·clone 통계를 traffic 브랜치에 기록한다. 이 workflow만 contents: write와 GitHub Actions secret TRAFFIC_TOKEN을 사용한다. 관리자가 token과 재사용 workflow 접근을 설정해야 하며 CI에는 통계 쓰기 권한을 주지 않는다.

## 변경과 권리

[CHANGELOG](CHANGELOG.md), [릴리스 규칙](docs/RELEASING.md), [NOTICE](NOTICE.md), [LICENSE](LICENSE)를 따른다. 자체 작성물의 라이선스는 GPL-3.0-only이며 제3자 자료의 권리는 NOTICE를 따른다. 공개 배포 시 자료별 개인정보·배포 권리를 별도로 확인한다. 보안 신고는 [SECURITY](SECURITY.md)를 따른다.
