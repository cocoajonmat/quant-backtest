"""
AM 시리즈: ADX 임계값 스윕
===========================
목적: 유니버스 선발 시 adx_min 값(현재 20)을 스윕해 최적값 확인.
      A~N 시리즈 전체를 통틀어 한 번도 검증되지 않은 파라미터.

스윕: adx_min = 0(없음) / 10 / 15 / 20(기준) / 25 / 30
구간: IS 2021-01-01 ~ 2023-06-30 / OOS 2023-07-01 ~ 2026-05-09
"""

import sys, os
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

IS_START  = '2021-01-01'
IS_END    = '2023-06-30'
OOS_START = '2023-07-01'
OOS_END   = '2026-05-09'

BASE = dict(
    top_n=5,
    momentum_mode='linreg', linreg_gate=0.15, linreg_window=90,
    ret12_min=0.20,
    bear_filter='block', spy_ma_period=200,
    exit_mode='hybrid', stop_mode='pct12',
    atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
    trailing_stop='original', adx_threshold=0, min_hold_days=0,
    portfolio_heat_cap=0.10, entry_mode='universe_only',
    use_macd_rsi_exit=False, require_52w_high=False,
    rebalance_days=5,
)

SWEEP = [
    ('AM0 adx=없음',  0),
    ('AM1 adx=10',   10),
    ('AM2 adx=15',   15),
    ('AM3 adx=20(기준)', 20),
    ('AM4 adx=25',   25),
    ('AM5 adx=30',   30),
]


def slice_data(price_data, start, end):
    warmup = pd.Timestamp(start) - pd.Timedelta(days=420)
    return {t: df.loc[warmup:end].copy() for t, df in price_data.items()}


def run_segment(price_data_full, label, start, end, initial_capital, adx_min):
    pd_s = slice_data(price_data_full, start, end)
    CONFIG['max_positions'] = 4
    p = PortfolioManager(initial_capital)
    run_dynamic_backtest(pd_s, p, **BASE, adx_min=adx_min)

    ec_raw = pd.DataFrame(p.equity_curve).set_index('date')
    ec_raw.index = pd.to_datetime(ec_raw.index)
    ec = ec_raw.loc[start:end]
    if len(ec) == 0:
        return None, None, None

    s0 = ec['equity'].iloc[0]
    sf = ec['equity'].iloc[-1]
    spy_s = pd_s[BENCHMARK]['Close'].loc[ec.index[0]:ec.index[-1]]
    spy_c = spy_s / spy_s.iloc[0] * s0

    years = (ec.index[-1] - ec.index[0]).days / 365
    ret = (sf / s0 - 1) * 100
    cagr = ((sf / s0) ** (1 / years) - 1) * 100
    mdd = ((ec['equity'] - ec['equity'].cummax()) / ec['equity'].cummax()).min() * 100
    dr = ec['equity'].pct_change().dropna()
    sharpe = (dr.mean() * 252 - 0.04) / (dr.std() * np.sqrt(252))
    spy_ret = (spy_c.iloc[-1] / s0 - 1) * 100

    trades = pd.DataFrame(p.trade_log)
    sells = trades[trades['action'].str.startswith('SELL')] if not trades.empty else pd.DataFrame()
    if not sells.empty and 'date' in sells.columns:
        sells = sells.copy()
        sells['date'] = pd.to_datetime(sells['date'])
        sells = sells[(sells['date'] >= pd.Timestamp(start)) & (sells['date'] <= pd.Timestamp(end))]
    n_trades = len(sells)

    m = dict(label=label, ret=ret, spy_ret=spy_ret, excess=ret - spy_ret,
             cagr=cagr, mdd=mdd, sharpe=sharpe, n_trades=n_trades)
    return m, ec, spy_c


