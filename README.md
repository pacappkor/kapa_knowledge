# kapa_knowledge

감정평가 법률 지식 지도(내부용, 비공개). 판례·법령해석·유권해석과 실무 쟁점을 kapa_skills의 조문·실무기준·업무 스킬에 연결한다. 법령은 복제하지 않는다.

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

`deps.lock`의 kapa_skills commit과 형제 체크아웃의 `docs/law-index.json`으로 참조를 검증한다. 개발 중 WORKTREE는 경고이며 PR에서는 실제 SHA를 고정한다. 형제 저장소가 없으면 검증 불가다.

## credential 검사 범위

`tools/secret_scan.py`는 실제 키를 환경변수 LAW_OC에서만 읽는 값 기반 검사다. 수집 API와 같이 앞뒤 공백·탭 등을 strip한 값을 기준으로 검색 바이트를 한 번 만들고 진단 가림에도 같은 바이트를 사용한다. 대소문자를 구분하여 UTF-8 원문, URL quote(safe 빈 문자열)·quote_plus, UTF-16-LE·BE, UTF-8 바이트의 hex(소문자·대문자·혼합 표기), 표준·URL-safe base64를 찾는다. base64는 전체 키의 독립 인코딩을 padding 유무와 무관하게 검사하고, 더 큰 blob 안의 세 바이트 정렬 조각은 8자 이상일 때만 검사하여 짧은 키의 오탐을 줄인다. CR·LF·공백·탭을 제거한 사본에서 MIME 줄바꿈도 탐지한다. URL의 percent escape는 hex 숫자의 대소문자만 정규화하며 키 자체는 대소문자를 구분한다. 값·파생 검색 바이트·일치 내용은 출력하지 않고 경로와 인코딩만 보고한다. API의 payload 가림과 수집 오류 진단 가림은 공용 선택 함수에서 API가 실제로 선택한 키를 사용하며 파일 fallback도 포함한다. 파일은 API만 명시적으로 읽고 다른 가림 함수는 선택된 값을 재사용한다. 저장 payload의 문자열 값과 속성명도 scanner의 같은 matcher로 위 인코딩·정규화 표현을 검사한다. 원문 키는 기존처럼 치환하고 남은 인코딩 일치가 있으면 그 문자열 전체를 가리며, 가림이 필요한 payload의 엄격한 정규 저장과 속성명 가림 후 충돌은 거부한다. scanner는 이와 별도로 환경변수 전용 정책을 유지한다.

범위는 Git 추적 파일의 현재 작업 사본 바이트 전체(바이너리 포함)와 상대 경로명의 바이트이며, 경로명에만 키가 있어도 경로를 가려 노출로 보고한다. 선택한 worktree 모드에서는 미추적·비무시 파일도 포함한다. Git이 무시하는 미추적 로컬 파일은 읽지 않는다. 강제로 추적한 파일은 ignore 패턴과 무관하게 검사한다. 심볼릭 링크는 링크 문자열만 읽으며 하위 모듈은 별도 저장소에서 검사한다. Git 이력이나 아직 작업 사본에 반영하지 않은 index 내용은 검사하지 않으므로 커밋할 내용과 같은 clean checkout에서 실행해야 한다.

