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
| 슈퍼사이클 추세추종 | [CONTEXT_supercycle.md](CONTEXT_supercycle.md) | 실험21 완료, 샤프 1.76 달성 |
| 일반 추세추종 | [CONTEXT_trend.md](CONTEXT_trend.md) | 방향A(M2) 최종 확정, 샤프 1.17 / Q2 완료 (MA200 기각) |

---

## 빠른 현황 요약

### 슈퍼사이클 (실험21 채택)
- 채택 전략: hybrid / SPY MA200 block / pct12 / trailing_stop=original / ATR 4% / max_positions=4 / ADX>=20 / min_hold_days=3 / 16종목
- 최고 기록: +606.9% / CAGR 59.9% / MDD -17.4% / 샤프 1.76 (SPY +86.9%)
- **다음 실험: 슈퍼사이클 유니버스 동적 갱신 로직** → 상세: `CONTEXT_supercycle.md`

### 일반 추세추종 (M2 채택)
- 채택 전략: NDX100 동적 top5 / linreg(window=90, gate=0.15) / ret12>20% / bear=block MA50 / ATR 4% / heat_cap=10% / max_positions=4 / use_macd_rsi_exit=False
- 최고 기록 (8년): +909.7% / CAGR 38.1% / MDD -20.7% / 샤프 1.17 (SPY +189.9%)
- **다음 실험: 진입 품질 강화 (52주 신고가 / 거래량 서지 조건)** → 상세: `CONTEXT_trend.md`