def print_table(rows, title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    print(f"  {'전략':<22} {'수익':>8} {'SPY초과':>9} {'MDD':>8} {'샤프':>7} {'거래수':>7}")
    print(f"  {'-'*70}")
    for r in rows:
        if r is None:
            continue
        star = ' ◀기준' if '기준' in r['label'] else ''
        print(f"  {r['label']:<22} {r['ret']:>+7.1f}%  {r['excess']:>+7.1f}%p  "
              f"{r['mdd']:>+7.1f}%  {r['sharpe']:>6.2f}  {r['n_trades']:>6}건{star}")
    print(f"{'='*80}")


def plot_results(is_rows, oos_rows, is_ecs, oos_ecs, spy_is, spy_oos):
    n = len(SWEEP)
    fig, axes = plt.subplots(2, n, figsize=(4 * n, 9))
    fig.suptitle("AM 시리즈: ADX 임계값 스윕 (IS / OOS)", fontsize=13, fontweight='bold')

    colors = ['#e41a1c','#ff7f00','#4daf4a','#377eb8','#984ea3','#a65628']

    for i, ((label, adx), color) in enumerate(zip(SWEEP, colors)):
        # IS
        ax = axes[0, i]
        is_r = is_rows[i]
        is_ec = is_ecs[i]
        if is_ec is not None:
            ax.plot(is_ec.index, is_ec['equity'], color=color, lw=1.5)
            ax.plot(spy_is.index, spy_is.values, color='gray', lw=1, ls='--', alpha=0.7)
        ax.set_title(f"{label}\nIS: {is_r['ret']:+.1f}% / 샤프 {is_r['sharpe']:.2f}", fontsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1e3:.0f}k"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', fontsize=7)
        ax.grid(True, alpha=0.3)
        if i == 0:
            ax.set_ylabel('IS', fontsize=9)

        # OOS
        ax = axes[1, i]
        oos_r = oos_rows[i]
        oos_ec = oos_ecs[i]
        if oos_ec is not None:
            ax.plot(oos_ec.index, oos_ec['equity'], color=color, lw=1.5)
            ax.plot(spy_oos.index, spy_oos.values, color='gray', lw=1, ls='--', alpha=0.7)
        ax.set_title(f"OOS: {oos_r['ret']:+.1f}% / 샤프 {oos_r['sharpe']:.2f}\nMDD {oos_r['mdd']:.1f}%", fontsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1e3:.0f}k"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', fontsize=7)
        ax.grid(True, alpha=0.3)
        if i == 0:
            ax.set_ylabel('OOS', fontsize=9)

    plt.tight_layout()
    plt.savefig('am_adx_sweep.png', dpi=130, bbox_inches='tight')
    print("\n[차트 저장] am_adx_sweep.png")
    plt.show()


if __name__ == '__main__':
    NDX100 = get_nasdaq100_tickers()
    CONFIG['max_positions'] = 4
    price_data = load_data(NDX100, period_years=8)

    is_rows, oos_rows = [], []
    is_ecs, oos_ecs = [], []
    spy_is_ref = spy_oos_ref = None

    for i, (label, adx_val) in enumerate(SWEEP):
        print(f"\n[{i+1}/{len(SWEEP)}] {label} 실행 중...")

        is_m, is_ec, is_spy = run_segment(price_data, label, IS_START, IS_END, 10000, adx_val)
        oos_m, oos_ec, oos_spy = run_segment(price_data, label, OOS_START, OOS_END, 10000, adx_val)

        is_rows.append(is_m)
        oos_rows.append(oos_m)
        is_ecs.append(is_ec)
        oos_ecs.append(oos_ec)

        if spy_is_ref is None and is_spy is not None:
            spy_is_ref = is_spy
        if spy_oos_ref is None and oos_spy is not None:
            spy_oos_ref = oos_spy

    print_table(is_rows,  "IS  결과 (2021-01 ~ 2023-06)")
    print_table(oos_rows, "OOS 결과 (2023-07 ~ 2026-05)")

    print("\n[IS vs OOS 병렬 비교]")
    print(f"  {'전략':<22} {'IS수익':>8} {'IS샤프':>7} | {'OOS수익':>8} {'OOS초과':>9} {'OOS MDD':>8} {'OOS샤프':>7}")
    print(f"  {'-'*80}")
    for ir, or_ in zip(is_rows, oos_rows):
        star = ' ◀기준' if '기준' in ir['label'] else ''
        print(f"  {ir['label']:<22} {ir['ret']:>+7.1f}%  {ir['sharpe']:>6.2f} | "
              f"{or_['ret']:>+7.1f}%  {or_['excess']:>+7.1f}%p  {or_['mdd']:>+7.1f}%  {or_['sharpe']:>6.2f}{star}")

    plot_results(is_rows, oos_rows, is_ecs, oos_ecs, spy_is_ref, spy_oos_ref)
