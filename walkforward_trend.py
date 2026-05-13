"""
워크포워드 테스트 — 일반 추세추종 (R6-A 파라미터)
================================================
목적: 실험R6-A 채택 파라미터가 과적합인지 아닌지 검증.

구간 분리:
  In-Sample  (IS) : 2019-01-01 ~ 2022-12-31  (4년, 파라미터 선택 기간)
  Out-of-Sample(OOS): 2023-01-01 ~ 2026-05-09  (3.3년, 진짜 예측력 확인)

비교 대상:
  A. IS 구간 단독
  B. OOS 구간 단독 ($10,000 시작)
  C. IS 종료 자본을 이어받아 OOS 연속 실행 (실전 시뮬레이션)

해석 기준:
  - OOS 샤프 >= 0.8  : 전략 견고성 확인 (일반 추세추종은 슈퍼사이클보다 낮은 기준)
  - OOS MDD <= IS MDD × 1.5 : 낙폭 구조 유지
  - OOS SPY 초과 수익 양수
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
    CONFIG, BENCHMARK,
    load_data, PortfolioManager, get_nasdaq100_tickers,
)
from trend_backtest import run_dynamic_backtest

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ─────────────────────────────────────────────
# R6-A 채택 파라미터 (고정)
# ─────────────────────────────────────────────
BEST_PARAMS = dict(
    top_n=5,
    adx_min=20,
    momentum_mode='linreg',
    linreg_gate=0.15,
    linreg_window=90,
    ret12_min=0.20,
    bear_filter='block',
    spy_ma_period=50,
    exit_mode='hybrid',
    stop_mode='pct12',
    atr_sizing=True,
    atr_risk_pct=0.04,
    atr_position_cap=0.40,
    trailing_stop='original',
    adx_threshold=20,
    min_hold_days=3,
    portfolio_heat_cap=0.10,
    entry_mode='score',
    use_macd_rsi_exit=False,
    sector_max=None,
    corr_max=None,
    require_52w_high=True,
    w52_pct=0.060,
)

# ─────────────────────────────────────────────
# 단순화 파라미터 (과적합 검증용)
# 제거: portfolio_heat_cap / require_52w_high / min_hold_days / adx_threshold / entry_mode=score
# 핵심만 유지: linreg 유니버스 + bear=MA50 + ATR sizing + hybrid exit
# ─────────────────────────────────────────────
# 현재 채택 파라미터 (T-Simple + MA200 + heat_cap=0.10, 2026-05-12 확정)
SIMPLE_PARAMS = dict(
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

IS_START  = '2021-01-01'
IS_END    = '2023-06-30'
OOS_START = '2023-07-01'
OOS_END   = '2026-05-09'


def slice_price_data(price_data, start, end):
    """price_data 딕셔너리를 날짜 구간으로 자른다. 지표 계산용 워밍업 여유 포함."""
    sliced = {}
    start_dt = pd.Timestamp(start)
    warmup_start = start_dt - pd.Timedelta(days=420)
    for ticker, df in price_data.items():
        df_cut = df.loc[warmup_start:end].copy()
        sliced[ticker] = df_cut
    return sliced


def run_segment(price_data_full, label, start, end, initial_capital, verbose=True, params=None):
    """특정 구간 백테스트 실행 → metrics, ec, spy_curve, portfolio 반환."""
    if params is None:
        params = BEST_PARAMS
    pd_sliced = slice_price_data(price_data_full, start, end)

    CONFIG['max_positions'] = 4
    portfolio = PortfolioManager(initial_capital)
    run_dynamic_backtest(pd_sliced, portfolio, **params)

    # equity_curve를 실제 구간(start ~ end)으로 재필터
    ec_raw = pd.DataFrame(portfolio.equity_curve).set_index('date')
    ec_raw.index = pd.to_datetime(ec_raw.index)
    ec = ec_raw.loc[start:end]

    if len(ec) == 0:
        print(f"[경고] {label}: equity_curve 비어있음 - 구간 확인 필요")
        return None, None, None, portfolio

    # 구간 시작 자본 기준으로 수익률 계산 (pre-IS 거래 영향 제거)
    start_equity = ec['equity'].iloc[0]
    final_equity = ec['equity'].iloc[-1]

    spy_df = pd_sliced[BENCHMARK]['Close']
    spy_in_range = spy_df.loc[ec.index[0]:ec.index[-1]]
    spy_curve = spy_in_range / spy_in_range.iloc[0] * start_equity

    years = (ec.index[-1] - ec.index[0]).days / 365
    total_return = (final_equity / start_equity - 1) * 100
    cagr = ((final_equity / start_equity) ** (1 / years) - 1) * 100

    rolling_max = ec['equity'].cummax()
    drawdown = (ec['equity'] - rolling_max) / rolling_max
    mdd = drawdown.min() * 100

    daily_ret = ec['equity'].pct_change().dropna()
    sharpe = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * np.sqrt(252))

    spy_return = (spy_curve.iloc[-1] / start_equity - 1) * 100

    trades = pd.DataFrame(portfolio.trade_log)
    sell_trades = trades[trades['action'].str.startswith('SELL')] if not trades.empty else pd.DataFrame()
    if not sell_trades.empty and 'pnl_pct' in sell_trades.columns:
        # 구간 내 청산 거래만 필터
        sell_trades = sell_trades.copy()
        if 'date' in sell_trades.columns:
            sell_trades['date'] = pd.to_datetime(sell_trades['date'])
            sell_trades = sell_trades[
                (sell_trades['date'] >= pd.Timestamp(start)) &
                (sell_trades['date'] <= pd.Timestamp(end))
            ]
        win_trades  = sell_trades[sell_trades['pnl_pct'] > 0]
        loss_trades = sell_trades[sell_trades['pnl_pct'] <= 0]
        win_rate  = len(win_trades) / len(sell_trades) * 100 if len(sell_trades) > 0 else 0
        avg_win   = win_trades['pnl_pct'].mean()  if len(win_trades)  > 0 else 0
        avg_loss  = loss_trades['pnl_pct'].mean() if len(loss_trades) > 0 else 0
        rr_ratio  = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    else:
        win_rate = avg_win = avg_loss = rr_ratio = 0

    metrics = {
        "label":        label,
        "total_return": total_return,
        "spy_return":   spy_return,
        "cagr":         cagr,
        "mdd":          mdd,
        "sharpe":       sharpe,
        "win_rate":     win_rate,
        "avg_win":      avg_win,
        "avg_loss":     avg_loss,
        "rr_ratio":     rr_ratio,
        "sell_trades":  len(sell_trades),
        "years":        years,
        "start_equity": start_equity,
        "final_equity": final_equity,
    }

    if verbose:
        print(f"\n{'='*55}")
        print(f"  [{label}] {start} ~ {end}")
        print(f"{'='*55}")
        print(f"  기간:               {years:.1f}년")
        print(f"  시작 자본:          ${start_equity:>10,.0f}")
        print(f"  최종 자본:          ${final_equity:>10,.0f}")
        print(f"  총 수익률:          {total_return:>8.1f}%")
        print(f"  SPY Buy&Hold:       {spy_return:>8.1f}%")
        print(f"  초과 수익:          {total_return - spy_return:>+8.1f}%p")
        print(f"  CAGR (연평균):      {cagr:>8.1f}%")
        print(f"  MDD (최대 낙폭):    {mdd:>8.1f}%")
        print(f"  샤프 비율:          {sharpe:>8.2f}")
        print(f"  승률:               {win_rate:>8.1f}%")
        print(f"  평균 수익 (승):     {avg_win:>+8.1f}%")
        print(f"  평균 손실 (패):     {avg_loss:>+8.1f}%")
        print(f"  손익비:             {rr_ratio:>8.2f}")
        print(f"  청산 거래 횟수:     {len(sell_trades):>8}건")
        print(f"{'='*55}")

    return metrics, ec, spy_curve, portfolio


def run_oos_chained(price_data_full, is_final_equity, verbose=True):
    """IS 종료 자본을 이어받아 OOS 연속 실행 (실전 시뮬레이션)."""
    label = f"OOS-연속 (IS 자본 이어받기, ${is_final_equity:,.0f} 시작)"
    return run_segment(price_data_full, label, OOS_START, OOS_END,
                       initial_capital=is_final_equity, verbose=verbose)


def print_comparison_table(is_m, oos_m, oos_chain_m):
    """IS vs OOS 비교표 출력."""
    print("\n" + "="*75)
    print("  워크포워드 비교 요약 -- 일반 추세추종 R6-A")
    print("="*75)
    print(f"  {'지표':<20} {'IS (4년)':>12} {'OOS 독립 (3.3년)':>16} {'OOS 연속':>12}  판정")
    print("  " + "-"*72)

    rows = [
        ("수익률",    "total_return",  "%",   None,  True),
        ("SPY 초과",  None,            "%p",  None,  True),
        ("CAGR",      "cagr",          "%",   None,  True),
        ("MDD",       "mdd",           "%",   None,  False),
        ("샤프",      "sharpe",        "",    0.8,   True),
        ("승률",      "win_rate",      "%",   None,  True),
        ("손익비",    "rr_ratio",      "",    None,  True),
        ("청산 거래", "sell_trades",   "건",  None,  None),
    ]

    for name, key, unit, threshold, higher_good in rows:
        if key is None:  # SPY 초과
            is_val  = is_m["total_return"]  - is_m["spy_return"]
            oos_val = oos_m["total_return"] - oos_m["spy_return"]
            oos_c   = oos_chain_m["total_return"] - oos_chain_m["spy_return"]
            ok = "OK" if oos_val > 0 else "주의"
        else:
            is_val  = is_m[key]
            oos_val = oos_m[key]
            oos_c   = oos_chain_m[key]

            if higher_good is True:
                ok = "OK" if oos_val >= is_val * 0.6 else "주의"
            elif higher_good is False:
                ok = "OK" if abs(oos_val) <= abs(is_val) * 1.5 else "주의"
            else:
                ok = "-"

        if threshold is not None and key:
            ok = f"{ok} (기준 {threshold})"

        if isinstance(oos_c, (int, float)):
            print(f"  {name:<20} {is_val:>+10.1f}{unit}  {oos_val:>+14.1f}{unit}  {oos_c:>+10.1f}{unit}  {ok}")
        else:
            print(f"  {name:<20} {is_val:>+10.1f}{unit}  {oos_val:>+14.1f}{unit}  {'':>12}  {ok}")

    print("="*75)

    # 핵심 판정
    sharpe_ok = oos_m["sharpe"] >= 0.8
    mdd_ok    = abs(oos_m["mdd"]) <= abs(is_m["mdd"]) * 1.5
    excess_ok = (oos_m["total_return"] - oos_m["spy_return"]) > 0

    print(f"\n  핵심 판정")
    print(f"  {'OOS 샤프 >= 0.8':<30} {'PASS' if sharpe_ok else 'FAIL':>6}  ({oos_m['sharpe']:.2f})")
    print(f"  {'OOS MDD <= IS MDD x 1.5':<30} {'PASS' if mdd_ok else 'FAIL':>6}  ({oos_m['mdd']:.1f}% vs {is_m['mdd']*1.5:.1f}%)")
    print(f"  {'OOS SPY 초과 수익 양수':<30} {'PASS' if excess_ok else 'FAIL':>6}  ({oos_m['total_return']-oos_m['spy_return']:+.1f}%p)")

    if sharpe_ok and mdd_ok and excess_ok:
        print("\n  [PASS] 최종 판정: 전략 견고성 확인 - 과적합 아님")
    elif sum([sharpe_ok, mdd_ok, excess_ok]) >= 2:
        print("\n  [WARN] 최종 판정: 부분 견고성 - OOS 성과 소폭 열화, 실전 주의")
    else:
        print("\n  [FAIL] 최종 판정: 과적합 의심 - 파라미터 재검토 필요")
    print("="*75)


def plot_walkforward(is_ec, is_spy, oos_ec, oos_spy, oos_chain_ec, oos_chain_spy,
                     is_m, oos_m, oos_chain_m):
    fig, axes = plt.subplots(2, 2, figsize=(18, 11))
    fig.suptitle("워크포워드 테스트 - 일반 추세추종 (R6-A 파라미터)", fontsize=13, fontweight='bold')

    # 차트 1: IS 자산 곡선
    ax = axes[0, 0]
    ax.plot(is_ec.index, is_ec['equity'], color='steelblue', lw=1.8, label='전략')
    ax.plot(is_spy.index, is_spy.values, color='gray', lw=1.2, ls='--', label='SPY B&H')
    ax.axvspan(pd.Timestamp(IS_START), pd.Timestamp(IS_END), alpha=0.08, color='steelblue')
    ax.set_title(
        f"In-Sample ({IS_START[:7]} ~ {IS_END[:7]})\n"
        f"수익률 {is_m['total_return']:+.1f}%  샤프 {is_m['sharpe']:.2f}  MDD {is_m['mdd']:.1f}%"
    )
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 차트 2: OOS 자산 곡선 (독립)
    ax = axes[0, 1]
    ax.plot(oos_ec.index, oos_ec['equity'], color='darkorange', lw=1.8, label='전략 (OOS 독립)')
    ax.plot(oos_spy.index, oos_spy.values, color='gray', lw=1.2, ls='--', label='SPY B&H')
    ax.axvspan(pd.Timestamp(OOS_START), pd.Timestamp(OOS_END), alpha=0.08, color='orange')
    ax.set_title(
        f"Out-of-Sample 독립 ({OOS_START[:7]} ~ {OOS_END[:7]})\n"
        f"수익률 {oos_m['total_return']:+.1f}%  샤프 {oos_m['sharpe']:.2f}  MDD {oos_m['mdd']:.1f}%"
    )
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 차트 3: OOS 연속 (IS 자본 이어받기)
    ax = axes[1, 0]
    if oos_chain_ec is not None:
        ax.plot(oos_chain_ec.index, oos_chain_ec['equity'],
                color='seagreen', lw=1.8, label='전략 (IS->OOS 연속)')
        ax.plot(oos_chain_spy.index, oos_chain_spy.values,
                color='gray', lw=1.2, ls='--', label='SPY B&H (비율 환산)')
        ax.set_title(
            f"OOS 연속 (IS 자본 ${is_m['final_equity']:,.0f} 이어받기)\n"
            f"수익률 {oos_chain_m['total_return']:+.1f}%  샤프 {oos_chain_m['sharpe']:.2f}  MDD {oos_chain_m['mdd']:.1f}%"
        )
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 차트 4: IS vs OOS 핵심 지표 비교 막대
    ax = axes[1, 1]
    labels_bar = ['수익률(%)', 'CAGR(%)', '샤프', '손익비', '승률(%)', '|MDD|(%)']
    is_vals  = [is_m['total_return'],  is_m['cagr'],  is_m['sharpe'],
                is_m['rr_ratio'],      is_m['win_rate'],  abs(is_m['mdd'])]
    oos_vals = [oos_m['total_return'], oos_m['cagr'], oos_m['sharpe'],
                oos_m['rr_ratio'],     oos_m['win_rate'], abs(oos_m['mdd'])]

    x = np.arange(len(labels_bar))
    w = 0.35
    bars_is  = ax.bar(x - w/2, is_vals,  w, label='IS',  color='steelblue',  alpha=0.8)
    bars_oos = ax.bar(x + w/2, oos_vals, w, label='OOS', color='darkorange', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels_bar, fontsize=9)
    ax.set_title("IS vs OOS 핵심 지표 비교")
    ax.legend(fontsize=9)
    ax.grid(True, axis='y', alpha=0.3)

    for bar in bars_is:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=7)
    for bar in bars_oos:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{bar.get_height():.1f}', ha='center', va='bottom', fontsize=7, color='darkorange')

    plt.tight_layout()
    plt.show()


def load_vix_data(period_years=8):
    """VIX 데이터 로드 (^VIX 티커)."""
    import yfinance as yf
    from datetime import datetime, timedelta
    end = datetime.today()
    start = end - timedelta(days=period_years * 365 + 60)
    vix_csv = os.path.join("data", "VIX.csv")
    if os.path.exists(vix_csv):
        df = pd.read_csv(vix_csv, index_col=0, parse_dates=True)
        if len(df) >= period_years * 240:
            print("  VIX 캐시 로드 완료")
            return df
    print("  VIX 다운로드 중...")
    df = yf.download("^VIX", start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs("^VIX", axis=1, level=1)
    df.to_csv(vix_csv)
    return df


def _run_one_variant(price_data, label, overrides, start, end, vix_df=None, base_params=None):
    """단일 옵션 구간 실행 -> 핵심 지표 반환."""
    if base_params is None:
        base_params = BEST_PARAMS
    params = {**base_params, **overrides}
    if vix_df is not None:
        params['vix_data'] = vix_df.loc[:end]
    pd_sliced = slice_price_data(price_data, start, end)
    CONFIG['max_positions'] = params.pop('max_positions', 4)
    port = PortfolioManager(CONFIG['initial_capital'])
    run_dynamic_backtest(pd_sliced, port, **params)

    ec_raw = pd.DataFrame(port.equity_curve).set_index('date')
    ec_raw.index = pd.to_datetime(ec_raw.index)
    ec = ec_raw.loc[start:end]
    if len(ec) == 0:
        return None

    start_eq = ec['equity'].iloc[0]
    final_eq  = ec['equity'].iloc[-1]
    spy_df = pd_sliced[bt.BENCHMARK]['Close']
    spy_r  = (spy_df.loc[ec.index[-1]] / spy_df.loc[ec.index[0]] - 1) * 100
    total_r = (final_eq / start_eq - 1) * 100
    mdd = ((ec['equity'] - ec['equity'].cummax()) / ec['equity'].cummax()).min() * 100
    dr  = ec['equity'].pct_change().dropna()
    sharpe = (dr.mean() * 252 - 0.04) / (dr.std() * np.sqrt(252))
    spy_curve = pd_sliced[bt.BENCHMARK]['Close']
    spy_curve = spy_curve.loc[ec.index[0]:ec.index[-1]]
    spy_curve = spy_curve / spy_curve.iloc[0] * start_eq

    return {"label": label, "total_r": total_r, "spy_excess": total_r - spy_r,
            "mdd": mdd, "sharpe": sharpe, "ec": ec, "spy_curve": spy_curve, "start_eq": start_eq}


def run_bear_filter_comparison(price_data, vix_df):
    """
    IS + OOS 구간 모두에서 bear filter 옵션 비교.
    목적: SPY 초과수익 & MDD 균형을 잡는 최적 bear filter 탐색.
    """
    variants = [
        ("R6-A (MA50 block)",   dict(bear_filter='block',     spy_ma_period=50,  vix_threshold=30)),
        ("bear=none",           dict(bear_filter='none',      spy_ma_period=50,  vix_threshold=30)),
        ("MA200 block",         dict(bear_filter='block',     spy_ma_period=200, vix_threshold=30)),
        ("VIX>30 block",        dict(bear_filter='vix',       spy_ma_period=50,  vix_threshold=30)),
        ("VIX>25 block",        dict(bear_filter='vix',       spy_ma_period=50,  vix_threshold=25)),
        ("MA50 OR VIX>30",      dict(bear_filter='ma_or_vix', spy_ma_period=50,  vix_threshold=30)),
        ("MA50 5일확인",         dict(bear_filter='block',     spy_ma_period=50,  vix_threshold=30, ma_confirm_days=5)),
        ("MA50 10일확인",        dict(bear_filter='block',     spy_ma_period=50,  vix_threshold=30, ma_confirm_days=10)),
    ]

    for segment, start, end in [("IS (2019~2022)", IS_START, IS_END),
                                  ("OOS (2023~2026)", OOS_START, OOS_END)]:
        print("\n" + "="*72)
        print(f"  Bear Filter 비교 [{segment}]")
        print("="*72)
        print(f"  {'옵션':<24} {'수익률':>8} {'SPY초과':>9} {'MDD':>8} {'샤프':>7}")
        print("  " + "-"*65)
        for label, overrides in variants:
            r = _run_one_variant(price_data, label, overrides, start, end, vix_df)
            if r:
                print(f"  {label:<24} {r['total_r']:>+7.1f}%  {r['spy_excess']:>+8.1f}%p"
                      f"  {r['mdd']:>7.1f}%  {r['sharpe']:>6.2f}")
        print("="*72)


def print_simple_vs_r6a(r6a_is, r6a_oos, sim_is, sim_oos):
    """단순화 vs R6-A 워크포워드 비교표."""
    print("\n" + "="*80)
    print("  단순화 vs R6-A 워크포워드 비교")
    print("="*80)
    print(f"  {'지표':<18} {'R6-A IS':>10} {'R6-A OOS':>10} {'단순화 IS':>10} {'단순화 OOS':>11}")
    print("  " + "-"*75)

    def row(name, key, is_excess=False):
        if is_excess:
            v1 = r6a_is['total_return']  - r6a_is['spy_return']
            v2 = r6a_oos['total_return'] - r6a_oos['spy_return']
            v3 = sim_is['total_return']  - sim_is['spy_return']
            v4 = sim_oos['total_return'] - sim_oos['spy_return']
        else:
            v1, v2, v3, v4 = r6a_is[key], r6a_oos[key], sim_is[key], sim_oos[key]
        print(f"  {name:<18} {v1:>+9.1f}  {v2:>+9.1f}  {v3:>+9.1f}  {v4:>+10.1f}")

    row("수익률(%)",   "total_return")
    row("SPY 초과(%p)", None, is_excess=True)
    row("CAGR(%)",     "cagr")
    row("MDD(%)",      "mdd")
    row("샤프",        "sharpe")
    row("승률(%)",     "win_rate")
    print("="*80)

    # OOS SPY 초과 기준 판정
    r6a_excess  = r6a_oos['total_return'] - r6a_oos['spy_return']
    sim_excess   = sim_oos['total_return'] - sim_oos['spy_return']
    print(f"\n  OOS SPY 초과: R6-A {r6a_excess:+.1f}%p  /  단순화 {sim_excess:+.1f}%p")
    if sim_excess > r6a_excess:
        print("  -> 단순화가 OOS에서 더 좋음 (과적합 레이어 제거 효과 확인)")
    else:
        print("  -> R6-A 추가 레이어가 OOS에서도 유효 (과적합 아님)")
    print("="*80)


def plot_variant_comparison(oos_results, title="OOS 에쿼티 커브 비교"):
    """OOS 구간 에쿼티 커브 + 드로우다운 비교 차트."""
    colors = ['#888888', 'steelblue', 'darkorange', 'seagreen', 'crimson', 'purple', 'brown']
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [3, 1]})
    fig.suptitle(title, fontsize=13, fontweight='bold')

    ax1 = axes[0]
    spy_plotted = False
    for i, r in enumerate(oos_results):
        if r is None:
            continue
        ec = r['ec']
        norm = ec['equity'] / r['start_eq'] * 100
        ax1.plot(ec.index, norm, color=colors[i % len(colors)], lw=1.8, label=r['label'])
        if not spy_plotted:
            spy_norm = r['spy_curve'] / r['start_eq'] * 100
            ax1.plot(spy_norm.index, spy_norm.values, color='gray', lw=1.2, ls='--', label='SPY B&H')
            spy_plotted = True

    ax1.set_ylabel("수익률 (시작=100)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    ax2 = axes[1]
    for i, r in enumerate(oos_results):
        if r is None:
            continue
        ec = r['ec']
        dd = (ec['equity'] - ec['equity'].cummax()) / ec['equity'].cummax() * 100
        ax2.plot(dd.index, dd.values, color=colors[i % len(colors)], lw=1.2, label=r['label'])

    ax2.set_ylabel("드로우다운 (%)")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax2.grid(True, alpha=0.3)
    ax2.axhline(0, color='black', lw=0.8)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    print("="*60)
    print("  AK 시리즈: 피라미딩 워크포워드 검증")
    print("  IS : 2021-01-01 ~ 2023-06-30")
    print("  OOS: 2023-07-01 ~ 2026-05-09")
    print("="*60)

    NDX100 = get_nasdaq100_tickers()
    CONFIG['max_positions'] = 4
    price_data = load_data(NDX100, period_years=8)

    # 채택 파라미터 (rebalance_days=5 포함)
    BASE = {**SIMPLE_PARAMS, "rebalance_days": 5}

    # AK 시리즈: 피라미딩 방식 비교
    # AK1: ATR 기반 (진입가 + 1ATR 상승 시 추가)
    # AK2: linreg score 기반 (진입 score 대비 20% 상승 시 추가)
    # AK3: ATR AND score 둘 다 충족 시 추가
    variants = [
        ("채택 (피라미딩없음)",      dict(pyramid_mode=None)),
        ("AK1: ATR (x1.0)",         dict(pyramid_mode='atr',   pyramid_atr_mult=1.0, pyramid_max=2)),
        ("AK2: score (+20%)",        dict(pyramid_mode='score', pyramid_score_pct=0.20, pyramid_max=2)),
        ("AK3: ATR AND score",       dict(pyramid_mode='and',   pyramid_atr_mult=1.0, pyramid_score_pct=0.20, pyramid_max=2)),
    ]

    for seg_label, start, end in [("IS (2021~2023H1)", IS_START, IS_END),
                                   ("OOS (2023H2~2026)", OOS_START, OOS_END)]:
        print(f"\n{'='*75}")
        print(f"  AK 시리즈 - {seg_label}")
        print(f"{'='*75}")
        print(f"  {'변형':<24} {'수익':>8} {'SPY초과':>10} {'MDD':>8} {'샤프':>7}  SPY")
        print("  " + "-"*72)
        for label, overrides in variants:
            r = _run_one_variant(price_data, label, overrides, start, end, base_params=BASE)
            if r:
                spy_r = (r['spy_curve'].iloc[-1] / r['start_eq'] - 1) * 100
                print(f"  {label:<24} {r['total_r']:>+7.1f}%  {r['spy_excess']:>+9.1f}%p"
                      f"  {r['mdd']:>7.1f}%  {r['sharpe']:>6.2f}  {spy_r:>+7.1f}%")
        print("  " + "-"*72)

    # OOS 에쿼티 커브 시각화
    oos_results = []
    for label, overrides in variants:
        r = _run_one_variant(price_data, label, overrides, OOS_START, OOS_END, base_params=BASE)
        if r:
            oos_results.append(r)

    plot_variant_comparison(oos_results, title="AK 시리즈 — OOS 에쿼티 커브 비교 (피라미딩)")
