# Fundamental Equity Analysis Reference

This reference provides valuation multiples, quality thresholds, financial solvency guidelines, and sector-specific benchmarks used in the `stock-analysis` skill.

---

## 1. Valuation Multiples

Valuation metrics assess how the current market price compares to the intrinsic cash-flow and asset generation of the business.

| Metric | Formula | Benchmark Range (General) | Notes / Caveats |
| :--- | :--- | :--- | :--- |
| **Trailing P/E** | Price / TTM Diluted EPS | 15x - 25x (Market Avg) | Backward-looking; distorted by one-time gains or non-cash charges. |
| **Forward P/E** | Price / Next 12M Estimated EPS | 12x - 20x | Sensitive to analyst consensus accuracy; compare to historical 5-yr median. |
| **PEG Ratio** | P/E / EPS Growth Rate | < 1.0 (Undervalued)<br>1.0 - 2.0 (Fair)<br>> 2.0 (Premium) | Peter Lynch benchmark: PEG < 1.0 signifies Growth at a Reasonable Price (GARP). |
| **EV / EBITDA** | Enterprise Value / TTM EBITDA | 8x - 14x | Capital structure neutral; ideal for capital-intensive or levered companies. |
| **Price / Sales (P/S)** | Market Cap / TTM Revenue | Sector dependent (< 3x mature, < 8x SaaS) | Used for early-stage or hyper-growth companies before GAAP profitability. |
| **Price / FCF** | Market Cap / Free Cash Flow | 15x - 25x | Closer to true cash reality than accounting earnings. |

---

## 2. Profitability & Returns on Capital

Durable competitive advantages ("economic moats") reveal themselves through sustained, superior returns on capital.

