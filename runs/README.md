# 수집 실행 기록

`runs/<source>/<YYYY-MM-DD>-<n>.json`에 started/finished, 질의·조문, 트랙별 status(success/zero/failure), 건수, 후보 파일, 오류를 남긴다. 실패는 0건이나 변동 없음이 아니다. zero는 정상 빈 응답을 확인했을 때만 쓴다. 반복 실행도 별도 실행 기록을 남기며 후보는 기존 자료와 대조한다.
