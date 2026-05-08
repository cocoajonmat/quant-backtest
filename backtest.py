import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 한글 폰트 설정 (Windows 맑은 고딕)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ─────────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────────
CONFIG = {
    "period_years": 5,
    "initial_capital": 10_000,
    "max_positions": 3,
    "strong_signal_threshold": 70,
    "medium_signal_threshold": 50,
    "strong_position_pct": 0.32,   # 총 자본 대비
    "medium_position_pct": 0.22,
    "slippage_cost": 0.001,        # 거래당 0.1%
    "hard_stop_pct": -0.15,        # -15% 하드 스탑
}

# 기존 슈퍼사이클 16종목 (보존용 — 실험10 재현 등에 사용)
LEGACY_TICKERS = [
    "NVDA", "PLTR", "ANET", "MRVL", "AVGO",
    "MU", "WDC",
    "CEG", "VST", "NRG",
    "AXON", "HWM", "KTOS", "RKLB",
    "HOOD", "COIN",
]

BENCHMARK = "SPY"

# 섹터 ETF 매핑 (종목 → 대표 섹터 ETF)
SECTOR_ETF_MAP = {
    "NVDA": "XLK", "PLTR": "XLK", "ANET": "XLK", "MRVL": "XLK", "AVGO": "XLK",
    "MU":   "XLK", "WDC":  "XLK",
    "CEG":  "XLU", "VST":  "XLU", "NRG":  "XLU",
    "AXON": "XLI", "HWM":  "XLI", "KTOS": "XLI", "RKLB": "XLI",
    "HOOD": "XLF", "COIN": "XLF",
}
SECTOR_ETFS = list(set(SECTOR_ETF_MAP.values()))  # ["XLK", "XLU", "XLI", "XLF"]


def get_nasdaq100_tickers():
    """나스닥100 구성종목 반환 (2025년 기준 하드코딩 — 분기별 수동 업데이트)."""
    tickers = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
        "NFLX", "ASML", "AMD", "PEP", "CSCO", "ADBE", "TMUS", "TXN", "QCOM", "INTU",
        "AMAT", "ISRG", "AMGN", "HON", "BKNG", "VRTX", "ADP", "MU", "LRCX", "REGN",
        "PANW", "SBUX", "GILD", "ADI", "MDLZ", "MELI", "INTC", "KLAC", "SNPS", "CDNS",
        "ABNB", "CEG", "CTAS", "CRWD", "CSX", "DXCM", "EA", "EXC", "FAST", "FTNT",
        "GFS", "IDXX", "ILMN", "KDP", "KHC", "LULU", "MAR", "MCHP", "MNST", "MRNA",
        "MRVL", "MSCI", "NXPI", "ODFL", "ON", "ORLY", "PAYX", "PCAR", "PDD", "ROST",
        "ROP", "SIRI", "SPLK", "TEAM", "TTD", "TTWO", "TXN", "VRSK", "WDAY", "WBA",
        "WBD", "XCEL", "ZS", "ANET", "BIIB", "DDOG", "FANG", "GEHC", "GFS", "SMCI",
        "PLTR", "APP", "HOOD", "COIN", "ARM", "AXON", "RKLB", "KTOS", "HWM", "VST",
    ]
    # 중복 제거
    tickers = list(dict.fromkeys(tickers))
    print(f"  나스닥100 종목 수: {len(tickers)}개 (하드코딩)")
    return tickers


# 기본 유니버스 — 실행 시점에 동적으로 교체 가능
UNIVERSE_TICKERS = LEGACY_TICKERS


