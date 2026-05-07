import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# 현재 최고 수익률 전략 파라미터 (실험10 채택값)
CONFIG = {
    "period_years": 5,
    "initial_capital": 10_000,
    "max_positions": 16,       # 전체 유니버스 모드에서는 16
    "strong_signal_threshold": 70,
    "medium_signal_threshold": 50,
    "strong_position_pct": 0.32,
    "medium_position_pct": 0.22,
    "slippage_cost": 0.001,
}

UNIVERSE_TICKERS = [
    "NVDA", "PLTR", "ANET", "MRVL", "AVGO",
    "MU", "WDC",
    "CEG", "VST", "NRG",
    "AXON", "HWM", "KTOS", "RKLB",
    "HOOD", "COIN",
]
BENCHMARK = "SPY"
TARGET = "MU"


# ─────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────
def calc_atr(df, idx, period=14):
    high = df['High'].iloc[idx - period:idx + 1]
    low  = df['Low'].iloc[idx - period:idx + 1]
    prev_close = df['Close'].iloc[idx - period - 1:idx]
    tr = pd.concat([
        high - low,
        (high - prev_close.values).abs(),
        (low  - prev_close.values).abs(),
    ], axis=1).max(axis=1)
    return tr.mean()


def calculate_signal_score(df, idx):
    score = 0
    close = df['Close']
    volume = df['Volume']

    if idx >= 252:
        high_52w = close.iloc[idx - 252:idx].max()
        if close.iloc[idx] >= high_52w:
            score += 20

    if idx >= 200:
        ma20 = close.iloc[idx - 20:idx].mean()
        ma50 = close.iloc[idx - 50:idx].mean()
        ma200 = close.iloc[idx - 200:idx].mean()
        if ma20 > ma50 > ma200:
            score += 15

    if idx >= 35:
        ema12 = close.iloc[:idx + 1].ewm(span=12).mean().iloc[-1]
        ema26 = close.iloc[:idx + 1].ewm(span=26).mean().iloc[-1]
        ema12_prev = close.iloc[:idx].ewm(span=12).mean().iloc[-1]
        ema26_prev = close.iloc[:idx].ewm(span=26).mean().iloc[-1]
        macd = ema12 - ema26
        macd_prev = ema12_prev - ema26_prev
        signal_line = close.iloc[:idx + 1].ewm(span=12).mean().sub(
            close.iloc[:idx + 1].ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        signal_prev = close.iloc[:idx].ewm(span=12).mean().sub(
            close.iloc[:idx].ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        if macd > signal_line and macd_prev <= signal_prev:
            score += 10

    if idx >= 14:
        delta = close.diff().iloc[idx - 13:idx + 1]
        gain = delta.clip(lower=0).mean()
        loss = (-delta.clip(upper=0)).mean()
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - 100 / (1 + rs)
        if 50 <= rsi <= 70:
            score += 10

    if idx >= 20:
        avg_vol = volume.iloc[idx - 20:idx].mean()
        if volume.iloc[idx] >= avg_vol * 1.5:
            score += 5

    return round(score / 60 * 100)


def check_sell_signals(df, idx, pos, stop_mode='pct12', exit_mode='hybrid', trailing_stop=True):
    close = df['Close']
    current = close.iloc[idx]
    signals = []

    # 하드 스탑
    if stop_mode == 'pct12':
        triggered = (current - pos['avg_price']) / pos['avg_price'] <= -0.12
    else:
        if idx >= 15:
            atr = calc_atr(df, idx)
            triggered = current <= pos['avg_price'] - atr * 2.5
        else:
            triggered = (current - pos['avg_price']) / pos['avg_price'] <= -0.12
    if triggered:
        return [('HARD_STOP', 1.0)]

    # 트레일링 스탑
    if trailing_stop:
        if current > pos['peak_price']:
            pos['peak_price'] = current
        pnl = (current - pos['avg_price']) / pos['avg_price']
        if pnl >= 0.40:
            trail_price = pos['peak_price'] * 0.85
        elif pnl >= 0.20:
            trail_price = pos['peak_price'] * 0.90
        elif pnl >= 0.10:
            trail_price = pos['avg_price']
        else:
            trail_price = None
        if trail_price is not None and current <= trail_price:
            return [('TRAIL_STOP', 1.0)]

    # MACD 데드크로스 + RSI 50 하향
    if idx >= 35:
        ema12 = close.iloc[:idx + 1].ewm(span=12).mean().iloc[-1]
        ema26 = close.iloc[:idx + 1].ewm(span=26).mean().iloc[-1]
        ema12_prev = close.iloc[:idx].ewm(span=12).mean().iloc[-1]
        ema26_prev = close.iloc[:idx].ewm(span=26).mean().iloc[-1]
        macd = ema12 - ema26
        macd_prev = ema12_prev - ema26_prev
        signal_line = close.iloc[:idx + 1].ewm(span=12).mean().sub(
            close.iloc[:idx + 1].ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        signal_prev = close.iloc[:idx].ewm(span=12).mean().sub(
            close.iloc[:idx].ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        macd_dead = macd < signal_line and macd_prev >= signal_prev
        delta = close.diff().iloc[idx - 13:idx + 1]
        gain = delta.clip(lower=0).mean()
        loss = (-delta.clip(upper=0)).mean()
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - 100 / (1 + rs)
        if macd_dead and rsi < 50:
            return [('MACD_RSI_EXIT', 1.0)]

    # MA 하이브리드 청산
    if idx >= 23:
        ma10 = close.iloc[idx - 10:idx + 1].mean()
        below_ma20_streak = all(
            close.iloc[idx - i] < close.iloc[idx - 20 - i:idx - i + 1].mean()
            for i in range(3)
        )
        if below_ma20_streak and pos['sold_pct'] >= 0.50:
            signals.append(('MA20_HYBRID_ALL', 1.0))
        elif below_ma20_streak and pos['sold_pct'] < 0.50:
            signals.append(('MA20_HYBRID_ALL', 1.0))
        elif current < ma10 and pos['sold_pct'] < 0.50:
            signals.append(('MA10_HYBRID_HALF', 0.50))

    return signals


# ─────────────────────────────────────────────
# MU 단일 종목 백테스트
# ─────────────────────────────────────────────
def run_single_backtest(df_mu, df_spy, initial_capital=10_000):
    """MU만 거래. SPY MA200 block 필터 적용. 매매 기록 반환."""
    cash = initial_capital
    pos = None          # dict or None
    equity_curve = []
    trade_log = []      # {date, action, price, shares, reason, pnl_pct}
    pending_tranche = None  # {tranche, trigger_date}

    start_idx = 252
    trading_days = df_mu.index[start_idx:]

    for date in trading_days:
        if date not in df_mu.index:
            continue
        idx = df_mu.index.get_loc(date)
        current_price = df_mu['Close'].iloc[idx]

        # SPY MA200 bear filter
        spy_above_ma200 = True
        if date in df_spy.index:
            spy_idx = df_spy.index.get_loc(date)
            if spy_idx >= 200:
                spy_ma = df_spy['Close'].iloc[spy_idx - 200:spy_idx].mean()
                spy_above_ma200 = df_spy['Close'].iloc[spy_idx] >= spy_ma

        # ── 포지션 보유 중: 매도 판단 ──
        if pos is not None:
            signals = check_sell_signals(df_mu, idx, pos, stop_mode='pct12',
                                         exit_mode='hybrid', trailing_stop=True)
            for reason, ratio in signals:
                full_exit = reason in ('HARD_STOP', 'TRAIL_STOP', 'MACD_RSI_EXIT',
                                       'MA20_HYBRID_ALL')
                if full_exit:
                    shares_to_sell = pos['shares']
                    proceeds = shares_to_sell * current_price * (1 - CONFIG['slippage_cost'])
                    pnl_pct = (current_price - pos['avg_price']) / pos['avg_price'] * 100
                    cash += proceeds
                    trade_log.append({
                        'date': date, 'action': 'SELL', 'price': current_price,
                        'shares': shares_to_sell, 'reason': reason, 'pnl_pct': pnl_pct,
                        'partial': False
                    })
                    pos = None
                    pending_tranche = None
                    break
                else:
                    shares_to_sell = int(pos['shares'] * ratio)
                    if shares_to_sell > 0:
                        proceeds = shares_to_sell * current_price * (1 - CONFIG['slippage_cost'])
                        pnl_pct = (current_price - pos['avg_price']) / pos['avg_price'] * 100
                        cash += proceeds
                        pos['shares'] -= shares_to_sell
                        pos['sold_pct'] += ratio
                        trade_log.append({
                            'date': date, 'action': 'SELL_PARTIAL', 'price': current_price,
                            'shares': shares_to_sell, 'reason': reason, 'pnl_pct': pnl_pct,
                            'partial': True
                        })

        # ── 추가 매수 트랜치 ──
        if pos is not None and pending_tranche is not None:
            pt = pending_tranche
            if date >= pt['trigger_date']:
                if pt['tranche'] == 2:
                    if current_price >= pos['entry_price']:
                        alloc = pos['capital_allocated'] * 0.30
                        alloc = min(alloc, cash * 0.95)
                        shares = int(alloc / current_price)
                        if shares > 0:
                            cost = shares * current_price * (1 + CONFIG['slippage_cost'])
                            if cost <= cash:
                                # 평단 업데이트
                                total_shares = pos['shares'] + shares
                                pos['avg_price'] = (pos['avg_price'] * pos['shares'] + current_price * shares) / total_shares
                                pos['shares'] = total_shares
                                cash -= cost
                                trade_log.append({
                                    'date': date, 'action': 'BUY_T2', 'price': current_price,
                                    'shares': shares, 'reason': 'ADD', 'pnl_pct': 0,
                                    'partial': False
                                })
                                pending_tranche = {
                                    'tranche': 3,
                                    'trigger_date': date + timedelta(days=14)
                                }
                elif pt['tranche'] == 3:
                    if idx >= 20:
                        ma20 = df_mu['Close'].iloc[idx - 20:idx].mean()
                        if current_price > ma20:
                            alloc = pos['capital_allocated'] * 0.20
                            alloc = min(alloc, cash * 0.95)
                            shares = int(alloc / current_price)
                            if shares > 0:
                                cost = shares * current_price * (1 + CONFIG['slippage_cost'])
                                if cost <= cash:
                                    total_shares = pos['shares'] + shares
                                    pos['avg_price'] = (pos['avg_price'] * pos['shares'] + current_price * shares) / total_shares
                                    pos['shares'] = total_shares
                                    cash -= cost
                                    trade_log.append({
                                        'date': date, 'action': 'BUY_T3', 'price': current_price,
                                        'shares': shares, 'reason': 'ADD', 'pnl_pct': 0,
                                        'partial': False
                                    })
                                    pending_tranche = None

        # ── 신규 진입 ──
        if pos is None:
            score = calculate_signal_score(df_mu, idx)
            strength = None
            if score >= CONFIG['strong_signal_threshold']:
                strength = 'strong'
            elif score >= CONFIG['medium_signal_threshold'] and spy_above_ma200:
                strength = 'medium'

            # bear filter: SPY MA200 아래면 진입 차단
            if not spy_above_ma200:
                strength = None

            if strength is not None:
                # 단일 종목: 총자산의 90%를 목표 배분, 3트랜치로 분할 진입
                current_eq = cash
                capital_allocated = current_eq * 0.90
                first_pct = 0.50  # 1차 50%, 2차 30%, 3차 20%

                first_capital = capital_allocated * first_pct
                first_capital = min(first_capital, cash * 0.95)
                shares = int(first_capital / current_price)
                if shares > 0:
                    cost = shares * current_price * (1 + CONFIG['slippage_cost'])
                    if cost <= cash:
                        cash -= cost
                        pos = {
                            'shares': shares,
                            'avg_price': current_price,
                            'entry_price': current_price,
                            'capital_allocated': capital_allocated,
                            'sold_pct': 0.0,
                            'peak_price': current_price,
                            'entry_date': date,
                            'strength': strength,
                        }
                        trade_log.append({
                            'date': date, 'action': 'BUY_T1', 'price': current_price,
                            'shares': shares, 'reason': f'ENTRY({strength.upper()})',
                            'pnl_pct': 0, 'partial': False
                        })
                        pending_tranche = {
                            'tranche': 2,
                            'trigger_date': date + timedelta(days=5)
                        }

        # ── 자산 기록 ──
        pos_value = pos['shares'] * current_price if pos is not None else 0
        equity_curve.append({'date': date, 'equity': cash + pos_value})

    return pd.DataFrame(equity_curve).set_index('date'), trade_log


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────
def load_data():
    end = datetime.today()
    start = end - timedelta(days=5 * 365 + 60)
    tickers = UNIVERSE_TICKERS + [BENCHMARK]
    print("데이터 다운로드 중...")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)

    price_data = {}
    for t in tickers:
        try:
            df = raw.xs(t, axis=1, level=1).dropna(how='all')
            if len(df) > 200:
                price_data[t] = df
        except Exception:
            pass
    print(f"  → {len(price_data)}개 로드 완료")
    return price_data


# ─────────────────────────────────────────────
# 멀티 종목 백테스트 (실험10 재현)
# ─────────────────────────────────────────────
def run_full_backtest():
    """기존 멀티 종목 실험10 백테스트를 별도 프로세스로 실행. 결과만 반환."""
    import subprocess, sys, json, os
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_run_multi.py')
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    if result.returncode != 0:
        print("멀티 백테스트 오류:", result.stderr[-500:])
        return None, None, None
    lines = [l for l in result.stdout.strip().split('\n') if l.startswith('JSON:')]
    if not lines:
        print("멀티 백테스트 결과 파싱 실패")
        return None, None, None
    data = json.loads(lines[-1][5:])
    ec = pd.DataFrame(data['equity_curve'])
    ec['date'] = pd.to_datetime(ec['date'])
    ec = ec.set_index('date')
    spy = pd.Series(data['spy_values'], index=pd.to_datetime(data['spy_dates']))
    return ec, data['metrics'], spy


# ─────────────────────────────────────────────
# 시각화
# ─────────────────────────────────────────────
def plot_single_with_trades(df_mu, trade_log, ec_single, ec_multi, metrics_single,
                            metrics_multi, spy_curve):
    trades = pd.DataFrame(trade_log)
    trades['date'] = pd.to_datetime(trades['date'])

    buys    = trades[trades['action'].str.startswith('BUY')]
    sells   = trades[trades['action'] == 'SELL']
    partial = trades[trades['action'] == 'SELL_PARTIAL']

    close = df_mu['Close']
    close = close[close.index >= ec_single.index[0]]
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    fig = plt.figure(figsize=(18, 20))
    fig.suptitle(f"MU (마이크론) 단일 종목 백테스트 vs 멀티 종목 실험10\n"
                 f"전략: hybrid exit / SPY MA200 block / ATR 4% sizing / trailing stop / 5Y",
                 fontsize=13, fontweight='bold', y=0.98)

    gs = fig.add_gridspec(4, 2, height_ratios=[3, 1.2, 1.5, 1.0], hspace=0.45, wspace=0.3)

    # ── 1) 주가 + 매매 표시 (상단 왼쪽, 넓게) ──
    ax_price = fig.add_subplot(gs[0, :])
    ax_price.plot(close.index, close.values, color='#1a1a2e', linewidth=1.2, label='MU 종가', zorder=2)
    ax_price.plot(ma20.index, ma20.values, color='#e67e22', linewidth=1.0, linestyle='--', alpha=0.8, label='MA20')
    ax_price.plot(ma50.index, ma50.values, color='#2980b9', linewidth=1.0, linestyle='--', alpha=0.8, label='MA50')
    ax_price.plot(ma200.index, ma200.values, color='#8e44ad', linewidth=1.2, linestyle=':', alpha=0.7, label='MA200')

    # 매수 마커
    for _, row in buys.iterrows():
        if row['date'] in df_mu.index:
            y = row['price']
            color = '#27ae60' if row['action'] == 'BUY_T1' else ('#f39c12' if row['action'] == 'BUY_T2' else '#1abc9c')
            label_text = '1차' if row['action'] == 'BUY_T1' else ('2차' if row['action'] == 'BUY_T2' else '3차')
            ax_price.annotate('', xy=(row['date'], y * 0.97),
                              xytext=(row['date'], y * 0.93),
                              arrowprops=dict(arrowstyle='->', color=color, lw=2))
            ax_price.scatter(row['date'], y * 0.97, marker='^', s=120, color=color, zorder=5)
            ax_price.text(row['date'], y * 0.91, f'B{label_text}\n${y:.0f}',
                         fontsize=6.5, color=color, ha='center', va='top',
                         bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor=color))

    # 전량 매도 마커
    for _, row in sells.iterrows():
        if row['date'] in df_mu.index:
            y = row['price']
            color = '#e74c3c'
            pnl = row['pnl_pct']
            pnl_color = '#27ae60' if pnl >= 0 else '#e74c3c'
            ax_price.scatter(row['date'], y * 1.03, marker='v', s=120, color=color, zorder=5)
            ax_price.text(row['date'], y * 1.05,
                         f'SELL\n${y:.0f}\n({pnl:+.1f}%)',
                         fontsize=6.5, color=pnl_color, ha='center', va='bottom',
                         bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor=color))

    # 부분 매도 마커
    for _, row in partial.iterrows():
        if row['date'] in df_mu.index:
            y = row['price']
            ax_price.scatter(row['date'], y * 1.02, marker='v', s=70, color='#e67e22', zorder=5, alpha=0.8)
            ax_price.text(row['date'], y * 1.035,
                         f'50%\n${y:.0f}',
                         fontsize=5.5, color='#e67e22', ha='center', va='bottom',
                         bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.6, edgecolor='#e67e22'))

    ax_price.set_title("MU 주가 + 매매 시그널 (▲매수 / ▼매도)", fontsize=11)
    ax_price.set_ylabel("주가 ($)")
    ax_price.legend(loc='upper left', fontsize=8)
    ax_price.grid(True, alpha=0.25)
    ax_price.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_price.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_price.xaxis.get_majorticklabels(), rotation=30)

    # 범례 패치
    legend_patches = [
        mpatches.Patch(color='#27ae60', label='1차 매수'),
        mpatches.Patch(color='#f39c12', label='2차 매수'),
        mpatches.Patch(color='#1abc9c', label='3차 매수'),
        mpatches.Patch(color='#e74c3c', label='전량 매도'),
        mpatches.Patch(color='#e67e22', label='50% 부분 매도'),
    ]
    ax_price.legend(handles=legend_patches + [
        plt.Line2D([0], [0], color='#e67e22', linestyle='--', label='MA20'),
        plt.Line2D([0], [0], color='#2980b9', linestyle='--', label='MA50'),
        plt.Line2D([0], [0], color='#8e44ad', linestyle=':', label='MA200'),
    ], fontsize=8, loc='upper left', ncol=2)

    # ── 2) 거래별 손익 막대 ──
    ax_pnl = fig.add_subplot(gs[1, :])
    all_sells = pd.concat([sells, partial]).sort_values('date')
    if not all_sells.empty:
        colors_bar = ['#27ae60' if p >= 0 else '#e74c3c' for p in all_sells['pnl_pct']]
        bars = ax_pnl.bar(range(len(all_sells)), all_sells['pnl_pct'], color=colors_bar, alpha=0.85)
        ax_pnl.axhline(0, color='black', linewidth=0.8)
        ax_pnl.set_xticks(range(len(all_sells)))
        ax_pnl.set_xticklabels(
            [f"{r['date'].strftime('%y-%m')}\n{r['reason'][:8]}" for _, r in all_sells.iterrows()],
            fontsize=6, rotation=45
        )
        ax_pnl.set_ylabel("손익 (%)")
        ax_pnl.set_title("거래별 손익", fontsize=10)
        ax_pnl.grid(True, axis='y', alpha=0.3)
        for bar, pnl in zip(bars, all_sells['pnl_pct']):
            ax_pnl.text(bar.get_x() + bar.get_width() / 2,
                       bar.get_height() + (0.5 if pnl >= 0 else -1.5),
                       f'{pnl:+.1f}%', ha='center', va='bottom', fontsize=6)

    # ── 3) 자산 곡선 비교 ──
    ax_eq = fig.add_subplot(gs[2, :])
    spy_aligned = spy_curve.reindex(ec_single.index, method='ffill')
    mu_bh = df_mu['Close']
    mu_bh = mu_bh[mu_bh.index >= ec_single.index[0]]
    mu_bh_curve = mu_bh / mu_bh.iloc[0] * CONFIG['initial_capital']

    ax_eq.plot(spy_aligned.index, spy_aligned.values,
               color='lightgray', linewidth=1.5, linestyle='--', label=f"SPY B&H  ({(spy_aligned.iloc[-1]/CONFIG['initial_capital']-1)*100:+.1f}%)")
    ax_eq.plot(mu_bh_curve.index, mu_bh_curve.values,
               color='#95a5a6', linewidth=1.5, linestyle=':', label=f"MU B&H  ({(mu_bh_curve.iloc[-1]/CONFIG['initial_capital']-1)*100:+.1f}%)")
    ax_eq.plot(ec_single.index, ec_single['equity'],
               color='#e74c3c', linewidth=2.2, label=f"MU 단일 전략  ({metrics_single['total_return']:+.1f}%  샤프={metrics_single['sharpe']:.2f})")

    if ec_multi is not None:
        ec_multi_aligned = ec_multi.reindex(ec_single.index, method='ffill')
        ax_eq.plot(ec_multi_aligned.index, ec_multi_aligned['equity'],
                   color='#2980b9', linewidth=2.2,
                   label=f"멀티 실험10  ({metrics_multi['total_return']:+.1f}%  샤프={metrics_multi['sharpe']:.2f})")

    ax_eq.set_title("자산 곡선 비교", fontsize=10)
    ax_eq.set_ylabel("Equity ($)")
    ax_eq.legend(fontsize=8)
    ax_eq.grid(True, alpha=0.25)
    ax_eq.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_eq.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_eq.xaxis.get_majorticklabels(), rotation=30)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

    # ── 4) 지표 비교 테이블 ──
    ax_tbl = fig.add_subplot(gs[3, :])
    ax_tbl.axis('off')

    mu_bh_ret = (mu_bh_curve.iloc[-1] / CONFIG['initial_capital'] - 1) * 100
    spy_ret = (spy_aligned.iloc[-1] / CONFIG['initial_capital'] - 1) * 100

    rows = [
        ['지표', 'SPY B&H', 'MU B&H', 'MU 단일 전략', '멀티 실험10'],
        ['총수익률',
         f'{spy_ret:+.1f}%',
         f'{mu_bh_ret:+.1f}%',
         f"{metrics_single['total_return']:+.1f}%",
         f"{metrics_multi['total_return']:+.1f}%" if metrics_multi else '-'],
        ['CAGR', '-', '-',
         f"{metrics_single['cagr']:.1f}%",
         f"{metrics_multi['cagr']:.1f}%" if metrics_multi else '-'],
        ['MDD', '-', '-',
         f"{metrics_single['mdd']:.1f}%",
         f"{metrics_multi['mdd']:.1f}%" if metrics_multi else '-'],
        ['샤프비율', '-', '-',
         f"{metrics_single['sharpe']:.2f}",
         f"{metrics_multi['sharpe']:.2f}" if metrics_multi else '-'],
        ['승률', '-', '-',
         f"{metrics_single['win_rate']:.1f}%",
         f"{metrics_multi['win_rate']:.1f}%" if metrics_multi else '-'],
        ['거래수(청산)', '-', '-',
         f"{metrics_single['sell_trades']}건",
         f"{metrics_multi['sell_trades']}건" if metrics_multi else '-'],
    ]

    col_labels = rows[0]
    cell_text  = rows[1:]

    tbl = ax_tbl.table(cellText=cell_text, colLabels=col_labels,
                       cellLoc='center', loc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.7)

    # MU 단일 열 하이라이트
    for row_idx in range(len(cell_text)):
        tbl[(row_idx + 1, 3)].set_facecolor('#fde8e8')
        if metrics_multi:
            tbl[(row_idx + 1, 4)].set_facecolor('#e8f0fd')

    ax_tbl.set_title("전략별 성과 비교", fontsize=10, pad=8)

    plt.savefig("mu_single_backtest.png", dpi=150, bbox_inches='tight')
    print("\n  차트 저장: mu_single_backtest.png")
    plt.show()


