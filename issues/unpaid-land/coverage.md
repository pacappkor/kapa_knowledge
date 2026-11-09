# 미지급용지 초기 역사 조사 범위

조사일: 2026-11-08. 법원·법제처·국토교통부 공개자료, 기간 제한 없음. 사용자가 지정한 P1–P7 번호를 사용한다. 내부 갱신 스킬의 경로 번호와 대응 명칭이 다르다.

## 기록 읽기

- 각 실행의 질의, 매개변수, 응답 페이지와 총 건수는 runs/pilot 및 runs/article에 있다. 원문 검색 응답은 비밀 제거 후 보존했다.
- 개별 검색 결과의 판정·제외 사유·출처는 ../../runs/pilot/screening.jsonl에 있다. deferred는 제외가 아니라 개별 전문 검토 미완료다.
- 선별 상태는 수집용이며 참조 가능성 판정이 아니다. 모든 문서는 unreviewed이며 source-verified 이하이다.

## P1 조문 연결 전 페이지

- 시행규칙 제25조: 판례 3, 법제처 2, 중앙부처 2. 법 제70조: 판례 29, 법제처 3, 중앙부처 2. 세 탭의 전 페이지를 도구의 총 건수/페이지 검증으로 회수했다.
- source URL: https://www.law.go.kr/LSW/joStmdInfoP.do?lsiSeq=261727&joNo=0025&joBrNo=00 및 lsiSeq=289333&joNo=0070. 각 탭 엔드포인트는 lsStmdConPrecListR.do, lsStmdConExpcListR.do, lsStmdConCgmExpcListR.do.
- 법 제70조의 일반 평가·개발이익·표준지 쟁점은 직접 미지급용지 판단이 없으면 제외한다. 상세 미선별 항목은 deferred로 남겼다.
- 중앙부처 상세 웹 225338, 23852는 재시도 후 통신 실패. 23852는 API 원문으로 회수. 225338은 연결 목록만 확인.

## P2 연혁과 전신법

- 잠금 의존성의 시행규칙 versions 파일 36판본을 확인했다. 29판본은 2003년 이후 현행 법률 시행규칙, 7판본은 토지수용법시행규칙이다.
- 처음 ID로 판본 일련번호를 요청해 36회 실패했다. MST 매개변수로 수정하여 재조회 성공. 실패 기록은 삭제하지 않았다.
- 2003-01-01 제25조 미불용지, 2015-04-28 제목·본문 용어가 미지급용지로 변경됨을 확인했다. 토지수용법시행규칙 7판본 전문에서 미불/미보상/보상금이 지급되지 문구에 대응하는 조문은 찾지 못했다. 이를 제25조 직접 전신이라고 추정하지 않는다.
- 공공용지의취득및손실보상에관한특례법시행규칙 제6조제7항은 92누4833, 92누2653, 94누14650 등 공식 판결 원문에서 확인했다. 독립 폐지법령 검색은 nw=2/3 및 이름 변형 모두 0건. 원법령 연혁 전체를 직접 확보하지 못했으므로 전신 연혁 조사 미완료.
- 법령 전문은 이 저장소에 복제하지 않았고 scratch에서만 비교했다.

## P3 참조판례 역방향

- 수록 판례의 참조판례 필드에 있는 사건번호를 모두 API 본문검색(search=2)으로 조회하고 정확 사건번호를 대조했다. 직접 미지급용지 문구가 없는 일반 법리는 확장자료로 제외했다. 후속 재실행의 질의·원문 검사 결과는 round 실행 기록에 보존했다.
- 본문의 인용 중 참조판례 필드에 없는 모든 인용의 재귀 확장은 아직 완료하지 못했다.

## P4 후속 인용

- 수록 사건번호를 따옴표로 감싸 prec search=2로 전 페이지 검색. 응답 section=bdyText를 확인하여 본문검색 지원을 확인했다. 일반 query는 분절 검색하므로 따옴표 질의를 병행했다.
- 최초 확장에서 98두13850, 98두7770 등 역사 판례를 추가했다. 이후 미보상용지 검색에서 98두6081, 92누17259 등을 추가했다.
- 라운드 도구는 검색 목록 법원명(서울고등법원)과 상세 법원명(서울고법)의 차이를 새 자료로 오인한 횟수가 있다. 문서 경로는 동일하므로 실제 고유 문서 증가와 구별해야 한다.

## P5 키워드 API

