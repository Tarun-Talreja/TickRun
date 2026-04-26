# Screen Rules

All thresholds are fixed. Change here only after careful consideration.

## 1. Graham Defensive (deep value)
- pe < 15
- pb < 1.5
- current_ratio > 2
- positive_earnings_5y == true
- dividend_paying_5y == true
- market_cap > 2_000_000_000

## 2. Magic Formula (Greenblatt)
- Rank by earnings_yield (inverse of EV/EBITDA) high to low
- Rank by roic high to low
- Sum ranks; top 30 pass

## 3. Piotroski F-Score (score 7-9 passes)
Score 1 point each:
- net_income > 0
- operating_cash_flow > 0
- roa_current > roa_prior
- operating_cash_flow > net_income
- long_term_debt_current < long_term_debt_prior
- current_ratio_current > current_ratio_prior
- shares_issued_current <= shares_issued_prior
- gross_margin_current > gross_margin_prior
- asset_turnover_current > asset_turnover_prior

## 4. GARP (Peter Lynch)
- eps_growth_5y > 15
- revenue_growth_5y > 10
- peg < 1.5
- roe > 15
- debt_equity < 0.5
- forward_pe < industry_avg_pe

## 5. Quality (defensive compounders)
- roic_5y_avg > 15
- gross_margin > 40
- fcf_margin > 10
- debt_equity < 1
- market_cap > 10_000_000_000

## 6. Momentum
- return_12m in top 20% of S&P 500
- price > ma_200
- price > ma_50
- ma_50 > ma_200

## 7. Dividend Quality
- dividend_yield > 2 AND dividend_yield < 6
- payout_ratio < 60
- dividend_growth_years >= 5
- fcf_dividend_coverage > 1.5
- debt_equity < 1
