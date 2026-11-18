# Technical Analysis & Indicator Reference

This reference outlines the technical indicators, formulas, benchmark values, and trading signals used in the `stock-analysis` skill.

---

## 1. Moving Averages (Trend & Momentum Baselines)

Moving averages smooth price fluctuations to highlight the underlying market trend.

| Indicator | Period | Primary Use Case | Bullish Interpretation | Bearish Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| **EMA 9** | 9 bars | Fast momentum trigger | Price trades above EMA 9; aggressive short-term trend | Price trades below EMA 9 |
| **EMA 21** | 21 bars | Short-term swing support | Pullbacks bounce off EMA 21 in healthy uptrends | EMA 21 acts as dynamic resistance |
| **SMA 20** | 20 bars | Centerline of Bollinger Bands | Upward slope; price riding upper half | Downward slope; price riding lower half |
| **SMA 50** | 50 bars | Institutional accumulation benchmark | Price firmly above SMA 50; institutional defense zone | Price rejected at descending SMA 50 |
| **SMA 200**| 200 bars | Secular macro bull/bear divide | Sustained above 200 SMA = long-term bull market | Below 200 SMA = long-term secular downtrend |

### Moving Average Crosses
* **Golden Cross**: The 50-day SMA crosses above the 200-day SMA. Indicates long-term bullish structural shift.
* **Death Cross**: The 50-day SMA crosses below the 200-day SMA. Signals long-term bearish distribution.

---

## 2. Momentum & Oscillators

### Relative Strength Index (RSI - 14 Periods)
Measures the velocity and magnitude of recent directional price movements.
* **Calculation**:
  $$\text{RSI} = 100 - \left( \frac{100}{1 + \text{RS}} \right), \quad \text{where } \text{RS} = \frac{\text{Average Gain}}{\text{Average Loss}}$$
* **Key Zones**:
  * **Overbought (> 70)**: High momentum, but risk of near-term consolidation or pullback increases.
  * **Oversold (< 30)**: Extreme selling; potential mean-reversion bounce or capitulation low.
  * **Bull Market Range (40 - 80)**: In strong uptrends, RSI tends to oscillate between 40 and 80, rarely dipping below 40.
  * **Bear Market Range (20 - 60)**: In downtrends, RSI rarely breaks above 60 and bounces fail near 50-60.
* **Divergence**:
  * *Regular Bearish Divergence*: Price makes a Higher High, but RSI makes a Lower High. Signals weakening upside momentum.
  * *Regular Bullish Divergence*: Price makes a Lower Low, but RSI makes a Higher Low. Signals seller exhaustion.

### MACD (Moving Average Convergence Divergence)
* **Standard Inputs**: Fast EMA (12), Slow EMA (26), Signal Line (9-day EMA of MACD line).
* **MACD Line**: $\text{EMA}_{12}(\text{Close}) - \text{EMA}_{26}(\text{Close})$
* **Signal Line**: $\text{EMA}_{9}(\text{MACD Line})$
* **Histogram**: $\text{MACD Line} - \text{Signal Line}$
* **Key Signals**:
  * *Zero-Line Cross*: MACD crossing above 0 confirms positive momentum; below 0 confirms negative momentum.
  * *Signal Line Cross*: MACD crossing above Signal is a buy trigger; crossing below is a sell/trim trigger.
  * *Histogram Ticking*: Color shift from red to green (or contracting negative bars) indicates momentum inflection before the line cross.

---

## 3. Volatility & Price Action

### Bollinger Bands (20, 2σ)
* **Upper Band**: $\text{SMA}_{20} + 2 \times \sigma$
* **Lower Band**: $\text{SMA}_{20} - 2 \times \sigma$
* **Bandwidth & The "Squeeze"**:
  $$\text{Bandwidth} = \frac{\text{Upper Band} - \text{Lower Band}}{\text{SMA}_{20}}$$
  When Bandwidth reaches historical multi-month lows, a high-volatility expansion/breakout is imminent.
* **Walking the Bands**: In very strong trends, prices can continuously hug or ride the upper (or lower) band without reversing immediately.

### Average True Range (ATR - 14 Periods)
* Measures volatility independent of direction.
* Used to set dynamic stop-losses (e.g., $2 \times \text{ATR}$ below support or entry price) and position sizing.

---

## 4. Volume & Market Structure

* **Volume Confirmation**:
  * Price breakout accompanied by Volume $> 1.5 \times \text{20-day Volume SMA}$ has a high success rate.
  * Price advance on declining volume indicates diminishing institutional interest (exhaustion).
* **Support & Resistance (S/R)**:
  * Horizontal reaction highs and lows established over 30-90 day windows.
  * Prior resistance becomes new support upon breakout (polarity change).