- prec 및 expc 각각 미지급용지, 미불용지, 종전의 공익사업, 보상금이 지급되지 아니한 토지를 search=2/display=100으로 전 페이지 조회했다. 정확 문구 따옴표 검색도 각 4회 실시했다.
- prec 정확 문구 총 결과: 4, 14, 7, 13. expc 정확 문구: 2, 0, 7, 3. 중복을 포함한 결과 수이며 고유 관련 건수가 아니다.
- 데이터출처명 대법원만 판례 수록 대상으로 삼았다. 국세법령정보시스템·지방세법령정보시스템 등은 세금/비법원 자료로 제외하고 원래 데이터출처명을 ledger에 보존했다.

## P6 법제처 사이트

- https://www.moleg.go.kr/lawinfo/nwLwAnList.mo?mid=a10106020000 에서 keyField=3, keyWord=네 문구; keyField=5, keyWord=토지수용법 및 공공용지의 취득 및 손실보상에 관한 특례법을 조회했다.
- 내용 검색 결과 각각 2, 0, 7, 3건, 모두 한 페이지. 전신법명 검색 각각 0건. 관련 법제처 자료 4건 중 소유자변경, 선행 미보상부지 사업인정, 무인가 도로, 매수청구 준용을 API로 수록했다. 환매·이주대책 3건은 제외.
- 사이트 cs_seq=451333/427118/374976/100029가 관련 자료에 대응한다. 사이트 원문과 API 문서의 개별 전면 대조는 미완료.

## P7 국토교통부와 교차 탐색

- target=molitCgmExpc에 네 문구와 정확 문구를 search=2로 전 페이지 조회. 정확 문구 결과 23, 3, 15, 18건. 27개 고유 상세 응답 검사.
- 안건번호가 없는 FAQ 11건은 기관+안건번호 계약키를 만들 수 없어 보류. 임의 번호를 만들지 않았다. 토지정책과-308(2015/2016), -1730(2015/2016)처럼 동일 번호·상이한 날짜는 동일성 검토 전 중복 추가 보류. -5599의 중복 API ID도 하나만 수록.
- 초기 API 원문은 보존하되 최신 skeleton 계약에 맞춰 중앙부처 원본 봉투를 cgmexpc, 문서 키를 cgmExpcDatSeq로 오프라인 이관했다. payload·출처 URL·해시는 유지했다.
- 실무기준 810-6.2.3 및 연결 업무 스킬 ID를 잠금 색인에서 확인.

## 잠정 포화와 한계

- 인용 검색의 후속 두 차례에서 새 고유 문서가 관찰되지 않은 구간은 있다. 그러나 전신법 원문 미확보, 분절 키워드 결과의 deferred 선별, 기관 번호 충돌과 미번호 FAQ, 중앙부처 상세 접근 실패가 남아 전체 P1–P7 포화 조건 충족이라고 선언하지 않는다.
- 공개 원문 범위의 조사이며 비공개·미등재 판결, 누락된 참조판례, 검색 색인 누락은 회수할 수 없다. 완전성을 주장하지 않는다.
- 적용 판본 unknown은 판결일을 법 적용 시점으로 대체하지 않았기 때문이다. 판본 특정과 과거 조문 ID 검증 범위 해결은 후속 작업이다. 과거 ID 통과를 위한 validator 완화는 하지 않았다.
- 최신 skeleton의 검증기를 그대로 사용한다. 지원명 공백은 계약 ID/court에서 제거하고 원문 표기는 보존했다. URL 인코딩 링크를 실제 경로로, 관계 유형을 끝점 계약에 맞게 정정했다.

## 실행별 집계

