# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실험 기록 규칙

백테스트를 실행할 때마다 결과를 **전략별 CONTEXT 파일의 실험 로그**에 누적 기록한다.
새 대화에서 히스토리 파악이 필요하면 먼저 **CONTEXT.md(인덱스)**를 읽고, 해당 전략 파일로 이동한다.

- 슈퍼사이클 추세추종 실험 → `CONTEXT_supercycle.md`
- 일반 추세추종 실험 → `CONTEXT_trend.md`
- 오래된 실험 로그(archived) → `CONTEXT_trend_archive.md`, `CONTEXT_supercycle_archive.md`

## 실행

```powershell
python backtest.py        # 슈퍼사이클
python trend_backtest.py  # 일반 추세추종
```

## 프로젝트 현황 (2026-05-09 기준)

미국 주식 추세추종 스윙 트레이딩 백테스팅 시스템.

**슈퍼사이클 (실험21 채택, 5년)**
- +606.9% / CAGR 59.9% / MDD -17.4% / 샤프 1.76 (SPY +86.9%)
- hybrid / MA200 block / pct12 / trailing_stop=original / ATR 4% / max_pos=4 / ADX>=20 / min_hold_days=3 / 16종목

**일반 추세추종 (M2 채택, 8년)**
- +909.7% / CAGR 38.1% / MDD -20.7% / 샤프 1.17 (SPY +189.9%)
- NDX100 동적 top5 / linreg(90일, gate=0.15) / ret12>20% / MA50 block / ATR 4% / heat_cap=10% / max_pos=4 / MACD제거

**다음 작업:** 슈퍼사이클 동적 유니버스 갱신 로직

## 코드 파일

- `backtest.py` — 슈퍼사이클 백테스트 메인 (load_data, run_backtest, PortfolioManager, 지표함수)
- `trend_backtest.py` — 일반 추세추종 방향A (get_dynamic_universe, run_dynamic_backtest)
- `backtest_single.py` — 단일 종목 시각화 (_run_multi.py subprocess로 yfinance 격리)
