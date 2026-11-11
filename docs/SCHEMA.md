# 지식 지도 스키마 v1

## 저장 형식과 ID

UTF-8, LF. 일반 계약 검증은 UTF-8 디코딩 실패와 NUL 문자를 오류로 보고한다. 이 정책과 별도로 값 기반 credential 검사는 바이너리까지 바이트 그대로 검사한다. 문서는 `---` 경계의 제한 YAML frontmatter를 쓴다. 키는 한 줄에 하나, 값은 JSON 문자열·숫자·null·배열·객체 또는 한 줄 문자열이다. 중복 키·다중 줄 YAML·앵커는 허용하지 않는다. 수동 필드도 이 형식을 따른다. JSON·JSONL도 중복 키와 NaN/Infinity/-Infinity 비유한 상수는 오류다.

| 대상 | ID |
|---|---|
| 법령 | `law/<6자리 lsId>` |
| 판본 | `law/<lsId>@<lsiSeq>` |
| 조문 | `law/<lsId>@<lsiSeq>#a<조>[-<가지>]` |
| 실무기준 | `apps@<admRulSeq>#<code>` |
| 판례 | `case/<법원명>/<공백 정규화 사건번호>` |
| 해석 | `interp/<agency>/<안건번호>` |
| 쟁점 | `issue/<slug>` |
| 업무 스킬 | `skill/<name>` |

판례 ID의 법원명과 문서 디렉터리는 공통 `court_slug()`로 원문 법원명에서 공백만 제거한다. source 출처인 frontmatter `court`는 payload 법원명을 공백 포함 그대로 보존한다. 파일럿의 정규화된 court 필드 복원은 저장 원본 식별·해시를 확인하는 오프라인 도구로 수행하며 ID·경로·검토·원본은 바꾸지 않는다.

법령·판본·조문·실무기준·스킬은 deps.lock의 kapa_skills commit에서 검증한다. WORKTREE이면 형제 체크아웃 작업 파일을 읽고 경고한다. 그 외에는 형제 체크아웃의 해당 SHA에서 `docs/law-index.json`을 읽는다. 저장소·SHA·색인이 없으면 `검증 불가` 오류다. 현재 조문만 있는 색인에 없는 과거 조문은 추정 통과하지 않는다. 해당 판본 원문을 별도로 확인하고 의존 색인 범위를 해결해야 한다.

### 과거 판본과 보류 자료 카탈로그

`catalogs/materials.json`은 schema 1의 `unpublished-evidence` 생성물이다. 저장 조사 기록에서 오프라인 재생성하며 검증기는 입력 파일의 실제 바이트 해시와 생성 결과 전체를 비교한다. 검토 기록이나 게시 문서를 대신하지 않는다. `dependency_commit`은 deps.lock과 같아야 하며 WORKTREE 생성은 거부한다. 원본·GENERATED·기존 검토는 수정하지 않는다.

`historical_versions`의 ID는 기존 판본 계약을 따른다. `catalog_status`는 `verified-version-list`, `verified-current-index`, `unavailable` 중 하나다. 잠금 색인의 `versions_file`을 공용 dependency reader로 읽고 법령 ID와 일련번호를 대조한다. vendor fallback은 기존 commit·SHA-256 검증을 유지한다. `metadata_sha256`은 메타데이터 원본 바이트 해시이며 같은 일련번호에 여러 시행일이 있으면 `entries`에 모두 보존한다. 판본 목록 확인은 조문 존재·본문·사건 적용·경과조치 확인이 아니다. `article_text_status`는 unavailable, `applicability_status`는 unverified다.

미확인은 `unavailable_reason`에 `law-id-absent-from-pinned-index`, `versions-file-absent-from-pinned-index`, `sequence-absent-from-pinned-version-list`로 구분한다. 현재 잠금에서 공특법 계열 001826·002258·006297의 38개 판본 주장은 첫 사유로 보류한다. 토지수용법 시기 009295의 연혁 10개는 기존 목록에서 확인된다. 새 전신법 계보를 만들지 않는다. `historical_case_annotations`는 8건 판례의 조문명·출처·주장 판본·적용 기준일·기준일 근거를 보존한다. 연구 목록과 유일하게 연결되는 판본만 `asserted_version_id`에 적으며 확인 상태를 올리지 않는다. `article_id`는 null이고 `publication_hold`는 true다. 미확인 재결일·판본 충돌은 `historical_gaps`에 남긴다. 법령 본문은 가져오지 않는다.

`records`에는 서로 다른 두 종류만 둔다.

| kind | ID | 계약 |
|---|---|---|
| faq | `faq/molit/lawgo/<숫자 source_id>` | 행정 FAQ, 정식 해석 아님 |
| identity-hold | `identity-hold/molit/<공문번호>` | 출처 간 행정상 동일성 미확정 |

FAQ의 `material_type`은 administrative-faq, `case_no`는 빈 문자열, progress는 candidate, reference_status는 unreviewed, publication_hold는 true다. source_id와 source_identifiers.lawgo는 같고 source_identifiers.epUnionSn은 국민신문고 레코드 ID다. 어느 것도 안건번호로 사용하지 않는다. source_url은 해당 law.go.kr 상세, upstream_url은 기록된 국민신문고 링크다. asserted_replied와 title은 저장 조사상의 출처 주장이다. source_envelope_status는 unavailable로서 완전한 수집 원본 봉투가 없음을 표시한다. reply_sha256은 저장 조사 full_reply 문자열의 UTF-8 바이트 해시이며 정규 source_sha256이나 원시 네트워크 응답 해시가 아니다. 원문을 복제하거나 정식 해석 문서로 수록하지 않는다.

