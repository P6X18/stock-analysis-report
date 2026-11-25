# Stock Analysis Report

An agent skill and standalone Python toolkit integrating **Fundamental Analysis** with **Technical Analysis** into multilingual reports.

> **Core Philosophy**: Fundamentals identify *what* to buy or avoid (business value & margin of safety); Technicals determine *when* and *at what price* to execute (trend alignment & risk-reward).

## Highlights

- **📊 Valuation & Fundamentals**: 3Y/5Y/10Y historical PE (TTM) percentiles, P10-P90 valuation bands, 2-panel PE chart (EastMoney daily series for China A-shares; rolling EPS / price-implied history for global equities), 3-year performance & CAGR matrix, ROE, OCF/FCF, Debt/Equity, and analyst targets.
- **📈 Technicals & Trade Setups**: High-res 4-panel chart (Price + 20/50/200 SMAs + Bollinger Bands, Volume, RSI-14, MACD), key support/resistance, entry zone, hard stop-loss, Target 1/2, `R:R` ratio, and 4-quadrant confluence rating (**Category A-D**) with Bull/Bear scenarios.
- **⚖️ Multi-Stock Comparison & TTM Alignment**: Ranks 2+ stocks by composite quality, valuation, and trend; automatically aligns Revenue, Net Income, Margins, and OCF on **TTM** when fiscal year-ends differ (e.g., Jan FY26 vs. Dec FY25).
- **📱 Mobile-Native & Multilingual Deliverables**: Generates `.md`, desktop `.html`, gap-free `112mm x 220mm` vertical smartphone `.pdf` (stacked KPI, comparison, and tactical cards for both single-stock and comparison reports), `.png` charts, and `*_data.json`. `--lang auto` outputs English for global inputs and pure Chinese (`亿` units) for Chinese inputs/equities.

## Structure

```text
stock-analysis-report/
├── SKILL.md                   # Agent skill workflow & formatting standards
├── scripts/
│   ├── analyze_stock.py       # Single-stock analyzer & report generator
│   └── compare_stocks.py      # Multi-stock comparison & priority ranker
├── fonts/                     # Bundled CJK & UI fonts for PDF rendering
└── references/                # Fundamental, technical & confluence guides
```

## Quick Start

### 1. As an Agent Skill
Place under `.agents/skills/stock-analysis-report` (workspace or global skills directory) and run:

```text
/stock-analysis-report Google, SpaceX, Nvidia
/stock-analysis-report 长江电力，工商银行，贵州茅台
```

### 2. Standalone CLI (Python 3.10+ & [`uv`](https://docs.astral.sh/uv/))

```bash
# Single stock (English or Chinese auto-detected via --lang auto)
uv run --with yfinance --with pandas --with matplotlib --with xhtml2pdf --with akshare \
  python scripts/analyze_stock.py --ticker NVDA --period 1y --name "Nvidia"

# Multi-stock horizontal comparison & ranking (run after analyzing 2+ tickers)
uv run --with yfinance --with pandas --with numpy --with matplotlib --with mplfinance --with xhtml2pdf --with requests \
  python scripts/compare_stocks.py --tickers GOOGL SPCX NVDA --output-dir "./stock_analysis_output"
```

| Option (`analyze_stock.py`) | Default | Description |
| :--- | :--- | :--- |
| `--ticker` | *(required)* | Ticker symbol (`NVDA`, `0700.HK`, `600519.SS`, `GC=F`) |
| `--name` | auto | Display name (sets `en` or `zh` when `--lang auto`) |
| `--period` / `--interval` | `1y` / `1d` | Lookback (`6mo`, `1y`, `2y`, `5y`) and bar interval (`1d`, `1wk`, `1mo`) |
| `--lang` | `auto` | Report language (`auto`, `en`, `zh`) |
| `--output-dir` | `./stock_analysis_output` | Base output folder |

## Disclaimer & License

For **educational and research purposes only** — not investment or trading advice. Licensed under the [MIT License](LICENSE).