# ─────────────────────────────────────────────
# 1. 데이터 로드
# ─────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def load_data(tickers, period_years=5):
    os.makedirs(DATA_DIR, exist_ok=True)
    end = datetime.today()
    start = end - timedelta(days=period_years * 365 + 60)

    # CSV 캐시 확인 — 있으면 로드, 없는 종목만 yfinance 다운로드
    all_tickers = list(dict.fromkeys(tickers + SECTOR_ETFS + [BENCHMARK]))
    cached, to_download = {}, []
    for ticker in all_tickers:
        csv_path = os.path.join(DATA_DIR, f"{ticker}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            # 캐시 데이터가 요청 기간을 충분히 커버하는지 확인
            if len(df) > 200 and len(df) >= period_years * 240:
                cached[ticker] = df
            else:
                to_download.append(ticker)
        else:
            to_download.append(ticker)

    if to_download:
        print(f"데이터 다운로드 중... ({len(to_download)}개 종목 - 신규/미캐시)")
        raw = yf.download(to_download, start=start, end=end,
                          auto_adjust=True, progress=False)
        for ticker in to_download:
            try:
                df = raw.copy() if len(to_download) == 1 else raw.xs(ticker, axis=1, level=1).dropna(how='all')
                if len(df) > 200:
                    df.to_csv(os.path.join(DATA_DIR, f"{ticker}.csv"))
                    cached[ticker] = df
            except Exception:
                pass
    else:
        print(f"데이터 캐시 로드 중... ({len(cached)}개 종목)")

    price_data = {t: cached[t] for t in all_tickers if t in cached}
    print(f"  → {len(price_data) - 1}개 종목 로드 완료")
    return price_data


# ─────────────────────────────────────────────
# 2. 유니버스 선정 (모멘텀 필터)
# ─────────────────────────────────────────────
def _sector_etf_ok(ticker, price_data, date, sector_filter):
    """섹터 ETF 모멘텀 필터 판단.
    sector_filter:
      'none'     — 필터 없음
      'absolute' — 섹터 ETF 3개월 수익률 > 0
      'relative' — 섹터 ETF 3개월 수익률 > SPY 3개월 수익률
    """
    if sector_filter == 'none':
        return True
    etf = SECTOR_ETF_MAP.get(ticker)
    if etf is None or etf not in price_data:
        return True  # 매핑 없으면 통과
    etf_df = price_data[etf]
    if date not in etf_df.index:
        return True
    idx = etf_df.index.get_loc(date)
    if idx < 63:
        return True
    etf_ret = etf_df['Close'].iloc[idx] / etf_df['Close'].iloc[idx - 63] - 1
    if sector_filter == 'absolute':
        return etf_ret > 0
    # relative: SPY 3개월 수익률과 비교
    spy_df = price_data.get(BENCHMARK)
    if spy_df is None or date not in spy_df.index:
        return True
    spy_idx = spy_df.index.get_loc(date)
    if spy_idx < 63:
        return True
    spy_ret = spy_df['Close'].iloc[spy_idx] / spy_df['Close'].iloc[spy_idx - 63] - 1
    return etf_ret > spy_ret


def get_universe(price_data, date, sector_filter='none'):
    candidates = []

    for ticker, df in price_data.items():
        if ticker == BENCHMARK:
            continue
        if ticker in SECTOR_ETFS:
            continue
        if date not in df.index:
            continue

        idx = df.index.get_loc(date)
        if idx < 252:
            continue

        close = df['Close']
        volume = df['Volume']
        current_close = close.iloc[idx]

        # 52주 신고가 대비 -5% 이내 (기존 -10%에서 강화 — 추세 지속 종목만)
        high_52w = close.iloc[idx - 252:idx].max()
        if current_close < high_52w * 0.95:
            continue

        # 최근 3개월 수익률
        ret_3m = current_close / close.iloc[idx - 63] - 1

        # 6개월 수익률도 양수여야 함 (단기 반등이 아닌 중기 추세 확인)
        if idx >= 126:
            ret_6m = current_close / close.iloc[idx - 126] - 1
            if ret_6m <= 0:
                continue

        # 일평균 거래대금 $50M 이상
        avg_dollar_vol = (close.iloc[idx - 20:idx] * volume.iloc[idx - 20:idx]).mean()
        if avg_dollar_vol < 50_000_000:
            continue

        # 섹터 ETF 모멘텀 필터
        if not _sector_etf_ok(ticker, price_data, date, sector_filter):
            continue

        candidates.append({"ticker": ticker, "ret_3m": ret_3m})

    if not candidates:
        return []

    cand_df = pd.DataFrame(candidates).sort_values('ret_3m', ascending=False)
    # 모멘텀 상위 30종목 고정 (유니버스 크기 명시적 제어)
    filtered = cand_df.head(30)['ticker'].tolist()
    return filtered


# ─────────────────────────────────────────────
# 3. 팩터 점수 계산
# ─────────────────────────────────────────────
def calculate_signal_score(df, idx):
    score = 0
    factors = {}

    close = df['Close']
    volume = df['Volume']

    # ── 기술적 팩터 (60점 만점) ──

    # 52주 신고가 돌파 (+20)
    if idx >= 252:
        high_52w = close.iloc[idx - 252:idx].max()
        if close.iloc[idx] >= high_52w:
            score += 20
            factors['52w_breakout'] = 20
        else:
            factors['52w_breakout'] = 0

    # MA 정배열 (+15): 20 > 50 > 200
    if idx >= 200:
        ma20 = close.iloc[idx - 20:idx].mean()
        ma50 = close.iloc[idx - 50:idx].mean()
        ma200 = close.iloc[idx - 200:idx].mean()
        if ma20 > ma50 > ma200:
            score += 15
            factors['ma_alignment'] = 15
        else:
            factors['ma_alignment'] = 0
    else:
        factors['ma_alignment'] = 0

    # MACD 골든크로스 (+10)
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
            factors['macd_cross'] = 10
        else:
            factors['macd_cross'] = 0
    else:
        factors['macd_cross'] = 0

    # RSI 50~70 구간 (+10)
    if idx >= 14:
        delta = close.diff().iloc[idx - 13:idx + 1]
        gain = delta.clip(lower=0).mean()
        loss = (-delta.clip(upper=0)).mean()
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - 100 / (1 + rs)
        if 50 <= rsi <= 70:
            score += 10
            factors['rsi'] = 10
        else:
            factors['rsi'] = 0
    else:
        factors['rsi'] = 0

    # 거래량 급증 (+5): 20일 평균의 1.5배 이상
    if idx >= 20:
        avg_vol = volume.iloc[idx - 20:idx].mean()
        if volume.iloc[idx] >= avg_vol * 1.5:
            score += 5
            factors['volume_surge'] = 5
        else:
            factors['volume_surge'] = 0
    else:
        factors['volume_surge'] = 0

    # ── 펀더멘털 팩터 (40점 만점) ──
    # yfinance 펀더멘털 데이터는 품질이 불안정하므로
    # 접근 실패 시 기술적 팩터(60점)로 정규화
    fundamental_available = False
    try:
        ticker_obj = yf.Ticker(df.attrs.get('ticker', ''))
        financials = ticker_obj.quarterly_financials
        if financials is not None and not financials.empty:
            # 매출 성장률 YoY (+15)
            if 'Total Revenue' in financials.index and financials.shape[1] >= 5:
                rev_recent = financials.loc['Total Revenue'].iloc[0]
                rev_year_ago = financials.loc['Total Revenue'].iloc[4]
                if rev_year_ago and rev_year_ago != 0:
                    rev_growth = (rev_recent - rev_year_ago) / abs(rev_year_ago)
                    if rev_growth >= 0.15:
                        score += 15
                        factors['revenue_growth'] = 15
                    else:
                        factors['revenue_growth'] = 0
                    fundamental_available = True
    except Exception:
        pass

    if not fundamental_available:
        # 기술적 팩터만으로 100점 만점 정규화
        tech_score = score
        score = round(tech_score / 60 * 100)
        factors['normalized'] = True
    else:
        factors['normalized'] = False

    return min(score, 100), factors


# ─────────────────────────────────────────────
# 4. 포지션 관리 클래스
# ─────────────────────────────────────────────
class Position:
    def __init__(self, ticker, signal_strength, entry_price, shares, capital_allocated, date):
        self.ticker = ticker
        self.signal_strength = signal_strength  # 'strong' | 'medium'
        self.avg_price = entry_price
        self.shares = shares
        self.capital_allocated = capital_allocated
        self.entry_date = date
        self.tranches = [{"shares": shares, "price": entry_price, "date": date, "tranche": 1}]
        self.next_tranche = 2
        self.sold_pct = 0.0  # 이미 매도한 비율
        self.peak_price = entry_price  # 트레일링 스탑용 고점 추적

    def add_tranche(self, shares, price, date):
        total_cost = self.avg_price * self.shares + price * shares
        self.shares += shares
        self.avg_price = total_cost / self.shares
        self.tranches.append({"shares": shares, "price": price, "date": date, "tranche": self.next_tranche})
        self.next_tranche += 1

    def current_value(self, price):
        return self.shares * price

    def pnl_pct(self, price):
        return (price - self.avg_price) / self.avg_price


class PortfolioManager:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.positions = {}   # ticker -> Position
        self.trade_log = []   # 거래 기록
        self.equity_curve = []  # (date, total_equity)

    def total_equity(self, price_snapshot):
        equity = self.cash
        for ticker, pos in self.positions.items():
            if ticker in price_snapshot:
                equity += pos.current_value(price_snapshot[ticker])
        return equity

    def position_count(self):
        return len(self.positions)

    def _buy_cost(self, shares, price):
        return shares * price * (1 + CONFIG['slippage_cost'])

    def _sell_proceeds(self, shares, price):
        return shares * price * (1 - CONFIG['slippage_cost'])

    def current_total_equity(self, price_snapshot):
        return self.total_equity(price_snapshot)

    def buy(self, ticker, price, signal_strength, date, tranche=1, price_snapshot=None, capital_override=None):
        # 현재 총자산 기준으로 포지션 크기 결정 (복리 반영)
        current_equity = self.total_equity(price_snapshot) if price_snapshot else self.cash

        if tranche == 1:
            if capital_override is not None:
                # ATR 사이징: 1차 진입금액을 외부에서 계산해 전달
                target_capital = capital_override
                capital_to_use = min(capital_override, self.cash * 0.95)
            else:
                if signal_strength == 'strong':
                    target_capital = current_equity * CONFIG['strong_position_pct']
                    first_pct = 0.50
                else:
                    target_capital = current_equity * CONFIG['medium_position_pct']
                    first_pct = 0.40
                capital_to_use = min(target_capital * first_pct, self.cash * 0.95)
            if capital_to_use < 100:
                return False

            shares = int(capital_to_use / price)
            if shares == 0:
                return False

            cost = self._buy_cost(shares, price)
            if cost > self.cash:
                return False

            self.cash -= cost
            self.positions[ticker] = Position(ticker, signal_strength, price, shares, target_capital, date)
            self.trade_log.append({
                "date": date, "ticker": ticker, "action": "BUY_T1",
                "price": price, "shares": shares, "signal": signal_strength
            })
            return True

        elif ticker in self.positions:
            pos = self.positions[ticker]
            if pos.next_tranche != tranche:
                return False

            if signal_strength == 'strong':
                pct_map = {2: 0.30, 3: 0.20}
            else:
                pct_map = {2: 0.60}

            alloc_pct = pct_map.get(tranche, 0)
            capital_to_use = min(pos.capital_allocated * alloc_pct, self.cash * 0.95)
            if capital_to_use < 100:
                return False

            shares = int(capital_to_use / price)
            if shares == 0:
                return False

            cost = self._buy_cost(shares, price)
            if cost > self.cash:
                return False

            self.cash -= cost
            pos.add_tranche(shares, price, date)
            self.trade_log.append({
                "date": date, "ticker": ticker, "action": f"BUY_T{tranche}",
                "price": price, "shares": shares, "signal": signal_strength
            })
            return True

        return False

    def sell_partial(self, ticker, price, sell_ratio, reason, date):
        if ticker not in self.positions:
            return
        pos = self.positions[ticker]
        shares_to_sell = int(pos.shares * sell_ratio)
        if shares_to_sell == 0:
            return

        proceeds = self._sell_proceeds(shares_to_sell, price)
        self.cash += proceeds
        pos.shares -= shares_to_sell

        pnl = (price - pos.avg_price) / pos.avg_price * 100
        self.trade_log.append({
            "date": date, "ticker": ticker, "action": f"SELL_{reason}",
            "price": price, "shares": shares_to_sell, "pnl_pct": pnl
        })

        if pos.shares <= 0:
            del self.positions[ticker]

    def sell_all(self, ticker, price, reason, date):
        if ticker not in self.positions:
            return
        self.sell_partial(ticker, price, 1.0, reason, date)


# ─────────────────────────────────────────────
# 5. 매도 조건 판단
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


def calc_adx(df, idx, period=14):
    """Wilder's ADX (0~100). pandas EWM alpha=1/period 방식."""
    need = period * 3
    if idx < need:
        return 0
    alpha = 1.0 / period
    high  = df['High'].iloc[idx - need:idx + 1]
    low   = df['Low'].iloc[idx - need:idx + 1]
    close = df['Close'].iloc[idx - need:idx + 1]

    up   = high.diff()
    down = -low.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)[1:]
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)[1:]
    tr_arr = pd.concat([
        high.diff().abs(),
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1).iloc[1:].values

    # Wilder smoothing: EWM with adjust=False, alpha=1/period
    def ws(arr):
        s = pd.Series(arr).ewm(alpha=alpha, adjust=False).mean().values
        return s

    atr_s  = ws(tr_arr)
    pdm_s  = ws(plus_dm)
    mdm_s  = ws(minus_dm)

    with np.errstate(divide='ignore', invalid='ignore'):
        pdi = np.where(atr_s > 0, 100 * pdm_s / atr_s, 0.0)
        mdi = np.where(atr_s > 0, 100 * mdm_s / atr_s, 0.0)
        dx  = np.where((pdi + mdi) > 0, 100 * np.abs(pdi - mdi) / (pdi + mdi), 0.0)

    adx = pd.Series(dx).ewm(alpha=alpha, adjust=False).mean().iloc[-1]
    return float(np.clip(adx, 0, 100))


# stop_mode: 'pct8' | 'pct12' | 'atr'
# exit_mode: 'current' | 'fast' | 'confirm' | 'hybrid' | 'ma20_simple'
def check_sell_signals(df, idx, pos, stop_mode='pct12', exit_mode='current', trailing_stop=False, use_macd_rsi_exit=True):
    close = df['Close']
    current = close.iloc[idx]
    signals = []

    # ── 하드 스탑 ──
    if stop_mode == 'pct8':
        triggered = pos.pnl_pct(current) <= -0.08
    elif stop_mode == 'pct12':
        triggered = pos.pnl_pct(current) <= -0.12
    else:  # atr
        if idx >= 15:
            atr = calc_atr(df, idx)
            stop_price = pos.avg_price - atr * 2.5
            triggered = current <= stop_price
        else:
            triggered = pos.pnl_pct(current) <= -0.12

    if triggered:
        return [('HARD_STOP', 1.0)]

    # ── 트레일링 스탑 ──
    # trailing_stop: False | 'original' | 'A' | 'B' | 'C'
    #   original : +10%→BEP / +20%→고점-10% / +40%→고점-15%
    #   A        : +10%→BEP / +20%→고점-12% / +40%→고점-18%                  (쿠션 소폭 확대)
    #   B        : +10%→BEP / +20%→고점-10% / +40%→고점-15% / +100%→고점-20% / +200%→고점-25%  (고구간 추가)
    #   C        : +10%→BEP / +20%→고점-12% / +40%→고점-18% / +100%→고점-20% / +200%→고점-25%  (A+B 조합)
    if trailing_stop:
        if current > pos.peak_price:
            pos.peak_price = current
        pnl = pos.pnl_pct(current)
        mode = trailing_stop  # 'original' | 'A' | 'B' | 'C'

        if mode == 'original':
            if pnl >= 0.40:
                trail_price = pos.peak_price * 0.85
            elif pnl >= 0.20:
                trail_price = pos.peak_price * 0.90
            elif pnl >= 0.10:
                trail_price = pos.avg_price
            else:
                trail_price = None
        elif mode == 'A':
            if pnl >= 0.40:
                trail_price = pos.peak_price * 0.82
            elif pnl >= 0.20:
                trail_price = pos.peak_price * 0.88
            elif pnl >= 0.10:
                trail_price = pos.avg_price
            else:
                trail_price = None
        elif mode == 'B':
            if pnl >= 2.00:
                trail_price = pos.peak_price * 0.75
            elif pnl >= 1.00:
                trail_price = pos.peak_price * 0.80
            elif pnl >= 0.40:
                trail_price = pos.peak_price * 0.85
            elif pnl >= 0.20:
                trail_price = pos.peak_price * 0.90
            elif pnl >= 0.10:
                trail_price = pos.avg_price
            else:
                trail_price = None
        elif mode == 'C':
            if pnl >= 2.00:
                trail_price = pos.peak_price * 0.75
            elif pnl >= 1.00:
                trail_price = pos.peak_price * 0.80
            elif pnl >= 0.40:
                trail_price = pos.peak_price * 0.82
            elif pnl >= 0.20:
                trail_price = pos.peak_price * 0.88
            elif pnl >= 0.10:
                trail_price = pos.avg_price
            else:
                trail_price = None
        else:
            trail_price = None

        if trail_price is not None and current <= trail_price:
            return [('TRAIL_STOP', 1.0)]

    # MACD 데드크로스 + RSI 50 하향
    if use_macd_rsi_exit and idx >= 35:
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

    # MA 청산 로직 — exit_mode로 방식 선택
    if idx >= 20:
        ma5  = close.iloc[idx - 5:idx + 1].mean()
        ma10 = close.iloc[idx - 10:idx + 1].mean()
        ma20 = close.iloc[idx - 20:idx + 1].mean()

        if exit_mode == 'current':
            # 기존: 단계적 부분 청산
            if current < ma20 and pos.sold_pct < 1.00:
                signals.append(('MA20_BREAK', 1.0))
            elif current < ma10 and pos.sold_pct < 0.60:
                signals.append(('MA10_BREAK', 0.30))
            elif current < ma5 and pos.sold_pct < 0.30:
                signals.append(('MA5_BREAK', 0.30))

        elif exit_mode == 'fast':
            # 옵션A: MA10 이탈 즉시 전량 청산
            if current < ma10:
                signals.append(('MA10_ALL', 1.0))

        elif exit_mode == 'confirm':
            # 옵션B: MA20 3일 연속 이탈 확인 후 전량 청산
            if idx >= 23:
                below_ma20_streak = all(
                    close.iloc[idx - i] < close.iloc[idx - 20 - i:idx - i + 1].mean()
                    for i in range(3)
                )
                if below_ma20_streak:
                    signals.append(('MA20_CONFIRM', 1.0))
                elif current < ma10 and pos.sold_pct < 0.60:
                    signals.append(('MA10_BREAK', 0.30))
                elif current < ma5 and pos.sold_pct < 0.30:
                    signals.append(('MA5_BREAK', 0.30))

        elif exit_mode == 'hybrid':
            # 하이브리드: MA10 이탈 시 50% 청산 + MA20 3일 연속 이탈 시 잔여 전량 청산
            if idx >= 23:
                below_ma20_streak = all(
                    close.iloc[idx - i] < close.iloc[idx - 20 - i:idx - i + 1].mean()
                    for i in range(3)
                )
                if below_ma20_streak and pos.sold_pct >= 0.50:
                    # MA20 3일 연속 이탈 → 잔여 전량 청산
                    signals.append(('MA20_HYBRID_ALL', 1.0))
                elif below_ma20_streak and pos.sold_pct < 0.50:
                    # MA10도 안 팔렸는데 MA20 확인 → 바로 전량
                    signals.append(('MA20_HYBRID_ALL', 1.0))
                elif current < ma10 and pos.sold_pct < 0.50:
                    # MA10 첫 이탈 → 50% 청산
                    signals.append(('MA10_HYBRID_HALF', 0.50))

        elif exit_mode == 'ma20_simple':
            # 가장 단순: MA20 이탈 즉시 전량 청산 (부분청산/MA10/MA5 없음)
            if current < ma20:
                signals.append(('MA20_SIMPLE', 1.0))

    return signals


# ─────────────────────────────────────────────
# 6. 메인 백테스팅 루프
# ─────────────────────────────────────────────
# bear_filter 옵션:
#   'none'   — 필터 없음 (기존)
#   'block'  — SPY 200일선 아래면 신규 진입 완전 차단
#   'strict' — SPY 200일선 아래면 Strong(70점+) 신호만 진입 허용
def run_backtest(price_data, portfolio, bear_filter='none', stop_mode='pct12', exit_mode='current', heat_cap=False, atr_sizing=False, atr_risk_pct=0.025, atr_position_cap=0.40, trailing_stop=False, spy_ma_period=200, sector_filter='none', adx_threshold=0, min_hold_days=0):
    benchmark_df = price_data[BENCHMARK]

    # 공통 거래일 인덱스 생성
    start_date = benchmark_df.index[252]  # MA 계산 여유
    trading_days = benchmark_df.index[benchmark_df.index >= start_date]

    pending_tranches = {}

    print(f"\n[bear_filter={bear_filter}, SPY MA{spy_ma_period}] 백테스팅 시작: {trading_days[0].date()} ~ {trading_days[-1].date()}")
    print(f"초기 자본: ${portfolio.initial_capital:,.0f}")
    print("-" * 50)

    current_universe = []
    last_universe_update = None

    for date in trading_days:
        price_snapshot = {}
        for ticker, df in price_data.items():
            if date in df.index:
                price_snapshot[ticker] = df.loc[date, 'Close']

        # ── SPY MA 상태 판단 ──
        spy_above_ma200 = True
        if bear_filter != 'none':
            spy_idx = benchmark_df.index.get_loc(date)
            if spy_idx >= spy_ma_period:
                spy_ma = benchmark_df['Close'].iloc[spy_idx - spy_ma_period:spy_idx].mean()
                spy_above_ma200 = benchmark_df['Close'].iloc[spy_idx] >= spy_ma

        # ── 유니버스 업데이트 (월 1회) ──
        if last_universe_update is None or (date - last_universe_update).days >= 21:
            current_universe = get_universe(price_data, date, sector_filter=sector_filter)
            last_universe_update = date

        # ── 기존 포지션 매도 판단 ──
        for ticker in list(portfolio.positions.keys()):
            if ticker not in price_data or date not in price_data[ticker].index:
                continue
            df = price_data[ticker]
            idx = df.index.get_loc(date)
            pos = portfolio.positions[ticker]

            # 최소 보유 기간 미달 시 하드스탑/트레일링 외 청산 신호 무시
            hold_days = (date - pos.entry_date).days if min_hold_days > 0 else 0

            sell_signals = check_sell_signals(df, idx, pos, stop_mode=stop_mode, exit_mode=exit_mode, trailing_stop=trailing_stop)
            if min_hold_days > 0 and hold_days < min_hold_days:
                sell_signals = [(r, ratio) for r, ratio in sell_signals if r in ('HARD_STOP', 'TRAIL_STOP')]

            for reason, ratio in sell_signals:
                if reason in ('HARD_STOP', 'TRAIL_STOP', 'MACD_RSI_EXIT', 'MA20_BREAK', 'MA10_ALL', 'MA20_CONFIRM', 'MA20_HYBRID_ALL'):
                    portfolio.sell_all(ticker, price_snapshot[ticker], reason, date)
                    pending_tranches.pop(ticker, None)
                    break
                else:
                    portfolio.sell_partial(ticker, price_snapshot[ticker], ratio, reason, date)
                    if ticker in portfolio.positions:
                        portfolio.positions[ticker].sold_pct += ratio

        # ── 추가 매수 (2차, 3차 트랜치) ──
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
                # 2차: 5일 후, 주가가 1차 매수가 이상
                if current_price >= pos.tranches[0]['price']:
                    portfolio.buy(ticker, current_price, pos.signal_strength, date, tranche=2, price_snapshot=price_snapshot)
                    # 3차 대기 등록 (strong만)
                    if pos.signal_strength == 'strong':
                        pending_tranches[ticker] = {
                            "tranche": 3,
                            "trigger_date": date + timedelta(days=14),
                        }
                    else:
                        pending_tranches.pop(ticker, None)

            elif pt['tranche'] == 3:
                # 3차: 20일선 위에서 눌림 후 재상승
                if idx >= 20:
                    ma20 = df['Close'].iloc[idx - 20:idx].mean()
                    if current_price > ma20:
                        portfolio.buy(ticker, current_price, pos.signal_strength, date, tranche=3, price_snapshot=price_snapshot)
                        pending_tranches.pop(ticker, None)

        # ── 신규 진입 ──
        # Portfolio Heat Cap: 기존 포지션 미실현 손실 합계가 총자산의 -15% 초과 시 진입 차단
        heat_ok = True
        if heat_cap and portfolio.positions:
            total_eq = portfolio.total_equity(price_snapshot)
            total_unrealized_pct = sum(
                pos_p.pnl_pct(price_snapshot[t]) * (pos_p.current_value(price_snapshot[t]) / total_eq)
                for t, pos_p in portfolio.positions.items()
                if price_snapshot.get(t)
            )
            heat_ok = total_unrealized_pct >= -0.15

        if heat_ok and portfolio.position_count() < CONFIG['max_positions']:
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

                score, _ = calculate_signal_score(df, idx)

                if score >= CONFIG['strong_signal_threshold']:
                    strength = 'strong'
                elif score >= CONFIG['medium_signal_threshold'] and spy_above_ma200:
                    # block: medium 신호는 SPY 200일선 위에서만
                    # strict: 200일선 아래면 이 분기 자체가 안 탐 (strong만 통과)
                    strength = 'medium'
                else:
                    continue

                # block 모드: 200일선 아래면 strong도 차단
                if bear_filter == 'block' and not spy_above_ma200:
                    continue

                # ADX 추세 강도 필터 (adx_threshold=0이면 비활성)
                if adx_threshold > 0 and idx >= 28:
                    if calc_adx(df, idx) < adx_threshold:
                        continue

                entry_price = price_snapshot.get(ticker)
                if entry_price is None:
                    continue

                # ATR 기반 포지션 사이징: 1트랜치에서 포트폴리오의 1%를 리스크로 설정
                cap_override = None
                if atr_sizing and idx >= 15:
                    atr = calc_atr(df, idx)
                    stop_dist_pct = (atr * 2.5) / entry_price
                    if stop_dist_pct > 0:
                        current_eq = portfolio.total_equity(price_snapshot)
                        cap_override = (current_eq * atr_risk_pct) / stop_dist_pct
                        # 최소 $200, 최대 총자산의 atr_position_cap 캡
                        cap_override = max(200, min(cap_override, current_eq * atr_position_cap))

                success = portfolio.buy(ticker, entry_price, strength, date, tranche=1,
                                        price_snapshot=price_snapshot, capital_override=cap_override)
                if success:
                    pending_tranches[ticker] = {
                        "tranche": 2,
                        "trigger_date": date + timedelta(days=5),
                    }

        # ── 자산 곡선 기록 ──
        equity = portfolio.total_equity(price_snapshot)
        portfolio.equity_curve.append({"date": date, "equity": equity})

    print(f"백테스팅 완료. 총 거래 횟수: {len(portfolio.trade_log)}건")


# ─────────────────────────────────────────────
# 7. 결과 지표 계산
# ─────────────────────────────────────────────
def compute_metrics(portfolio, price_data):
    ec = pd.DataFrame(portfolio.equity_curve).set_index('date')
    ec.index = pd.to_datetime(ec.index)

    # 벤치마크 (SPY Buy & Hold)
    spy = price_data[BENCHMARK]['Close']
    spy_start = spy.loc[spy.index >= ec.index[0]].iloc[0]
    spy_curve = spy.loc[spy.index >= ec.index[0]] / spy_start * CONFIG['initial_capital']

    years = (ec.index[-1] - ec.index[0]).days / 365
    final_equity = ec['equity'].iloc[-1]
    total_return = (final_equity / CONFIG['initial_capital'] - 1) * 100
    cagr = ((final_equity / CONFIG['initial_capital']) ** (1 / years) - 1) * 100

    # MDD
    rolling_max = ec['equity'].cummax()
    drawdown = (ec['equity'] - rolling_max) / rolling_max
    mdd = drawdown.min() * 100

    # 샤프 비율 (연율화, 무위험 금리 4%)
    daily_ret = ec['equity'].pct_change().dropna()
    sharpe = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * np.sqrt(252))

    # SPY 수익률
    spy_return = (spy_curve.iloc[-1] / CONFIG['initial_capital'] - 1) * 100

    # 거래 통계
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
    }

    return metrics, ec, spy_curve


