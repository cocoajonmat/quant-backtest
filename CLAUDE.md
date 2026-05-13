# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실험 기록 규칙

백테스트를 실행할 때마다 결과를 **전략별 CONTEXT 파일의 실험 로그**에 누적 기록한다.
새 대화에서 히스토리 파악이 필요하면 먼저 **CONTEXT.md(인덱스)**를 읽고, 해당 전략 파일로 이동한다.
**작업 중인 전략과 관련 없는 CONTEXT 파일은 명시적 요청 없이 열지 않는다.**

- 슈퍼사이클 추세추종 실험 → `CONTEXT_supercycle.md`
- 일반 추세추종 실험 → `CONTEXT_trend.md`
- 오래된 실험 로그(archived) → `CONTEXT_trend_archive.md`, `CONTEXT_supercycle_archive.md`

**아카이브 규칙:** /done 실행 시, 세션에서 완료된 실험 로그를 즉시 archive 파일로 이동한다.
현재 채택 파라미터 요약과 다음 실험 목록은 CONTEXT 파일에 유지하고, 실험 상세 로그만 archive로 옮긴다.

## 실행

```powershell
python backtest.py        # 슈퍼사이클
python trend_backtest.py  # 일반 추세추종
```

## 프로젝트 현황 (2026-05-13 기준)

미국 주식 추세추종 스윙 트레이딩 백테스팅 시스템.

**슈퍼사이클 (실험21 채택, 5년)**
- +606.9% / CAGR 59.9% / MDD -17.4% / 샤프 1.76 (SPY +86.9%)
- hybrid / MA200 block / pct12 / trailing_stop=original / ATR 4% / max_pos=4 / ADX>=20 / min_hold_days=3 / 16종목

**일반 추세추종 (T-Simple+MA200+heat_cap+rebalance_days=5 채택, 워크포워드 기준)**
- OOS (2023~2026): +427.4% / MDD -29.5% / 샤프 1.68 / SPY 초과 +356.7%p
- NDX100 동적 top5 / linreg(90일, gate=0.15) / ret12>20% / MA200 block / ATR 4% / max_pos=4 / heat_cap=0.10 / entry=universe_only / rebalance_days=5
- V/W/X/Y/AA/AB/AC/AD/AE/AF/AG/AH/AI/AK 시리즈: ec_cap / atr_trail / top_n / 재진입 / ret12_min / exit방식 / linreg_gate / linreg_window / atr_risk_pct / max_positions / OOS구간분할 / 베어마켓강제청산 / 주별리밸런싱 / 피라미딩 — AI2(5일) 채택, AK 전부 기각(8년 풀백 열위)
- 종합 검증 완료 (validation.py): 수수료 반영 확인 / 서바이버십 바이어스 낮음 / MDD 26회·평균50일 / 롤링WF 3/5 SPY 초과 / 평균 포지션 1.74개

**다음 작업 (일반 추세추종):** AJ(절대모멘텀) → AL(손절후재진입금지) 순서로 진행
**다음 작업 (슈퍼사이클):** 동적 유니버스 갱신 로직

## 데이터 관리 규칙 (중요)

**표준 CSV 상태:** git commit `d3abfb4` — 2018-03-12 ~ 2026-05-07, 트레이딩 시작 2019-03-13
- `load_data(period_years=8)` 기준. 모든 실험은 이 CSV 기준으로 비교한다.
- **절대 period_years를 9 이상으로 올리지 말 것** — CSV 재다운로드가 발생해 데이터 기준이 깨짐
- 워크포워드 등 다른 스크립트 실행 후 CSV가 바뀐 것 같으면: `git checkout d3abfb4 -- data/`

## 코드 파일

- `backtest.py` — 슈퍼사이클 백테스트 메인 (load_data, run_backtest, PortfolioManager, 지표함수)
- `trend_backtest.py` — 일반 추세추종 방향A (get_dynamic_universe, run_dynamic_backtest)
- `backtest_single.py` — 단일 종목 시각화 (_run_multi.py subprocess로 yfinance 격리)
- `walkforward_trend.py` — 일반 추세추종 워크포워드 테스트 (M2 파라미터, IS 2019~2022 / OOS 2023~2026)
