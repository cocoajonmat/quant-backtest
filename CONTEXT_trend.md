# 일반 추세추종 전략

A~N 시리즈 실험 로그는 `CONTEXT_trend_archive.md` 참고.

---

## 현재 채택 파라미터 (실험M2, 2026-05-09 확정)

- 유니버스: NDX100 동적 감지 / top_n=5 / ret12>20% / ADX>=20
- momentum_mode: linreg (90일 지수회귀 기울기×R², gate=0.15)
- bear_filter: block MA50
- exit_mode: hybrid (MA10→50% + MA20 3일확인→잔여 전량)
- use_macd_rsi_exit: False
- stop_mode: pct12
- trailing_stop: original
- atr_sizing: on / atr_risk_pct: 4.0% / cap: 40%
- max_positions: 4
- adx_threshold: 20
- min_hold_days: 3
- portfolio_heat_cap: 10%
- entry_mode: score (5팩터 점수합산)

**최고 기록 (8년, 2019~2026):** +909.7% / CAGR 38.1% / MDD -20.7% / 샤프 1.17 / SPY +189.9%  
**5년 기준 (2022~2026):** +210.6% / CAGR 31.3% / MDD -23.5% / 샤프 1.00 (불리한 구간, 8년이 신뢰 기준)

---

## 핵심 발견 요약 (A~N 시리즈)

| 시리즈 | 핵심 결정 |
|--------|----------|
| A~D | top5 / max_pos=4 / 5년 기준 bear=MA100 확정 |
| E~G | 8년 기준 필요성 확인, ret12>30% + bear=MA50 채택 |
| H | linreg(Clenow) 채택 — ret3m 대비 샤프 +0.11 |
| I | linreg gate=0.15 확정 |
| J | ret12>20% 채택 — 수익률 +195%p, MDD -7%p |
| K1 | linreg window=90일 확정 |
| K2 | portfolio_heat_cap=10% 채택 |
| L | 5팩터 점수합산 유지 — 단순화 시 MDD 폭등 |
| M | MACD+RSI 제거 채택 (use_macd_rsi_exit=False) |
| N | 상관계수 제한 역효과 확인, 기준 유지 |

---

## 다음 실험 목록 (우선순위 순)

| 순서 | 내용 | 이유 | 상태 |
|------|------|------|------|
| 1 | ~~방향 B (채널 돌파 터틀 스타일)~~ | — | 완료 → archive |
| 2 | ~~워크포워드 테스트 (IS/OOS 분리)~~ | 과적합 검증 최우선 | 완료 → archive |
| 3 | **bear filter MA50 → MA200 교체 검증** | OOS MDD -42.8% 원인 — MA50이 2024-11 랠리 노출 못 막음, MA200으로 완화 여부 확인 | 대기 |
| 4 | 진입 품질 강화 | 52주 신고가 / 거래량 서지 조건 추가 — 노이즈 진입 감소 | 대기 |
| 5 | 유니버스 다양화 | NDX100 → Russell 1000 성장주 or S&P500 모멘텀 확장 | 대기 |
| 6 | 자본 규모별 ATR% 자동 축소 | 실전 적용 시 달러 손실 규모 고정 | 대기 |
| 7 | 슈퍼사이클 동적 유니버스 갱신 로직 | 슈퍼사이클 전략 작업 | 대기 |

상세 실험 로그 (O/P/Q 시리즈) → `CONTEXT_trend_archive.md`