동일성 보류의 identity_status는 unresolved다. assertions는 source_id·asserted_replied·source_url·upstream_url·citation·title·reply_sha256을 각각 보존한다. existing_document_id는 기존 해석 문서 연결이며 동등성·별개 발행·대체 관계를 뜻하지 않는다. 같은 본문이나 다른 연도만으로 합치거나 새 해석 ID를 부여하지 않는다. 기존 검토 상태는 보존하되 보류 문서의 published 진행은 거부한다. 원 회신문 또는 기관 정정이 확보되기 전 동일성은 확정하지 않는다.

모든 records는 evidence_file·evidence_sha256·evidence_item·evidence_basis와 전 필드 provenance를 가진다. evidence_basis는 stored-pilot-research이며 새 원문 확인을 주장하지 않는다. evidence_file은 records에서 `runs/pilot/held-items-research.json`, 과거 판본·사건 주석에서 `runs/pilot/predecessor-versions-research.json`이다. evidence_sha256은 전체 파일 바이트 해시다. limitations는 원 회신문 미확보·국토교통부 FAQ 목록 접근 실패·공식 안건번호 미확인 등 저장된 한계를 보존한다. 별도 ID들은 관계 끝점이나 정식 문서 참조 계약으로 승격하지 않는다. reader는 이 경로를 별도 허용 목록에 추가한 경우에 카탈로그 종류·knowledge revision·파일 해시·보류 사유를 함께 전달한다.

카탈로그·두 입력 중 하나 또는 기존 동일성 보류 해석 문서가 있으면 세 파일을 모두 요구한다. 입력과 카탈로그를 함께 삭제해도 해당 문서의 published 금지는 유지된다. 영향을 받는 자료가 없는 일반 빈 저장소에는 이 요구를 적용하지 않는다. 동일성 assertion의 law.go.kr URL은 source_id와 같은 cgmExpcDatSeq의 정확한 상세 URL이어야 하고, LAIIS URL은 보존된 law.go.kr–nttNo 출처 쌍과 일치해야 한다. 호스트·경로·ID·추가 query·fragment가 다르면 거부한다.

FAQ의 빈 case_no는 기계 생성이므로 machine이고 limitations는 저장 조사자의 판단을 복사하므로 analysis다. assertions 컨테이너는 기계가 구성한 목록이므로 machine이며 각 assertion 안에 전 필드 provenance를 별도로 둔다. 개별 날짜·인용·출처는 source, 계산한 reply_sha256은 machine이다. 네 가지 기존 provenance category만 사용한다. 역사 주석 생성 전에 연구 객체의 키·case_id·case_file과 실제 로컬 판례 frontmatter의 ID·법원·사건번호·판결일·출처를 대조한다. case_file은 cases 아래 법원·4자리 연도·파일명 구조의 정규 상대 경로여야 하며 공용 안전 읽기로 링크·reparse·누락 파일을 거부한다. 다른 판례로의 바꿔치기나 문서 없는 주석 생성은 허용하지 않는다.

## 두 상태 축

`progress`: candidate → source-verified → relations-reviewed → published. 수집·검증 진행이며 자동 지정 가능하다. 참조 가능성 판정이 아니다.

`reference_status`:

| 상태 | 의미 |
|---|---|
| unreviewed | 미검토 |
| current-usable | 적용 범위와 현행 관계를 검토해 참조 가능 |
| recheck-amendment | 개정 영향 재검토 필요 |
| recheck-relation | 후속 관계 재검토 필요 |
| overruled-confirmed | 판례 변경 확인, 판례 전용 |
| superseded-confirmed | 해석 대체 확인, 해석 전용 |
| historical-only | 명시적 검토에 따라 과거 적용 범위에서만 사용 |
| indeterminate | 근거로도 판단 미확정 |

unreviewed 외 상태는 대상 ID·동일 상태·모델·시각·판단·인용 증거가 있는 reviews 기록과 일치해야 한다. last_reviewed는 그 시각이다. overruled-confirmed에는 변경 판결의 `overruling_id`와 `change_quote`가 필수다. superseded-confirmed에는 `superseding_id`와 대체 근거가 필수다. 후일 결정만으로 두 확정 상태를 부여하지 않는다. 오래된 날짜만으로 historical-only를 부여하지 않는다.

## credential 검사 범위

값 기반 `tools/secret_scan.py`는 환경변수 LAW_OC에서만 실제 키를 읽고 수집 API와 동일하게 앞뒤 공백·탭 등을 strip한다. 정규 값에서 만든 동일한 검색 바이트를 검사와 진단 가림에 공유하며 그 값의 대소문자 구분 UTF-8 원문·URL quote(safe 빈 문자열)와 quote_plus·UTF-16-LE/BE·UTF-8 바이트의 hex(소문자/대문자/혼합 표기)·표준/URL-safe base64를 검사한다. base64는 전체 키의 독립 인코딩을 padding 유무와 무관하게 검사하고, 큰 blob 내부의 세 바이트 정렬 조각은 8자 이상일 때만 포함한다. CR·LF·공백·탭을 제거한 사본에서도 검사하여 MIME 줄바꿈을 허용한다. URL percent escape의 hex 숫자만 대소문자 정규화하며 키 자체의 대소문자는 유지한다. 값·파생 검색 바이트·일치 내용은 출력·로그·저장하지 않고 경로와 인코딩만 보고한다.

