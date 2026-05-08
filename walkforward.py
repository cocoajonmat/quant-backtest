"""
워크포워드 테스트 (Walk-Forward Analysis)
==========================================
목적: 실험21 채택 파라미터가 과적합인지 아닌지 검증.

구간 분리:
  In-Sample  (IS)  : 2021-05-01 ~ 2023-12-31  (약 2.5년, 파라미터 선택 기간)
  Out-of-Sample (OOS): 2024-01-01 ~ 2026-05-07  (약 2.3년, 진짜 예측력 확인)

비교 대상:
  A. IS 전체 (기존 실험21 재현)
  B. IS 구간만 단독 실행
  C. OOS 구간만 단독 실행
  D. IS 종료 시 자본을 이어받아 OOS 연속 실행 (실전 시뮬레이션)

해석 기준:
  - OOS 샤프 >= 1.0  : 전략 견고성 확인
  - OOS MDD <= IS MDD × 1.5 : 낙폭 구조 유지
  - OOS 승률/손익비가 IS 대비 크게 꺾이지 않으면 과적합 아님
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
    LEGACY_TICKERS, CONFIG, BENCHMARK,
    load_data, run_backtest, compute_metrics, print_metrics,
    PortfolioManager,
)

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ─────────────────────────────────────────────
# 실험21 채택 파라미터 (고정)
# ─────────────────────────────────────────────
BEST_PARAMS = dict(
    bear_filter='block',
    stop_mode='pct12',
    exit_mode='hybrid',
    atr_sizing=True,
    atr_risk_pct=0.04,
    atr_position_cap=0.40,
    trailing_stop='original',
    spy_ma_period=200,
    adx_threshold=20,
    min_hold_days=3,
)

IS_START  = '2021-05-01'
IS_END    = '2023-12-31'
OOS_START = '2024-01-01'
OOS_END   = '2026-05-07'  # 데이터 가용 시점


def slice_price_data(price_data, start, end):
    """price_data 딕셔너리의 모든 DataFrame을 날짜 구간으로 자른다."""
    sliced = {}
    for ticker, df in price_data.items():
        # 워밍업(지표 계산용) 여유 포함: start 기준 300 거래일 이전부터
        df_cut = df.loc[:end].copy()
        # start 전 최소 300일 확보 (MA200·ATR 계산)
        start_dt = pd.Timestamp(start)
        warmup_start = start_dt - pd.Timedelta(days=420)  # 캘린더 기준 여유
        df_cut = df.loc[warmup_start:end].copy()
        sliced[ticker] = df_cut
    return sliced


def run_segment(price_data_full, label, start, end, initial_capital, verbose=True):
    """특정 구간의 price_data를 잘라 백테스트 실행 후 metrics, ec, spy_curve 반환."""
    pd_sliced = slice_price_data(price_data_full, start, end)

    # run_backtest 내부에서 start_date = benchmark.index[252] 으로 자동 설정됨
    # → 워밍업 포함해서 잘랐으므로 실제 거래는 start 부근부터 시작
    portfolio = PortfolioManager(initial_capital)
    run_backtest(pd_sliced, portfolio, **BEST_PARAMS)

    # equity_curve를 실제 구간(start ~ end)으로 재필터
    ec_raw = pd.DataFrame(portfolio.equity_curve).set_index('date')
    ec_raw.index = pd.to_datetime(ec_raw.index)
    ec = ec_raw.loc[start:end]

    if len(ec) == 0:
        print(f"[경고] {label}: equity_curve 비어있음 - 구간 확인 필요")
        return None, None, None, portfolio

    # metrics 재계산 (구간 ec 기준)
    spy_df = pd_sliced[BENCHMARK]['Close']
    spy_in_range = spy_df.loc[ec.index[0]:ec.index[-1]]
    spy_curve = spy_in_range / spy_in_range.iloc[0] * initial_capital

    years = (ec.index[-1] - ec.index[0]).days / 365
    final_equity = ec['equity'].iloc[-1]
    total_return = (final_equity / initial_capital - 1) * 100
    cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

    rolling_max = ec['equity'].cummax()
    drawdown = (ec['equity'] - rolling_max) / rolling_max
    mdd = drawdown.min() * 100

    daily_ret = ec['equity'].pct_change().dropna()
    sharpe = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * np.sqrt(252))

    spy_return = (spy_curve.iloc[-1] / initial_capital - 1) * 100

    trades = pd.DataFrame(portfolio.trade_log)
    sell_trades = trades[trades['action'].str.startswith('SELL')] if not trades.empty else pd.DataFrame()
    if not sell_trades.empty and 'pnl_pct' in sell_trades.columns:
        win_trades = sell_trades[sell_trades['pnl_pct'] > 0]
        loss_trades = sell_trades[sell_trades['pnl_pct'] <= 0]
        win_rate = len(win_trades) / len(sell_trades) * 100
        avg_win = win_trades['pnl_pct'].mean() if len(win_trades) > 0 else 0
        avg_loss = loss_trades['pnl_pct'].mean() if len(loss_trades) > 0 else 0
        rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    else:
        win_rate = avg_win = avg_loss = rr_ratio = 0

    metrics = {
        "label": label,
        "total_return": total_return,
        "spy_return": spy_return,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "rr_ratio": rr_ratio,
        "total_trades": len(trades),
        "sell_trades": len(sell_trades),
        "years": years,
        "final_equity": final_equity,
    }

    if verbose:
        print(f"\n{'='*55}")
        print(f"  [{label}] {start} ~ {end}")
        print(f"{'='*55}")
        print(f"  기간:               {years:.1f}년")
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
    def flag(val, threshold, higher_is_good=True):
        if higher_is_good:
            return "✓" if val >= threshold else "✗"
        return "✓" if val <= threshold else "✗"

    print("\n" + "="*75)
    print("  워크포워드 비교 요약")
    print("="*75)
    print(f"  {'지표':<20} {'IS (2.5년)':>14} {'OOS 독립 (2.3년)':>16} {'OOS 연속':>12}  {'판정'}")
    print("  " + "-"*72)

    rows = [
        ("수익률",        "total_return",  "%",    None,    True),
        ("SPY 초과",      None,            "%p",   None,    True),
        ("CAGR",          "cagr",          "%",    None,    True),
        ("MDD",           "mdd",           "%",    None,    False),
        ("샤프",          "sharpe",        "",     1.0,     True),
        ("승률",          "win_rate",      "%",    None,    True),
        ("손익비",        "rr_ratio",      "",     None,    True),
        ("청산 거래",     "sell_trades",   "건",   None,    None),
    ]

    for name, key, unit, threshold, higher_good in rows:
        if key == "SPY 초과" or key is None:
            is_val  = is_m["total_return"]  - is_m["spy_return"]
            oos_val = oos_m["total_return"] - oos_m["spy_return"]
            oos_c   = oos_chain_m["total_return"] - oos_chain_m["spy_return"] if oos_chain_m else "-"
        else:
            is_val  = is_m[key]
            oos_val = oos_m[key]
            oos_c   = oos_chain_m[key] if oos_chain_m else "-"

        # 판정: OOS가 IS 대비 크게 꺾이지 않으면 OK
        if higher_good is True and key:
            ok = "OK" if oos_m[key] >= is_m[key] * 0.6 else "주의"
        elif higher_good is False and key:
            ok = "OK" if abs(oos_m[key]) <= abs(is_m[key]) * 1.5 else "주의"
        else:
            ok = "-"

        if threshold is not None and key:
            ok = f"{ok} (기준 {threshold})"

        if isinstance(oos_c, float):
            print(f"  {name:<20} {is_val:>+12.1f}{unit}  {oos_val:>+14.1f}{unit}  {oos_c:>+10.1f}{unit}  {ok}")
        else:
            print(f"  {name:<20} {is_val:>+12.1f}{unit}  {oos_val:>+14.1f}{unit}  {'':>12}  {ok}")

    print("="*75)

    # 핵심 판정
    sharpe_ok  = oos_m["sharpe"] >= 1.0
    mdd_ok     = abs(oos_m["mdd"]) <= abs(is_m["mdd"]) * 1.5
    excess_ok  = (oos_m["total_return"] - oos_m["spy_return"]) > 0

    print(f"\n  핵심 판정")
    print(f"  {'OOS 샤프 >= 1.0':<30} {'PASS' if sharpe_ok else 'FAIL':>6}  ({oos_m['sharpe']:.2f})")
    print(f"  {'OOS MDD <= IS MDD × 1.5':<30} {'PASS' if mdd_ok else 'FAIL':>6}  ({oos_m['mdd']:.1f}% vs {is_m['mdd']*1.5:.1f}%)")
    print(f"  {'OOS SPY 초과 수익 양수':<30} {'PASS' if excess_ok else 'FAIL':>6}  ({oos_m['total_return']-oos_m['spy_return']:+.1f}%p)")

    if sharpe_ok and mdd_ok and excess_ok:
        print("\n  ★ 최종 판정: 전략 견고성 확인 - 과적합 아님")
    elif sum([sharpe_ok, mdd_ok, excess_ok]) >= 2:
        print("\n  △ 최종 판정: 부분 견고성 - OOS 성과 소폭 열화, 실전 주의")
    else:
        print("\n  ✗ 최종 판정: 과적합 의심 - 파라미터 재검토 필요")
    print("="*75)


def plot_walkforward(is_ec, is_spy, oos_ec, oos_spy, oos_chain_ec, oos_chain_spy,
                     is_m, oos_m, oos_chain_m):
    fig, axes = plt.subplots(2, 2, figsize=(18, 11))
    fig.suptitle("워크포워드 테스트 - 슈퍼사이클 추세추종 (실험21 파라미터)", fontsize=13, fontweight='bold')

    # ── 차트 1: IS 자산 곡선 ──
    ax = axes[0, 0]
    ax.plot(is_ec.index, is_ec['equity'], color='steelblue', lw=1.8, label='전략')
    ax.plot(is_spy.index, is_spy.values, color='gray', lw=1.2, ls='--', label='SPY B&H')
    ax.axvspan(pd.Timestamp(IS_START), pd.Timestamp(IS_END), alpha=0.08, color='steelblue')
    ax.set_title(f"In-Sample ({IS_START[:7]} ~ {IS_END[:7]})\n수익률 {is_m['total_return']:+.1f}%  샤프 {is_m['sharpe']:.2f}  MDD {is_m['mdd']:.1f}%")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ── 차트 2: OOS 자산 곡선 (독립, $10,000 시작) ──
    ax = axes[0, 1]
    ax.plot(oos_ec.index, oos_ec['equity'], color='darkorange', lw=1.8, label='전략 (OOS 독립)')
    ax.plot(oos_spy.index, oos_spy.values, color='gray', lw=1.2, ls='--', label='SPY B&H')
    ax.axvspan(pd.Timestamp(OOS_START), pd.Timestamp(OOS_END), alpha=0.08, color='orange')
    ax.set_title(f"Out-of-Sample 독립 ({OOS_START[:7]} ~ {OOS_END[:7]})\n수익률 {oos_m['total_return']:+.1f}%  샤프 {oos_m['sharpe']:.2f}  MDD {oos_m['mdd']:.1f}%")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ── 차트 3: OOS 연속 (IS 자본 이어받기) ──
    ax = axes[1, 0]
    if oos_chain_ec is not None:
        ax.plot(oos_chain_ec.index, oos_chain_ec['equity'], color='seagreen', lw=1.8, label='전략 (IS→OOS 연속)')
        ax.plot(oos_chain_spy.index, oos_chain_spy.values, color='gray', lw=1.2, ls='--', label='SPY B&H (비율 환산)')
        ax.set_title(f"OOS 연속 (IS 자본 ${is_m['final_equity']:,.0f} 이어받기)\n수익률 {oos_chain_m['total_return']:+.1f}%  샤프 {oos_chain_m['sharpe']:.2f}  MDD {oos_chain_m['mdd']:.1f}%")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ── 차트 4: IS vs OOS 핵심 지표 비교 막대 ──
    ax = axes[1, 1]
    metrics_labels = ['수익률(%)', 'CAGR(%)', '샤프', '손익비', '승률(%)']
    is_vals  = [is_m['total_return'],  is_m['cagr'],  is_m['sharpe'],  is_m['rr_ratio'],  is_m['win_rate']]
    oos_vals = [oos_m['total_return'], oos_m['cagr'], oos_m['sharpe'], oos_m['rr_ratio'], oos_m['win_rate']]

    # MDD는 절대값으로 변환 (낮을수록 좋으므로 별도 표시)
    metrics_labels += ['|MDD|(%)']
    is_vals  += [abs(is_m['mdd'])]
    oos_vals += [abs(oos_m['mdd'])]

    x = np.arange(len(metrics_labels))
    w = 0.35
    bars_is  = ax.bar(x - w/2, is_vals,  w, label='IS',  color='steelblue',  alpha=0.8)
    bars_oos = ax.bar(x + w/2, oos_vals, w, label='OOS', color='darkorange', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics_labels, fontsize=9)
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


if __name__ == "__main__":
    print("="*60)
    print("  워크포워드 테스트 - 슈퍼사이클 추세추종 (실험21)")
    print(f"  IS : {IS_START} ~ {IS_END}")
    print(f"  OOS: {OOS_START} ~ {OOS_END}")
    print("="*60)

    # 전체 5년치 데이터 한 번만 로드
    CONFIG['max_positions'] = 4
    price_data = load_data(LEGACY_TICKERS, 6)  # 워밍업 포함 6년치

    # ── A. In-Sample 단독 ──
    is_m, is_ec, is_spy, is_portfolio = run_segment(
        price_data, "In-Sample", IS_START, IS_END, CONFIG['initial_capital']
    )

    # ── B. Out-of-Sample 독립 ($10,000 시작) ──
    oos_m, oos_ec, oos_spy, oos_portfolio = run_segment(
        price_data, "OOS 독립", OOS_START, OOS_END, CONFIG['initial_capital']
    )

    # ── C. OOS 연속 (IS 최종 자본 이어받기) ──
    oos_chain_m, oos_chain_ec, oos_chain_spy, _ = run_oos_chained(
        price_data, is_final_equity=is_m['final_equity']
    )

    # ── 비교표 출력 ──
    print_comparison_table(is_m, oos_m, oos_chain_m)

    # ── 시각화 ──
    plot_walkforward(
        is_ec, is_spy,
        oos_ec, oos_spy,
        oos_chain_ec, oos_chain_spy,
        is_m, oos_m, oos_chain_m,
    )
