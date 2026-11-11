# 버전과 릴리스 기록

0.x에서는 호환성 깨짐도 MINOR이며 CHANGELOG에 명시한다. 이후 ID·경로·스키마 비호환은 MAJOR, 새 쟁점·자료 범위·기능은 MINOR, 정정·문서·도구 수정은 PATCH다.

CHANGELOG는 Unreleased에 먼저 기록한다. 릴리스 시 vX.Y.Z와 실제 날짜를 적고 자료·판본 변화, 검토 모델·근거, 조사 범위·미확인, 검증 결과를 포함한다. 병합된 main 커밋에 태그와 릴리스를 둔다. 갱신 실행 절차는 [갱신 스킬](../rules/knowledge-update-maintenance/SKILL.md)에만 있다.

PR에서는 deps.lock을 실제 kapa_skills SHA로 고정한다. WORKTREE는 개발 전용이다. 저장소는 공개 배포할 수 있다. 공개 여부와 무관하게 인증정보는 Actions secrets 또는 셸 환경변수로만 전달하고 저장소에 포함하지 않는다. 공개 전 개인정보·제3자 자료의 배포 권리를 별도 확인한다.
