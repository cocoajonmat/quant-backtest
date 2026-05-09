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

import scipy.stats
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
# NDX100 세밀한 섹터 그룹 매핑
# 목적: 상관관계가 높은 종목끼리 같은 그룹으로 묶어 집중도 제한
# 기준: 실제 가격 상관관계 0.7+ 기준으로 묶음 (단순 GICS보다 세밀)
# ─────────────────────────────────────────────
NDX100_SECTOR_MAP = {
    # 반도체 설계 (AI/데이터센터 집중 — 상관 0.80+)
    "NVDA": "semicon_design", "AMD": "semicon_design", "AVGO": "semicon_design",
    "QCOM": "semicon_design", "MRVL": "semicon_design", "TXN": "semicon_design",
    "ADI":  "semicon_design", "NXPI": "semicon_design", "MCHP": "semicon_design",
    "ON":   "semicon_design", "INTC": "semicon_design", "ARM":  "semicon_design",
    # 반도체 장비 (AMAT/LRCX 상관 0.85+)
    "AMAT": "semicon_equip", "LRCX": "semicon_equip",
    "KLAC": "semicon_equip", "ASML": "semicon_equip",
    # 메모리/스토리지 서버
    "MU": "memory", "GFS": "memory", "SMCI": "memory",
    # 네트워크 하드웨어
    "ANET": "network_hw", "CSCO": "network_hw",
    # 빅테크 플랫폼 (AAPL/MSFT/GOOGL/META/AMZN — 상관 0.75+)
    "AAPL": "bigtech", "MSFT": "bigtech", "GOOGL": "bigtech",
    "GOOG": "bigtech", "META": "bigtech", "AMZN": "bigtech",
    # 소프트웨어 (엔터프라이즈/클라우드)
    "ADBE": "software", "INTU": "software", "SNPS": "software",
    "CDNS": "software", "WDAY": "software", "ADP":  "software",
    "PAYX": "software", "MSCI": "software", "VRSK": "software",
    "ROP":  "software", "SPLK": "software", "TEAM": "software",
    # AI 데이터/분석 소프트웨어
    "PLTR": "ai_software", "DDOG": "ai_software",
    "TTD":  "ai_software", "APP":  "ai_software",
    # 사이버보안
    "CRWD": "cybersec", "PANW": "cybersec",
    "FTNT": "cybersec", "ZS":   "cybersec",
    # 헬스케어 테크/의료기기
    "ISRG": "health_tech", "DXCM": "health_tech", "IDXX": "health_tech",
    "ILMN": "health_tech", "MRNA": "health_tech", "GEHC": "health_tech",
    # 바이오/전통 제약
    "AMGN": "biotech", "GILD": "biotech", "VRTX": "biotech",
    "REGN": "biotech", "BIIB": "biotech",
    # 인터넷/이커머스/OTT
    "NFLX": "internet", "MELI": "internet", "PDD":  "internet",
    "BKNG": "internet", "ABNB": "internet",
    # EV/소비자 기술
    "TSLA": "consumer_tech", "EA": "consumer_tech", "TTWO": "consumer_tech",
    # 소비재 (음식/음료/리테일)
    "SBUX": "consumer", "LULU": "consumer", "MAR":  "consumer",
    "COST": "consumer", "PEP":  "consumer", "MDLZ": "consumer",
    "KDP":  "consumer", "KHC":  "consumer", "MNST": "consumer",
    "ROST": "consumer", "ORLY": "consumer", "FAST": "consumer",
    # 통신
    "TMUS": "telecom", "SIRI": "telecom", "WBD": "telecom",
    # 유틸리티/에너지
    "CEG":  "utility", "VST":  "utility", "EXC":  "utility",
    "XCEL": "utility", "FANG": "utility",
    # 금융/핀테크/암호화폐
    "HOOD": "fintech", "COIN": "fintech",
    # 방산/항공우주
    "AXON": "defense", "KTOS": "defense", "RKLB": "defense", "HWM": "defense",
    # 산업재
    "HON": "industrial", "CTAS": "industrial", "CSX":  "industrial",
    "ODFL": "industrial", "PCAR": "industrial",
}


# ─────────────────────────────────────────────
# 동적 슈퍼사이클 감지 유니버스
# ─────────────────────────────────────────────
def calc_momentum_score(close, idx, window=90):
    """
    지수회귀 기울기 × R² 모멘텀 점수 (Clenow 방식).
    로그 가격에 선형회귀 → 기울기(연환산) × R²
    값이 클수록 추세가 강하고 선형적(노이즈 적음).
    """
    if idx < window:
        return 0.0
    log_prices = np.log(close.iloc[idx - window:idx + 1].values)
    x = np.arange(len(log_prices))
    slope, _, r_value, _, _ = scipy.stats.linregress(x, log_prices)
    annualized_slope = slope * 252
    return annualized_slope * (r_value ** 2)


