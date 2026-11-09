# 검토 이력

`reviews/YYYY/*.jsonl`에 한 줄 한 객체로 추가한다. 기존 기록을 덮어쓰지 않는다.
필수: id(review-고유값), target(문서/관계 ID), reviewer_model(실제 모델 ID), reviewed_at(ISO 8601), reference_status(문서 상태 변경 시), evidence(원문 URL·정확한 인용), decision(accept / reject / needs-review). evidence는 source(HTTPS 원문 URL)·quote(정확한 인용) 문자열 객체다. reviewed_at은 시간대가 있는 ISO 8601 시각이다. 상태·관계 확정에는 accept만 사용하며 boolean 증거·판단은 허용하지 않는다.
overruled-confirmed에는 overruling_id(case ID), change_quote(변경 선언 문구)가 필요하다. superseded-confirmed에는 superseding_id와 대체 근거가 필요하다. last_reviewed는 대응 검토 시각이다. 관계 검토 기록은 relation_review를 둔다.

예시의 임의 기록을 실제 검토로 넣지 않는다. 에이전트의 검토는 법적 효력의 보장이 아니다.