# ─────────────────────────────────────────────
# 지표 계산 (단순화 버전 — 단일 종목용)
# ─────────────────────────────────────────────
def compute_single_metrics(ec, spy_curve, trade_log):
    ec.index = pd.to_datetime(ec.index)
    years = (ec.index[-1] - ec.index[0]).days / 365
    final = ec['equity'].iloc[-1]
    total_return = (final / CONFIG['initial_capital'] - 1) * 100
    cagr = ((final / CONFIG['initial_capital']) ** (1 / years) - 1) * 100

    rolling_max = ec['equity'].cummax()
    mdd = ((ec['equity'] - rolling_max) / rolling_max).min() * 100

    daily_ret = ec['equity'].pct_change().dropna()
    sharpe = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * np.sqrt(252))

    trades = pd.DataFrame(trade_log)
    sells = trades[trades['action'].isin(['SELL', 'SELL_PARTIAL'])]
    win_trades = sells[sells['pnl_pct'] > 0]
    win_rate = len(win_trades) / len(sells) * 100 if len(sells) > 0 else 0
    avg_win  = win_trades['pnl_pct'].mean() if len(win_trades) > 0 else 0
    loss_trades = sells[sells['pnl_pct'] <= 0]
    avg_loss = loss_trades['pnl_pct'].mean() if len(loss_trades) > 0 else 0
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    return {
        'total_return': total_return, 'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe,
        'win_rate': win_rate, 'avg_win': avg_win, 'avg_loss': avg_loss,
        'rr_ratio': rr_ratio, 'total_trades': len(trades), 'sell_trades': len(sells),
    }


