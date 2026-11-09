# 기계 수집 원본

직접 편집하지 않는다. `sources/prec/<precSeq>.json`, `sources/expc/<id>.json`은 수집 시각·가린 URL·payload·sha256를 가진다. sha256는 비밀 제거 후 payload의 정렬 키·2칸 들여쓰기·UTF-8·LF 끝줄 JSON 바이트 기준이다. `sources/candidates/<run-id>.jsonl`은 조문별 후보·발견 경로다. 원문을 바꾸려면 수집·변환 로직을 고친다. 법령 전문은 저장하지 않는다.
