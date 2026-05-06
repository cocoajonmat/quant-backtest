# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실행

```powershell
python backtest.py
```

의존성 설치:
```powershell
pip install yfinance pandas numpy matplotlib
```

## 프로젝트 현황 (2026-05-06 기준)

미국 주식 추세추종 스윙 트레이딩 백테스팅 시스템. 슈퍼사이클 종목(최근 5년 5배+ 상승) 위주로 다중 팩터 점수화 후 분할 매수/매도.

**마지막 백테스트 결과 (5년, $10,000 초기자본, SPY +82.9%)**
| 청산 방식 | 수익률 | CAGR | MDD | 샤프 |
|----------|--------|------|-----|------|
| 현재 (단계적 MA) | +150.0% | 24.6% | -15.9% | 1.16 |
| A안 MA10 즉시전량 | +169.0% | 26.8% | -13.6% | 1.24 |
| B안 MA20 3일확인 | +173.7% | 27.4% | -16.9% | 1.22 |

**다음 작업:** 하이브리드 청산 구현 — MA10 이탈 시 50% 청산 + MA20 3일 연속 이탈 시 잔여 전량 청산

## 코드 구조

`backtest.py` 단일 파일로 구성. 실행 흐름:

```
load_data()
  └─ yfinance로 전체 종목 일괄 다운로드 (auto_adjust=True)

run_backtest(price_data, portfolio, bear_filter, stop_mode, exit_mode)
  ├─ get_universe()        월 1회 모멘텀 필터 (52주 신고가 -10% 이내, 3개월 RS 상위 25%, 거래대금 $50M+)
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
- `exit_mode`: `'current'`(단계적) / `'fast'`(MA10 즉시전량) / `'confirm'`(MA20 3일확인)

**팩터 점수 (기술적 60점 만점 → 100점 정규화)**
- 52주 신고가 돌파 +20, MA 정배열 +15, MACD 골든크로스 +10, RSI 50~70 +10, 거래량 1.5배+ +5
- 펀더멘털(yfinance) 데이터 불안정으로 사실상 기술적 팩터만 작동 중

## 종목 유니버스

슈퍼사이클 테마별 19개 종목:
- AI 인프라: NVDA, PLTR, ANET, MRVL, AVGO
- 메모리: MU, WDC
- 원자력/전력: CEG, VST, NRG
- 방산 테크: AXON, HWM, KTOS, RKLB
- 비만치료: LLY, NVO, HIMS
- 핀테크/암호화폐: HOOD, COIN

## 알려진 이슈 및 설계 결정

- **펀더멘털 팩터 미작동**: `df.attrs.get('ticker', '')`가 항상 빈 문자열 반환 → 어닝 서프라이즈(+25점) 비활성화 상태. 기술적 팩터 60점을 100점으로 정규화해서 사용 중
- **RSI 계산**: 표준 Wilder's smoothing 대신 단순 평균 사용 (값이 표준과 다소 다름)
- **한글 폰트**: Windows 맑은 고딕 고정 (`plt.rcParams['font.family'] = 'Malgun Gothic'`). macOS/Linux에서는 다른 폰트로 변경 필요
- **MA 청산 sold_pct 추적**: `pos.sold_pct`는 `PortfolioManager.sell_partial()` 호출 후 루프에서 수동 누적. 청산 단계가 중복 발동되지 않도록 `elif` 체인으로 하루 1단계만 실행