Git 추적 파일의 현재 작업 바이트 전체(바이너리 포함)와 상대 경로명의 바이트를 검사한다. 빈 파일도 경로명에 키가 있으면 경로 전체를 가려 노출로 보고한다. worktree 모드에서는 미추적·비무시 파일도 더하며 무시된 미추적 로컬 파일은 읽지 않는다. 추적 파일에는 ignore 패턴을 적용하지 않는다. credential scanner는 심볼릭 링크의 링크 문자열만 검사하고 하위 모듈은 별도 검사한다. 일반 검증과 쓰기 전 링크 검사는 Git index의 추적 symlink(mode 120000)와 gitlink(mode 160000)를 모두 거부한다. manifest 생성·이관·법원 복원·오프라인 재생성·JSON 및 관계 저장을 포함한 모든 도구 파일 쓰기는 공용 경로 검사와 안전 쓰기 함수를 거치며 저장소 밖 출력 및 symlink·junction·reparse point를 경유한 출력을 열기 전에 거부한다. 준비·교체·롤백도 같은 경로 정책을 유지하고 갱신 절차의 첫 쓰기 전에 가벼운 추적 링크 검사 직후 worktree 필수 credential 검사를 수행하고 실패하면 중단한다. 저장소 JSON을 읽는 CLI는 공용 실행 래퍼에서 출력·오류 전체와 처리되지 않은 예외를 같은 redactor로 가리며 원문을 포함한 traceback을 내보내지 않는다. index·과거 이력 검사가 아니므로 커밋할 내용과 같은 clean checkout에서의 성공을 기준으로 삼는다. 유효한 실제 LAW_OC가 제공된 성공 검사는 문서화한 인코딩의 해당 키가 검사 파일에 없음을 보장한다. 다른 키, 문자열 조립·escape·난독화·암호화·그 밖의 인코딩은 범위 밖이다. 공개 여부와 무관하게 가시성에 의존하지 않고 모든 변경의 PR 검토를 전제로 한다.

미설정·빈 LAW_OC는 기본 종료 0의 안내이며 필수 모드에서는 종료 2다. 4자 미만·마스크 등 잘못된 값과 검사 실행 오류도 값을 노출하지 않고 종료 2다. 일치는 종료 1, 일치 없음은 종료 0이다. 일반 검증기는 LAW_OC가 설정되면 의존성 등 다른 계약을 읽기 전에 worktree 모드로 추적·미추적 비무시 파일을 검사하고 같은 집합만 순회한다. 별도로 여는 의존성 색인·지정 snapshot·참조 파일도 파싱 전에 바이트를 검사하며, 무시 파일과 로컬 링크 대상은 읽지 않는다. 일치나 검사 오류가 있으면 안전한 오류만 반환하여 중단하고, 진단에 문서화한 키 인코딩이 있으면 정규화 변형까지 포함해 진단 전체를 가린다. 추적 텍스트의 명백한 OC/LAW_OC quoted literal 대입(8자 이상)은 최대 한 번의 비실패 경고일 뿐 보안 보장이 아니다. 로컬 개발자는 셸 LAW_OC를 설정하며 CI는 GitHub Actions secret LAW_OC를 전용 credential-scan 단계의 환경변수로만 전달한다. main 푸시·수동 실행·main 대상 same-repo PR(작성자와 실행 actor 모두 Dependabot이 아닌 경우)에서는 필수 검사하고 fork PR·비-main 대상 PR·Dependabot 작성 또는 실행 PR은 secret-free offline-checks만 실행한다. secret-free scanner의 건너뜀과 literal 경고를 실제 키 검사 성공으로 해석하지 않는다. 명령은 갱신 스킬에만 둔다.

도구 실행은 `-I -B`로 import 전부터 바이트코드 쓰기를 막는다. 비격리 실행에서는 `PYTHONDONTWRITEBYTECODE=1`과 동등하지만 `-I`는 Python 환경변수를 무시하므로 이 절차에서 `-B`를 대신하지 못한다.

## 문서 필드

공통 필수: `id`, `title`, `progress`, `reference_status`, `last_reviewed`, `found_via`, `provenance`.

판례 필수: `court`, `case_no`, `decided`, `kind`, `precSeq`, `source_url`, `source_sha256`, `ref_articles_raw`, `applied_version`.

해석 필수: `agency`, `case_no`(안건번호), `replied`, `requester`, `source_url`, `source_sha256`, `applied_version`, `facts_summary`. 해석은 숫자 문자열 `expcSeq` 또는 `cgmExpcDatSeq` 중 정확히 하나만 둔다(둘 다 있거나 둘 다 없으면 오류). 수집 도구는 법제처에 `expcSeq`, 중앙부처에 `cgmExpcDatSeq`를 둔다. 원본은 각각 sources/expc, sources/cgmexpc에 저장한다. 기관 코드는 법제처 moleg, 국토교통부 molit, 국세청 nts이며 미등록 기관은 보류한다. 중앙부처 웹 상세는 cgmExpcInfoR.do의 cgmExpcDatSeq로 확인하며 법제처 해석으로 분류하지 않는다.

