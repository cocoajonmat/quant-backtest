# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실험 기록 규칙

백테스트를 실행할 때마다 결과를 **전략별 CONTEXT 파일의 실험 로그**에 누적 기록한다.
새 대화에서 히스토리 파악이 필요하면 먼저 **CONTEXT.md(인덱스)**를 읽고, 해당 전략 파일로 이동한다.

- 슈퍼사이클 추세추종 실험 → `CONTEXT_supercycle.md`
- 일반 추세추종 실험 → `CONTEXT_trend.md`

## 실행

```powershell
python backtest.py
```

의존성 설치:
```powershell
pip install yfinance pandas numpy matplotlib
```

## 프로젝트 현황 (2026-05-09 기준)

미국 주식 추세추종 스윙 트레이딩 백테스팅 시스템. 슈퍼사이클 종목(최근 5년 5배+ 상승) 위주로 다중 팩터 점수화 후 분할 매수/매도.

**핵심 실험 결과 (5년, $10,000 초기자본, SPY +86.9%)**
| 전략 | 수익률 | CAGR | MDD | 샤프 |
|------|--------|------|-----|------|
| 초기 하이브리드 (실험1) | +188.4% | 29.0% | -16.8% | 1.27 |
| + 트레일링 스탑 (실험7) | +203.1% | 30.5% | -14.0% | 1.42 |
| + ATR 4% 사이징, 바이오 제외 (실험9B) | +537.5% | 56.0% | -29.8% | 1.63 |
| + MA200 block (실험10) | +480.0% | 52.5% | -22.0% | 1.56 |
| + max_positions=4 (실험17) | +553.6% | 57.0% | -16.8% | 1.71 |
| + ADX 20+ 필터 (실험19) | +593.7% | 59.2% | -18.4% | 1.73 |
| **+ 최소 보유 3일 (실험21, 현재 채택)** | **+606.9%** | **59.9%** | **-17.4%** | **1.76** |
| NDX100 동적 유니버스 (실험12) | +144.5% | 23.9% | -22.6% | 0.83 |
| NDX100 Top30 필터 강화 (실험13) | +188.1% | 28.9% | -30.7% | 0.99 |

현재 채택 파라미터: hybrid / bear=block(MA200) / pct12 / trailing_stop=original / atr_sizing=4.0% / max_positions=4 / adx_threshold=20 / min_hold_days=3 / 16종목

**룩어헤드 바이어스 검증 결과 (실험12~14)**
- 기존 16종목 → 나스닥100 97종목으로 교체 시 샤프 1.72 → 0.83
- NDX100 추가 종목 평균 손익 -0.3%, 승률 31.9% → 유니버스 종목 품질이 핵심
- 필터 강화·포지션 수 조정으로는 근본 해결 안 됨

**다음 작업:**
- **슈퍼사이클**: 유니버스 동적 갱신 로직 — 반기/분기마다 테마 재검토
- **일반 추세추종**: 방향A(M2) 최종 확정. 방향B(채널 돌파 터틀 스타일) 검증 후 포기 — NDX100 구조상 5팩터 진입이 압도적 (O/P 시리즈)

## 코드 구조

`backtest.py` — 멀티 종목 백테스트 메인 파일  
`backtest_single.py` — 단일 종목(현재 MU) 트레이딩 시각화. 매수/매도 시점을 차트에 표시하고 멀티 실험10과 비교  
`_run_multi.py` — `backtest_single.py`가 subprocess로 호출하는 멀티 백테스트 격리 실행 스크립트 (같은 프로세스에서 yfinance 이중 호출 시 결과가 달라지는 버그 방지)

`backtest.py` 실행 흐름:

