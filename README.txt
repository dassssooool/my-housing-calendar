청약 캘린더 자동연동 v2 (배포용 준비본)

현재 상태: 공식 API 문서에 근거한 수집 코드 + GitHub Actions 일일 실행 + 웹 화면의 notices.json 읽기 기능을 구성했습니다.
실제 인증키 호출/정확도/공고 링크 검증은 아직 수행하지 않았습니다. 실시간 데이터가 연결되었다고 간주하면 안 됩니다.

사용자에게 필요한 것:
1) GitHub 계정 준비
2) 이 폴더 내용을 새 GitHub 저장소에 업로드 (숨김 .github 폴더 포함)
3) 저장소 Settings > Secrets and variables > Actions > New repository secret 에 APPLYHOME_API_KEY 저장 (절대 코드에 입력 금지)
4) Actions > Update housing notices > Run workflow 실행하여 성공 여부 확인
5) Settings > Pages > Deploy from a branch > main / root 활성화
6) 발급된 Pages 주소에서 index.html 접속

주의: 최초 notices.json 생성 전까지 가상 예시만 표시됩니다.
청약홈만 지원합니다. LH/SH/GH/iH 공공임대는 별도 수집이 필요합니다.
공고별 특별공급·1순위 일정, 자격 구분, 원문 링크는 검증 후 보완해야 합니다.
API 오류 시 자동 실행이 실패하고 이전 파일이 유지됩니다.
