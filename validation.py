"""
일반 추세추종 전략 — 종합 검증 스크립트
=========================================
검증 항목:
  1. MDD 상세 분석  — 낙폭 이벤트 횟수·지속일·회복일 통계
  2. 롤링 워크포워드 — IS 3년 / OOS 1년, 1년씩 슬라이딩 (5 윈도우)
  3. 포지션 분포     — 실제 평균 보유 포지션 수 / 현금 비율

채택 파라미터: T-Simple + MA200 + heat_cap=0.10 (2026-05-12 확정)
"""

import sys
import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings('ignore')

import backtest as bt
from backtest import CONFIG, BENCHMARK, load_data, PortfolioManager, get_nasdaq100_tickers
from trend_backtest import run_dynamic_backtest

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ─────────────────────────────────────────────
# 채택 파라미터 (T-Simple + MA200 + heat_cap=0.10)
# ─────────────────────────────────────────────
PARAMS = dict(
    top_n=5,
    adx_min=20,
    momentum_mode='linreg',
    linreg_gate=0.15,
    linreg_window=90,
    ret12_min=0.20,
    bear_filter='block',
    spy_ma_period=200,
    exit_mode='hybrid',
    stop_mode='pct12',
    atr_sizing=True,
    atr_risk_pct=0.04,
    atr_position_cap=0.40,
    trailing_stop='original',
    adx_threshold=0,
    min_hold_days=0,
    portfolio_heat_cap=0.10,
    entry_mode='universe_only',
    use_macd_rsi_exit=False,
    sector_max=None,
    corr_max=None,
    require_52w_high=False,
)


# ─────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────
def slice_price_data(price_data, start, end):
    """날짜 구간으로 자르되 지표 계산용 워밍업(420일) 포함."""
    start_dt = pd.Timestamp(start)
    warmup = start_dt - pd.Timedelta(days=420)
    return {t: df.loc[warmup:end].copy() for t, df in price_data.items()}


def run_segment(price_data_full, label, start, end, initial_capital=10_000):
    """특정 구간 백테스트 → (metrics dict, equity_curve, spy_curve, portfolio)."""
    pd_sliced = slice_price_data(price_data_full, start, end)
    CONFIG['max_positions'] = 4
    portfolio = PortfolioManager(initial_capital)
    run_dynamic_backtest(pd_sliced, portfolio, **PARAMS)

    ec_raw = pd.DataFrame(portfolio.equity_curve).set_index('date')
    ec_raw.index = pd.to_datetime(ec_raw.index)
    ec = ec_raw.loc[start:end]
    if len(ec) == 0:
        return None, None, None, portfolio

    start_eq = ec['equity'].iloc[0]
    final_eq  = ec['equity'].iloc[-1]
    years     = (ec.index[-1] - ec.index[0]).days / 365

    spy_df   = pd_sliced[BENCHMARK]['Close']
    spy_range = spy_df.loc[ec.index[0]:ec.index[-1]]
    spy_curve = spy_range / spy_range.iloc[0] * start_eq

    rolling_max = ec['equity'].cummax()
    dd          = (ec['equity'] - rolling_max) / rolling_max
    mdd         = dd.min() * 100

    daily_ret = ec['equity'].pct_change().dropna()
    sharpe    = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * np.sqrt(252))

    trades      = pd.DataFrame(portfolio.trade_log)
    sell_trades = trades[trades['action'].str.startswith('SELL')] if not trades.empty else pd.DataFrame()
    if not sell_trades.empty and 'pnl_pct' in sell_trades.columns:
        sell_trades = sell_trades.copy()
        if 'date' in sell_trades.columns:
            sell_trades['date'] = pd.to_datetime(sell_trades['date'])
            sell_trades = sell_trades[
                (sell_trades['date'] >= pd.Timestamp(start)) &
                (sell_trades['date'] <= pd.Timestamp(end))
            ]
        wins   = sell_trades[sell_trades['pnl_pct'] > 0]
        losses = sell_trades[sell_trades['pnl_pct'] <= 0]
        win_rate = len(wins) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
        avg_win  = wins['pnl_pct'].mean()   if len(wins)   > 0 else 0
        avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
        rr       = abs(avg_win / avg_loss)  if avg_loss != 0 else float('inf')
    else:
        win_rate = avg_win = avg_loss = rr = 0

    metrics = dict(
        label        = label,
        total_return = (final_eq / start_eq - 1) * 100,
        spy_return   = (spy_curve.iloc[-1] / start_eq - 1) * 100,
        cagr         = ((final_eq / start_eq) ** (1 / years) - 1) * 100,
        mdd          = mdd,
        sharpe       = sharpe,
        win_rate     = win_rate,
        avg_win      = avg_win,
        avg_loss     = avg_loss,
        rr_ratio     = rr,
        sell_trades  = len(sell_trades),
    )
    return metrics, ec, spy_curve, portfolio