# ─────────────────────────────────────────────
# 8. 결과 출력 및 시각화
# ─────────────────────────────────────────────
def print_metrics(metrics):
    print("\n" + "=" * 55)
    print("  백테스팅 결과 요약")
    print("=" * 55)
    print(f"  총 수익률:          {metrics['total_return']:>8.1f}%")
    print(f"  SPY Buy&Hold:       {metrics['spy_return']:>8.1f}%")
    print(f"  초과 수익:          {metrics['total_return'] - metrics['spy_return']:>+8.1f}%")
    print(f"  CAGR (연평균):      {metrics['cagr']:>8.1f}%")
    print(f"  MDD (최대 낙폭):    {metrics['mdd']:>8.1f}%")
    print(f"  샤프 비율:          {metrics['sharpe']:>8.2f}")
    print(f"  승률:               {metrics['win_rate']:>8.1f}%")
    print(f"  평균 수익 (승):     {metrics['avg_win']:>+8.1f}%")
    print(f"  평균 손실 (패):     {metrics['avg_loss']:>+8.1f}%")
    print(f"  손익비:             {metrics['rr_ratio']:>8.2f}")
    print(f"  총 거래 횟수:       {metrics['total_trades']:>8}건")
    print(f"  청산 거래 횟수:     {metrics['sell_trades']:>8}건")
    print("=" * 55)


