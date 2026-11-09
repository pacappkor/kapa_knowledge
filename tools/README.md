# 도구 안내

실행 명령과 절차는 [갱신 스킬](../rules/knowledge-update-maintenance/SKILL.md)에만 둔다. Python 표준 라이브러리를 사용하며 네트워크 결과는 코드로 실행하지 않는다.

| 파일 | 역할 |
|---|---|
| common.py | KK_ROOT 경로, 잠금 색인, JSON·해시·관계 ID·제한 frontmatter |
| lawapi.py | DRF JSON search/service, 비밀 로딩·제거, 재시도·호출 간격·응답 검증 |
| lawweb.py | 조문 메타데이터 검증, 판례·해석·중앙부처 1차해석 세 탭 전 페이지 |
| collect_article.py | 계약 조문 ID를 풀어 후보 JSONL과 실행 기록 생성, 기존 자료 제외 |
| fetch_material.py | 원문 JSON·해시·문서 GENERATED 갱신, 기존 수동 절·검토 보존, 조문 대응과 미대응 이유 |
| rerender_source.py | 저장 원문 메타데이터·해시 검증 후 원문 절만 오프라인 재생성 |
| fetch_case.py | precSeq 판례 상세 수집과 실행 기록 |
| fetch_interp.py | expc ID 법제처 해석 상세 수집과 실행 기록 |
| markdown_context.py | frontmatter·산문·코드 문맥 분리, 구조적 명령 모양 판별 |
| validate.py | 필수 필드·중복·참조·원본 해시·검토·관계·링크·규칙 분리 검사 |
| test_tools.py | 가짜 응답과 임시 fixture를 쓰는 오프라인 회귀 시험 |

## 환경

- KK_ROOT: 출력 및 검증 대상. 기본은 이 저장소다. 스모크 시험은 스크래치 복사본으로 지정한다.
- KK_SKILLS_ROOT: 색인 형제 체크아웃 경로 재지정. 기본은 코드 저장소 부모의 kapa_skills다. fixture 사용은 시험 전용이며 실제 검증 결과와 구별한다.
- LAW_OC / LAW_OC_FILE: API 인증정보. 둘 다 없으면 코드 저장소 부모의 law_oc.txt를 읽는다. 출력 대상 KK_ROOT를 바꿔도 인증정보 기본 경로는 바뀌지 않는다.
- KK_TEST_TMP: 오프라인 테스트 임시 디렉터리 부모. 세션 스크래치 경로를 지정할 수 있다.

## 경계

조문 수집의 agency 후보는 cgmExpcDatSeq로 남긴다. expcSeq와 다른 식별 체계이므로 fetch_interp에 그대로 넘기지 않는다. 해당 API와 기관별 원문은 별도 검토가 필요하다. molitCgmExpc API는 lawapi 인터페이스로 사용할 수 있으나 기본 수집 CLI가 자동 호출하지 않는다.

참조조문은 완전한 법령명과 명시적 조문만 보수적으로 대응한다. 약칭·같은 법·구법명·판본 추정은 미대응으로 남긴다. cites는 참조 후보이지 적용 판본 확인이 아니다. 후보에서 판례 문서로 올릴 때 비법원 출처를 보류한다.

저장 해시는 비밀 제거된 payload의 정규 JSON 기준이다. 원문 메타데이터가 바뀐 경우 기존 문서의 source_url/source_sha256와 GENERATED만 갱신한다. 사람의 검토가 필요한 상태 축은 자동 변경하지 않는다.
