"""
일반 추세추종 전략 — 방향 A: 동적 슈퍼사이클 감지
====================================================
핵심 아이디어:
  NDX100 전체 종목 중 "지금 슈퍼사이클 초입 특성을 보이는 종목"을 실시간 감지해
  기존 슈퍼사이클 전략(hybrid/ATR4%/trailing_stop)과 동일한 방식으로 진입.

유니버스 선정 기준 (get_dynamic_universe):
  1) 12개월 수익률 > 40%        — 이미 강한 추세 존재
  2) 3개월 수익률 > 12개월 / 12  — 모멘텀 가속 (최근 3개월이 연간 평균보다 빠름)
  3) 현재가 > MA50 > MA200      — MA 정배열
  4) ADX >= adx_min             — 추세 강도 확인
  5) 일평균 거래대금 $100M 이상  — 유동성
  → 조건 충족 종목을 3개월 수익률 순 정렬 후 Top top_n 선택

기존 슈퍼사이클 전략과의 차이:
  - 유니버스: 수작업 16종목 → NDX100 동적 감지
  - 나머지 파라미터: 실험21 기준에서 출발해 스윕
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings('ignore')

import backtest as bt
from backtest import (
    CONFIG, BENCHMARK, SECTOR_ETFS,
    load_data, run_backtest, compute_metrics, print_metrics, plot_comparison,
    PortfolioManager, calc_adx,
    get_nasdaq100_tickers,
)

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False


# ─────────────────────────────────────────────
# 동적 슈퍼사이클 감지 유니버스
# ─────────────────────────────────────────────
def get_dynamic_universe(price_data, date, top_n=8, adx_min=20,
                         ret12_min=0.40, dollar_vol_min=100_000_000):
    """
    NDX100 전체에서 슈퍼사이클 초입 특성을 보이는 종목 동적 선발.

    조건 (전부 충족):
      - 12개월 수익률 > ret12_min (기본 40%)
      - 3개월 수익률 > 12개월 수익률 / 4  (모멘텀 가속 — 연간 평균의 25% 이상을 최근 3개월에 달성)
      - MA 정배열: 현재가 > MA50 > MA200
      - ADX >= adx_min
      - 일평균 거래대금 >= dollar_vol_min

    반환: 3개월 수익률 내림차순 Top top_n 종목 리스트
    """
    candidates = []

    for ticker, df in price_data.items():
        if ticker == BENCHMARK or ticker in SECTOR_ETFS:
            continue
        if date not in df.index:
            continue

        idx = df.index.get_loc(date)
        if idx < 252:
            continue

        close = df['Close']
        volume = df['Volume']
        current = close.iloc[idx]

        # 12개월 수익률
        ret_12m = current / close.iloc[idx - 252] - 1
        if ret_12m <= ret12_min:
            continue

        # 6개월 수익률 (양수 확인 — 추세 지속성)
        if idx >= 126:
            ret_6m = current / close.iloc[idx - 126] - 1
            if ret_6m <= 0:
                continue

        # 3개월 수익률
        ret_3m = current / close.iloc[idx - 63] - 1

        # 모멘텀 가속: 최근 3개월이 12개월 평균 분기 수익률보다 높아야 함
        if ret_3m <= ret_12m / 4:
            continue

        # MA 정배열
        if idx < 200:
            continue
        ma50  = close.iloc[idx - 50:idx].mean()
        ma200 = close.iloc[idx - 200:idx].mean()
        if not (current > ma50 > ma200):
            continue

        # ADX 추세 강도
        adx = calc_adx(df, idx)
        if adx < adx_min:
            continue

        # 유동성: 20일 평균 거래대금
        avg_dollar_vol = (close.iloc[idx - 20:idx] * volume.iloc[idx - 20:idx]).mean()
        if avg_dollar_vol < dollar_vol_min:
            continue

        candidates.append({"ticker": ticker, "ret_3m": ret_3m, "ret_12m": ret_12m, "adx": adx})

    if not candidates:
        return []

    cand_df = pd.DataFrame(candidates).sort_values('ret_3m', ascending=False)
    return cand_df.head(top_n)['ticker'].tolist()


# ─────────────────────────────────────────────
# 동적 유니버스를 사용하는 백테스트 래퍼
# ─────────────────────────────────────────────
def run_dynamic_backtest(price_data, portfolio, top_n=8, adx_min=20,
                         ret12_min=0.40, dollar_vol_min=100_000_000,
                         bear_filter='block', stop_mode='pct12', exit_mode='hybrid',
                         atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
                         trailing_stop='original', spy_ma_period=200,
                         adx_threshold=20, min_hold_days=3):
    """
    get_dynamic_universe를 유니버스 공급원으로 사용하는 백테스트.
    backtest.run_backtest의 get_universe 호출 부분을 monkey-patch 방식으로 교체.
    """
    from datetime import timedelta

    benchmark_df = price_data[BENCHMARK]
    start_date = benchmark_df.index[252]
    trading_days = benchmark_df.index[benchmark_df.index >= start_date]

    pending_tranches = {}
    current_universe = []
    last_universe_update = None

    print(f"\n[동적 유니버스 / top_n={top_n} / ret12>{ret12_min*100:.0f}% / ADX>={adx_min}]")
    print(f"  백테스팅: {trading_days[0].date()} ~ {trading_days[-1].date()}")
    print("-" * 60)

    for date in trading_days:
        price_snapshot = {}
        for ticker, df in price_data.items():
            if date in df.index:
                price_snapshot[ticker] = df.loc[date, 'Close']

        # SPY MA 상태
        spy_above_ma = True
        if bear_filter != 'none':
            spy_idx = benchmark_df.index.get_loc(date)
            if spy_idx >= spy_ma_period:
                spy_ma = benchmark_df['Close'].iloc[spy_idx - spy_ma_period:spy_idx].mean()
                spy_above_ma = benchmark_df['Close'].iloc[spy_idx] >= spy_ma

        # 유니버스 업데이트 (월 1회)
        if last_universe_update is None or (date - last_universe_update).days >= 21:
            current_universe = get_dynamic_universe(
                price_data, date, top_n=top_n, adx_min=adx_min,
                ret12_min=ret12_min, dollar_vol_min=dollar_vol_min,
            )
            last_universe_update = date

        # 기존 포지션 매도 판단
        for ticker in list(portfolio.positions.keys()):
            if ticker not in price_data or date not in price_data[ticker].index:
                continue
            df = price_data[ticker]
            idx = df.index.get_loc(date)
            pos = portfolio.positions[ticker]

            hold_days = (date - pos.entry_date).days if min_hold_days > 0 else 0
            sell_signals = bt.check_sell_signals(df, idx, pos, stop_mode=stop_mode,
                                                  exit_mode=exit_mode, trailing_stop=trailing_stop)
            if min_hold_days > 0 and hold_days < min_hold_days:
                sell_signals = [(r, ratio) for r, ratio in sell_signals
                                if r in ('HARD_STOP', 'TRAIL_STOP')]

            for reason, ratio in sell_signals:
                if reason in ('HARD_STOP', 'TRAIL_STOP', 'MACD_RSI_EXIT',
                              'MA20_BREAK', 'MA10_ALL', 'MA20_CONFIRM', 'MA20_HYBRID_ALL'):
                    portfolio.sell_all(ticker, price_snapshot[ticker], reason, date)
                    pending_tranches.pop(ticker, None)
                    break
                else:
                    portfolio.sell_partial(ticker, price_snapshot[ticker], ratio, reason, date)
                    if ticker in portfolio.positions:
                        portfolio.positions[ticker].sold_pct += ratio

        # 추가 매수 (2차, 3차 트랜치)
        for ticker in list(pending_tranches.keys()):
            if ticker not in portfolio.positions:
                pending_tranches.pop(ticker, None)
                continue
            pt = pending_tranches[ticker]
            if date < pt['trigger_date']:
                continue
            df = price_data[ticker]
            if date not in df.index:
                continue
            idx = df.index.get_loc(date)
            current_price = price_snapshot.get(ticker)
            if current_price is None:
                continue
            pos = portfolio.positions[ticker]

            if pt['tranche'] == 2:
                if current_price >= pos.tranches[0]['price']:
                    portfolio.buy(ticker, current_price, pos.signal_strength, date,
                                  tranche=2, price_snapshot=price_snapshot)
                    if pos.signal_strength == 'strong':
                        pending_tranches[ticker] = {
                            "tranche": 3,
                            "trigger_date": date + timedelta(days=14),
                        }
                    else:
                        pending_tranches.pop(ticker, None)
            elif pt['tranche'] == 3:
                if idx >= 20:
                    ma20 = df['Close'].iloc[idx - 20:idx].mean()
                    if current_price > ma20:
                        portfolio.buy(ticker, current_price, pos.signal_strength, date,
                                      tranche=3, price_snapshot=price_snapshot)
                        pending_tranches.pop(ticker, None)

        # 신규 진입
        if portfolio.position_count() < CONFIG['max_positions']:
            for ticker in current_universe:
                if ticker in portfolio.positions:
                    continue
                if portfolio.position_count() >= CONFIG['max_positions']:
                    break
                if ticker not in price_data or date not in price_data[ticker].index:
                    continue

                df = price_data[ticker]
                idx = df.index.get_loc(date)
                if idx < 252:
                    continue

                score, _ = bt.calculate_signal_score(df, idx)

                if score >= CONFIG['strong_signal_threshold']:
                    strength = 'strong'
                elif score >= CONFIG['medium_signal_threshold']:
                    strength = 'medium'
                else:
                    continue

                if bear_filter == 'block' and not spy_above_ma:
                    continue

                if adx_threshold > 0 and idx >= 28:
                    if bt.calc_adx(df, idx) < adx_threshold:
                        continue

                entry_price = price_snapshot.get(ticker)
                if entry_price is None:
                    continue

                cap_override = None
                if atr_sizing and idx >= 15:
                    atr = bt.calc_atr(df, idx)
                    stop_dist_pct = (atr * 2.5) / entry_price
                    if stop_dist_pct > 0:
                        current_eq = portfolio.total_equity(price_snapshot)
                        cap_override = (current_eq * atr_risk_pct) / stop_dist_pct
                        cap_override = max(200, min(cap_override, current_eq * atr_position_cap))

                success = portfolio.buy(ticker, entry_price, strength, date, tranche=1,
                                        price_snapshot=price_snapshot, capital_override=cap_override)
                if success:
                    pending_tranches[ticker] = {
                        "tranche": 2,
                        "trigger_date": date + timedelta(days=5),
                    }

        equity = portfolio.total_equity(price_snapshot)
        portfolio.equity_curve.append({"date": date, "equity": equity})

    print(f"백테스팅 완료. 총 거래 횟수: {len(portfolio.trade_log)}건")


# ─────────────────────────────────────────────
# 실험 실행부
# ─────────────────────────────────────────────
if __name__ == "__main__":

    NDX100 = get_nasdaq100_tickers()
    CONFIG['max_positions'] = 4

    print("="*60)
    print("  일반 추세추종 - 방향 A: bear_filter MA 기준 스윕")
    print("  A1 기준 고정 (top8/ret12>40%/ADX>=20), bear_filter만 변경")
    print("="*60)

    price_data = load_data(NDX100, period_years=5)

    # 공통 파라미터
    COMMON = dict(
        top_n=8, adx_min=20, ret12_min=0.40,
        stop_mode='pct12', exit_mode='hybrid',
        atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
        trailing_stop='original', adx_threshold=20, min_hold_days=3,
    )

    # ── 실험 B1: bear_filter=none ──
    print("\n[실험 B1] bear_filter=none (필터 없음)")
    CONFIG['max_positions'] = 4
    p_b1 = PortfolioManager(CONFIG['initial_capital'])
    run_dynamic_backtest(price_data, p_b1, bear_filter='none', spy_ma_period=200, **COMMON)
    m_b1, ec_b1, spy_curve = compute_metrics(p_b1, price_data)
    m_b1['label'] = 'B1: none'
    print_metrics(m_b1)

    # ── 실험 B2: bear_filter=block MA200 (기존 기준) ──
    print("\n[실험 B2] bear_filter=block MA200 (기존 A1 기준)")
    CONFIG['max_positions'] = 4
    p_b2 = PortfolioManager(CONFIG['initial_capital'])
    run_dynamic_backtest(price_data, p_b2, bear_filter='block', spy_ma_period=200, **COMMON)
    m_b2, ec_b2, _ = compute_metrics(p_b2, price_data)
    m_b2['label'] = 'B2: block MA200'
    print_metrics(m_b2)

    # ── 실험 B3: bear_filter=block MA100 ──
    print("\n[실험 B3] bear_filter=block MA100")
    CONFIG['max_positions'] = 4
    p_b3 = PortfolioManager(CONFIG['initial_capital'])
    run_dynamic_backtest(price_data, p_b3, bear_filter='block', spy_ma_period=100, **COMMON)
    m_b3, ec_b3, _ = compute_metrics(p_b3, price_data)
    m_b3['label'] = 'B3: block MA100'
    print_metrics(m_b3)

    # ── 실험 B4: bear_filter=block MA50 ──
    print("\n[실험 B4] bear_filter=block MA50")
    CONFIG['max_positions'] = 4
    p_b4 = PortfolioManager(CONFIG['initial_capital'])
    run_dynamic_backtest(price_data, p_b4, bear_filter='block', spy_ma_period=50, **COMMON)
    m_b4, ec_b4, _ = compute_metrics(p_b4, price_data)
    m_b4['label'] = 'B4: block MA50'
    print_metrics(m_b4)

    # ── 결과 비교 차트 ──
    results = [
        {"label": m_b1['label'], "ec": ec_b1, "metrics": m_b1},
        {"label": m_b2['label'], "ec": ec_b2, "metrics": m_b2},
        {"label": m_b3['label'], "ec": ec_b3, "metrics": m_b3},
        {"label": m_b4['label'], "ec": ec_b4, "metrics": m_b4},
    ]
    plot_comparison(results, spy_curve,
                    title="일반 추세추종 방향A - bear_filter MA 기준 스윕 (5Y)")