def plot_comparison(results, spy_curve, title="백테스트 비교 — 슈퍼사이클 종목 (5Y)"):
    """results: [{"label": str, "ec": df, "metrics": dict, "trades": list}]"""
    fig, axes = plt.subplots(3, 1, figsize=(15, 13))
    fig.suptitle(title, fontsize=14, fontweight='bold')

    colors = ['steelblue', 'seagreen', 'darkorange', 'mediumpurple', 'crimson', 'teal', 'goldenrod']

    # ── 1) 수익률 곡선 ──
    ax1 = axes[0]
    spy_aligned = spy_curve.reindex(results[0]['ec'].index, method='ffill')
    ax1.plot(spy_aligned.index, spy_aligned.values, label='SPY Buy&Hold',
             color='lightgray', linewidth=1.5, linestyle='--')
    for r, c in zip(results, colors):
        m = r['metrics']
        ax1.plot(r['ec'].index, r['ec']['equity'],
                 label=f"{r['label']}  ({m['total_return']:+.1f}%  샤프={m['sharpe']:.2f})",
                 color=c, linewidth=2)
    ax1.set_title("Portfolio Equity vs SPY")
    ax1.set_ylabel("Equity ($)")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # ── 2) 드로우다운 ──
    ax2 = axes[1]
    for r, c in zip(results, colors):
        rolling_max = r['ec']['equity'].cummax()
        dd = (r['ec']['equity'] - rolling_max) / rolling_max * 100
        ax2.plot(r['ec'].index, dd, label=f"{r['label']}  MDD={r['metrics']['mdd']:.1f}%",
                 color=c, linewidth=1.5)
    ax2.fill_between(results[0]['ec'].index,
                     (results[0]['ec']['equity'] - results[0]['ec']['equity'].cummax()) /
                     results[0]['ec']['equity'].cummax() * 100,
                     0, color=colors[0], alpha=0.1)
    ax2.set_title("Drawdown 비교")
    ax2.set_ylabel("Drawdown (%)")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    # ── 3) 지표 비교 테이블 ──
    ax3 = axes[2]
    ax3.axis('off')
    labels = ['총수익률', 'CAGR', 'MDD', '샤프비율', '승률', '손익비', '거래수(청산)']
    table_data = [labels]
    for r in results:
        m = r['metrics']
        table_data.append([
            f"{m['total_return']:+.1f}%",
            f"{m['cagr']:.1f}%",
            f"{m['mdd']:.1f}%",
            f"{m['sharpe']:.2f}",
            f"{m['win_rate']:.1f}%",
            f"{m['rr_ratio']:.2f}",
            f"{m['sell_trades']}건",
        ])
    col_labels = ['지표'] + [r['label'] for r in results]
    tbl = ax3.table(
        cellText=list(zip(*table_data)),
        colLabels=col_labels,
        cellLoc='center', loc='center'
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.8)
    ax3.set_title("지표 비교", pad=12)

    plt.tight_layout()
    plt.savefig("backtest_result.png", dpi=150, bbox_inches='tight')
    print("\n  차트 저장: backtest_result.png")
    plt.show()


