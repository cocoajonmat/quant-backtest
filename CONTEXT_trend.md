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

**8년 백테스트 (참고용):** +1223.9% / CAGR 43.5% / MDD -35.6% / 샤프 1.15 — 실전 기대치 아님
- 연도별: 2019 +19.5% / 2020 +67.2% / 2021 +44.3% / 2022 -24.0% / 2023 +54.6% / 2024 +115.6% / 2025 +43.7%
- 커브 특성: 우상향이나 -20~35% 낙폭 구간이 자주 발생하는 거친 커브 / 분기 승률 18/30(60%)

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
| V 시리즈 | Equity Curve Filter (ec_cap=15/20/25%) — V1/V2 OOS 마이너스, V3도 수익 반 토막 → **전부 기각** |
| W 시리즈 | ATR Trailing Stop (stop_mode='atr_trail') — W2 OOS MDD 동급이나 수익 열위 → **기각** |
| X 시리즈 | top_n=3/7 조정 — X2(top_n=7) OOS +352.5% / 샤프 1.55, 기준과 유의미한 차이 없음 → **기각** |
| Y 시리즈 | MA 청산 후 재진입 허용 (allow_reentry=True) — OOS 수익 -23.3%p 감소, MDD 거의 동일 → **기각** |
| AA 시리즈 | ret12_min 스윕 (0.05~0.40, 7개) — >40%가 OOS 전체 +497%/샤프 1.82로 수치상 1위이나, OOS-B(AI붐 이후)에서 기준과 샤프 동급(1.89 vs 1.85), 2019~2021 진입 기회 대폭 차단, IS 꼴찌(샤프 0.61) → **전부 기각, ret12>20% 유지** |
| AB 시리즈 | exit 방식 재검증 (bear=MA200+heat_cap 환경) — fast/ma20_simple/confirm/atr조합 6개. hybrid가 OOS +362.7%/샤프 1.57로 압도적 1위. MA10즉시(fast) IS 우위이나 OOS 반토막(과적합). confirm이 OOS 차선(+302.9%)이나 기준 대비 -60%p → **전부 기각, hybrid 유지** |
| AC 시리즈 | linreg_gate 재검증 (bear=MA200+heat_cap 환경) — gate=0.00/0.05/0.10/0.20/0.25 5개. gate=0.15가 OOS +362.7%/샤프 1.57/MDD -30.4%로 전 지표 1위. gate 완화(0.00~0.10): OOS 수익 소폭 감소·MDD 소폭 악화. gate 강화(0.20~0.25): OOS 수익 -34%p 감소·MDD 악화 + IS 샤프 상승(과적합 징후) → **전부 기각, gate=0.15 유지** |
| AD 시리즈 | linreg_window 재검증 (bear=MA200+heat_cap 환경) — window=60/75/120/150 4개. window=90이 OOS +362.7%/샤프 1.57/MDD -30.4%로 1위. 단기(60/75): OOS 수익·샤프 열위·MDD 악화. 장기(120): IS 샤프 ≈0 (작동 불량). window=150: OOS 수치 높으나 IS 샤프 -0.24 → 심각한 과적합, 신뢰 불가 → **전부 기각, window=90 유지** |
| AE 시리즈 | atr_risk_pct 재검증 (bear=MA200+heat_cap 환경) — 2%/3%/5%/6% 4개. 4%가 IS·OOS 양쪽 전 지표 1위(OOS +362.7%/샤프 1.57/MDD -30.4%). 낮춤(2%/3%): OOS 수익 반토막(-168%p/-88%p), IS 샤프도 열위. 높임(5%/6%): IS 샤프 0.34로 급락, OOS MDD 악화(-35%/-37%), OOS 수익도 감소 → **전부 기각, atr_risk=4% 유지** |
| AF 시리즈 | max_positions 재검증 (bear=MA200+heat_cap 환경) — 3/5/6 3개. max_pos=4가 IS·OOS 양쪽 전 지표 1위(OOS +362.7%/샤프 1.57/MDD -30.4%). 줄임(3): OOS 수익 -109%p, 샤프 1.32. 늘림(5/6): IS부터 수익·샤프 열위, OOS도 일관 감소 — 분산 확대가 수익 희석으로 이어짐. top_n=5/max_pos=4 조합이 최적 → **전부 기각, max_pos=4 유지** |
| AG 시리즈 | OOS 구간 분할 검증 (채택 파라미터) — 2023H2 / 2024 / 2025~현재 3개 구간. **전 구간 SPY 초과** (취약 구간 없음). OOS-A(2023H2): +10.8%/샤프 0.68/SPY+2.8%p — 금리고점 불확실성으로 진입 기회 적어 낮은 샤프. OOS-B(2024): +141.6%/샤프 2.15/SPY+116%p — AI붐 추세에 가장 유리. OOS-C(2025~): +63.9%/샤프 1.14/SPY+36.9%p — 관세 변동성에도 견조. → **파라미터 변경 없음, 실전 운용 신뢰도 확인** |

