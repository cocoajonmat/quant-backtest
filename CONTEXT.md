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
| 일반 추세추종 | [CONTEXT_trend.md](CONTEXT_trend.md) | R6-A 채택, 샤프 1.29 / 52주신고가 6% 필터 추가 |

---

## 빠른 현황 요약

### 슈퍼사이클 (실험21 채택)
- 채택 전략: hybrid / SPY MA200 block / pct12 / trailing_stop=original / ATR 4% / max_positions=4 / ADX>=20 / min_hold_days=3 / 16종목
- 최고 기록: +606.9% / CAGR 59.9% / MDD -17.4% / 샤프 1.76 (SPY +86.9%)
- **다음 실험: 슈퍼사이클 유니버스 동적 갱신 로직** → 상세: `CONTEXT_supercycle.md`

### 일반 추세추종 (R6-A 채택)
- 채택 전략: NDX100 동적 top5 / linreg(window=90, gate=0.15) / ret12>20% / bear=block MA50 / ATR 4% / heat_cap=10% / max_positions=4 / use_macd_rsi_exit=False / **52주신고가 6% 필터**
- 최고 기록 (8년): +1062.4% / CAGR 40.9% / MDD -18.2% / 샤프 1.29 (SPY +189.9%)
- **다음 실험: 워크포워드 재실행 (R6-A 기준, 52주 신고가 필터 포함 OOS 검증)** → 상세: `CONTEXT_trend.md`