|실행|경로|질의|상태|페이지|응답 총 건수|
|---|---|---|---|---|---|
|exact-expc-0.json|P5-exact|"미지급용지"|success|1|2|
|exact-expc-1.json|P5-exact|"미불용지"|zero|1|0|
|exact-expc-2.json|P5-exact|"종전의 공익사업"|success|1|7|
|exact-expc-3.json|P5-exact|"보상금이 지급되지 아니한 토지"|success|1|3|
|exact-molitCgmExpc-0.json|P5-exact|"미지급용지"|success|1|23|
|exact-molitCgmExpc-1.json|P5-exact|"미불용지"|success|1|3|
|exact-molitCgmExpc-2.json|P5-exact|"종전의 공익사업"|success|1|15|
|exact-molitCgmExpc-3.json|P5-exact|"보상금이 지급되지 아니한 토지"|success|1|18|
|exact-prec-0.json|P5-exact|"미지급용지"|success|1|4|
|exact-prec-1.json|P5-exact|"미불용지"|success|1|14|
|exact-prec-2.json|P5-exact|"종전의 공익사업"|success|1|7|
|exact-prec-3.json|P5-exact|"보상금이 지급되지 아니한 토지"|success|1|13|
|expand-1.json|P2|"공공용지의취득및손실보상에관한특례법시행규칙" "제6조" "보상"|success|1|5|
|expand-10.json|P3|2004나7753|success|1|3|
|expand-11.json|P3|2006다28065|success|1|28|
|expand-12.json|P3|2006두11507|success|1|11|
|expand-13.json|P3|2007가단93857|success|1|2|
|expand-14.json|P3|2007누841|success|2|179|
|expand-15.json|P3|2007다36445|success|1|26|
|expand-16.json|P3|2007다42112|success|1|19|
|expand-17.json|P3|2007두25237|success|1|7|
|expand-18.json|P3|2008다7314|success|1|9|
|expand-19.json|P3|2008두22129|success|1|7|
|expand-2.json|P2|"토지수용법시행규칙" "미불용지"|zero|1|0|
|expand-20.json|P3|2009가합22429|success|1|2|
|expand-21.json|P3|2009나331|success|5|467|
|expand-22.json|P3|2009다99143|success|1|8|
|expand-23.json|P3|2009두4029|success|1|7|
|expand-24.json|P3|2010가합118281|success|1|2|
|expand-25.json|P3|2010구합680|success|6|540|
|expand-26.json|P3|2010다33866|success|1|17|
|expand-27.json|P3|2011가합21186|success|1|2|
|expand-28.json|P3|2011누41559|success|1|1|
|expand-29.json|P3|2011두7007|success|1|18|
|expand-3.json|P2|토지수용법시행규칙|failure|0|?|
|expand-30.json|P3|2011타경8155|success|1|1|
|expand-31.json|P3|2012가합4444|success|1|1|
|expand-32.json|P3|2012구합875|success|2|144|
|expand-33.json|P3|2012다20819|success|1|10|
|expand-34.json|P3|2012다54133|success|1|5|
|expand-35.json|P3|2013다211575|success|1|2|
|expand-36.json|P3|2013두20219|success|1|4|
|expand-37.json|P3|2015나2001015|success|1|1|
|expand-38.json|P3|2015다237588|success|1|1|
|expand-39.json|P3|2016구합442|success|2|117|
|expand-4.json|P2|공공용지의취득및손실보상에관한특례법시행규칙|failure|0|?|
|expand-40.json|P3|2016다264556|success|1|21|
|expand-41.json|P3|2017다249073|success|1|1|
|expand-42.json|P3|2017다360|success|8|728|
|expand-43.json|P3|2018가소60177|success|1|1|
|expand-44.json|P3|2018가합21858|success|1|2|
|expand-45.json|P3|2022나57947|success|1|2|
|expand-46.json|P3|250기각4|success|1|1|
|expand-47.json|P3|400기각6|success|1|1|
|expand-48.json|P3|400전도로22249|success|1|2|
|expand-49.json|P3|500기각2|success|1|2|
|expand-5.json|P3|000기각5|success|1|1|
|expand-50.json|P3|57조의2|success|16|1575|
|expand-51.json|P3|750기각1|success|1|1|
|expand-52.json|P3|80다3269|success|1|12|
|expand-53.json|P3|86누256|success|2|108|
|expand-54.json|P3|86누760|success|2|156|
|expand-55.json|P3|87누1141|success|1|18|
|expand-56.json|P3|87누395|success|2|104|
|expand-57.json|P3|89누1056|success|1|9|
|expand-58.json|P3|90구20048|success|1|4|
|expand-59.json|P3|90구21539|success|1|2|
|expand-6.json|P3|000답답52835|success|1|2|
|expand-60.json|P3|90누9971|success|1|17|
|expand-61.json|P3|91누10831|success|1|3|
|expand-62.json|P3|91누2038|success|1|7|
|expand-63.json|P3|91누7774|success|1|9|
|expand-64.json|P3|91누8388|success|1|2|
|expand-65.json|P3|91다21206|success|1|11|
|expand-66.json|P3|91다24311|success|1|5|
|expand-67.json|P3|92누14779|success|1|15|
|expand-68.json|P3|92누17259|success|1|3|
|expand-69.json|P3|92누4833|success|1|10|
|expand-7.json|P3|100기각3|success|1|1|
|expand-70.json|P3|92다19804|success|1|16|
|expand-71.json|P3|92다25045|success|1|5|
|expand-72.json|P3|93구23635|success|1|1|
|expand-73.json|P3|93누2131|success|1|12|
|expand-74.json|P3|93누24230|success|1|7|
|expand-75.json|P3|95누13241|success|1|5|
|expand-76.json|P3|95다18956|success|1|5|
|expand-77.json|P3|96누14661|success|1|8|
|expand-78.json|P3|97가합23377|success|1|2|
|expand-79.json|P3|97다27114|success|1|8|
|expand-8.json|P3|2000다58576|success|1|5|
|expand-80.json|P3|98다41759|success|1|6|
|expand-81.json|P3|98다59132|success|1|12|
|expand-82.json|P3|98두28523|success|1|2|
|expand-83.json|P3|98두8896|success|1|10|
|expand-84.json|P3|99다39524|success|1|3|
|expand-85.json|P3|99두9957|success|1|2|
|expand-86.json|P4|"92누4833"|success|1|5|
|expand-87.json|P4|"92누2653"|success|1|5|
|expand-88.json|P4|"94누14650"|success|1|4|
|expand-89.json|P4|"2008두22129"|success|1|6|
|expand-9.json|P3|2003두14222|success|1|2|
|expand-90.json|P4|"2011나81123"|success|1|1|
|expand-91.json|P4|"2013두20219"|success|1|2|
|old-extra-0.json|P2|공공용지|success|1|0|
|old-extra-1.json|P2|공공용지|success|1|0|
|old-extra-2.json|P2|공공용지의 취득 및 손실보상에 관한 특례법 시행규칙|success|1|0|
|old-extra-3.json|P2|미보상용지|success|1|11|
|oldlaw-0.json|P2|토지수용법시행규칙|success|1|1|
|oldlaw-1.json|P2|공공용지의취득및손실보상에관한특례법시행규칙|success|1|0|
|search-1.json|P5|미지급용지|success|2|141|
|search-10.json|P7|미불용지|success|1|3|
|search-11.json|P7|종전의 공익사업|success|1|32|
|search-12.json|P7|보상금이 지급되지 아니한 토지|success|1|21|
|search-2.json|P5|미불용지|success|1|19|
|search-3.json|P5|종전의 공익사업|success|12|1114|
|search-4.json|P5|보상금이 지급되지 아니한 토지|success|14|1316|
|search-5.json|P5|미지급용지|success|1|2|
|search-6.json|P5|미불용지|zero|1|0|
|search-7.json|P5|종전의 공익사업|success|2|137|
|search-8.json|P5|보상금이 지급되지 아니한 토지|success|1|32|
|search-9.json|P7|미지급용지|success|1|23|