def get_dynamic_universe(price_data, date, top_n=8, adx_min=20,
                         ret12_min=0.40, dollar_vol_min=100_000_000,
                         momentum_mode='ret3m', linreg_gate=0.15, linreg_window=90):
    """
    NDX100 전체에서 슈퍼사이클 초입 특성을 보이는 종목 동적 선발.

    momentum_mode:
      'ret3m'   — 기존 방식: 3개월 수익률 > ret12m / 4 (가속 필터) + 3개월 수익률로 정렬
      'linreg'  — 신규 방식: 90일 지수회귀 기울기 × R² 로 가속 판정 + 정렬 (Clenow)

    공통 필터 (전부 충족):
      - 12개월 수익률 > ret12_min
      - 6개월 수익률 > 0
      - MA 정배열: 현재가 > MA50 > MA200
      - ADX >= adx_min
      - 일평균 거래대금 >= dollar_vol_min

    반환: 모멘텀 점수 내림차순 Top top_n 종목 리스트
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

        # 12개월 수익률 필터
        ret_12m = current / close.iloc[idx - 252] - 1
        if ret_12m <= ret12_min:
            continue

        # 6개월 수익률 양수 확인
        if idx >= 126:
            ret_6m = current / close.iloc[idx - 126] - 1
            if ret_6m <= 0:
                continue

        # 3개월 수익률
        ret_3m = current / close.iloc[idx - 63] - 1

        if momentum_mode == 'ret3m':
            # 기존: 모멘텀 가속 필터 (3개월이 연간 평균 분기보다 빨라야 함)
            if ret_3m <= ret_12m / 4:
                continue
            sort_key = ret_3m

        else:  # linreg
            # 신규: 지수회귀 기울기 × R² — 추세 강도 + 선형성 동시 측정
            score = calc_momentum_score(close, idx, window=linreg_window)
            if score <= linreg_gate:
                continue
            sort_key = score

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

        candidates.append({
            "ticker": ticker,
            "sort_key": sort_key,
            "ret_3m": ret_3m,
            "ret_12m": ret_12m,
            "adx": adx,
        })

    if not candidates:
        return []

    cand_df = pd.DataFrame(candidates).sort_values('sort_key', ascending=False)
    return cand_df.head(top_n)['ticker'].tolist()


# ─────────────────────────────────────────────
# 동적 유니버스를 사용하는 백테스트 래퍼
# ─────────────────────────────────────────────
def run_dynamic_backtest(price_data, portfolio, top_n=8, adx_min=20,
                         ret12_min=0.40, dollar_vol_min=100_000_000,
                         bear_filter='block', stop_mode='pct12', exit_mode='hybrid',
                         atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
                         trailing_stop='original', spy_ma_period=200,
                         adx_threshold=20, min_hold_days=3,
                         momentum_mode='ret3m', linreg_gate=0.15, linreg_window=90,
                         portfolio_heat_cap=None,
                         entry_mode='score',
                         use_macd_rsi_exit=True,
                         sector_max=None,
                         corr_max=None, corr_window=180):
    """
    get_dynamic_universe를 유니버스 공급원으로 사용하는 백테스트.
    backtest.run_backtest의 get_universe 호출 부분을 monkey-patch 방식으로 교체.

    entry_mode:
      'score'          — 기존: 5팩터 점수합산 (strong >= 70 / medium >= 50)
      'universe_only'  — 유니버스 필터 통과한 모든 종목 직접 'strong' 처리 (점수 제거)
      'and_52w'        — 52주 신고가 5% 이내 AND 조건 충족 시 'strong' 처리 (Minervini SEPA)

    use_macd_rsi_exit:
      True  — MACD 데드크로스 + RSI 50 하향 시 즉시 전량 청산 (기존)
      False — 해당 청산 규칙 비활성화

    sector_max:
      None — 제한 없음 (기존)
      int  — 동일 섹터 그룹(NDX100_SECTOR_MAP) 내 최대 보유 포지션 수

    corr_max:
      None  — 제한 없음 (기존)
      float — 기존 포지션과의 corr_window일 상관계수가 이 값 이상이면 진입 차단
    """
    from datetime import timedelta

    benchmark_df = price_data[BENCHMARK]
    start_date = benchmark_df.index[252]
    trading_days = benchmark_df.index[benchmark_df.index >= start_date]

    pending_tranches = {}
    current_universe = []
    last_universe_update = None

    print(f"\n[동적 유니버스 / top_n={top_n} / ret12>{ret12_min*100:.0f}% / ADX>={adx_min} / momentum={momentum_mode}]")
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
                momentum_mode=momentum_mode, linreg_gate=linreg_gate,
                linreg_window=linreg_window,
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
                                                  exit_mode=exit_mode, trailing_stop=trailing_stop,
                                                  use_macd_rsi_exit=use_macd_rsi_exit)
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

                if entry_mode == 'score':
                    score, _ = bt.calculate_signal_score(df, idx)
                    if score >= CONFIG['strong_signal_threshold']:
                        strength = 'strong'
                    elif score >= CONFIG['medium_signal_threshold']:
                        strength = 'medium'
                    else:
                        continue
                elif entry_mode == 'and_52w':
                    high_52w = df['Close'].iloc[idx - 252:idx].max()
                    if df['Close'].iloc[idx] < high_52w * 0.95:
                        continue
                    strength = 'strong'
                else:  # 'universe_only'
                    strength = 'strong'

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

                # 섹터 집중도 제한 (N1)
                if sector_max is not None:
                    my_sector = NDX100_SECTOR_MAP.get(ticker)
                    if my_sector is not None:
                        sector_count = sum(
                            1 for h in portfolio.positions
                            if NDX100_SECTOR_MAP.get(h) == my_sector
                        )
                        if sector_count >= sector_max:
                            continue

                # 상관계수 집중도 제한 (N2)
                if corr_max is not None and portfolio.positions:
                    if ticker not in price_data:
                        pass
                    else:
                        t_close = price_data[ticker]['Close']
                        t_idx = price_data[ticker].index.get_loc(date)
                        t_win = t_close.iloc[max(0, t_idx - corr_window):t_idx]
                        too_correlated = False
                        for h_ticker in portfolio.positions:
                            if h_ticker not in price_data:
                                continue
                            h_close = price_data[h_ticker]['Close']
                            if date not in price_data[h_ticker].index:
                                continue
                            h_idx = price_data[h_ticker].index.get_loc(date)
                            h_win = h_close.iloc[max(0, h_idx - corr_window):h_idx]
                            common = t_win.index.intersection(h_win.index)
                            if len(common) < 60:
                                continue
                            c = t_win[common].corr(h_win[common])
                            if c >= corr_max:
                                too_correlated = True
                                break
                        if too_correlated:
                            continue

                # 포트폴리오 열 리스크 캡 체크
                if portfolio_heat_cap is not None and atr_sizing:
                    current_eq = portfolio.total_equity(price_snapshot)
                    total_heat = 0.0
                    for h_ticker, h_pos in portfolio.positions.items():
                        if h_ticker not in price_data or date not in price_data[h_ticker].index:
                            continue
                        h_df = price_data[h_ticker]
                        h_idx = h_df.index.get_loc(date)
                        if h_idx < 15:
                            continue
                        h_atr = bt.calc_atr(h_df, h_idx)
                        h_price = price_snapshot.get(h_ticker, 0)
                        if h_price <= 0:
                            continue
                        h_stop_dist = (h_atr * 2.5) / h_price
                        h_value = h_pos.shares * h_price
                        total_heat += (h_value * h_stop_dist) / current_eq
                    if total_heat >= portfolio_heat_cap:
                        continue

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

    print("="*60)
    print("  N 시리즈 -- 상관관계 집중도 제한 비교")
    print("  N0: 기준(제한없음) / N1-A: 섹터1개 / N1-B: 섹터2개")
    print("  N2-A: 상관0.7 / N2-B: 상관0.6 / N3: 섹터2+상관0.7")
    print("="*60)

    CONFIG['max_positions'] = 4
    price_data = load_data(NDX100, period_years=8)

    # 채택 파라미터 (M2 기준)
    COMMON = dict(
        top_n=5, adx_min=20,
        momentum_mode='linreg', linreg_gate=0.15, linreg_window=90,
        ret12_min=0.20,
        bear_filter='block', spy_ma_period=50,
        exit_mode='hybrid',
        stop_mode='pct12',
        atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
        trailing_stop='original', adx_threshold=20, min_hold_days=3,
        portfolio_heat_cap=0.10,
        entry_mode='score',
        use_macd_rsi_exit=False,
    )

    # Q 시리즈: bear_filter MA50 vs MA200 비교
    results = []
    spy_curve = None

    experiments = [
        dict(spy_ma_period=50,  label='Q0 기준 MA50 (M2)'),
        dict(spy_ma_period=200, label='Q1 MA200'),
    ]

    for exp in experiments:
        label = exp.pop('label')
        params = {**COMMON, **exp}
        print(f"\n[{label}]")
        p = PortfolioManager(CONFIG['initial_capital'])
        run_dynamic_backtest(price_data, p, **params)
        m, ec, sc = compute_metrics(p, price_data)
        m['label'] = label
        print_metrics(m)
        results.append({"label": label, "ec": ec, "metrics": m})
        if spy_curve is None:
            spy_curve = sc

    plot_comparison(results, spy_curve,
                    title="Q 시리즈 — bear filter MA50 vs MA200 (8Y)")
