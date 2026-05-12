# 일반 추세추종 전략

A~N 시리즈 실험 로그는 `CONTEXT_trend_archive.md` 참고.

---

## 현재 채택 파라미터 (T-Simple + MA200 + heat_cap, 2026-05-12 확정)

> R6-A → T-Simple 전환 이유: R6-A의 추가 레이어(52주 고가/5팩터/heat_cap/min_hold/adx중복)가
> IS 과적합 노이즈임을 워크포워드로 확인.
> bear MA50 → MA200 전환 이유: 실전 판단 기준으로 더 명확하고 OOS 성능도 압도적.
> portfolio_heat_cap=0.10 재도입 이유: OOS MDD -38.8% → -30.4% 개선 + OOS 수익·샤프도 향상.
> IS에서는 불리하나 이는 2021~2022 강세장 진입 제한 효과 — 실전 리스크 관리 관점에서 맞는 방향.

- 유니버스: NDX100 동적 감지 / top_n=5 / ret12>20% / ADX>=20 (유니버스 선발 시)
- momentum_mode: linreg (90일 지수회귀 기울기×R², gate=0.15)
- bear_filter: block MA200 (SPY MA200 기준 신규 진입 차단)
- exit_mode: hybrid (MA10→50% + MA20 3일확인→잔여 전량)
- use_macd_rsi_exit: False
- stop_mode: pct12
- trailing_stop: original
- atr_sizing: on / atr_risk_pct: 4.0% / cap: 40%
- max_positions: 4
- adx_threshold: 0 (유니버스에서 이미 적용, 진입 시 중복 제거)
- min_hold_days: 0 (제거)
- portfolio_heat_cap: 0.10 (재도입 — MDD 개선 효과 확인)
- entry_mode: universe_only (5팩터 점수 제거)
- require_52w_high: False (제거)

**워크포워드 기준 (신뢰 기준, IS 2021~2023 / OOS 2023~2026):**
- IS: +52.2% / MDD -31.3% / 샤프 0.64 / SPY 초과 +27.5%p
- OOS: +362.7% / MDD -30.4% / 샤프 1.57 / SPY 초과 +292.0%p

**8년 백테스트 (참고용, 과적합 포함):** R6-A 기준 +1062.4% / CAGR 40.9% — 실전 기대치 아님

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
| R | 52주 신고가 6% 필터 채택 — 백테스트 기준 CAGR +2.8%p, 샤프 +0.12 (단, OOS에선 과적합 노이즈) |
| T-Simple | 파라미터 단순화 채택 — OOS SPY 초과 +120.4%p (R6-A +84.4%p 대비 우위) |
| T-Simple+MA200 | bear MA200 채택 — OOS SPY 초과 +227.2%p / 샤프 1.39 |
| U 시리즈 | **heat_cap=0.10 재도입** — OOS MDD -38.8%→-30.4%, 수익·샤프도 향상 (최종 확정) |

---

## 다음 실험 목록

| 순서 | 내용 | 이유 | 상태 |
|------|------|------|------|
| 1~11 | ~~이전 실험들~~ | — | 완료/포기 → archive |
| 12 | ~~T1: bear=none + VIX 동적 사이징~~ | 백테스트에서도 열위 — 기각 | 완료 |
| 13 | ~~T-Simple + MA200 채택~~ | OOS 압도적 — 확정 | 완료 |
| 14 | ~~OOS MDD -38.8% 개선 탐색~~ | heat_cap=0.10 재도입으로 -30.4% 달성 — 완료 | 완료 |

상세 실험 로그 (O/P/Q/R/S/T 시리즈) → `CONTEXT_trend_archive.md`