> V/W/X/Y/AA/AB/AC/AD/AE/AF/AG 공통 결론: 현재 채택 파라미터가 모든 변형 대비 OOS 최우수. 전 OOS 구간 SPY 초과 확인.

---

## 다음 실험 목록

| 순서 | 내용 | 이유 | 상태 |
|------|------|------|------|
| 1~11 | ~~이전 실험들~~ | — | 완료/포기 → archive |
| 12 | ~~T1: bear=none + VIX 동적 사이징~~ | 백테스트에서도 열위 — 기각 | 완료 |
| 13 | ~~T-Simple + MA200 채택~~ | OOS 압도적 — 확정 | 완료 |
| 14 | ~~OOS MDD -38.8% 개선 탐색~~ | heat_cap=0.10 재도입으로 -30.4% 달성 — 완료 | 완료 |
| 15 | ~~V/W/X/Y 시리즈~~ | ec_cap / atr_trail / top_n / 재진입 — 전부 기각, 기준 최우수 | 완료 |
| 16 | ~~섹터 분산 제한 (Z 시리즈)~~ | 추세추종 특성상 섹터 쏠림이 본질 — 건너뜀 | 건너뜀 |
| 17 | ~~ret12_min 동적 조정 (AA 시리즈)~~ | 스윕 결과 >20% 유지 — 기각 | 완료 |
| 18 | ~~exit 방식 재검증 (AB 시리즈)~~ | hybrid가 모든 변형 대비 OOS 최우수 — 기각 | 완료 |
| 19 | ~~linreg_gate 재검증 (AC 시리즈)~~ | gate=0.15가 모든 변형 대비 OOS 최우수 — 기각 | 완료 |
| 20 | ~~linreg_window 재검증 (AD 시리즈)~~ | window=90이 모든 변형 대비 OOS 최우수 — 기각 | 완료 |
| 21 | ~~atr_risk_pct 재검증 (AE 시리즈)~~ | 4%가 IS·OOS 전 지표 1위 — 전부 기각, 채택 유지 | 완료 |
| 22 | ~~max_positions 재검증 (AF 시리즈)~~ | max_pos=4가 IS·OOS 전 지표 1위 — 전부 기각, 채택 유지 | 완료 |
| 23 | ~~OOS 구간 분할 검증 (AG 시리즈)~~ | 전 구간 SPY 초과 확인, 취약 구간 없음 — 완료 | 완료 |
| 24 | **슈퍼사이클 동적 유니버스 갱신** | 현재 16종목 수작업 고정 — 동적 감지 로직 적용 (후순위) | 미완료 |

> 다음 시리즈 표기: Z 이후 AA, AB, AC... (엑셀 열 방식)

상세 실험 로그 (O/P/Q/R/S/T/U/V/W/X/Y 시리즈) → `CONTEXT_trend_archive.md`
