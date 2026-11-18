# Stock Analysis Report Skill (`stock-analysis`)

An institutional-grade equity research skill and standalone Python toolkit that combines **Fundamental Analysis** (business quality, financial health, 3-year performance trends, and 10-year PE percentile valuation) with **Technical Analysis** (market structure, moving averages, RSI, MACD, Bollinger Bands, and risk-reward trade setups).

> **Core Philosophy**: Fundamentals identify *what* to buy or avoid (business value and safety margin); Technicals determine *when* and *at what price* to execute (market timing, trend alignment, and risk-reward structure).

---

## Key Features

- **Global & Chinese Market Coverage**: Supports US/global equities (`NVDA`, `GOOGL`, `SPCX`), Hong Kong stocks (`0700.HK`), China A-Shares (`600519.SS`, `002516.SZ`), ETFs, and macro commodities (`GC=F`).
- **Automatic Language Matching**: With `--lang auto`, English stock names/inputs generate full English deliverables, while Chinese stock names/assets generate pure Chinese deliverables (using Chinese units `亿` instead of `B`, localized sectors/industries, and `暂无` for missing values).
- **10-Year Historical PE (TTM) & Valuation Bands**:
  - For A-Shares: pulls daily PE (TTM) history via EastMoney (`akshare`).
  - For US/Global equities: pulls up to 10 years of daily price history paired with 4-quarter rolling `Reported EPS` (with annual `income_stmt` EPS and listing-history fallbacks) to generate 3Y/5Y/10Y percentiles, benchmark bands ($P_{10}, P_{25}, P_{50}, P_{75}, P_{90}$), and a 2-panel valuation chart.
- **3-Year Financial Performance & Moat Deep-Dive**: Side-by-side comparison of revenue, operating income, net income, margins, ROE, OCF, FCF, YoY growth, and 2-year CAGR.
- **4-Panel Technical Chart & Tactical Trade Setup**: Price + 20/50/200 SMAs + Bollinger Bands, Volume + 20 SMA, RSI (14), and MACD (12, 26, 9), paired with accumulation zones, hard stop-loss levels, targets, and Risk-to-Reward ($R:R$) ratios.
- **4-Quadrant Confluence Rating**: Synthesizes Technical and Fundamental scores into Categories **A** (High-Probability Compounder), **B** (Speculative Squeeze), **C** (Value Accumulation Watch), or **D** (High Risk / Value Trap).
- **Multi-Stock Horizontal Comparison**: Automatically ranks and compares 2+ tickers in a dedicated portfolio comparison report (KPI summary cards, 11-row fundamental matrix, 7-column tactical trade matrix, and priority ranking).
- **Multi-Format Deliverables**: Generates Markdown (`.md`), responsive standalone HTML (`.html`), mobile-adapted/A4 PDF (`.pdf`) with continuous gap-free flow and word-safe wrapping, high-res PNG charts, and structured JSON (`*_data.json`).

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
