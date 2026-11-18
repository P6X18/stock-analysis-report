# Stock Analysis Report Skill (`stock-analysis`)

A stock analysis agent skill and standalone Python toolkit that combines **Fundamental Analysis** (business quality, financial health, 3-year performance trends, and 10-year PE percentile valuation) with **Technical Analysis** (market structure, moving averages, RSI, MACD, Bollinger Bands, and risk-reward trade setups).

> **Core Philosophy**: Fundamentals identify *what* to buy or avoid (business value and safety margin); Technicals determine *when* and *at what price* to execute (market timing, trend alignment, and risk-reward structure).

---

## Key Features

### 📊 Fundamental Valuation & 10-Year PE Bands
- **10-Year Historical PE (TTM) & Percentile Bands**: Pulls daily PE (TTM) via EastMoney (`akshare`) for China A-Shares, and pairs up to 10 years of daily price history with 4-quarter rolling `Reported EPS` (with annual `income_stmt` EPS and listing-history fallbacks) for US/Global equities — generating 3Y/5Y/10Y percentiles, P10 - P90 benchmark bands, 5 valuation zones, and a 2-panel valuation chart.
- **3-Year Financial Performance & Moat Deep-Dive**: Tracks multi-year revenue, operating profit, net income, margins, ROE, OCF, FCF, YoY growth, and 2-year CAGR alongside sector positioning and competitive moats.
- **Complete Valuation & Balance Sheet Scorecard**: Summarizes Market Cap, EV, Trailing/Forward P/E, PEG, P/S, P/B, EV/EBITDA, Debt/Equity, Dividend Yield, and analyst consensus targets.

### 📈 Technical Analysis & Tactical Trade Setups
- **4-Panel Technical Chart**: Plots Price + 20/50/200 SMAs + Bollinger Bands (20, 2σ), Volume + 20 SMA, RSI (14), and MACD (12, 26, 9).
- **Actionable Tactical Trade Plans**: Computes key support/resistance zones, accumulation ranges, hard invalidation stop-loss levels, primary/secondary targets, and Risk-to-Reward (`R:R`) ratios.
- **4-Quadrant Confluence & Scenario Planning**: Synthesizes Technical and Fundamental scores into Categories **A** (High-Probability Compounder), **B** (Speculative Squeeze), **C** (Value Accumulation Watch), or **D** (High Risk / Value Trap), paired with Bull vs. Bear scenarios.

### ⚖️ Multi-Stock Horizontal Comparison & Ranking
- **Dedicated Comparison Dashboard**: When analyzing 2+ stocks, automatically ranks candidates by composite quality, valuation, and technical alignment into a standalone portfolio report.
- **Structured Side-by-Side Matrices**: Includes top priority KPI cards, an 11-row fundamental & valuation comparison matrix, a 7-column tactical trade & risk matrix, and actionable allocation commentary.

### 🌍 Multi-Market, Multilingual & Publication-Ready Outputs
- **Global Asset Coverage**: Supports US/global equities (`NVDA`, `GOOGL`, `SPCX`), Hong Kong stocks (`0700.HK`), China A-Shares (`600519.SS`, `002516.SZ`), ETFs, and macro commodities (`GC=F`).
- **Automatic Language Matching**: With `--lang auto`, English stock names/inputs generate English reports, while Chinese stock names/assets generate pure Chinese reports using Chinese units (`亿` instead of `B`), localized sector/industry names, and `暂无` for missing values.
- **5 Synchronized Deliverables**: Produces Markdown (`.md`), responsive standalone HTML (`.html`), gap-free word-safe mobile & A4 PDFs (`.pdf`), high-resolution PNG charts, and structured JSON (`*_data.json`).

---

## Repository Structure

```text
stock-analysis/
├── SKILL.md                          # Agent skill instructions & formatting standards
├── README.md                         # Project overview & usage guide
├── scripts/
│   ├── analyze_stock.py              # Single-stock fundamental + technical analyzer
│   └── compare_stocks.py             # Multi-stock horizontal comparison & ranking generator
└── references/
    ├── fundamental-metrics.md        # Sector valuation & financial health benchmarks
    ├── technical-indicators.md       # Indicator definitions, formulas, and edge cases
    └── confluence-framework.md       # 4-quadrant scoring & risk/reward matrix
```

---

## Usage

### 1. As an Agent Skill

Place this directory under `.agents/skills/stock-analysis` in your workspace (or global skills directory) and invoke:

```text
/stock-analysis SpaceX, Google, Nvidia
```

or in Chinese:

```text
/stock-analysis 新亚强、旷达科技、航发动力
```

### 2. Standalone CLI (`uv`)

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).

**Analyze a single stock (English auto-detected):**

```bash
uv run --with yfinance --with pandas --with matplotlib --with xhtml2pdf --with akshare python scripts/analyze_stock.py --ticker NVDA --period 1y --name "Nvidia"
```

**Analyze a Chinese stock (Chinese auto-detected):**

```bash
uv run --with yfinance --with pandas --with matplotlib --with xhtml2pdf --with akshare python scripts/analyze_stock.py --ticker 603155.SS --period 1y --name "新亚强"
```

**Generate a multi-stock comparison report (after analyzing 2+ stocks):**

```bash
uv run --with yfinance --with pandas --with numpy --with matplotlib --with mplfinance --with xhtml2pdf --with requests python scripts/compare_stocks.py --tickers SPCX GOOGL NVDA --output-dir "./stock_analysis_output"
```

#### Common Options (`analyze_stock.py`)

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--ticker` | *(required)* | Ticker symbol or Chinese/English stock name |
| `--name` | auto | Display name (English name selects `en`; Chinese name selects `zh` in `auto` mode) |
| `--period` | `1y` | Chart & technical lookback (`6mo`, `1y`, `2y`, `5y`) |
| `--interval` | `1d` | Bar frequency (`1d`, `1wk`, `1mo`) |
| `--lang` | `auto` | Output language (`auto`, `en`, `zh`) |
| `--output-dir` | `./stock_analysis_output` | Base output directory |

---

## Font Notes (Optional for PDF CJK Rendering)

On Windows, `analyze_stock.py` and `compare_stocks.py` look for `msyh.ttc`, `msyhbd.ttc`, `segoeui.ttf`, and `segoeuib.ttf` in a local `fonts/` folder or fall back to `C:/Windows/Fonts`. On macOS/Linux, place compatible CJK/sans-serif fonts inside `fonts/` if generating Chinese PDFs.

---

## Disclaimer

This tool and its generated reports are for **educational and research purposes only** and do not constitute investment, financial, or trading advice. Financial markets carry substantial risk of loss; always verify data and conduct independent due diligence.

---

## License

This project is licensed under the [MIT License](LICENSE).