유효한 실제 LAW_OC가 주어지고 검사에 성공하면 문서화한 인코딩의 그 키가 검사한 파일에 없음을 보장한다. 다른 키·문자열 조립·escape·난독화·암호화 및 문서화하지 않은 인코딩의 탐지는 보장하지 않는다. 비공개 저장소와 모든 변경의 PR 검토를 전제로 하며 실제 값은 GitHub secret LAW_OC와 추적하지 않는 로컬 보관소에만 둔다. 키 미설정·빈 값은 기본적으로 건너뛰지만 필수 모드에서는 실패한다. 일반 검증기와 쓰기 전 링크 검사는 Git index의 추적 symlink(mode 120000)와 gitlink(mode 160000)를 모두 거부한다. 하위 모듈 내부로 쓰는 별도 절차는 이 저장소의 갱신 범위가 아니다. manifest·이관·법원 복원·오프라인 재생성·JSON 및 관계 저장을 포함한 모든 도구 파일 쓰기는 공용 경로 검사와 안전 쓰기 함수를 거친다. 출력 경로가 저장소 안에 있고 기존 부모가 링크·junction·reparse point가 아닌 실제 디렉터리인지 확인하며 최종 링크 파일과 안전하지 않은 경로는 열기 전에 거부한다. 갱신 절차는 쓰기 전 가벼운 추적 링크 검사 직후 worktree 필수 credential 검사를 수행하고 미설정·노출·실패 시 수집·이관 전에 중단한다. 저장소 JSON을 읽는 CLI의 출력·오류와 처리되지 않은 예외는 공용 실행 래퍼에서 모아 같은 redactor를 적용하므로 traceback으로 원문 키가 새지 않는다. 자식 프로세스는 표준 출력과 오류를 모두 명시적으로 캡처하거나 버려야 하며, 캡처 결과를 출력할 때도 공용 redactor를 거친다. Python 스트림 래퍼만으로 자식의 상속 파일 디스크립터를 가릴 수 없으므로 tools 전체 회귀 검사가 캡처 없는 subprocess 호출을 거부한다. production 자식 실행은 literal git 실행기와 고정된 읽기 전용 하위 명령·옵션 allowlist만 허용하며 shell 실행·동적 argv 확장·다른 실행 파일·Git 설정 쓰기는 거부한다. Git 허용 목록은 ls-files·ls-tree·rev-parse·cat-file(-e·-t·-s·-p·--batch) plumbing으로 한정한다. show·diff·log·status·config·check-ignore 및 textconv·외부 diff·filter 옵션은 거부하며 객체 원문은 cat-file -p로 읽는다. 모든 운영 Git은 공용 git_read.run_git helper만 사용하여 core.fsmonitor=false·core.untrackedCache=false를 고정하고, LAW_OC·LAW_OC_FILE 및 모든 GIT_* 설정·저장소 재지정 변수를 제거한 환경 사본을 넘긴다. 부모 scanner의 환경은 바꾸지 않으며 helper 밖의 직접 자식 실행은 회귀 검사에서 거부한다. os·asyncio·pty와 임의 객체의 이벤트 루프 subprocess_exec·subprocess_shell 등 대체 자식 실행 API도 현재 허용하지 않는다. 시험 fixture 쓰기 면제는 실제 unittest discovery 대상 중 production import 경로에서 도달하지 않는 모듈에만 적용하며 production이 test_ 이름 모듈을 import하면 실패한다. 문서 snapshot은 rules/·docs/ 아래 모든 파일(확장자·대소문자 무관)과 루트 README*·AGENTS*·CLAUDE*·SKILL* 파일(접두사 대소문자 무관)의 전체 바이트를 경로·SHA-256·크기로 고정한다. 내용·추가·삭제·이름 변경은 명시적 재생성 전 실패하며 snapshot diff를 같은 PR에서 검토한다. 읽기 전에 index mode 및 공용 경로 검사로 링크·junction·reparse point·비정규 파일·저장소 이탈을 거부하고 불일치 진단은 본문 없이 가려진 경로·해시·크기로 제한한다. 문서 영역 추출은 하지 않고 rules/**/SKILL.md의 정규 사전 검사 쌍만 보조 sanity 검사로 유지한다. 이 AST 검사는 import 별칭과 직접 호출을 다루는 회귀 방지 수단이며 임의 재결속·데이터 흐름·Git 환경 설정까지 격리하는 sandbox는 아니므로 신뢰된 코드와 PR 검토가 전제다. 일반 검증기는 LAW_OC가 있으면 다른 계약을 읽기 전에 추적·미추적 비무시 파일을 worktree 모드로 검사하고 같은 파일 집합만 순회한다. 별도로 여는 의존성 색인·지정 snapshot·참조 파일도 파싱 전에 바이트를 검사하고 무시 파일과 로컬 링크 대상은 읽지 않는다. 노출이나 검사 오류가 있으면 내용이 진단으로 새지 않도록 중단하며, 진단에 문서화한 키 인코딩이 있으면 진단 전체를 가린다. 명백한 긴 quoted literal 대입은 실패하지 않는 참고 경고만 낸다.

도구 실행은 `-I -B`를 함께 사용하여 import 전부터 바이트코드 캐시 쓰기를 막는다. 비격리 실행의 `PYTHONDONTWRITEBYTECODE=1`도 같은 효과지만 `-I`는 Python 환경변수를 무시하므로 이 절차에서는 명시적 `-B`가 필수다.

로컬에서는 개발자가 셸 환경변수 LAW_OC를 설정하여 실행한다. CI는 GitHub secret LAW_OC를 환경변수 LAW_OC로 전달하는 전용 필수 검사 단계를 별도 CI PR에서 추가할 예정이다. 실행 명령과 종료 코드는 [갱신 절차](rules/knowledge-update-maintenance/SKILL.md)에 둔다. 이 PR은 workflow를 추가하지 않는다.

## 변경과 권리

[CHANGELOG](CHANGELOG.md), [릴리스 규칙](docs/RELEASING.md), [NOTICE](NOTICE.md), [LICENSE](LICENSE)를 따른다. 저장소는 GPL-3.0-only이며 비공개 상태를 유지한다.