## 수록 자료

- case/광주고등법원/(전주)2017누1853 / 20180820
- case/대법원/2008두22129 / 20090326
- case/대법원/2013두20219 / 20141127
- case/대법원/2023다295442 / 20240215
- case/대법원/92누17259 / 19930525
- case/대법원/92누2653 / 19930323
- case/대법원/92누4833 / 19921110
- case/대법원/94누14650 / 19950613
- case/대법원/98두13850 / 19990323
- case/대법원/98두6081 / 20000728
- case/대법원/98두7770 / 19991022
- case/부산고등법원/2019나51607 / 20191030
- case/부산지법 울산지원/94가합9739 / 19970702
- case/서울고등법원/2011나81123 / 20120525
- case/서울고등법원/2011누21234 / 20120921
- case/서울고등법원/2012누35322 / 20130830
- case/서울고법/2001누9150 / 20020322
- case/서울고법/2010나47706 / 20110414
- case/수원지방법원평택지원/2019가합11854 / 20191205
- case/수원지방법원/2012구합875 / 20121024
- case/수원지법/2009가합22429 / 20100422
- case/울산지방법원/2018가합21858 / 20190124
- interp/moleg/11-0073 / 20110407
- interp/moleg/16-0618 / 20170223
- interp/moleg/21-0150 / 20210504
- interp/moleg/26-0385 / 20260915
- interp/molit/토지정책과-1552 / 20170308
- interp/molit/토지정책과-1554 / 20170308
- interp/molit/토지정책과-1730 / 20150309
- interp/molit/토지정책과-1948 / 20140324
- interp/molit/토지정책과-3012 / 20170504
- interp/molit/토지정책과-308 / 20160114
- interp/molit/토지정책과-318 / 20170111
- interp/molit/토지정책과-3609 / 20170605
- interp/molit/토지정책과-3613 / 20170625
- interp/molit/토지정책과-4348 / 20140709
- interp/molit/토지정책과-5599 / 20170831
- interp/molit/토지정책과-6383 / 20160818
- interp/molit/토지정책과-7109 / 20160907

## 재수집과 최종 검증