- `applied_version`: 완전한 계약 판본 ID(`law/<6자리 lsId>@<lsiSeq>`) 문자열 또는 `unknown`. 현행 판본은 잠금 색인, 과거 판본은 같은 잠금 commit의 versions_file(`sources/laws/<collection>/versions/<level>.json`)로 확인한다. 참조조문 원문은 현행 판본 적용의 증거가 아니다.
- `source_sha256`: sources의 payload를 비밀 제거 후 키 정렬·2칸 들여쓰기·ensure_ascii=false·UTF-8·끝 LF로 직렬화한 바이트의 SHA256. 네트워크 원시 바이트 해시가 아니다. 저장 payload는 이미 비밀이 제거되어 있어야 하며 속성명·값 모두 API가 실제로 선택한 정규 키(파일 fallback 포함)로 가린다. 가림 후 속성명이 충돌하면 원문을 조용히 버리지 않고 거부한다. 해시 검증과 오프라인 재생성은 raw 객체가 mask 결과와 다르면 거부한다. 저장소 전체의 실제 키 노출 검사는 위의 값 기반 credential 검사 범위를 따른다.
- `ref_articles_raw`: 참조조문을 원문 그대로 보존한다. 대응 실패 이유는 GENERATED에 남긴다.
- `found_via`: 비어 있지 않은 객체 배열. 각 객체에 비어 있지 않은 문자열 `path`, 유효한 ISO 달력 날짜(`YYYY-MM-DD`) 문자열 `date`, 그리고 비어 있지 않은 문자열 `query` 또는 `article`이 필요하다. 둘 다 있으면 둘 다 문자열이어야 한다.
- `provenance`: 필드명 → source/summary/analysis/machine. `provenance` 자신을 제외한 모든 frontmatter 필드(선택 필드 포함)를 빠짐없이 덮는다. 원문 인용은 source, 요약은 summary, 판단은 analysis, 기계 식별·연결은 machine이다.
- `decided`·`replied`: 실제 달력에 존재하는 `YYYYMMDD` 또는 `YYYY.MM.DD` 문자열이다. 문서 경로는 각각 `cases/<파일명 정규화 법원>/<YYYY>/<파일>.md`, `interpretations/<agency>/<YYYY>/<파일>.md`이며 연도는 해당 원문 날짜와 같아야 한다. 잘못된 날짜는 수집 시 디렉터리를 만들기 전에 보류한다.
- 해석도 응답의 참조조문(중앙부처의 관련법령 포함)을 `ref_articles_raw`에 보존하고 조문 연결 후보와 미대응 진단을 생성한다.
- 재수집은 같은 target/source_id의 sources/candidates JSONL 발견 경로를 기존 `found_via`에 중복 없이 합친다. 미검토 문서의 source 출처 필드만 새 응답으로 갱신하고 수동 요약·분석·판본·검토 필드는 보존한다. 검토된 문서의 해시 변경은 보류한다. 미검토 문서의 해시가 바뀌면 재생성 관계는 미검토이므로 relations-reviewed/published 진행 상태를 source-verified로 내린다. 해시가 같아도 잠금 색인의 변경 등으로 재생성 자동 관계 ID 집합이 바뀌면 같은 방식으로 내린다. 문서 reference_status와 무관하게 교체 가능한 자동 관계 집합(미검토 cites-article 단독 cites)의 추가·제거를 비교하고 교체한다. 검토된 자동 관계의 재생성 근거가 사라지면 관계는 보존하되 문서 `relation_recheck`에 해당 관계 ID 배열을 기록하고 progress를 source-verified로 내린다. 이 필드가 남아 있는 문서는 relations-reviewed/published로 올리지 않는다. 검증 시에도 저장 payload와 잠금 색인으로 자동 집합을 재생성해 실제 관계와 비교한다. 교체 가능한 자동 관계는 ID뿐 아니라 생성기의 모든 정규 필드(evidence와 null reviewed_by·reviewed_at 포함)가 재생성 결과와 같아야 한다. 수동·혼합·검토 관계에는 이 자동 필드 대조를 적용하지 않는다. 원문 해시가 바뀌면 수동·혼합 발견 경로를 포함한 모든 outgoing confirmed 관계를 needs-review로 내리고 relation_recheck에 기록한다. 기존 accept 검토는 과거 이력으로 보존하며 새 원문의 승인으로 재사용하지 않는다. relation_recheck는 사라진 근거를 가진 검토 자동 관계 ID, accept confirmed 이력이 있으나 needs-review로 내려간 관계 ID, 원래 출발 문서에 결속된 삭제 승인 관계 ID의 합집합과 정확히 같아야 하며 집합 변경·재검토가 있으면 progress는 source-verified여야 한다. 외부에서 삭제·추가한 자동 관계도 오류다. 수동·혼합 발견 관계는 보존한다. 해시와 자동 관계 집합이 모두 같고 관계 재검토 표시도 없을 때만 진행 상태를 유지한다.
- 쟁점은 필수 `articles`, `standards`, `skills` 배열을 둔다. 각 항목은 각각 조문 ID, 실무기준 ID, 업무 스킬 ID여야 하며 잠금 색인으로 검증한다. `coverage.md`는 P1–P7별 질의·기간·페이지·결과·실패·제외·잠정 포화를 기록한다.

판례·해석 본문은 GENERATED:source의 메타데이터·연결·수집 전문과 수동 절로 나눈다. 쟁점은 canonical 생성기가 없으므로 모든 절이 수동이며 GENERATED:source 표지를 금지한다. 기존 쟁점의 표지만 제거하는 오프라인 이관은 내용·frontmatter·관계를 보존한다. 수동 절은 판시사항/질의요지 요약, 쟁점과의 관계, 적용 판본과 현행 조문 대조, 후속 관계, 검토 기록이다. 생성기는 기존 수동 절과 검토 상태를 보존한다. 원문 전문은 허용한다. 법령 전문은 복제하지 않는다.

## 관계

`relations/relations.jsonl` 한 줄 한 객체. 필수 필드:

- `id`: `rel-` + type/src/dst/scope JSON 배열(공백 없는 UTF-8)의 SHA256 앞 20자리
- `type`, `src`, `dst`, `scope`(필수 문자열이며 범위가 없으면 명시적으로 빈 문자열)
- `found_by`: linked-by-center / cites-article / cites-case / manual 배열
- `review`: unreviewed / confirmed / rejected / needs-review
- `evidence`: 인용 문구·출처(문자열 또는 객체), `reviewed_by`(모델), `reviewed_at`(ISO 8601)