# ─────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    price_data = load_data()

    df_mu  = price_data[TARGET]
    df_spy = price_data[BENCHMARK]

    # MU 단일 종목 백테스트
    print(f"\n[MU 단일 종목] 백테스팅 시작...")
    ec_single, trade_log = run_single_backtest(df_mu, df_spy, CONFIG['initial_capital'])

    spy_start = df_spy['Close'].loc[df_spy.index >= ec_single.index[0]].iloc[0]
    spy_curve = df_spy['Close'].loc[df_spy.index >= ec_single.index[0]] / spy_start * CONFIG['initial_capital']

    metrics_single = compute_single_metrics(ec_single, spy_curve, trade_log)

    print(f"\n[MU 단일 전략 결과]")
    print(f"  총 수익률: {metrics_single['total_return']:+.1f}%")
    print(f"  CAGR: {metrics_single['cagr']:.1f}%")
    print(f"  MDD: {metrics_single['mdd']:.1f}%")
    print(f"  샤프: {metrics_single['sharpe']:.2f}")
    print(f"  승률: {metrics_single['win_rate']:.1f}%")
    print(f"  거래수(청산): {metrics_single['sell_trades']}건")

    # 멀티 종목 실험10 재실행
    print(f"\n[멀티 종목 실험10] 백테스팅 시작 (비교용)...")
    ec_multi, metrics_multi, _ = run_full_backtest()

    print(f"\n[멀티 실험10 결과]")
    print(f"  총 수익률: {metrics_multi['total_return']:+.1f}%")
    print(f"  샤프: {metrics_multi['sharpe']:.2f}")

    plot_single_with_trades(df_mu, trade_log, ec_single, ec_multi,
                            metrics_single, metrics_multi, spy_curve)