- 2차 수집은 조문 연결 두 목록 전 페이지와 수록 자료 39건 전체 원문을 다시 요청했다. 자료 ID 집합은 39 → 39, 추가 0, 삭제 0. 쟁점 골격 포함 문서 40.
- 두 차례 검증 모두 최종 정정 후 documents: 40 / errors: 0 / warnings: 0. 도구 테스트 9개 통과.
- P1 개별 후보 판정은 runs/pilot/article-screening.json에 있다. 미선별은 제외로 세지 않았다.
- 초기 36판본 실패는 ID/MST 매개변수 오류였고 보정 후 모두 성공했다. 중앙부처 웹 상세 실패는 별도로 미해결이다.

## 추가 전문 선별 결과 (2026-11-08 당시 집계; 아래 2026-11-09 갱신 우선)

- 실행 시작 2026-11-08T13:34:19.151864+00:00, 종료 2026-11-08T14:05:18.066359+00:00.
- 비법원 출처 제외 후 P3/P4/P5 deferred 고유 prec ID는 3,183건. P1 개별 선별 완료 후 최종 큐 3,183건(초기 합산 큐 3,196건에서 P1 전용 13건 제거). 출처명 대법원만 사용했다.
- 순위: 서로 다른 주제 키워드에 걸린 수, 주제 정확문구 질의 수, 서로 다른 발견 질의 수 내림차순. 사건번호 검색의 반복횟수는 키워드 강도로 오인하지 않았다.
- 전체를 API ID로 중복 제거했다. 전문 주제 문구 정규식: 미지급용지 | 미불용지 | 미보상용지 | 보상금이 지급되지 아니한 | 종전(의)? 공익사업. 무문구는 주제 문구 없음(전문 확인)로 제외. 문구 검출은 수동 문맥 판정.
- 초당 약 1회 요청 및 캐시 재사용. 1,500건 자원 상한 적용. 상한 밖 자료는 관련성 부정이 아닌 미선별로 남겼다.
- 전문 처리 1500건: {"relevant": 0, "excluded": 1500, "manual-pending": 0, "failure": 0}. 상한 밖 1683건. 정확 ID는 deferred-fulltext.json의 remaining_unscreened에 있다.

### 경로별 고유 API ID 수

|경로|전체|관련|제외|보류|미선별|
|---|---:|---:|---:|---:|---:|
|P1|40|6|31|3|0|
|P2|16|12|2|0|2|
|P3|4053|24|2349|0|1680|
|P4|36|11|11|0|14|
|P5|2554|26|2386|0|142|
|P5-exact|57|40|6|11|0|
|P7|46|16|0|17|13|

- P1 미선별 28개 후보 전부 개별 전문 확인 및 한 줄 이유 기록 완료. 그중 일반 평가 27건은 무문구, 2016두940은 종전 기보상 구분지상권/일단지 쟁점이므로 제외. 새 관련 자료 없음.
- cgmexpc 225338 대체 DRF lawService.do target=cgmExpc도 실패하여 보류 유지. 11개 무번호 FAQ 보류 유지.
- 초기 수록 94가합9739는 재검사 결과 선분양 채무승계 사건으로 잘못 포함된 것이 확인되어 쟁점 자료에서 제외했다. 원문 source와 제외 실행 기록은 보존했다.
- 이번 후속 작업에서 tools 파일 추가 수정 없음. 이전 수집기의 변경 목록은 앞선 보고와 같다.

### 추가자료 인용 확장의 포화 라운드

- P3 참조판례 역방향 및 P4 후속 본문 인용 검색을 이번 선별 신규 자료에 한정하여 실행했다.
- 라운드 1: 시드 0, 질의 0, 새 고유 문서 0, 수동 판정 대기 0.
- 위 제한 범위의 포화 여부: True. P2 전신법 원문, P5 상한 밖 전문 선별, P7 식별 불가/접근 실패는 부분 조사이므로 전체 포화 또는 완전성을 주장하지 않는다.

### 최종 확인