# ─────────────────────────────────────────────
# 검증 1: MDD 상세 분석
# ─────────────────────────────────────────────
def analyze_mdd(ec, label=""):
    """낙폭 이벤트(>5%) 목록 추출 — 시작일·저점일·회복일·낙폭·지속일·회복일."""
    equity = ec['equity']
    rolling_max = equity.cummax()
    dd = (equity - rolling_max) / rolling_max

    events = []
    in_dd = False
    peak_date = None
    trough_date = None
    trough_val = 0.0
    threshold = -0.05  # 5% 이상 낙폭만 집계

    for date, val in dd.items():
        if not in_dd:
            if val <= threshold:
                in_dd = True
                peak_date = rolling_max.loc[:date].idxmax()
                trough_date = date
                trough_val = val
        else:
            if val < trough_val:
                trough_date = date
                trough_val = val
            if val >= -0.001:  # 회복 기준: 고점 -0.1% 이내
                recovery_date = date
                duration = (trough_date - peak_date).days
                recovery  = (recovery_date - trough_date).days
                events.append(dict(
                    peak      = peak_date.date(),
                    trough    = trough_date.date(),
                    recovery  = recovery_date.date(),
                    drawdown  = trough_val * 100,
                    duration  = duration,
                    recovery_days = recovery,
                ))
                in_dd = False
                peak_date = trough_date = None
                trough_val = 0.0

    # 마지막 낙폭이 회복 안 된 경우
    if in_dd and peak_date is not None:
        duration = (trough_date - peak_date).days
        events.append(dict(
            peak      = peak_date.date(),
            trough    = trough_date.date(),
            recovery  = None,
            drawdown  = trough_val * 100,
            duration  = duration,
            recovery_days = None,
        ))

    print(f"\n{'='*65}")
    print(f"  [검증1] MDD 상세 분석 — {label}")
    print(f"{'='*65}")
    if not events:
        print("  낙폭 이벤트 없음 (>5%)")
        return events

    df_ev = pd.DataFrame(events)
    print(f"  낙폭 이벤트 수 (>5%): {len(df_ev)}회")
    print(f"  평균 낙폭:            {df_ev['drawdown'].mean():.1f}%")
    print(f"  최대 낙폭:            {df_ev['drawdown'].min():.1f}%")
    print(f"  평균 낙폭 지속:       {df_ev['duration'].mean():.0f}일")
    recovered = df_ev[df_ev['recovery_days'].notna()]
    if len(recovered) > 0:
        print(f"  평균 회복 기간:       {recovered['recovery_days'].mean():.0f}일")
        print(f"  최장 회복 기간:       {recovered['recovery_days'].max():.0f}일")

    print(f"\n  {'피크':<12} {'저점':<12} {'회복':<12} {'낙폭':>7} {'지속':>6} {'회복일':>7}")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*7} {'-'*6} {'-'*7}")
    for _, r in df_ev.iterrows():
        rec = str(r['recovery']) if r['recovery'] else '미회복'
        rec_days = f"{r['recovery_days']:.0f}일" if r['recovery_days'] is not None else '  —'
        print(f"  {str(r['peak']):<12} {str(r['trough']):<12} {rec:<12} "
              f"{r['drawdown']:>6.1f}% {r['duration']:>5}일 {rec_days:>7}")

    return events