accept 관계 검토 기록은 실제 존재하는 관계 ID를 가리켜야 한다. 관계를 제거하려면 accept 검토에 원래 type/src/dst/scope 문자열을 가진 relation_snapshot 객체를 보존해야 하며 이 객체로 계산한 결정적 ID가 검토 target과 같아야 한다. 관계를 제거했으면 snapshot의 src와 같은 문서 relation_recheck에 그 ID를 남겨야 하며 해당 문서는 source-verified여야 한다. 출발점이 로컬 문서가 없는 법령·조문·실무기준·스킬 계약 ID인 경우에는 대신 같은 target과 원래 relation_snapshot을 가진 decision=needs-review, relation_review=needs-review 검토 기록을 남긴다. 이 삭제 재검토 기록도 모델·시각·증거를 갖추고 해당 관계의 모든 accept 기록보다 나중 시각이어야 한다. 과거 accept와 snapshot은 보존한다. 다른 문서의 표시로 대체할 수 없고, 동일 원문을 재수집해도 누락된 승인 관계의 표시를 지우지 않는다. 검토된 관계와 재검토 표시를 함께 지우면 오류이며, 재검토 ID가 남아 있는 문서는 게시할 수 없다.

관계 type: cites, interprets, applies, special-rule-of, cites-case, overrules, distinguishes, conflict-candidate, recheck-due-to, same-provision.

끝점 계약은 검토 상태와 무관하게 적용한다. 조문은 완전한 판본·조문 ID이며 법령/판본 ID와 구별한다. 모든 confirmed 자기참조 관계는 금지한다.

| type | src → dst |
|---|---|
| cites | 모든 계약 ID → 모든 계약 ID (일반 인용, 자동 조문 후보 포함) |
| interprets | 해석 → 조문 |
| applies | 판례 → 조문 |
| special-rule-of | 조문 또는 실무기준 → 조문 또는 실무기준 |
| cites-case, overrules, distinguishes | 판례 → 판례 |
| conflict-candidate | 판례·해석·조문·실무기준 → 판례·해석·조문·실무기준 |
| recheck-due-to | 판례·해석·쟁점 → 판례·해석·조문·실무기준·법령/판본 |
| same-provision | 조문 → 조문 |

저장 source_url은 HTTPS이며 authority는 law.go.kr 또는 www.law.go.kr만 허용한다 (인증정보·포트·fragment 금지). 경로는 정확히 /DRF/lawService.do, /DRF/lawSearch.do 또는 자료 종류별 /LSW/precInfoP.do (판례), /LSW/expcInfoP.do (법제처), /LSW/cgmExpcInfoP.do 및 /LSW/cgmExpcInfoR.do (중앙부처)다. 다른 탭·접미 경로는 허용하지 않는다. DRF 두 경로의 query에는 해당 자료 종류의 `target`(prec, expc, 중앙부처는 cgmexpc 또는 molitCgmExpc)과 저장 source_id와 같은 `ID`가 각각 정확히 하나 있어야 한다. LSW는 종류별 `precSeq`·`expcSeq`·`cgmExpcDatSeq`가 정확히 하나 있으며 저장 source_id와 같아야 한다. 누락·중복·다른 ID는 오류다. DRF query는 target·ID·type·OC만, LSW query는 해당 일련번호·mode·ofiClsCd·efYd·OC만 허용한다. OC가 있으면 값은 정확히 마스크 문자열 `***`여야 한다.

