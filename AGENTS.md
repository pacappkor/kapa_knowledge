# AGENTS.md — kapa_knowledge 작업 규칙

## 두 갈래

- 읽고 답하기: [knowledge-reading-rules](rules/knowledge-reading-rules/SKILL.md). 파일은 바꾸지 않는다.
- 명시적 갱신 지시: [knowledge-update-maintenance](rules/knowledge-update-maintenance/SKILL.md). 절차와 도구 명령은 그곳에만 둔다.
- 입구: [00-knowledge-start](00-knowledge-start/SKILL.md). 쟁점·업무에서 출발한다.
- `rules/`에는 두 스킬만 둔다. 입구는 읽기 규칙을 가리킨다.

## 작성과 운영

- CI credential 검사 PR base는 기본 브랜치 main만 허용한다. secret-free 검사는 모든 PR에 실행하고 실제 값 검사에서는 런타임 base ref == main == default branch 확인을 적용하고 immutable base SHA·blob 접근 전에 거부한다. main의 신뢰된 리뷰가 전제이며 실제 branch protection 설정을 가정하지 않는다.

- 법령과 실무기준 원문은 kapa_skills가 단일 출처다. 여기에는 복제하지 않고 계약 ID로 연결한다.
- `sources/`와 GENERATED 블록은 생성물이다. 손으로 고치지 않는다. 사람이 쓴 요약·분석은 경계 밖에 둔다.
- 자동 진행 상태와 근거 있는 참조 상태를 섞지 않는다. 상세는 [SCHEMA](docs/SCHEMA.md).
- 에이전트가 원문 근거와 검토 모델 ID를 남긴다. 후속 결정이나 오래된 날짜만으로 폐기 상태를 붙이지 않는다.
- 사용자가 요청할 때만 갱신한다. 자료의 정기 갱신·스케줄은 없다. 방문·clone 통계 workflow만 매일 실행한다.
- 변경은 작업 브랜치와 PR로 반영한다. main 직접 반영 금지. CHANGELOG의 Unreleased에 기록한다.
- PR은 의존성 commit을 실제 SHA로 고정한다. WORKTREE는 개발 경고 상태다.
- 공개 가능한 저장소이며 저장소 가시성을 보안 경계로 삼지 않는다. 인증정보는 GitHub Actions secrets 또는 셸 환경변수로만 전달한다. 개인정보·민감한 사건 정보와 제3자 자료의 공개 권리는 별도 검토한다.
- 새 코드에 SPDX-License-Identifier: GPL-3.0-only를 단다. LF를 쓴다.
- rules/·docs/ 아래의 모든 파일(확장자·대소문자 무관)과 루트의 README*·AGENTS*·CLAUDE*·SKILL* 파일(접두사 대소문자 무관)은 전체 바이트의 경로·SHA-256·크기를 tools/doc_command_snapshot.json과 비교한다. 내용·추가·삭제·이름 변경은 모두 명시적 재생성 전 실패하며 snapshot 변경을 같은 PR에서 검토한다. 읽기 전에 index mode와 공용 경로 검사로 링크·reparse·비정규 파일·저장소 이탈을 거부하고 불일치는 가려진 경로·해시·크기만 보고한다. 문서 영역·실행기 추론은 하지 않으며 rules/**/SKILL.md의 정규 사전 검사 쌍은 보조 sanity 검사로만 유지한다.
- production 자식 프로세스는 캡처된 literal git의 plumbing ls-files·ls-tree·rev-parse·cat-file(-e·-t·-s·-p·--batch)만 허용한다. show·diff·log·status와 textconv·외부 diff·filter 옵션은 거부한다. 모든 운영 Git 호출은 git_read.run_git 하나를 거쳐 fsmonitor·untrackedCache를 명시적으로 끄며 LAW_OC·LAW_OC_FILE과 모든 GIT_* 변수를 제거한 환경 사본 및 출력 캡처로 실행한다. helper 밖의 직접 자식 실행은 거부한다. 이벤트 루프의 subprocess_exec·subprocess_shell을 포함한 다른 프로세스 API와 명령은 기본 거부하며 추적 symlink·gitlink도 갱신 전에 거부한다. fixture 쓰기 면제는 실제 unittest discovery 대상이면서 production import 경로에서 도달하지 않는 시험 모듈에만 적용하고 production의 test_ 이름 모듈 import는 거부한다.
- 모든 문서·시험의 도구 실행은 `-I -B`를 함께 사용하여 import 전부터 바이트코드 캐시 쓰기를 막는다. 비격리 실행에서는 `PYTHONDONTWRITEBYTECODE=1`도 동등하지만 `-I`는 환경변수를 무시하므로 이 절차에서는 명시적 `-B`를 생략하지 않는다.
- 토큰·OC 키는 출력·로그·커밋하지 않는다. URL의 OC는 `***`로 가린다.
- credential 검사는 LAW_OC 환경변수의 실제 값과 README에 문서화한 인코딩을 비교한다. 로컬은 셸에서 LAW_OC를 설정한다. CI 준비는 PR 코드를 실행하지 않는 인라인 표준 라이브러리로 trusted base의 scanner·credentials·git_read 일반 blob만 작업 트리 밖으로 추출하며 credential-scan 작업의 첫 저장소 코드 실행 단계에서 이 scanner에만 GitHub secret LAW_OC를 전달한다. PR 작업 트리의 추적·미추적 비무시 파일 전체를 필수 검사한다. 값·검색 바이트는 출력하지 않는다. workflow YAML 자체를 바꿀 수 있는 same-repo 작성자까지 격리하지는 않으며 workflow 권한·리뷰가 신뢰 경계다. 난독화·암호화는 범위 밖이며 PR 검토를 유지한다. 실제 값 검사는 main 푸시·수동 실행·same-repo PR에서만 --require로 실행하고 fork PR은 secret-free offline-checks만 실행한다. scanner는 키가 없으면 건너뛰며 검증기의 literal-shape 경고는 보안 보장이 아니다.
- `.github/ci/`는 운영 tools에서 import하지 않는 CI 전용 감독 영역이다. Git diff·상태 검사·Actions 출력 파일·시험 자식 실행은 이곳에서만 조정하며 tools의 안전 쓰기·공용 Git helper 제한은 그대로 유지한다. vendor에는 deps.lock의 commit·SHA-256으로 고정한 색인·과거 판본 메타데이터만 두고 법령 본문은 복제하지 않는다.