```
load_data()
  └─ yfinance로 전체 종목 일괄 다운로드 (auto_adjust=True)

run_backtest(price_data, portfolio, bear_filter, stop_mode, exit_mode)
  ├─ get_universe()        월 1회 모멘텀 필터 (52주 신고가 -5% 이내, 6개월 수익률 양수, 3개월 RS 상위 30종목, 거래대금 $50M+)
  ├─ check_sell_signals()  매일 포지션별 청산 조건 판단
  │    ├─ 하드스탑 (stop_mode: pct8 / pct12 / atr×2.5)
  │    ├─ MACD 데드크로스 + RSI 50 하향 → 즉시 전량
  │    └─ MA 이탈 (exit_mode: current / fast / confirm)
  └─ calculate_signal_score()  신규 진입 팩터 점수 계산

compute_metrics() → plot_comparison()
```

## 핵심 파라미터

**CONFIG** (전역 딕셔너리)
- `strong_signal_threshold`: 70점 이상 → Strong 신호 (총자산의 32% 배분, 3트랜치)
- `medium_signal_threshold`: 50점 이상 → Medium 신호 (총자산의 22% 배분, 2트랜치)
- `slippage_cost`: 0.001 (매수/매도 각 0.1%)
- 포지션 사이징은 `initial_capital` 아닌 **현재 총자산** 기준 (복리 반영)

**run_backtest 파라미터**
- `bear_filter`: `'none'` / `'block'`(SPY 200일선 아래 진입 차단) / `'strict'`(Strong만 허용)
- `stop_mode`: `'pct8'` / `'pct12'` / `'atr'`
- `exit_mode`: `'current'`(단계적) / `'fast'`(MA10 즉시전량) / `'confirm'`(MA20 3일확인) / `'hybrid'`(MA10→50% + MA20 3일확인→잔여전량, **현재 최우수**) / `'ma20_simple'`(MA20 즉시전량, 단순화용)
- `use_macd_rsi_exit`: True(기본) / **False**(일반 추세추종 채택 — MACD+RSI 조기청산 제거)

**팩터 점수 (기술적 60점 만점 → 100점 정규화)**
- 52주 신고가 돌파 +20, MA 정배열 +15, MACD 골든크로스 +10, RSI 50~70 +10, 거래량 1.5배+ +5
- 펀더멘털(yfinance) 데이터 불안정으로 사실상 기술적 팩터만 작동 중

## 종목 유니버스

슈퍼사이클 테마별 16개 종목 (바이오 LLY/NVO/HIMS 제외 — PnL 분해 결과 드래그 확인):
- AI 인프라: NVDA, PLTR, ANET, MRVL, AVGO
- 메모리: MU, WDC
- 원자력/전력: CEG, VST, NRG
- 방산 테크: AXON, HWM, KTOS, RKLB
- 핀테크/암호화폐: HOOD, COIN

## 알려진 이슈 및 설계 결정

- **펀더멘털 팩터 미작동**: `df.attrs.get('ticker', '')`가 항상 빈 문자열 반환 → 어닝 서프라이즈(+25점) 비활성화 상태. 기술적 팩터 60점을 100점으로 정규화해서 사용 중
- **RSI 계산**: 표준 Wilder's smoothing 대신 단순 평균 사용 (값이 표준과 다소 다름)
- **한글 폰트**: Windows 맑은 고딕 고정 (`plt.rcParams['font.family'] = 'Malgun Gothic'`). macOS/Linux에서는 다른 폰트로 변경 필요
- **MA 청산 sold_pct 추적**: `pos.sold_pct`는 `PortfolioManager.sell_partial()` 호출 후 루프에서 수동 누적. 청산 단계가 중복 발동되지 않도록 `elif` 체인으로 하루 1단계만 실행
- **yfinance 이중 호출 버그**: 같은 Python 프로세스 내에서 `backtest` 모듈을 import한 뒤 yfinance를 다시 호출하면 내부 세션 상태가 달라져 결과가 달라짐 (590%→470%). `backtest_single.py`에서 멀티 백테스트를 `_run_multi.py` subprocess로 격리해서 해결. **`backtest` 모듈을 import하는 스크립트에서 별도로 yfinance를 재호출하면 안 됨**
