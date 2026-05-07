# 프로젝트 컨텍스트 인덱스

## 작업 배경
AI 반도체 투자 전략 PDF(Gap and Go, VCP, 3:3:4 피라미딩)를 분석하고,
해당 전략의 통계적 유효성을 검증하기 위해 파이썬 백테스팅 시스템을 구축 중.

## 개발 환경
- Windows 11, Python 3.10, VS Code
- 노트북 ↔ 데스크탑 번갈아 작업 (GitHub으로 동기화)
- 한국 주식 버전은 추후 KIS Open API 연동 예정

---

## 전략별 상세 기록

| 전략 | 파일 | 현황 |
|------|------|------|
| 슈퍼사이클 추세추종 | [CONTEXT_supercycle.md](CONTEXT_supercycle.md) | 실험 14개 완료, 샤프 1.72 달성 |
| 일반 추세추종 | [CONTEXT_trend.md](CONTEXT_trend.md) | 설계 방향 정의, 미시작 |

---

## 빠른 현황 요약

**슈퍼사이클 (현재 집중)**
- 채택 전략: hybrid / SPY MA200 block / pct12 / trailing_stop=on / ATR 4% / 16종목
- 최고 기록: +480.0% / CAGR 52.5% / MDD -22.0% / 샤프 1.56 (SPY +86.9%, data/ CSV 스냅샷 기준)
- 다음 실험: 섹터 ETF 모멘텀 필터 추가

**일반 추세추종**
- 아직 시작 전. 슈퍼사이클 다음 단계로 예정.