overrules와 distinguishes는 confirmed와 증거가 있을 때만 확인 관계로 센다. 자동 수집은 unreviewed다. 확인된 관계에는 검토자와 시각, 해당 관계 ID를 target으로 하는 reviews/YYYY/*.jsonl 기록이 필요하다. 기록의 relation_review는 confirmed, reviewer_model과 reviewed_at은 관계 인라인 값과 일치해야 하며 evidence와 decision이 있어야 한다. 관계 인라인 evidence는 승인 기록의 evidence와 같은 객체여야 한다(source URL과 quote 정확히 일치, 다른 증거로 승인 전용 불가). 출발점이 case/interp인 confirmed 관계의 승인 기록은 검토 당시 원문 source_sha256도 가지며 현재 출발 문서의 해시와 같아야 한다. 원문 변경 후 과거 기록은 이력으로만 남기고 관계를 needs-review와 relation_recheck로 보류하거나 현재 해시로 다시 검토한다. issue와 외부 계약 ID 출발 관계에는 원문 digest를 요구하지 않는다. src/dst는 계약 ID이며 자료 ID는 실제 문서가 있어야 한다. 자동 참조조문 파싱은 법령명·조문 대응 후보일 뿐 적용 법령 판본 확정이 아니다.

## 검토·실행·중복

검토: `reviews/YYYY/*.jsonl`, 필수 `id`, `target`, `reviewer_model`, `reviewed_at`, `evidence`, `decision`; 문서 상태 검토는 `reference_status`와 원문이 있는 case/interp 대상의 `source_sha256`(소문자 16진수 64자리), 관계 검토는 `relation_review`를 추가한다. 승인에 사용되지 않는 기록도 포함하여 모든 target은 위 계약 ID 또는 `rel-`와 소문자 16진수 20자리여야 한다. 존재하는 reference_status와 relation_review는 각각 문서 상태 enum 및 unreviewed / confirmed / rejected / needs-review enum의 문자열이어야 한다. 검토 증거는 `{"source":"https://원문 URL","quote":"정확한 인용"}` 객체이며 두 값은 비어 있지 않은 문자열이다. decision은 accept / reject / needs-review 중 하나다. 상태·관계 확정에는 accept 기록만 사용한다. reviewed_at은 시간대가 있는 ISO 8601 날짜·시각 문자열이고 모델·대상·기록 ID는 비어 있지 않은 문자열이다. change_quote도 비어 있지 않은 문자열이어야 한다. confirmed 관계의 인라인 evidence도 같은 증거 객체 형식을 사용한다. overruling_id는 실제 존재하는 case 문서, superseding_id는 실제 존재하는 interp 문서여야 한다. 두 대체 ID는 검토 대상 자신과 달라야 한다. 검토 JSONL은 reviewed_at의 연도와 같은 reviews 바로 아래 4자리 연도 디렉터리의 파일만 허용하며 다른 위치의 기록은 승인 근거로 사용하지 않는다. 증거 URL은 HTTPS 절대 URL로 호스트가 있어야 하며 사용자명·암호는 허용하지 않는다.

실행: `runs/<source>/<YYYY-MM-DD>-<n>.json`. 기계 수집 기록은 started·finished(시간대 포함 ISO 시각), 비어 있지 않은 tracks 객체가 필수다. 각 track의 status는 success / zero / failure, count는 boolean이 아닌 0 이상의 정수이며 zero의 count는 0, success의 count는 1 이상이다. 파일명은 started의 달력 날짜와 1 이상의 실행 순번이며 디렉터리는 상세 수집의 source 또는 조문 수집의 article과 일치해야 한다. 실패에는 error 문자열을 둔다. 상세 수집은 source와 query 문자열이 필수이며 source는 prec / expc / cgmexpc / molitCgmExpc다. 상세 tracks의 키는 source와 같은 하나뿐이며 다른 자료 종류나 추가 트랙을 허용하지 않는다. 수집 시작 시각은 한 번만 읽고 실행 날짜·파일명·후보 발견 날짜를 그 started 값에서 가져온다. 조문 수집은 id·article·candidate_count·candidates가 필수다. candidate_count와 relations가 있으면 0 이상의 정수다.

`runs/pilot/`은 기존 조사 보조 기록이며 기계 수집 성공 증빙과 구별한다. 시간형 기록은 started·finished를 요구하고 시간대를 반영한 종료 시각이 시작 시각 이상이어야 한다. 시간 없는 연구·검증 snapshot은 date 또는 integrated_on, 법령 판본 조사 객체(laws·cases·method·unresolved), 또는 숫자 ID별 decision·reason 객체 형식을 사용한다. 최상위 status와 track status가 있으면 success / zero / failure만 허용한다. tracks는 count를 갖춘 이름별 객체 또는 query·status를 갖춘 실행 목록이다. 목록의 count는 선택 사항이나 있으면 정수다. counts 객체의 값도 0 이상의 정수다. 역사 조사 실패 count는 시도한 판본 수이며 세부 versions에 실패 이유를 둘 수 있다. 보조 기록의 payload·pages·분석 상태는 API 원본/조사 메모로 보존하며 자동 승인으로 사용하지 않는다.

후보는 sources/candidates/article-YYYY-MM-DD-n.jsonl에 저장하며 runs/article/YYYY-MM-DD-n.json의 id·candidates 경로·started 날짜·article·candidate_count와 일치해야 한다. 검증은 실행 기록에서도 정규 후보 경로의 실제 파일 존재와 행 수를 확인하며 0건 실행도 빈 후보 파일을 보존한다. 후보 파일과 조문 실행 기록은 상세 수집과 같은 공용 준비·교체·롤백 단위로 저장한다. success·zero·failure 모두 기록 준비나 교체에 실패하면 두 파일의 기존 바이트 또는 부재를 복원한다. 각 행의 target은 prec/expc/cgmexpc, source_id는 숫자 문자열이며 같은 파일의 target/source_id는 유일하다. article은 실행과 같은 조문 ID, found_by는 linked-by-center 단독 배열, source_tabs는 target 단독 배열이며 source_tab이 있으면 target과 같아야 한다. found_via는 해당 article·파일 날짜·article-linked 경로 하나이며 target의 success 트랙과 그 후보 이상인 count가 필요하다. 선택 데이터출처명은 비어 있지 않은 문자열이다. 수집기와 검증기는 이 계약을 통과한 후보만 발견 경로·출처명으로 사용하며 대응 실행 없는 후보를 신뢰하지 않는다.

실행 기록은 트랙별 success/zero/failure를 구별하고 후보 건수·원인·파일·시작/종료를 남긴다. 시각이 있는 기록은 시간대를 반영하여 종료가 시작 이상이어야 한다. 조문·상세 수집의 실패 진단은 저장·출력 전에 API가 실제로 선택한 정규 키(환경변수 또는 파일 fallback)와 문서화한 인코딩으로 검사하여 가린다. 파일 읽기는 API만 명시적으로 수행하며 가림 함수는 선택된 값을 재사용하고 scanner는 환경변수 전용으로 유지한다. failure는 무변동이 아니다. 조문 수집의 잠금 저장소·색인 실패도 dependency failure 트랙으로 기록한다. 기존 문서 스캔 오류도 preflight failure 트랙으로 기록한다. 다른 탭의 상세 링크가 반환되면 정상 결과가 아닌 실패다. 빈 응답은 요청 탭의 고유 form ID와 정상 0건 표식을 함께 확인해야 zero다. 조문 문맥의 응답 lsiSeq·joNo·joBrNo도 요청 값과 일치해야 한다.

판례 중복: precSeq + 공백 정규화 사건번호(어느 하나가 기존 자료와 충돌하면 보류). 해석 중복: agency + 안건번호. 관계는 결정적 ID로 중복 방지한다. 같은 목적지라도 원문 ID가 다르면 충돌로 보류한다. DRF 상세는 서비스 root와 응답 일련번호가 요청 종류·ID와 일치해야 한다. 법원명 전체는 `대법원` / `헌법재판소` 또는 한글 지역명 뒤 `지방법원` / `고등법원` / `가정법원` / `행정법원` / `특허법원` / `회생법원` / `지법` / `고법`이며 선택적으로 공백 한 칸과 한글 지원명이 붙는 고정 패턴과 일치해야 한다. 부분 문자열 일치는 허용하지 않으며 fetch와 validate가 같은 정책을 적용한다. 법원도서관·민간법원자료업체·헌법재판소사칭업체는 법원명이 아니다. 파일럿 수원지법(143909), 서울고법(192870·192382)은 공식 법원명의 약칭이고 law.go.kr prec 원문이므로 삭제 대상이 아니다. 출처명이 없으면 추정하지 않는 원칙은 유지하며 명시된 출처명의 허용 목록은 넓히지 않는다. 판례의 데이터출처명은 응답과 후보에서 수집해 data_source_name 배열에 보존하고, 제공된 값 중 법원도서관·대법원·헌법재판소 외 출처가 있으면 보류한다. 응답·후보 모두 출처명이 없는 조문 연결 자료는 법원명 검사와 출처 URL을 유지하며 출처명을 추정하지 않는다. 재수집해도 수동 영역을 덮지 않는다. 재수집 시 해당 문서의 cites 중 unreviewed이며 found_by가 cites-article만인 자동 관계는 새 집합으로 교체한다. 검토 관계·수동 관계·혼합 발견 경로는 보존한다. 저장 원본의 source_url·target·source_id는 문서와 일치해야 한다. 해시·렌더링 전에 payload root는 종류별 PrecService / ExpcService / CgmExpcService 하나뿐인 객체이고, 내부 판례정보일련번호 / 법령해석례일련번호 / 법령해석일련번호가 source_id 및 문서 precSeq / expcSeq / cgmExpcDatSeq와 일치하는지 검사한다. 문서가 참조하지 않는 파일도 포함해 sources/prec·expc·cgmexpc 아래 모든 파일에 같은 원본 봉투 계약을 적용한다. 파일은 바로 아래 숫자 ID의 JSON이고 target·source_id·URL·시간대 포함 fetched·canonical payload SHA256·서비스 root·내부 일련번호가 모두 유효해야 한다. 재수집 중복 사전 검사는 루트 cases/README.md와 interpretations/README.md만 제외하며 중첩 README.md도 문서로 검사한다. 재수집은 기존 frontmatter·GENERATED 경계와 순서의 검증 및 렌더링을 끝낸 뒤에만 원본을 교체한다. 상세 수집 명령의 success 실행 기록은 원본·문서·관계와 함께 임시 준비하고 같은 교체·롤백 범위에 포함한다. 실행 기록 준비·교체가 실패하면 자료 변경을 남기지 않는다. 커밋 후 CLI 출력은 수집 예외 처리와 분리한다. stdout 오류로 이미 저장한 success 실행을 failure로 덮어쓰지 않으며 조문 후보·실행 기록도 출력 실패와 무관하게 보존한다.

## 분리와 문체

읽기 스킬은 파일을 수정하지 않는다. 도구 실행 명령은 갱신 스킬에만 둔다. tools 아래 Markdown도 예외가 아니며 비 Markdown 구현 파일만 검사 범위 밖이다. fence info 문자열과 무관하게 fenced/indented code, inline code, 일반 행의 명령 모양을 검사한다. 목록·prompt·인용 표지를 벗긴 뒤 launcher/실행 경로(절대·상대 경로 포함), 환경 변수 접두사와 중첩 셸 wrapper, 옵션·경로·URL·파일명·하위 명령 등 인수 구문으로 판단하며 자연어 문구 허용 목록은 쓰지 않는다. 입구·AGENTS·CLAUDE는 읽기 규칙을 가리킨다.

Markdown 산문 본문에서 물결 기호는 쓰지 않고 범위는 `–`로 적는다. frontmatter와 code는 산문 검사의 대상이 아니다. 생성 원문 절과 미대응 원문 진단의 `&`, `<`, `>`, `[`, `]`, 물결과 백틱은 공통 renderer에서 HTML entity로 보존한다. 원문 절의 필드는 정렬된 키 순서로 렌더링한다. GENERATED 블록 전체(원문 URL·원본 파일 경로·SHA·참조 조문 목록·미대응 진단·전문)를 저장 payload와 잠금 색인에서 새로 만든 공통 renderer 결과와 정확히 대조한다. 원문 인용 번호를 Markdown 링크로 해석하거나 원문 HTML을 활성화하지 않는다. 렌더링한 원문은 각 줄 끝의 공백·탭 등 공백 문자를 제거한다. 이는 의도하지 않은 Markdown 강제 줄바꿈을 막는 표시 전용 변경이며, 그대로의 원문은 sources/에 보존한다. 저장 JSON 원문과 해시는 바꾸지 않는다. 오프라인 재생성은 원문 종류·ID·URL·해시를 대조하고 같은 renderer로 GENERATED 블록 전체를 교체하며 frontmatter·수동 절·원본·관계를 보존한다. GENERATED:source BEGIN/END는 본문에 각각 한 번이며 BEGIN이 END보다 앞서야 한다.

링크는 산문에 있는 inline/image 및 reference-style 목적지와 정의를 검사한다. inline/fenced/indented code 안 예시는 링크가 아니다. 명시적 참조 링크의 label은 정의되어야 하고 목적지는 존재해야 한다. `/`로 시작하는 로컬 링크는 저장소 루트 기준이며 상대 링크는 문서 부모 기준이다. URL decoding 후 `..` 또는 symlink로 저장소 밖에 나가는 경로는 금지한다.


읽기 경로의 코드는 SAFE-CONTENT 계약을 따른다. fence는 명시적 json / jsonl / yaml / yml / csv / tsv 데이터 형식과 명령 모양 행이 없는 text만 허용한다. 무표시·실행 언어·미등록 언어 fence와 들여쓴 코드 블록은 오류다. inline code는 ID·경로를 허용하되 알려진 실행기 이름과 무관하게 단어 뒤 인수·옵션·URL·연산자 또는 ASCII 다중 단어 명령 모양을 거부한다. 산문은 기존 인수 증거 규칙에 더해, 목록·인용·prompt를 제거한 행이 소문자 ASCII 실행명 모양으로 시작하고 전체가 두 개 이상의 ASCII token이며 문장 종결 마침표·물음표가 없으면 실행기 이름과 무관하게 거부한다. 데이터 fence는 내부 문자열에 명령 검사를 하지 않고 문법만 검사한다: JSON/JSONL 파싱, YAML의 안전한 key-value/list/comment 부분집합(따옴표 닫힘 필수, flow 배열·객체는 JSON 문법, plain scalar는 불균형 괄호·따옴표 및 tag/anchor/block scalar 제외), CSV/TSV의 2열 이상 동일 열 수. text fence만 명령 모양을 검사한다. 저장 payload와 정확히 대조하는 GENERATED 원문 블록은 이 읽기 코드 제한에서 제외하며 사람의 절은 포함한다.

payload에서 추출한 frontmatter 필드는 provenance 표지와 무관하게 수집기와 공유하는 추출 함수의 결과와 같아야 하며, 아래 category도 정확히 일치해야 한다(제목·날짜·사건번호·법원/기관·종류·참조조문 등). machine/analysis 재표지로 검사를 면제하지 않는다. 기존에 없던 참조조문·출처명 필드는 원본에서 채우는 오프라인 이관을 제공하며 기존 값은 덮어쓰지 않는다. 블록과 digest만 같더라도 source 필드 위조는 오류다. 수집 허용 정책과 순수 원문 추출은 분리한다.

### 필드별 provenance 허용 표

| 필드 | 허용 category |
|---|---|
| court, case_no, decided, kind, precSeq, agency, replied, requester, expcSeq, cgmExpcDatSeq | source |
| title, ref_articles_raw, data_source_name (case/interp 원문 필드) | source |
| id, source_url, source_sha256 (case/interp) | machine |
| change_quote 및 issue title | source / machine |
| facts_summary, summary, holding_summary, question_summary, issue_summary, analysis 및 `_summary` 접미사 필드 | summary / analysis |
| 그 밖의 상태·연결·선택 필드 | source / summary / analysis / machine (전 필드 표시 의무 유지) |

### 검토와 원본 결속 및 파일럿 1회 이관

case/interp의 unreviewed 이외 상태는 accept 검토 기록의 `source_sha256`이 현재 문서의 `source_sha256`과 같아야 승인된다. 모델·시각·상태·대상·증거 일치 요건도 그대로 적용한다. 변경된 원문에는 새 검토가 필요하다. case/interp에서 출발하는 confirmed 관계의 승인 검토에도 동일한 source_sha256 일치 요건을 적용한다. 원문 payload가 없는 issue와 외부 계약 ID에서 출발하는 관계 검토는 이 digest 요건의 대상이 아니다. 기존 digest가 있는 검토는 이관 도구가 덮어쓰지 않는다.

파일럿 0f90463에는 검토 86개 중 원문 문서 상태 검토 38개와 원문 출발 confirmed 관계 검토 48개에 digest 추가가 필요하다. `tools/migrate_review_digest.py`는 일회성 baseline의 원본을 코드에 고정한 전체 commit `0f90463b34127b71af14c7046f7b27660ed9adf7`로 제한한다. 명시한 로컬 저장소가 해당 commit 객체를 실제로 보유하고 입력 revision이 그 전체 SHA로 해석되어야 하며 다른 commit은 manifest를 읽기 전에 거부한다. 같은 객체를 가진 로컬 mirror는 허용하며 remote URL에 의존하지 않는다. 고정 commit 해석과 manifest용 Git 읽기는 replace refs를 무시해 다른 객체로 바꿔 읽지 않는다. 도구는 이 고정 commit·문서 또는 관계 모드로 manifest를 재계산해 일치 여부를 확인하고, 저장 payload·문서·원본의 현재 해시를 검증한 뒤 명시적 manifest에 있는 누락 digest만 채우는 네트워크 없는 도구다. manifest는 `id`와 `review_sha256`을 가진 객체 배열이다. review_sha256은 고정 commit 검토 행 전체를 키 정렬·2칸 들여쓰기·ensure_ascii=false·UTF-8·끝 LF로 정규 직렬화한 SHA256이며 현재 행의 대상·판단·근거·모델·시각 등 모든 필드와 대조한다. 재실행 때만 도구가 추가한 migrated-baseline basis와 source_sha256 두 필드를 해시 대조에서 제외한다. ID만 나열한 구형 manifest나 고정 commit에서 재계산한 목록·내용과 다른 manifest는 거부하므로 최신 생성기로 다시 만들어야 한다. 관계의 출발 문서는 결정적 ID를 검증한 실제 관계 또는 삭제 관계의 relation_snapshot으로 확인한다. manifest 밖 기록은 절대 stamp하지 않으며 없는 ID·중복 ID·원문 출발 문서 상태 또는 confirmed 관계 검토가 아닌 ID는 쓰기 전에 거부한다. `tools/build_review_manifest.py`는 고정 파일럿 commit의 reviews/2026 JSONL에서 기본 문서 검토 38개, 선택 옵션으로 관계 검토 48개 ID를 별도 추출한다. 각 이관 기록에는 `source_sha256_basis: migrated-baseline`을 반드시 남긴다. 검증기는 이 marker가 있는 경우에만 digest를 이관 baseline으로 해석해 승인하며, marker가 없거나 다른 비어 있지 않은 basis는 실제 검토 bytes의 digest라는 기존 계약을 따른다. basis는 digest 일치 요건을 면제하지 않는다. **이 1회 이관은 과거 검토 당시 판본을 입증하지 않으며 이관 시점의 현재 판본을 baseline으로 삼는다.** 과거에 payload가 바뀌지 않았다는 보증으로 해석하지 않는다. 이후 새 검토는 실제 검토 당시 해시를 기록해야 한다. 이관 및 전체 GENERATED 재생성 명령은 갱신 스킬에만 둔다.