* **Return on Equity (ROE)**:
  $$\text{ROE} = \frac{\text{Net Income}}{\text{Shareholders' Equity}}$$
  * *Threshold*: $> 15\%$ is strong; $> 25\%$ indicates elite capital compounders (verify not inflated by excessive leverage via DuPont analysis).
* **Return on Invested Capital (ROIC)**:
  $$\text{ROIC} = \frac{\text{NOPAT}}{\text{Total Invested Capital (Debt + Equity - Excess Cash)}}$$
  * *Threshold*: ROIC $> 12\%$ and consistently exceeding the company's Weighted Average Cost of Capital (WACC) generates economic value added.
* **Operating Margin (OPM)**:
  $$\text{OPM} = \frac{\text{Operating Income}}{\text{Total Revenue}}$$
  * Expanding operating margins over 3-5 consecutive quarters demonstrate operating leverage.

---

## 3. Financial Solvency & Balance Sheet Resilience

Solvency and liquidity metrics ensure the company can withstand recessions, rate hikes, or credit crunches.

| Metric | Formula | Healthy Benchmark | Distress Warning |
| :--- | :--- | :--- | :--- |
| **Current Ratio** | Current Assets / Current Liabilities | $> 1.2\times$ | $< 1.0\times$ |
| **Quick Ratio (Acid-Test)** | (Cash + Marketable Sec + Receivables) / Cur Liab | $> 1.0\times$ | $< 0.8\times$ |
| **Total Debt / Equity** | Total Debt / Total Stockholders' Equity | $< 100\%$ ($< 1.0$) | $> 200\%$ ($> 2.0$) |
| **Net Debt / EBITDA** | (Total Debt - Cash) / EBITDA | $< 2.0\times$ | $> 4.0\times$ |
| **Interest Coverage** | EBIT / Interest Expense | $> 4.0\times$ | $< 2.0\times$ |

---

## 4. Cash Flow Quality Checklist

1. **Free Cash Flow Conversion**: $\frac{\text{Free Cash Flow}}{\text{Net Income}} \ge 80\%$.
   * A persistent divergence where Net Income rises while Free Cash Flow collapses is a major red flag (aggressive revenue recognition or inventory bloating).
2. **Capital Expenditure Intensity**: $\frac{\text{CapEx}}{\text{Operating Cash Flow}}$.
   * Low CapEx intensity ($< 25\%$) leaves substantial discretionary cash for share buybacks, dividends, or strategic M&A.
3. **Share Count Dilution**:
   * Diluted shares outstanding should be flat or decreasing over time (disciplined repurchases). Rapidly expanding share count ($> 3\%$ annually) indicates severe stock-based compensation (SBC) dilution.

---

## 5. PE Historical Percentile & Valuation Bands (历史PE百分位与估值带宽模型)

The Historical PE Percentile measures where the current Trailing P/E (TTM) stands relative to the company's own historical valuation distribution over a standard 10-year cycle (or full listing history if < 10 years).

### 5.1 Mathematical Formulation
Given the daily historical PE(TTM) series $\{PE_1, PE_2, \dots, PE_N\}$ over the lookback window (minimum 1 trading year, standard 10 years):
$$\text{Percentile}(PE_{\text{current}}) = \frac{\sum_{k=1}^N \mathbb{I}(PE_k < PE_{\text{current}})}{N} \times 100\%$$
Where:
* $P_{10}, P_{25}, P_{50}, P_{75}, P_{90}$ are the 10th, 25th, 50th (median), 75th, and 90th empirical percentiles of the valuation distribution.

### 5.2 Institutional 5-Zone Valuation Framework
| Zone | Percentile Range | Valuation Assessment | Tactical Action Guideline |
| :--- | :--- | :--- | :--- |
| **Deep Value / Margin of Safety** | $0\% - 20\%$ ($< P_{20}$) | Extremely Undervalued / Historic Discount | Favorable risk/reward for accumulation; verify balance sheet solvency to avoid insolvency traps. |
| **Value Accumulation Band** | $20\% - 40\%$ ($P_{20} - P_{40}$) | Moderately Undervalued | Attractive entry window for compounding quality franchises. |
| **Fair Valuation Core** | $40\% - 60\%$ ($P_{40} - P_{60}$) | Fair Value / Historical Median ($P_{50}$) | Price reflects normalized earnings; returns driven primarily by business earnings growth rather than multiple expansion. |
| **Elevated Valuation Band** | $60\% - 80\%$ ($P_{60} - P_{80}$) | Multiple Expansion / Premium Territory | Tighten trailing stops; multiple expansion potential diminishes. |
| **Overvaluation Hazard Zone** | $> 80\%$ ($> P_{80} / P_{90}$) | Extreme Multiple Bubble / Vulnerable | Asymmetric downside risk; prone to sharp multiple compression upon earnings misses. |

### 5.3 The Cyclical PE Trap & Paradox ("高PE买入、低PE卖出")
> [!WARNING]
> Trailing P/E percentiles can be profoundly deceptive for cyclical and capital-intensive industries (e.g., silicone/chemicals, shipping, metals, commodities, semiconductor foundry):
> 1. **Cycle Trough Passive PE Expansion**: During industry cyclical downturns, company net earnings collapse while stock prices stabilize at asset/replacement values (PB support). This mathematical collapse of denominator ($E$) causes trailing PE to passively explode into high percentiles ($> 80\%$), creating an illusion of extreme overvaluation when the stock may actually be bottoming.
> 2. **Cycle Peak Deceptive Low PE**: At cyclical peaks, super-normal peak profits drive trailing PE down into single digits ($< 10\times, < 10\%$ percentile), creating a classic value trap.
> 3. **Institutional Dissection Protocol**: For cyclical tickers showing high PE percentiles, analysts must cross-reference **Price-to-Book (PB) historical percentile**, gross margin trough reversion, normalized mid-cycle EPS, and capacity supply-demand dynamics rather than discarding the asset purely on PE percentile.

### 5.4 Multi-Horizon Lookback Framework (3年 / 5年 / 10年 对照体系)
Institutional analysis synthesizes three distinct valuation lookback horizons:
* **10-Year Horizon (Executive Headline Anchor)**: Captures a complete macroeconomic and industry super-cycle (peak, bust, consolidation, recovery). This 10-year metric serves as the headline anchor in executive summary KPI cards (e.g. `10年PE分位: 80.3%`).
* **5-Year Horizon (Capex & Capacity Cycle)**: Isolates the medium-term corporate reinvestment and capacity commissioning cycle.
* **3-Year Horizon (Near-Term Sentiment & Trend)**: Reflects immediate post-earnings re-rating and current market regime.
* **Standard Reporting Matrix**: In fundamental equity scorecards, always present the triad `PE 历史分位数 (3年 / 5年 / 10年)` alongside the 10-year empirical range $[Min — Max]$ and median ($P_{50}$) benchmark.