- 2026-11-08 추가 전문 선별 최종: 1,500건 중 무문구 제외 1,497건, 문구 검출 3건을 모두 수동 제외(149953 변호사법, 100162 공무원 징계, 184645 일단지 평가). 실패 0, 새 관련 자료 0, 수동 판정 대기 0. P3/P4/P5 미선별 고유 법원 출처 ID 1,683건은 1,500건 상한 때문에 남겼다.
- 신규 자료 대상 P3/P4 포화 라운드 1은 시드 0, 질의 0, 추가 0이다. 이는 이번 전문 선별에서 신규 자료가 없어 확장할 대상이 없다는 뜻이며, 기존 전체 검색이나 상한 밖 후보의 포화를 증명하지 않는다.
- P1 고유 40개 후보: 관련 6, 제외 31, 보류 3, deferred 0. 보류는 225338 및 법 제70조 중앙부처 후보 24216/48124(후자의 상세 개별 선별 미완료).
- 수록 총계는 판례 21건 및 해석 17건(법제처 4, 국토교통부 13), 쟁점 골격 포함 문서 39. 초기 22건 판례 총계는 제외 정정 전 수치이다.
- 최종 2차 재수집은 조문 두 목록 및 수록 38개 원문 전체를 요청했다. ID 집합 38 → 38, 추가 0, 삭제 0. 전후 검증 documents: 39 / errors: 0 / warnings: 0. 도구 테스트 9개 통과.
- 새 도구 수정은 없다. 1차 작업의 fetch_material.py/fetch_interp.py/validate.py 변경만 별도 worktree 수정과 조정하면 된다.

## 2026-11-09 잔여 법원 ID 단일 matcher 전수 재선별 완료 [analysis]

- 기존 2·3차 배치는 1차보다 좁은 정규식을 사용했다. 이를 보완하여 캐시 원문 1,683건 전체를 공백 무관 9개 신호의 단일 matcher `unpaid-land-complete-whitespace-v1`로 다시 선별했다. 처리 1,683건·적중 0건·실패 0건·해당 큐 미선별 0건이며, 행별 공식 URL·정규화 전 판례내용 문자열의 UTF-8 SHA-256·바이트 크기·선별시각을 보존했다. 원문 전문은 로컬 캐시에 남으며 동일 바이트 재현에는 해당 캐시 또는 digest가 일치하는 재취득 원문이 필요하다.

- 실행 증거: [메타데이터](../../runs/pilot/screening-remaining-1683.json), [개별 1,683건](../../runs/pilot/screening-remaining-1683.jsonl). `screened_text_sha256`는 SHA-256 digest 32바이트를 패딩 포함 RFC 4648 표준 Base64로 인코딩하고 `sha256-` 접두사를 붙인 SRI `sha256-<Base64 digest>` 문자열이다. hex와 표기만 다르며 digest 바이트와 계산 대상 원문은 동일하다. 재선별 matcher·시각·digest 정의는 메타데이터에 기록했다. 세 배치는 과거 취득 시각·요청 간격만 나타내며 재선별은 네트워크 요청 없이 수행했다. 과거 요청 간격은 작업자별이며 병렬 실행 전체의 초당 1회 보장은 아니다.
- 기존 remaining_unscreened 1,683개 ID와 새 1,683행의 고유 ID 집합이 정확히 일치한다. 처리 1,683, 무문구 제외 1,683, 새 관련 0, 실패 0, 수동대기 0, 해당 큐 미선별 0. 이전 1,500건과 합쳐 3,183건 처리·제외 완료(무문구 3,180 + 문맥 수동 제외 3).
- 문구 기반 선별 결과일 뿐 모든 사건이 실체적으로 무관하다는 판단은 아니다. 초기 deferred-fulltext 및 발견 ledger는 당시 스냅샷으로 유지한다. 이번 1,683건만 단일 matcher로 재선별했으며 이전 1,500건의 방법은 역사 기록 그대로다. P2 전신법 계약·일부 판본 공백, P3·P4 재귀 인용 확장, P5 다른 기관 자료의 미선별, P7 식별·회신일 보류와 하급심 후속 결과 미확인 등은 남아 있다.
- 아래 표는 기존 경로별 표에서 이번 ID 집합과 겹치는 미선별만 제외로 이동한 집계다. 경로 간 중복이 있으므로 합산하지 않는다. 다른 기관 자료의 미선별은 별도다.

|경로|이번 문구 선별 제외 추가|현재 제외|현재 미선별|
|---|---:|---:|---:|
|P1|0|31|0|
|P2|1|3|1|
|P3|1680|4029|0|
|P4|14|25|0|
|P5|0|2386|142|
|P5-exact|0|6|0|
|P7|0|0|13|

## 2026-11-09 보류 자료 재판정 [analysis]

근거와 정확 인용은 [보류 자료 조사](../../runs/pilot/held-items-research.json)에 보존했다. 참조 상태는 변경하지 않았다. 초기 접근 실패 기록은 당시 사실이며 아래 결과가 현재 판정이다.

