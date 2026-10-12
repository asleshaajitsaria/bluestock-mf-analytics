# Day 1 Data Quality Summary

## Datasets loaded

| Dataset | Rows | Columns |
|---|---|---|
| 08_investor_transactions | 32778 | 13 |
| aum_by_fund_house | 90 | 5 |
| benchmark_indices | 8050 | 3 |
| category_inflows | 144 | 3 |
| fund_master | 40 | 15 |
| industry_folio_count | 21 | 6 |
| investor_transactions | 32778 | 13 |
| monthly_sip_flows | 48 | 6 |
| nav_history | 46000 | 3 |
| portfolio_holdings | 322 | 8 |
| scheme_performance | 40 | 19 |

## Anomalies by dataset

**08_investor_transactions**
- `transaction_date`: date column stored as text

**aum_by_fund_house**
- `date`: date column stored as text

**benchmark_indices**
- `date`: date column stored as text

**category_inflows**
- none detected

**fund_master**
- `min_sip_amount`: constant column
- `launch_date`: date column stored as text

**industry_folio_count**
- none detected

**investor_transactions**
- `transaction_date`: date column stored as text

**monthly_sip_flows**
- `yoy_growth_pct`: 12 null(s) (25.0%)

**nav_history**
- `date`: date column stored as text

**portfolio_holdings**
- `portfolio_date`: date column stored as text

**scheme_performance**
- `max_drawdown_pct`: 40 negative value(s)

## AMFI code validation

- fund_master unique codes: 40
- nav_history unique codes: 40
- fund_master codes missing from nav_history: 0 []
- nav_history codes missing from fund_master: 0 []

## Additional checks (cross-file consistency, gaps, outliers)

- `08_investor_transactions` and `investor_transactions` have identical content (duplicate file).
- `portfolio_holdings`: covers only 34/40 fund_master codes (6 missing, e.g. ['100025', '101208', '118636', '119120', '120507', '120844'])
- `nav_history`: 2022-01-03 to 2026-05-29, rows per scheme min=1150 max=1150
- `benchmark_indices`: indices = ['BSE_SMALLCAP', 'CRISIL_GILT', 'CRISIL_LIQUID', 'NIFTY100', 'NIFTY50', 'NIFTY500', 'NIFTY_MIDCAP150']
- `benchmark_indices`: 0 duplicate (date, index) rows
- `portfolio_holdings`: weight_pct per fund sums to 100.0%-100.0%; 0 of 34 funds are outside 95-105%
- `portfolio_holdings`: current_price_inr for the same stock differs >2x across funds for 30 of 30 stocks (price not consistent per stock)
- `portfolio_holdings`: covers 34 schemes only
- `monthly_sip_flows`: sip_inflow_crore repeats the previous month in 3 month(s): ['2023-05', '2024-04', '2024-06']
- `monthly_sip_flows`: outlier in `new_sip_accounts_lakh`: [['2025-04', 46.0]]
- `monthly_sip_flows`: sip_aum_lakh_crore jumps >15% in one month at ['2025-01']
- `monthly_sip_flows`: active_sip_accounts_crore falls month-on-month at ['2025-01', '2025-03']
- `category_inflows`: months 2024-04 to 2025-03 (12 months, 12 categories)
- `industry_folio_count`: 21 rows but 48 months in range (irregular, non-monthly spacing)
- `aum_by_fund_house`: 9 snapshot dates, irregular spacing (e.g. gap from 2025-03-31 to 2025-12-31)
- `aum_by_fund_house`: 0 rows where aum_crore != aum_lakh_crore x 100000
- `investor_transactions`: types = {'SIP': 19716, 'Lumpsum': 8095, 'Redemption': 4967}
- `investor_transactions`: kyc_status = {'Verified': 30146, 'Pending': 2632}
- `investor_transactions`: 0 duplicate rows; amount_inr min=400 max=597498
- `investor_transactions`: SIP amount median=5139, max=59998
- `investor_transactions`: annual_income_lakh range 3.0 to 99.7
- `investor_transactions`: dates 2024-01-01 to 2025-05-30
- fund_master vs scheme_performance: 40 matched schemes; 0 expense_ratio mismatches; 0 risk grade mismatches
- `scheme_performance`: implausible sharpe_ratio > 3 for ['ICICI Pru Liquid Fund - Regular - Growth', 'Kotak Liquid Fund - Regular - Growth', 'ABSL Liquid Fund - Regular - Growth'] (sharpe equals return_3yr in these rows)
- `fund_master`: sub_category uses both `Index` and `Index/ETF` (inconsistent labels)