# ─────────────────────────────────────────────
# 9. 종목별 PnL 분해
# ─────────────────────────────────────────────
def analyze_ticker_pnl(trade_log, price_data, initial_capital):
    trades = pd.DataFrame(trade_log)
    if trades.empty:
        return

    buy_trades  = trades[trades['action'].str.startswith('BUY')].copy()
    sell_trades = trades[trades['action'].str.startswith('SELL')].copy()

    stats = {}
    for ticker in [t for t in price_data if t != BENCHMARK]:
        buys  = buy_trades[buy_trades['ticker'] == ticker]
        sells = sell_trades[sell_trades['ticker'] == ticker]

        invested = (buys['price'] * buys['shares']).sum() * (1 + CONFIG['slippage_cost'])
        proceeds = (sells['price'] * sells['shares']).sum() * (1 - CONFIG['slippage_cost'])

        # 백테스트 종료 시점에 미청산 포지션이 남아있으면 마지막 가격으로 평가
        remaining_shares = buys['shares'].sum() - sells['shares'].sum()
        if remaining_shares > 1 and ticker in price_data:
            last_price = price_data[ticker]['Close'].iloc[-1]
            proceeds += remaining_shares * last_price * (1 - CONFIG['slippage_cost'])
            open_pos = True
        else:
            open_pos = False

        pnl_dollar = proceeds - invested
        pnl_pct    = pnl_dollar / invested * 100 if invested > 0 else 0
        contrib    = pnl_dollar / initial_capital * 100  # 전체 수익률 기여도

        n_entries  = len(buys[buys['action'] == 'BUY_T1'])
        n_wins     = len(sells[sells['pnl_pct'] > 0]) if 'pnl_pct' in sells.columns else 0
        n_sells    = len(sells)
        win_rate   = n_wins / n_sells * 100 if n_sells > 0 else 0

        stats[ticker] = {
            'invested':     invested,
            'pnl_dollar':   pnl_dollar,
            'pnl_pct':      pnl_pct,
            'contrib_pct':  contrib,
            'n_entries':    n_entries,
            'n_sells':      n_sells,
            'win_rate':     win_rate,
            'open_pos':     open_pos,
        }

    df = pd.DataFrame(stats).T
    df = df[df['n_entries'] > 0].sort_values('contrib_pct', ascending=False)

    print("\n" + "=" * 75)
    print("  종목별 PnL 기여도 분석")
    print("=" * 75)
    print(f"  {'종목':<6}  {'기여도':>8}  {'PnL($)':>9}  {'수익률':>7}  {'진입':>4}  {'청산':>4}  {'승률':>6}  {'미결'}")
    print("  " + "-" * 70)
    for ticker, r in df.iterrows():
        flag = " ★" if r['open_pos'] else ""
        print(f"  {ticker:<6}  {r['contrib_pct']:>+7.1f}%  {r['pnl_dollar']:>+9,.0f}  "
              f"{r['pnl_pct']:>+6.1f}%  {int(r['n_entries']):>4}  {int(r['n_sells']):>4}  "
              f"{r['win_rate']:>5.0f}%{flag}")
    print("  " + "-" * 70)
    total_contrib = df['contrib_pct'].sum()
    total_pnl     = df['pnl_dollar'].sum()
    print(f"  {'합계':<6}  {total_contrib:>+7.1f}%  {total_pnl:>+9,.0f}")
    print("=" * 75)

    # 차트: 기여도 막대그래프
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle("종목별 PnL 기여도 분석", fontsize=13, fontweight='bold')

    colors_bar = ['seagreen' if v >= 0 else 'crimson' for v in df['contrib_pct']]
    axes[0].barh(df.index[::-1], df['contrib_pct'][::-1], color=colors_bar[::-1])
    axes[0].axvline(0, color='black', linewidth=0.8)
    axes[0].set_xlabel("전체 수익률 기여도 (%p)")
    axes[0].set_title("종목별 기여도 (%p)")
    axes[0].grid(True, axis='x', alpha=0.3)
    for i, (ticker, row) in enumerate(df[::-1].iterrows()):
        axes[0].text(row['contrib_pct'] + (0.3 if row['contrib_pct'] >= 0 else -0.3),
                     i, f"{row['contrib_pct']:+.1f}%", va='center',
                     ha='left' if row['contrib_pct'] >= 0 else 'right', fontsize=8)

    axes[1].barh(df.index[::-1], df['pnl_dollar'][::-1],
                 color=['seagreen' if v >= 0 else 'crimson' for v in df['pnl_dollar'][::-1]])
    axes[1].axvline(0, color='black', linewidth=0.8)
    axes[1].set_xlabel("PnL ($)")
    axes[1].set_title("종목별 절대 수익 ($)")
    axes[1].grid(True, axis='x', alpha=0.3)
    axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    plt.tight_layout()
    plt.savefig("ticker_pnl.png", dpi=150, bbox_inches='tight')
    print("  차트 저장: ticker_pnl.png")
    plt.show()