- 225338: 국토교통부가 아닌 **국세청** 서면인터넷방문상담5팀-137(2008-01-18), 양도소득세 회신. 원문 회수로 접근 보류를 해소하고 제외했다. molitCgmExpc 자료로 대응하지 않는다.
- 24216(토지정책과-5551): 사업인정 실효 후 새 사업의 용도지역 변경 평가. 48124(토지정책과-10058): 적법하게 형질변경한 대지의 현실 이용상황 평가. 둘 다 P1 일반 평가 제외 기준(종전 coverage 15행)에 따라 제외한다. 24216의 인접성은 인정하되 미지급용지 자체 판단으로 확대하지 않는다.
- P1 현재 고유 40건: 관련 6, 제외 34, 보류 0, 미선별 0. 기존 3개 보류만 제외로 이동했다.

### 토지정책과-308 동일성 보류

회답 전체 469자는 정확히 동일하며 SHA256은 `f2550d889ae679b7ab90219357c19bec5f880bc5a43c88f7c5fcf4222241cae9`이다. 제목·질의는 다르고 원기관 LAIIS 본문도 각각 해당 연도를 명시한다. 단순 DRF 날짜 변환 오류로 단정할 수 없다.

- 원문 ID 40786, 날짜 20150114; https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40786 ; 원기관 https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37805 ; 정확 인용: “토지정책과-308(2015.1.14.)”.
- 원문 ID 40696, 날짜 20160114; https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40696 ; 원기관 https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37808 ; 정확 인용: “토지정책과-308(2016.1.14.)”.

원 회신문 또는 기관 정정 확인 전 중복 병합·별개 행정행위 확정 모두 보류한다. 기존 ID와 indeterminate 상태를 유지한다. 별도 회신임이 입증된 경우에만 기관+번호+날짜 계약 개정 및 명시적 이관을 검토하며 지금 날짜 접미 ID를 만들지 않는다.

### 토지정책과-1730 동일성 보류

회답 전체 760자는 정확히 동일하며 SHA256은 `38117a084f81657ef21d9d2a351493fb227f188f16a08d934145befd5211556d`이다. 제목·질의는 다르고 원기관 LAIIS 본문도 각각 해당 연도를 명시한다. 단순 DRF 날짜 변환 오류로 단정할 수 없다.

- 원문 ID 23932, 날짜 20150309; https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=23932 ; 원기관 https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37643 ; 정확 인용: “토지정책과-1730(2015.3.9.)”.
- 원문 ID 40580, 날짜 20160309; https://www.law.go.kr/LSW/cgmExpcInfoR.do?cgmExpcDatSeq=40580 ; 원기관 https://www.laiis.go.kr/lips/nya/lrn/localRegulationDetail.do?nttNo=37950 ; 정확 인용: “토지정책과-1730(2016.3.9.)”.

원 회신문 또는 기관 정정 확인 전 중복 병합·별개 행정행위 확정 모두 보류한다. 기존 ID와 indeterminate 상태를 유지한다. 별도 회신임이 입증된 경우에만 기관+번호+날짜 계약 개정 및 명시적 이관을 검토하며 지금 날짜 접미 ID를 만들지 않는다.

### FAQ 11건: 계속 보류

국민신문고 epUnionSn은 공식 출처 식별자이지 회신 안건번호가 아니다. 현행 interp/기관/안건번호 계약을 유지하고 임의 안건번호를 만들지 않는다.

|law.go.kr ID|국민신문고 epUnionSn|공식 원출처|
|---|---|---|
|2284827|6892751|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6892751|
|2285119|6897179|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6897179|
|2285647|181130|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=181130|
|2285723|465155|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=465155|
|2286795|6875657|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6875657|
|2287409|6875656|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6875656|
|2288509|337597|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=337597|
|2372909|6900441|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6900441|
|2372927|6900440|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6900440|
|2372961|6900434|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6900434|
|2380945|6900670|https://www.epeople.go.kr/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid?dutySctnNm=tqapttn&epUnionSn=6900670|

## 2026-11-09 전신법 적용 판본 조사 [analysis]

[판본 조사 실행 기록](../../runs/pilot/predecessor-versions-research.json). 판결일 대신 판결 전문에 명시된 수용재결일을 사용했다. 일반 시행판본 선택은 모든 경과규정 적용의 확정을 뜻하지 않는다. 각 사건 문서의 수동 영역에 적용 조문·lsiSeq/efYd·날짜 근거·정확 인용을 기록했다. reference_status 및 applied_version 기계 필드는 변경하지 않았다.

