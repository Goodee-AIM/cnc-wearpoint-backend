# Set test 폴더 및 여러 파일 업로드

> 2026-11-20 기준: **여러 파일·폴더 업로드와 재생 목록 기능은 현재 화면에서 제거되었다.**
> 현재 Set test는 이미지(PNG/JPEG) 1개와 센서 CSV 1개만 선택해 `POST /api/measurements/auto-predict`로
> 업로드와 AI 추론을 한 번에 요청한다. 현재 동작은 `docs/manual-inputs.md`와 `docs/deployment/auto_prediction.md`를 참고한다.
> 아래 백엔드 재생 목록 API는 남아 있지만 현재 프런트는 호출하지 않는다.

## 현재 화면/사용법

- 이미지와 CSV 입력은 각각 한 파일만 선택한다. '파일 선택' 버튼은 바로 파일 선택 창을 열며 폴더 선택 메뉴는 표시하지 않는다.
- 파일 선택 창에서 여러 파일을 고를 수 없다. 지원 확장자가 아니면 "파일을 한 개만 선택해 주세요." 안내를 표시하고, 이미지·CSV 중 하나가 빠지면 업로드하지 않는다. WebP는 선택 단계에서 걸러지지 않지만 업로드 시 PNG/JPEG만 허용한다.
- 연결 확인 목록, 파일명 자동 매칭, 순차 재생 목록, 저장된 입력 선택 목록은 현재 화면에 없다.
- Set 1~8 자동 모니터링과 DB 알림/세션 reset은 Set test의 영향을 받지 않는다.

이전에 저장한 여러 파일 재생 기록을 브라우저(localStorage)가 기억하고 있으면 해당 목록을 순서대로 한 번 재생할 수 있다.
이 기록에서 새 추론을 하려면 파일을 다시 업로드해야 한다.

## 이전 동작 (참고, 현재 미사용)

- 각 '파일 선택' 버튼의 메뉴에서 여러 파일 또는 폴더(Chrome/Edge `webkitdirectory`, 하위 폴더 포함)를 골랐다.
- 확장자를 제외한 파일명이 같은 이미지·CSV만 자동 매칭하고, 나머지는 연결 확인 목록에서 직접 지정했다.
- 이미지 경로/파일명의 자연 정렬 순서(2 다음 10)로 재생하고 마지막 데이터 다음에는 처음으로 돌아갔다.
- 업로드는 `/api/manual-inputs`를 한 쌍씩 호출한 뒤 `/api/manual-inputs/playlists`로 목록을 저장했다. 추론은 포함하지 않았다.
- 관련 코드 일부(`src/utils/manualPlaylist.js`의 매칭 함수, `ManualFilePicker.jsx`의 폴더 입력)는 프런트 저장소에 남아 있지만 현재 화면에서는 사용하지 않는다.

## 저장/실패

현재 Set test 업로드는 이미지 8MB, CSV 20MB 이하 한 쌍이며 검증·실패 처리는 `auto-predict` 계약을 따른다.

백엔드에 남아 있는 이전 재생 목록 저장의 제한:

- 이미지 한 파일 8MB, CSV 한 파일 20MB, 재생 목록 항목 최대 1,000개(중복 ID 불가), 목록 요청 본문 64KB 이하.
- 목록은 이미 저장된 입력 UUID만 참조하며, 모든 ID를 확인한 뒤 저장한다. 없는 ID가 있으면 404를 반환한다.
- 기본 저장 총 용량은 512MB이며 백엔드 환경변수 `MANUAL_INPUT_QUOTA_MB`로 조정한다.
- 운영에서 이 저장소를 사용한다면 영구 볼륨(`MANUAL_INPUT_ROOT`) 및 Nginx 업로드 크기 설정이 필요하다.

이전 API:
- GET /api/manual-inputs/playlists: 저장 목록과 연결된 입력 조회
- POST /api/manual-inputs/playlists: item_ids(순서 있는 UUID 목록), name으로 목록 저장
기존 업로드/이미지/센서/단건 조회 API와 이전 저장 기록은 유지한다. 이 API들은 공통 모니터링과 측정·알림 테이블에 쓰지 않는다.

## 적용 후 검증

1. 백엔드 재시작(리셋 호출 불필요), 프런트 새로고침.
2. Set test에서 이미지 1개 + CSV 1개 업로드, 재생과 추론 결과 표시 확인.
3. 파일 선택 창에서 여러 파일·폴더를 고를 수 없고, 한쪽 파일이 없으면 업로드되지 않고 안내가 표시되는지 확인.
4. 기존 Set으로 이동했을 때 Set test 재생이 초기화되고 기존 그래프가 정상인지 확인.

자동 검증(2026-11-20): 프런트 Node 회귀 테스트 89개(`tests/manualPlaylist.test.js` 포함), 백엔드 `277 passed, 10 skipped`
(`tests/test_manual_playlists.py` 포함, 실제 MySQL·Registry opt-in 테스트 생략).