# ─────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # 실험21: 최소 보유 기간 스윕 (0/5/10/15일)
    # 진입 후 N 거래일 이내에는 하드스탑/트레일링 외 청산 신호 무시
    # 채택 파라미터 고정: bear=block MA200 / pct12 / hybrid / ATR 4% / 캡40% / trailing=original / max_positions=4 / ADX 20+
    price_data = load_data(LEGACY_TICKERS, 5)
    CONFIG['max_positions'] = 4

    results = []
    spy_curve = None

    for hold in [0, 3, 5, 10, 15]:
        label = f"기준 (hold=0)" if hold == 0 else f"min_hold={hold}일"
        portfolio = PortfolioManager(CONFIG['initial_capital'])
        run_backtest(price_data, portfolio, bear_filter='block', stop_mode='pct12', exit_mode='hybrid',
                     atr_sizing=True, atr_risk_pct=0.04, atr_position_cap=0.40,
                     trailing_stop='original', spy_ma_period=200, adx_threshold=20, min_hold_days=hold)
        metrics, ec, spy_crv = compute_metrics(portfolio, price_data)
        if spy_curve is None:
            spy_curve = spy_crv
        print_metrics(metrics)
        results.append({"label": label, "ec": ec, "metrics": metrics, "trades": portfolio.trade_log})

    plot_comparison(results, spy_curve, title="실험21: 최소 보유 기간 스윕 (0/5/10/15일) - 5Y")