|사건|재결일 또는 한계|규칙 lsiSeq / efYd|추가 판본|
|---|---|---|---|
|case/대법원/92누4833|1990-04-07|36383 / 19890922|공공용지의취득및손실보상에관한특례법 제4조 3항: 8936/19760701; 공공용지의취득및손실보상에관한특례법시행령 제2조: 10079/19890124|
|case/대법원/92누2653|1990-02-27|36383 / 19890922|토지수용법 제46조 2항: 129804/19890701|
|case/대법원/92누17259|전문에 수용재결일 없음|미확정 / 미확정|공공용지의취득및손실보상에관한특례법시행규칙 제6조의2 2항: 미확정/미확정|
|case/대법원/94누14650|판결은 1995.1.7. 건설교통부령3 개정 전이라고만 특정|미확정 / 미확정|공공용지의취득및손실보상에관한특례법시행규칙 제6조의2 2항,3항: 미확정/미확정; 토지수용법 제57조의2: 미확정/미확정|
|case/대법원/98두13850|1995-11-21|36385 / 19950107|공공용지의취득및손실보상에관한특례법 제4조 4항: 9050/19950101; 공공용지의취득및손실보상에관한특례법시행령 제2조의10: 10190/19950101; 공공용지의취득및손실보상에관한특례법시행령 제10조: 10190/19950101; 토지수용법 제46조 1항: 129824/19911231; 토지수용법 제57조의2: 129824/19911231|
|case/대법원/98두7770|1996-07-15|36385 / 19950107|공공용지의취득및손실보상에관한특례법 제4조 2항: 9051/19960101; 토지수용법 제46조 1항,2항: 129823/19960101|
|case/대법원/98두6081|1996-09-09|36385 / 19950107|토지수용법 제46조 2항: 129823/19960101; 토지수용법 제29조: 미확정/미확정; 토지수용법 제45조: 미확정/미확정|
|case/서울고법/2001누9150|1998-03-27|36386 / 19971015|공공용지의취득및손실보상에관한특례법 제4조 2항: 9052/19961230; 토지수용법 제14조: 129822/19980101; 토지수용법 제16조: 129822/19980101; 토지수용법 제75조: 129822/19980101; 토지수용법 제75조의2: 129822/19980101; 공공용지의취득및손실보상에관한특례법시행규칙 부칙(1995.1.7. 건설교통부령 제3호) 제4항: 36385/19950107|

### 계약 공백과 미해결

- 공특법 법률 lsId 001826, 시행령 002258, 시행규칙 006297은 잠금 kapa_skills 색인에 없다. 검증기는 조문형 law/lsId@lsiSeq#a번호를 색인의 articles에 정확히 존재할 때만 허용하므로 역사 조문 관계를 추가하지 않았다. 009295(토지수용법 predecessor 판본 계보)도 해당 과거 조문 키가 없으면 동일하게 연결 불가다. 문헌 매핑만 남기며 현행 조문 관계로 대체하지 않는다.
- 92누17259·94누14650은 수용재결일/적용 규칙 판본 미확정. 36384/19911028은 대조용일 뿐 적용 확정이 아니다.
- 98두6081은 규칙 36385/19950107 및 제46조 대조와 별도로 토지수용법 제29·45조의 1995 개정 전 참조 표지와 1996-09-09 재결일이 충돌한다. 129824/19911231, 129823/19960101 두 판본을 대조하되 충돌은 미해결로 유지한다.
- 토지수용법 독립 폐지법령 계보 ID는 별도 미조사다. 전체 전신 연혁·기관 식별 및 재귀 인용 확장은 완료 선언하지 않는다.

## 통합 검증 및 테스트 제약 (2026-11-09)

- 최신 skeleton 98c263f의 tools 전체를 변경 없이 유지했다. pilot 데이터 검증 결과 documents: 39 / errors: 0 / warnings: 0.
- skeleton 테스트는 fixture에서 저장소 전체를 복사한 뒤 단일 테스트법만 들어 있는 색인으로 검증한다. 실제 pilot이 있는 체크아웃에서는 기존 중앙부처 ID 23852와 테스트 회신 ID가 충돌해 test_agency_detail_and_fetch가 중복 식별 키 오류를 낸다. 이는 데이터 삭제나 검증 완화로 해결하지 않았다.
- 동일 98c263f를 scratch의 빈 skeleton fixture로 내보내 변경 없는 테스트를 실행하면 43 tests / OK (errors 0, failures 0). pilot 체크아웃에서 직접 실행하는 테스트까지 통과했다는 뜻은 아니다. populated repository와 무관한 fixture 격리는 skeleton 측 후속 수정 과제이며, 본 pilot에서는 tools 변경 금지에 따라 남겼다.