# ─────────────────────────────────────────────
# 검증 2: 롤링 워크포워드 (IS 3년 / OOS 1년, 5 윈도우)
# ─────────────────────────────────────────────
ROLLING_WINDOWS = [
    # (IS_start, IS_end, OOS_start, OOS_end)
    ('2019-01-01', '2021-12-31', '2022-01-01', '2022-12-31'),
    ('2020-01-01', '2022-12-31', '2023-01-01', '2023-12-31'),
    ('2021-01-01', '2023-12-31', '2024-01-01', '2024-12-31'),
    ('2022-01-01', '2024-12-31', '2025-01-01', '2025-12-31'),
    ('2023-01-01', '2025-12-31', '2026-01-01', '2026-12-31'),
]


def run_rolling_walkforward(price_data):
    print(f"\n{'='*65}")
    print("  [검증2] 롤링 워크포워드 (IS 3년 / OOS 1년, 5 윈도우)")
    print(f"{'='*65}")
    print(f"  {'윈도우':<8} {'IS 기간':<24} {'OOS 기간':<14} {'OOS수익':>8} {'SPY':>8} {'초과':>8} {'MDD':>8} {'샤프':>6}")
    print(f"  {'-'*8} {'-'*24} {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

    results = []
    for i, (is_s, is_e, oos_s, oos_e) in enumerate(ROLLING_WINDOWS, 1):
        label = f"W{i}"
        # OOS 종료가 미래면 현재까지만
        oos_e_clamped = min(oos_e, '2026-05-11')

        m_is,  _, _, _ = run_segment(price_data, f"{label}-IS",  is_s,  is_e,  10_000)
        m_oos, ec_oos, spy_oos, _ = run_segment(price_data, f"{label}-OOS", oos_s, oos_e_clamped, 10_000)

        if m_oos is None:
            print(f"  {label:<8} {is_s}~{is_e:<4}  {oos_s}~{oos_e_clamped}   데이터 부족")
            continue

        excess = m_oos['total_return'] - m_oos['spy_return']
        spy_beat = "✓" if excess > 0 else "✗"
        print(f"  {label:<8} {is_s}~{is_e}  {oos_s}~{oos_e_clamped}  "
              f"{m_oos['total_return']:>+7.1f}% {m_oos['spy_return']:>+7.1f}% "
              f"{excess:>+7.1f}%{spy_beat} {m_oos['mdd']:>7.1f}% {m_oos['sharpe']:>5.2f}")

        results.append(dict(
            window     = label,
            is_period  = f"{is_s}~{is_e}",
            oos_period = f"{oos_s}~{oos_e_clamped}",
            oos_return = m_oos['total_return'],
            spy_return = m_oos['spy_return'],
            excess     = excess,
            oos_mdd    = m_oos['mdd'],
            oos_sharpe = m_oos['sharpe'],
            spy_beat   = excess > 0,
        ))

    if results:
        df_r = pd.DataFrame(results)
        beats = df_r['spy_beat'].sum()
        print(f"\n  SPY 초과 달성: {beats}/{len(df_r)} 윈도우")
        print(f"  OOS 수익 평균: {df_r['oos_return'].mean():.1f}%  |  MDD 평균: {df_r['oos_mdd'].mean():.1f}%  |  샤프 평균: {df_r['oos_sharpe'].mean():.2f}")
        if beats == len(df_r):
            print("  → 전 윈도우 SPY 초과 — 시장 환경 무관하게 견고함 확인")
        elif beats >= len(df_r) * 0.6:
            print(f"  → 과반 윈도우 SPY 초과 — 부분적 견고성 확인 ({beats}/{len(df_r)})")
        else:
            print(f"  → 과반 미달 — 특정 시장 환경 의존성 있음 ({beats}/{len(df_r)})")

    return results


# ─────────────────────────────────────────────
# 검증 3: 포지션 분포 (실제 노출도)
# ─────────────────────────────────────────────
def analyze_positions(portfolio, ec, label=""):
    """equity_curve에 함께 기록된 포지션 수 또는 trade_log 기반 추정."""
    print(f"\n{'='*65}")
    print(f"  [검증3] 포지션 분포 — {label}")
    print(f"{'='*65}")

    # equity_curve에 n_positions 컬럼이 있으면 사용
    ec_df = pd.DataFrame(portfolio.equity_curve)
    if 'n_positions' in ec_df.columns:
        ec_df['date'] = pd.to_datetime(ec_df['date'])
        ec_df = ec_df.set_index('date')
        n = ec_df['n_positions']
        print(f"  평균 보유 포지션:   {n.mean():.2f}개")
        print(f"  중앙값:             {n.median():.0f}개")
        dist = n.value_counts().sort_index()
        total = len(n)
        print(f"\n  포지션 수  비중")
        for k, v in dist.items():
            bar = '█' * int(v / total * 30)
            print(f"  {k:>3}개     {v/total*100:>5.1f}%  {bar}")
        cash_pct = (n == 0).mean() * 100
        print(f"\n  전액 현금 비율:     {cash_pct:.1f}%")
    else:
        # trade_log 기반 간접 추정: 날짜별 open positions 재구성
        trades = pd.DataFrame(portfolio.trade_log)
        if trades.empty:
            print("  trade_log 없음")
            return
        trades['date'] = pd.to_datetime(trades['date'])
        buys  = trades[trades['action'].str.startswith('BUY')][['date', 'ticker']].copy()
        sells = trades[trades['action'].str.startswith('SELL')][['date', 'ticker']].copy()

        open_pos = {}
        daily_counts = {}
        all_dates = sorted(set(trades['date']))
        for d in all_dates:
            for _, row in buys[buys['date'] == d].iterrows():
                open_pos[row['ticker']] = d
            for _, row in sells[sells['date'] == d].iterrows():
                open_pos.pop(row['ticker'], None)
            daily_counts[d] = len(open_pos)

        counts = pd.Series(daily_counts)
        print(f"  (trade_log 기반 추정 — 거래일 기준)")
        print(f"  평균 보유 포지션:   {counts.mean():.2f}개")
        print(f"  중앙값:             {counts.median():.0f}개")
        dist = counts.value_counts().sort_index()
        total = len(counts)
        print(f"\n  포지션 수  비중")
        for k, v in dist.items():
            bar = '█' * int(v / total * 30)
            print(f"  {k:>3}개     {v/total*100:>5.1f}%  {bar}")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
if __name__ == '__main__':
    print("데이터 로드 중...")
    tickers = get_nasdaq100_tickers()
    price_data = load_data(tickers, period_years=8)

    # ── 검증 1+3: 전체 구간(8년) 백테스트로 MDD·포지션 분석 ──
    print("\n전체 구간(8년) 백테스트 실행 중...")
    m_full, ec_full, spy_full, port_full = run_segment(
        price_data, "전체(8년)", '2019-01-01', '2026-05-11', 10_000
    )
    if m_full:
        print(f"\n  전체 수익: {m_full['total_return']:+.1f}%  MDD: {m_full['mdd']:.1f}%  샤프: {m_full['sharpe']:.2f}")
        events = analyze_mdd(ec_full, "전체 8년 / 채택 파라미터")
        analyze_positions(port_full, ec_full, "전체 8년")

    # ── 검증 2: 롤링 워크포워드 ──
    rolling_results = run_rolling_walkforward(price_data)

    print("\n\n검증 완료.")
