"""멀티 종목 실험10 백테스트를 독립 프로세스로 실행. JSON 결과를 stdout에 출력."""
import json
from backtest import (load_data, PortfolioManager, run_backtest,
                      compute_metrics, UNIVERSE_TICKERS, CONFIG)

price_data = load_data(UNIVERSE_TICKERS, CONFIG['period_years'])
portfolio = PortfolioManager(CONFIG['initial_capital'])
run_backtest(price_data, portfolio,
             bear_filter='block', stop_mode='pct12', exit_mode='hybrid',
             atr_sizing=True, atr_risk_pct=0.04, trailing_stop=True,
             spy_ma_period=200)
metrics, ec, spy_curve = compute_metrics(portfolio, price_data)

out = {
    'metrics': {k: float(v) for k, v in metrics.items()},
    'equity_curve': [{'date': str(d.date()), 'equity': float(v)}
                     for d, v in zip(ec.index, ec['equity'])],
    'spy_dates': [str(d.date()) for d in spy_curve.index],
    'spy_values': [float(v) for v in spy_curve.values],
}
print('JSON:' + json.dumps(out))
