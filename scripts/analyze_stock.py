#!/usr/bin/env python3
"""
Stock Analysis Engine: Institutional Fundamental & Technical Confluence
Supports Global & Chinese Markets (A-Shares, HK Stocks, US Equities, Commodities, Crypto).
Generates institutional-grade deliverables: Markdown, standalone HTML, and printable PDF.
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import re
import requests
import shutil

try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from xhtml2pdf import pisa
    HAS_PISA = True
except ImportError:
    HAS_PISA = False

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import yfinance as yf

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
YAHEI_REGULAR = os.path.join(FONT_DIR, "msyh.ttc")
YAHEI_BOLD = os.path.join(FONT_DIR, "msyhbd.ttc")
SEGOE_REGULAR = os.path.join(FONT_DIR, "segoeui.ttf")
SEGOE_BOLD = os.path.join(FONT_DIR, "segoeuib.ttf")
FONT_PATH = YAHEI_REGULAR

TICKER_ALIASES = {
    "XAUUSD": "GC=F",
    "XAU-USD": "GC=F",
    "XAU/USD": "GC=F",
    "XAUUSD=X": "GC=F",
    "GOLD": "GC=F",
    "XAGUSD": "SI=F",
    "XAG-USD": "SI=F",
    "SILVER": "SI=F",
    "BTCUSD": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "DXY": "DX-Y.NYB",
    "CRUDE": "CL=F",
    "OIL": "CL=F",
}

CHINESE_NAME_ALIASES = {
    "贵州茅台": "600519.SS",
    "茅台": "600519.SS",
    "腾讯控股": "0700.HK",
    "腾讯": "0700.HK",
    "阿里巴巴": "9988.HK",
    "阿里": "9988.HK",
    "宁德时代": "300750.SZ",
    "比亚迪": "002594.SZ",
    "美团": "3690.HK",
    "小米集团": "1810.HK",
    "小米": "1810.HK",
    "中芯国际": "688981.SS",
    "招商银行": "600036.SS",
    "中国平安": "601318.SS",
    "五粮液": "000858.SZ",
    "恒生指数": "^HSI",
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "创业板指": "399006.SZ",
}

SECTOR_MAP_ZH = {
    "Basic Materials": "基础材料 / 精细化工",
    "Communication Services": "通信服务 / 互联网",
    "Consumer Cyclical": "非必需消费品 / 汽车家电",
    "Consumer Defensive": "必需消费品 / 食品饮料",
    "Energy": "能源 / 石油煤炭",
    "Financial Services": "金融服务 / 银行非银",
    "Healthcare": "医疗健康 / 医药生物",
    "Industrials": "工业制造 / 机械设备",
    "Real Estate": "房地产",
    "Technology": "信息技术 / 电子半导体",
    "Utilities": "公用事业 / 电力环保",
}

INDUSTRY_MAP_ZH = {
    "Aerospace & Defense": "航空航天与国防",
    "Chemicals": "精细化工",
    "Specialty Chemicals": "精细化学品",
    "Semiconductors": "半导体",
    "Semiconductor Equipment & Materials": "半导体设备与材料",
    "Electronic Components": "电子元件",
    "Consumer Electronics": "消费电子",
    "Computer Hardware": "计算机硬件",
    "Communication Equipment": "通信设备",
    "Auto Manufacturers": "汽车制造",
    "Auto Parts": "汽车零部件",
    "Software": "软件服务",
    "Software - Infrastructure": "基础软件",
    "Software - Application": "应用软件",
    "Information Technology Services": "信息技术服务",
    "Internet Content & Information": "互联网服务",
    "Internet Retail": "互联网零售",
    "Biotechnology": "生物制药",
    "Drug Manufacturers - General": "综合医药",
    "Medical Devices": "医疗器械",
    "Banks - Diversified": "综合银行",
    "Banks - Regional": "区域银行",
    "Asset Management": "资产管理",
    "Capital Markets": "资本市场",
    "Oil & Gas Integrated": "石油石化",
    "Utilities - Regulated Electric": "电力公用事业",
    "Real Estate - Development": "房地产开发",
    "Specialty Industrial Machinery": "专用工业机械",
    "Electrical Equipment & Parts": "电气设备",
    "Airlines": "航空运输",
    "Railroads": "铁路运输",
    "Solar": "光伏新能源",
    "Gold": "黄金采掘",
}


def get_unit_and_divisor(currency: str, is_zh: bool) -> tuple:
    """Return display unit and divisor; Chinese reports always use 亿 (1e8), never B."""
    if is_zh or str(currency or "").upper() in ["CNY", "CNH", "HKD"]:
        return "亿", 1e8
    return "B", 1e9


def search_ticker_by_chinese_name(name: str) -> Optional[str]:
    """Search ticker symbol given a Chinese company or stock name via EastMoney API."""
    try:
        url = f"https://searchapi.eastmoney.com/api/suggest/get?input={name}&type=14"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        data = r.json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        for item in items:
            code = item.get("Code", "")
            classify = item.get("Classify", "")
            if code and len(code) == 6 and code.isdigit():
                if code.startswith(("60", "68", "90")):
                    return f"{code}.SS"
                elif code.startswith(("00", "30", "20")):
                    return f"{code}.SZ"
                elif code.startswith(("8", "4")):
                    return f"{code}.BJ"
            elif code and ("HK" in classify or classify in ["HKStock"]):
                return f"{code.zfill(4)}.HK"
    except Exception:
        pass
    return None


def fetch_chinese_stock_name(ticker_sym: str) -> Optional[str]:
    """Fetch official Chinese stock name for China A-Shares, HK stocks, etc. via Tencent & EastMoney APIs."""
    clean = ticker_sym.upper().replace(".SS", "").replace(".SZ", "").replace(".BJ", "").replace(".HK", "").strip()

    # 1. Reverse lookup in CHINESE_NAME_ALIASES
    for name, sym in CHINESE_NAME_ALIASES.items():
        if sym.upper() == ticker_sym.upper():
            return name

    # 2. Tencent quote API (fast & reliable for A-shares & HK stocks)
    try:
        if ".HK" in ticker_sym.upper():
            q_sym = f"r_hk{clean.zfill(5)}"
        elif ".SS" in ticker_sym.upper() or clean.startswith(("6", "9")):
            q_sym = f"sh{clean}"
        elif ".SZ" in ticker_sym.upper() or clean.startswith(("0", "3")):
            q_sym = f"sz{clean}"
        elif ".BJ" in ticker_sym.upper() or clean.startswith(("4", "8")):
            q_sym = f"bj{clean}"
        else:
            q_sym = f"sh{clean}" if clean.isdigit() else clean

        url = f"http://qt.gtimg.cn/q={q_sym}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        text = r.content.decode("gbk", errors="ignore")
        parts = text.split("~")
        if len(parts) > 2 and parts[1].strip():
            c_name = parts[1].strip()
            if any("\u4e00" <= ch <= "\u9fff" for ch in c_name):
                return c_name
    except Exception:
        pass

    # 3. EastMoney suggest API fallback
    try:
        url = f"https://searchapi.eastmoney.com/api/suggest/get?input={clean}&type=14"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        data = r.json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        for item in items:
            code = item.get("Code", "")
            if code == clean or code.zfill(5) == clean.zfill(5):
                c_name = item.get("Name", "").strip()
                if any("\u4e00" <= ch <= "\u9fff" for ch in c_name):
                    return c_name
    except Exception:
        pass

    return None


def fetch_company_description(ticker_sym: str, info: dict, lang: str = "zh") -> str:
    """Fetch official concise company business description for China A-Shares (EastMoney F10 / THS) or global equities (yfinance)."""
    clean = ticker_sym.upper().replace(".SS", "").replace(".SZ", "").replace(".BJ", "").replace(".HK", "").strip()
    is_cn_ashare = ticker_sym.endswith((".SS", ".SZ", ".BJ")) or (clean.isdigit() and len(clean) == 6)

    if is_cn_ashare and lang == "zh":
        # 1. Primary: EastMoney HTTPS F10 Company Survey API
        try:
            if ticker_sym.endswith(".SS") or clean.startswith(("6", "9")):
                pfx = "SH"
            elif ticker_sym.endswith(".SZ") or clean.startswith(("0", "3")):
                pfx = "SZ"
            elif ticker_sym.endswith(".BJ") or clean.startswith(("4", "8")):
                pfx = "BJ"
            else:
                pfx = "SH"
            url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code={pfx}{clean}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            data = json.loads(r.content.decode("utf-8", errors="ignore"))
            gsjj = data.get("jbzl", {}).get("gsjj", "").strip()
            if gsjj:
                lines = [l.strip() for l in gsjj.split("\n") if l.strip()]
                clean_desc = " ".join(lines)
                if len(clean_desc) > 350:
                    clean_desc = clean_desc[:350].rsplit("。", 1)[0] + "。"
                return clean_desc
        except Exception:
            pass

        # 2. Fallback: akshare TongHuaShun (THS) Main Business & Product Profile
        try:
            import akshare as ak
            df_ths = ak.stock_zyjs_ths(symbol=clean)
            zy = df_ths["主营业务"].iloc[0] if "主营业务" in df_ths.columns else ""
            cp = df_ths["产品名称"].iloc[0] if "产品名称" in df_ths.columns else ""
            if zy:
                desc = f"主营业务涵盖{zy}"
                if cp and cp != zy:
                    desc += f"核心产品包括：{cp}。"
                return desc
        except Exception:
            pass

    # 3. yfinance summary or sector/industry fallback
    summary = info.get("longBusinessSummary") or info.get("description") or ""
    if summary:
        clean_summary = " ".join([l.strip() for l in summary.split("\n") if l.strip()])
        if lang == "zh":
            # If language is Chinese and description lacks Chinese characters, provide authentic Chinese profile
            zh_chars = len(re.findall(r'[一-龥]', clean_summary))
            if zh_chars < 15:
                sector_raw = info.get("sector", "")
                industry_raw = info.get("industry", "")
                sector_zh = SECTOR_MAP_ZH.get(sector_raw, "")
                industry_zh = INDUSTRY_MAP_ZH.get(industry_raw, "")
                cname = info.get("shortName") or ticker_sym
                if sector_zh and industry_zh and industry_zh not in sector_zh:
                    track_desc = f"{sector_zh}与{industry_zh}"
                elif sector_zh or industry_zh:
                    track_desc = sector_zh or industry_zh
                else:
                    track_desc = "核心主营"
                return f"{cname}深耕{track_desc}细分核心赛道，专业从事相关前沿产品与核心技术的研发、生产与销售。"
        if len(clean_summary) > 400:
            clean_summary = clean_summary[:400].rsplit(".", 1)[0] + "."
        return clean_summary

    sector = info.get("sector", "")
    industry = info.get("industry", "")
    if sector or industry:
        if lang == "zh":
            sec_zh = SECTOR_MAP_ZH.get(sector, "")
            ind_zh = INDUSTRY_MAP_ZH.get(industry, "")
            track_zh = f"{sec_zh}板块中{ind_zh}" if (sec_zh and ind_zh) else (sec_zh or ind_zh or "核心")
            return f"专注于{track_zh}细分领域的重点企业。"
        return f"An enterprise operating within the {sector} - {industry} sector."
    return "暂无主营业务详细描述。" if lang == "zh" else "No business profile available."


def normalize_ticker(input_ticker: str) -> str:
    cleaned = input_ticker.strip()
    if cleaned in CHINESE_NAME_ALIASES:
        return CHINESE_NAME_ALIASES[cleaned]

    # Check if input contains Chinese characters
    if any("\u4e00" <= ch <= "\u9fff" for ch in cleaned):
        searched = search_ticker_by_chinese_name(cleaned)
        if searched:
            return searched

    cleaned_upper = cleaned.upper()
    if cleaned_upper in TICKER_ALIASES:
        return TICKER_ALIASES[cleaned_upper]

    # Handle 6-digit pure numbers (A-Shares)
    if len(cleaned_upper) == 6 and cleaned_upper.isdigit():
        if cleaned_upper.startswith(("60", "68", "90")):
            return f"{cleaned_upper}.SS"
        elif cleaned_upper.startswith(("00", "30", "20")):
            return f"{cleaned_upper}.SZ"
        elif cleaned_upper.startswith(("8", "4")):
            return f"{cleaned_upper}.BJ"

    # Handle 4-5 digit pure numbers (HK Stocks)
    if cleaned_upper.isdigit() and len(cleaned_upper) in [4, 5]:
        return f"{cleaned_upper.zfill(4)}.HK"

    return cleaned_upper


def is_chinese_market(ticker_sym: str, ticker_input: str, info: dict) -> bool:
    """Detect if ticker is from China A-Share, Hong Kong, or Chinese company."""
    chinese_suffixes = [".SS", ".SZ", ".BJ", ".HK"]
    for s in chinese_suffixes:
        if ticker_sym.endswith(s) or ticker_input.upper().endswith(s):
            return True

    if ticker_input in CHINESE_NAME_ALIASES:
        return True

    if ticker_input.isdigit() and len(ticker_input) in [4, 5, 6]:
        return True

    country = str(info.get("country", "")).lower()
    if country in ["china", "hong kong", "taiwan"]:
        return True

    currency = str(info.get("currency", "")).upper()
    if currency in ["CNY", "CNH", "HKD"]:
        return True

    exchange = str(info.get("exchange", "")).upper()
    if any(ex in exchange for ex in ["SHH", "SHZ", "HKG", "BSE"]):
        return True

    return False


def format_analyst_target(target) -> str:
    if target is None:
        return "N/A"
    try:
        return f"{float(target):.2f}"
    except (ValueError, TypeError):
        return str(target)


def format_dividend_yield(dy) -> str:
    if dy is None:
        return "N/A"
    try:
        val = float(dy)
        pct = val if val > 0.5 else val * 100.0
        return f"{pct:.2f}%"
    except (ValueError, TypeError):
        return str(dy)


def format_currency_zh(curr: str) -> str:
    mapping = {
        "CNY": "人民币",
        "CNH": "人民币",
        "HKD": "港币",
        "USD": "美元",
        "EUR": "欧元",
        "JPY": "日元",
        "GBP": "英镑",
        "TWD": "新台币",
    }
    return mapping.get(str(curr).upper(), str(curr))


def format_period_zh(period: str) -> str:
    mapping = {
        "1d": "1天",
        "5d": "5天",
        "1mo": "近1个月",
        "3mo": "近3个月",
        "6mo": "近6个月",
        "1y": "近1年",
        "2y": "近2年",
        "5y": "近5年",
        "10y": "近10年",
        "ytd": "年初至今",
        "max": "全部历史",
    }
    return mapping.get(str(period).lower(), str(period))


def format_recommendation_zh(rec_key: str) -> str:
    if not rec_key or str(rec_key).lower() in ["none", "nan", "null"]:
        return "暂无明确评级"
    mapping = {
        "buy": "买入",
        "strong_buy": "强力买入",
        "outperform": "跑赢行业",
        "hold": "中性/持有",
        "neutral": "中性",
        "underperform": "弱于大市",
        "sell": "卖出",
    }
    return mapping.get(str(rec_key).lower(), str(rec_key))


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Comprehensive Institutional Fundamental and Technical Stock Analysis"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Stock ticker symbol (e.g. AAPL, MSFT, TSLA, 0700.HK, 600519.SS, XAUUSD)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional explicit Chinese/English company or stock name (e.g. '新亚强', '腾讯控股'). If omitted, auto-resolved in Chinese for Chinese market assets.",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="1y",
        choices=["3mo", "6mo", "1y", "2y", "5y"],
        help="Historical price period (default: 1y)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1d",
        choices=["1d", "1wk", "1mo"],
        help="Price interval / bar frequency: '1d' (Daily), '1wk' (Weekly), '1mo' (Monthly) (default: 1d)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./stock_analysis_output",
        help="Base directory to save outputs (default: ./stock_analysis_output)",
    )
    parser.add_argument(
        "--subfolder",
        type=str,
        default=None,
        help="Dedicated sub-folder name under output-dir (default: ticker symbol)",
    )
    parser.add_argument(
        "--report-name",
        type=str,
        default=None,
        help="Optional custom base filename for report deliverables (e.g. '新亚强' -> '新亚强.html', '新亚强.md', '新亚强.pdf'). If omitted, defaults to the resolved stock name.",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="auto",
        choices=["auto", "en", "zh"],
        help="Report language: 'auto' (detects Chinese market), 'en', or 'zh' (default: auto)",
    )
    return parser.parse_args()


def extract_historical_performance(ticker_obj) -> list:
    """Extract past 2-3 years of annual financial statements to evaluate multi-year performance trends."""
    try:
        fin = ticker_obj.financials
        cf = ticker_obj.cashflow
        bs = ticker_obj.balance_sheet
    except Exception:
        return []

    if fin is None or fin.empty:
        return []

    cols = sorted(list(fin.columns), reverse=True)
    valid_cols = []
    for c in cols:
        rev = None
        for r_key in ['Total Revenue', 'Operating Revenue']:
            if r_key in fin.index and not pd.isna(fin.loc[r_key, c]):
                rev = fin.loc[r_key, c]
                break
        if rev is not None and not pd.isna(rev):
            valid_cols.append(c)

    sample_cols = valid_cols[:3]
    if len(sample_cols) < 2:
        return []

    chrono_cols = sorted(sample_cols)
    records = []
    for c in chrono_cols:
        year_str = c.strftime('%Y') if hasattr(c, 'strftime') else str(c)[:4]
        date_str = c.strftime('%Y-%m-%d') if hasattr(c, 'strftime') else str(c)

        rev = None
        for r_key in ['Total Revenue', 'Operating Revenue']:
            if r_key in fin.index and not pd.isna(fin.loc[r_key, c]):
                rev = float(fin.loc[r_key, c])
                break

        gp = float(fin.loc['Gross Profit', c]) if 'Gross Profit' in fin.index and not pd.isna(fin.loc['Gross Profit', c]) else None
        op_inc = float(fin.loc['Operating Income', c]) if 'Operating Income' in fin.index and not pd.isna(fin.loc['Operating Income', c]) else None

        ni = None
        for n_key in ['Net Income Common Stockholders', 'Net Income']:
            if n_key in fin.index and not pd.isna(fin.loc[n_key, c]):
                ni = float(fin.loc[n_key, c])
                break

        ocf = float(cf.loc['Operating Cash Flow', c]) if (cf is not None and not cf.empty and 'Operating Cash Flow' in cf.index and c in cf.columns and not pd.isna(cf.loc['Operating Cash Flow', c])) else None
        fcf = float(cf.loc['Free Cash Flow', c]) if (cf is not None and not cf.empty and 'Free Cash Flow' in cf.index and c in cf.columns and not pd.isna(cf.loc['Free Cash Flow', c])) else None
        equity = float(bs.loc['Stockholders Equity', c]) if (bs is not None and not bs.empty and 'Stockholders Equity' in bs.index and c in bs.columns and not pd.isna(bs.loc['Stockholders Equity', c])) else None

        gm = (gp / rev * 100) if (gp is not None and rev and rev > 0) else None
        nm = (ni / rev * 100) if (ni is not None and rev and rev > 0) else None
        op_m = (op_inc / rev * 100) if (op_inc is not None and rev and rev > 0) else None
        roe = (ni / equity * 100) if (ni is not None and equity and equity > 0) else None

        records.append({
            'year': year_str,
            'date': date_str,
            'revenue': rev,
            'net_income': ni,
            'operating_income': op_inc,
            'gross_margin': gm,
            'net_margin': nm,
            'operating_margin': op_m,
            'roe': roe,
            'ocf': ocf,
            'fcf': fcf,
            'equity': equity,
        })

    for i in range(len(records)):
        if i > 0 and records[i-1]['revenue'] and records[i]['revenue']:
            prev_r = records[i-1]['revenue']
            records[i]['revenue_yoy'] = (records[i]['revenue'] - prev_r) / abs(prev_r) * 100
        else:
            records[i]['revenue_yoy'] = None

        if i > 0 and records[i-1]['net_income'] and records[i]['net_income']:
            prev_ni = records[i-1]['net_income']
            records[i]['net_income_yoy'] = (records[i]['net_income'] - prev_ni) / abs(prev_ni) * 100
        else:
            records[i]['net_income_yoy'] = None

        if i > 0 and records[i-1]['operating_income'] and records[i]['operating_income']:
            prev_op = records[i-1]['operating_income']
            records[i]['operating_income_yoy'] = (records[i]['operating_income'] - prev_op) / abs(prev_op) * 100
        else:
            records[i]['operating_income_yoy'] = None

        if i > 0 and records[i-1]['gross_margin'] is not None and records[i]['gross_margin'] is not None:
            records[i]['gross_margin_change'] = records[i]['gross_margin'] - records[i-1]['gross_margin']
        else:
            records[i]['gross_margin_change'] = None

        if i > 0 and records[i-1]['net_margin'] is not None and records[i]['net_margin'] is not None:
            records[i]['net_margin_change'] = records[i]['net_margin'] - records[i-1]['net_margin']
        else:
            records[i]['net_margin_change'] = None

        if i > 0 and records[i-1]['roe'] is not None and records[i]['roe'] is not None:
            records[i]['roe_change'] = records[i]['roe'] - records[i-1]['roe']
        else:
            records[i]['roe_change'] = None

    return records


def format_historical_performance_table(hist_perf: list, currency: str = 'CNY', is_zh: bool = True) -> tuple:
    """Format past 2-3 years performance comparison into Markdown and HTML tables."""
    if not hist_perf or len(hist_perf) < 2:
        return "", ""

    curr_sym = "¥" if currency in ["CNY", "CNH"] else ("HK$" if currency == "HKD" else "$")
    unit_name, divisor = get_unit_and_divisor(currency, is_zh)
    na_str = "暂无" if is_zh else "N/A"

    years = [r['year'] for r in hist_perf]
    has_2y = (len(hist_perf) >= 3)

    def fmt_amt(val):
        if val is None:
            return na_str
        return f"{curr_sym}{val / divisor:.2f}{unit_name}"

    def fmt_pct(val):
        if val is None:
            return na_str
        return f"{val:.1f}%"

    def fmt_yoy(val):
        if val is None:
            return "-"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%"

    def fmt_pp(val):
        if val is None:
            return "-"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%"

    def calc_cagr(start_val, end_val, n_years):
        if start_val and end_val and start_val > 0 and end_val > 0 and n_years > 0:
            cagr = ((end_val / start_val) ** (1 / n_years) - 1) * 100
            sign = "+" if cagr > 0 else ""
            return f"{sign}{cagr:.1f}%"
        return "-"

    n_years = len(hist_perf) - 1
    t_start = hist_perf[0]
    t_latest = hist_perf[-1]

    metrics = [
        ("营业收入", "Total Revenue", "revenue", "amt", True),
        ("营业利润", "Operating Income", "operating_income", "amt", True),
        ("归母净利润", "Net Income", "net_income", "amt", True),
        ("毛利率", "Gross Margin", "gross_margin", "pct", False),
        ("营业利润率", "Operating Margin", "operating_margin", "pct", False),
        ("净利率", "Net Profit Margin", "net_margin", "pct", False),
        ("净资产收益率", "ROE", "roe", "pct", False),
        ("经营活动现金流", "Operating Cash Flow", "ocf", "amt", True),
        ("自由现金流", "Free Cash Flow", "fcf", "amt", False),
    ]

    # Markdown Table
    md_header = "| " + ("核心经营与财务指标" if is_zh else "Key Financial Metric")
    for y in years[:-1]:
        md_header += f" | {y}年" if is_zh else f" | {y}"
    md_header += f" | {years[-1]}年最新" if is_zh else f" | {years[-1]} (Latest)"
    md_header += f" | {'同比变动' if is_zh else 'YoY Change'}"
    if has_2y:
        md_header += f" | {'2年复合变动' if is_zh else '2Y Change / CAGR'}"
    md_header += " |\n"
    md_sep = "| :--- " + "| :--- " * (len(years) + (2 if has_2y else 1)) + "|\n"
    md_rows = ""

    for name_zh, name_en, key, m_type, calc_growth in metrics:
        name = name_zh if is_zh else name_en
        row = f"| **{name}** "
        for r in hist_perf:
            val = r.get(key)
            row += f"| {fmt_amt(val) if m_type == 'amt' else fmt_pct(val)} "

        latest_r = hist_perf[-1]
        prev_r = hist_perf[-2]
        if m_type == 'amt':
            yoy = latest_r.get(f"{key}_yoy")
            if yoy is None and latest_r.get(key) and prev_r.get(key) and prev_r.get(key) != 0:
                yoy = (latest_r[key] - prev_r[key]) / abs(prev_r[key]) * 100
            row += f"| {fmt_yoy(yoy)} "
        else:
            chg = None
            if latest_r.get(key) is not None and prev_r.get(key) is not None:
                chg = latest_r[key] - prev_r[key]
            row += f"| {fmt_pp(chg)} "

        if has_2y:
            if m_type == 'amt' and calc_growth:
                row += f"| {calc_cagr(t_start.get(key), t_latest.get(key), n_years)} "
            elif m_type == 'pct':
                diff_2y = None
                if t_latest.get(key) is not None and t_start.get(key) is not None:
                    diff_2y = t_latest[key] - t_start[key]
                row += f"| {fmt_pp(diff_2y)} "
            else:
                row += "| - "

        row += "|\n"
        md_rows += row

    md_table = md_header + md_sep + md_rows

    # HTML Table
    html_header = f"<thead><tr><th style='width: 26%;'>{'核心经营与财务指标' if is_zh else 'Key Financial Metric'}</th>"
    col_w = "14%" if has_2y else "20%"
    for y in years[:-1]:
        html_header += f"<th style='width: {col_w};'>{y}{'年' if is_zh else ''}</th>"
    html_header += f"<th style='width: {'15%' if has_2y else '24%'};'>{years[-1]}{'年最新' if is_zh else ' (Latest)'}</th>"
    html_header += f"<th style='width: {'15%' if has_2y else '20%'};'>{'同比变动' if is_zh else 'YoY Change'}</th>"
    if has_2y:
        html_header += f"<th style='width: 16%;'>{'2年复合变动' if is_zh else '2Y Change / CAGR'}</th>"
    html_header += "</tr></thead>\n"

    html_rows = "<tbody>\n"
    for name_zh, name_en, key, m_type, calc_growth in metrics:
        name = name_zh if is_zh else name_en
        html_rows += f"<tr><td><strong>{name}</strong></td>"
        for r in hist_perf:
            val = r.get(key)
            html_rows += f"<td>{fmt_amt(val) if m_type == 'amt' else fmt_pct(val)}</td>"

        latest_r = hist_perf[-1]
        prev_r = hist_perf[-2]
        if m_type == 'amt':
            yoy = latest_r.get(f"{key}_yoy")
            if yoy is None and latest_r.get(key) and prev_r.get(key) and prev_r.get(key) != 0:
                yoy = (latest_r[key] - prev_r[key]) / abs(prev_r[key]) * 100
            yoy_txt = fmt_yoy(yoy)
            color = "#16a34a" if (yoy and yoy > 0) else ("#dc2626" if (yoy and yoy < 0) else "inherit")
            html_rows += f"<td style='color: {color}; font-weight: 600;'>{yoy_txt}</td>"
        else:
            chg = None
            if latest_r.get(key) is not None and prev_r.get(key) is not None:
                chg = latest_r[key] - prev_r[key]
            chg_txt = fmt_pp(chg)
            color = "#16a34a" if (chg and chg > 0) else ("#dc2626" if (chg and chg < 0) else "inherit")
            html_rows += f"<td style='color: {color}; font-weight: 600;'>{chg_txt}</td>"

        if has_2y:
            if m_type == 'amt' and calc_growth:
                cagr_txt = calc_cagr(t_start.get(key), t_latest.get(key), n_years)
                color = "#16a34a" if ("+" in cagr_txt) else ("#dc2626" if ("-" in cagr_txt and cagr_txt != "-") else "inherit")
                html_rows += f"<td style='color: {color}; font-weight: 600;'>{cagr_txt}</td>"
            elif m_type == 'pct':
                diff_2y = None
                if t_latest.get(key) is not None and t_start.get(key) is not None:
                    diff_2y = t_latest[key] - t_start[key]
                diff_txt = fmt_pp(diff_2y)
                color = "#16a34a" if (diff_2y and diff_2y > 0) else ("#dc2626" if (diff_2y and diff_2y < 0) else "inherit")
                html_rows += f"<td style='color: {color}; font-weight: 600;'>{diff_txt}</td>"
            else:
                html_rows += "<td>-</td>"

        html_rows += "</tr>\n"
    html_rows += "</tbody>"

    html_table = f'<table class="data-table">\n{html_header}{html_rows}\n</table>'
    return md_table, html_table


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate moving averages, RSI, MACD, Bollinger Bands, ATR, and Volume SMA."""
    # Moving Averages
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    df["SMA_200"] = df["Close"].rolling(window=200).mean()
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()

    # Bollinger Bands (20 periods, 2 standard deviations)
    rolling_std = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = df["SMA_20"] + (rolling_std * 2)
    df["BB_Lower"] = df["SMA_20"] - (rolling_std * 2)
    df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["SMA_20"]

    # RSI (14 periods - Wilder smoothing)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema_12 - ema_26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # Average True Range (ATR 14)
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR_14"] = tr.rolling(window=14).mean()

    # Volume Moving Average
    df["Volume_SMA_20"] = df["Volume"].rolling(window=20).mean()

    return df


def detect_support_resistance(df: pd.DataFrame, window: int = 15) -> tuple:
    """Find recent local support (minima) and resistance (maxima) levels."""
    close = df["Close"].values
    supports = []
    resistances = []

    for i in range(window, len(close) - window):
        curr = close[i]
        if curr == min(close[i - window : i + window + 1]):
            supports.append(curr)
        elif curr == max(close[i - window : i + window + 1]):
            resistances.append(curr)

    latest_price = close[-1]
    valid_supports = [s for s in supports if s < latest_price]
    valid_resistances = [r for r in resistances if r > latest_price]

    nearest_support = max(valid_supports) if valid_supports else float(df["Low"].min())
    nearest_resistance = min(valid_resistances) if valid_resistances else float(df["High"].max())

    return round(nearest_support, 2), round(nearest_resistance, 2)


def get_timeframe_info(df: pd.DataFrame, interval: str = "1d", lang: str = "en") -> dict:
    """Detect and return human-readable metadata for the chart timeframe/scale."""
    is_zh = (lang == "zh")
    intv = (interval or "1d").lower()

    # Detect if interval wasn't provided or mismatch with index
    if len(df) > 2 and isinstance(df.index, pd.DatetimeIndex):
        diff_days = (df.index[-1] - df.index[-2]).total_seconds() / 86400
        if diff_days >= 20:
            intv = "1mo"
        elif diff_days >= 4:
            intv = "1wk"

    if intv == "1wk":
        code = "1W"
        name = "周线" if is_zh else "Weekly"
        full_name = "周线级别" if is_zh else "Weekly Timeframe (1W)"
        unit_zh = "周"
        unit_en = "W"
        bar_desc = "单K线周期: 1周" if is_zh else "Bar Frequency: 1 Week"
    elif intv == "1mo":
        code = "1M"
        name = "月线" if is_zh else "Monthly"
        full_name = "月线级别" if is_zh else "Monthly Timeframe (1M)"
        unit_zh = "月"
        unit_en = "M"
        bar_desc = "单K线周期: 1月" if is_zh else "Bar Frequency: 1 Month"
    else:
        code = "1D"
        name = "日线" if is_zh else "Daily"
        full_name = "日线级别" if is_zh else "Daily Timeframe (1D)"
        unit_zh = "日"
        unit_en = "D"
        bar_desc = "单K线周期: 1日" if is_zh else "Bar Frequency: 1 Day"

    return {
        "code": code,
        "name": name,
        "full_name": full_name,
        "unit_zh": unit_zh,
        "unit_en": unit_en,
        "bar_desc": bar_desc,
        "interval_raw": intv,
    }


def generate_chart(df: pd.DataFrame, ticker: str, company_name: str, output_path: str, currency: str = "USD", lang: str = "en", interval: str = "1d", period: str = "1y"):
    """Generate high-resolution 4-panel technical chart (Price, Volume, RSI, MACD) with timeframe & indicator labeling."""
    is_zh = (lang == "zh")
    tf = get_timeframe_info(df, interval, lang)
    curr_sym = "¥" if currency in ["CNY", "CNH"] else ("HK$" if currency == "HKD" else "$")

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    import matplotlib.font_manager as fm
    if os.path.exists(YAHEI_REGULAR):
        fm.fontManager.addfont(YAHEI_REGULAR)
    if os.path.exists(YAHEI_BOLD):
        fm.fontManager.addfont(YAHEI_BOLD)
    if os.path.exists(SEGOE_REGULAR):
        fm.fontManager.addfont(SEGOE_REGULAR)
    if os.path.exists(SEGOE_BOLD):
        fm.fontManager.addfont(SEGOE_BOLD)

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "Microsoft YaHei UI",
        "Segoe UI",
        "SimHei",
        "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax_price, ax_vol, ax_rsi, ax_macd) = plt.subplots(
        4, 1, figsize=(15, 12.5), sharex=True, gridspec_kw={"height_ratios": [4.8, 1.8, 2.0, 2.2]}
    )

    close_label = "收盘价" if is_zh else "Close Price"
    sma20_label = f"20{tf['unit_zh']}均线" if is_zh else f"SMA 20 ({tf['unit_en']})"
    sma50_label = f"50{tf['unit_zh']}均线" if is_zh else f"SMA 50 ({tf['unit_en']})"
    sma200_label = f"200{tf['unit_zh']}均线 · 牛熊线" if is_zh else f"SMA 200 ({tf['unit_en']})"
    bb_label = f"布林通道 20{tf['unit_zh']} · 2σ" if is_zh else f"BB (20-{tf['unit_en']}, 2 std)"

    # 1. Price Panel
    ax_price.plot(df.index, df["Close"], label=close_label, color="#1f77b4", linewidth=2.2)
    if "SMA_20" in df.columns and df["SMA_20"].notna().any():
        ax_price.plot(df.index, df["SMA_20"], label=sma20_label, color="#2ca02c", linestyle="--", linewidth=1.5)
    if "SMA_50" in df.columns and df["SMA_50"].notna().any():
        ax_price.plot(df.index, df["SMA_50"], label=sma50_label, color="#ff7f0e", linestyle="-.", linewidth=1.7)
    if "SMA_200" in df.columns and df["SMA_200"].notna().any():
        ax_price.plot(df.index, df["SMA_200"], label=sma200_label, color="#d62728", linewidth=2.0)

    if "BB_Upper" in df.columns and df["BB_Upper"].notna().any():
        ax_price.plot(df.index, df["BB_Upper"], color="#64748b", linestyle=":", linewidth=1.1, alpha=0.8)
        ax_price.plot(df.index, df["BB_Lower"], color="#64748b", linestyle=":", linewidth=1.1, alpha=0.8)
        ax_price.fill_between(df.index, df["BB_Upper"], df["BB_Lower"], color="#bcbd22", alpha=0.09, label=bb_label)

    curr_close = df["Close"].iloc[-1]
    supp, res = detect_support_resistance(df)
    supp_label = f"关键支撑 {curr_sym}{supp:.2f}" if is_zh else f"Key Support ({curr_sym}{supp:.2f})"
    res_label = f"关键阻力 {curr_sym}{res:.2f}" if is_zh else f"Key Resistance ({curr_sym}{res:.2f})"
    ax_price.axhline(supp, color="#16a34a", linestyle="--", linewidth=1.8, alpha=0.9, label=supp_label)
    ax_price.axhline(res, color="#dc2626", linestyle="--", linewidth=1.8, alpha=0.9, label=res_label)

    title_main = (
        f"{company_name} {ticker} · 全维度量价与动量图表"
        if is_zh else
        f"{ticker} ({company_name}) - Technical Structure & Momentum Analysis"
    )
    period_str_disp = format_period_zh(period) if is_zh else period.upper()
    title_sub = (
        f"时间级别: {tf['name']}  |  数据周期: {period_str_disp}  |  最新价: {curr_sym}{curr_close:.2f}  |  更新: {datetime.now().strftime('%Y-%m-%d')}"
        if is_zh else
        f"Time Scale: [{tf['full_name']}]  |  Period: {period.upper()}  |  Last: {curr_sym}{curr_close:.2f}  |  Date: {datetime.now().strftime('%Y-%m-%d')}"
    )
    ax_price.set_title(f"{title_main}\n{title_sub}", fontsize=14, fontweight="bold", pad=14, linespacing=1.35)
    curr_unit_chart = "元" if is_zh and currency in ["CNY", "CNH"] else (format_currency_zh(currency) if is_zh else currency)
    ax_price.set_ylabel(f"价格 ({curr_unit_chart})\n[{tf['name'] if is_zh else tf['code']}]", fontsize=12, fontweight="bold", labelpad=8)
    ax_price.tick_params(axis="both", which="major", labelsize=11)
    ax_price.legend(loc="upper left", framealpha=0.95, fontsize=10, ncol=3)
    ax_price.grid(True, linestyle="--", alpha=0.5)

    badge_p1 = f"价格走势与均线 · {tf['name']}" if is_zh else f"[P1] Price Action & MAs · {tf['code']}"
    ax_price.text(0.988, 0.93, badge_p1, transform=ax_price.transAxes, ha="right", va="top",
                  fontsize=10.5, fontweight="bold", color="#1e293b",
                  bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.92))

    # 2. Volume Panel
    colors = np.where(df["Close"] >= df["Open"], "#16a34a", "#dc2626")
    vol_label = f"成交量 ({tf['name']})" if is_zh else f"Volume ({tf['code']})"
    vol_sma_label = f"20{tf['unit_zh']}成交均量" if is_zh else f"20-{tf['unit_en']} Vol SMA"
    ax_vol.bar(df.index, df["Volume"], color=colors, alpha=0.75, width=0.85, label=vol_label)
    if "Volume_SMA_20" in df.columns and df["Volume_SMA_20"].notna().any():
        ax_vol.plot(df.index, df["Volume_SMA_20"], color="#1f77b4", linewidth=1.5, label=vol_sma_label)
    ax_vol.set_ylabel(f"成交量\n[{tf['name'] if is_zh else tf['code']}]" if is_zh else f"Volume\n[{tf['code']}]", fontsize=12, fontweight="bold", labelpad=8)
    ax_vol.tick_params(axis="both", which="major", labelsize=11)
    ax_vol.legend(loc="upper left", framealpha=0.95, fontsize=10)
    ax_vol.grid(True, linestyle="--", alpha=0.5)

    badge_p2 = f"量能与活跃度 · {tf['name']}" if is_zh else f"[P2] Volume & Liquidity · {tf['code']}"
    ax_vol.text(0.988, 0.88, badge_p2, transform=ax_vol.transAxes, ha="right", va="top",
                fontsize=10, fontweight="bold", color="#1e293b",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.92))

    # 3. Dedicated RSI Panel
    rsi_label = f"14{tf['unit_zh']} RSI" if is_zh else f"RSI (14-{tf['unit_en']})"
    ax_rsi.plot(df.index, df["RSI_14"], color="#7c3aed", linewidth=1.8, label=rsi_label)
    ax_rsi.axhline(70, color="#dc2626", linestyle="--", alpha=0.85, linewidth=1.2, label="超买阈值 70" if is_zh else "Overbought (70)")
    ax_rsi.axhline(30, color="#16a34a", linestyle="--", alpha=0.85, linewidth=1.2, label="超卖阈值 30" if is_zh else "Oversold (30)")
    ax_rsi.axhline(50, color="#64748b", linestyle=":", alpha=0.7, linewidth=1.0)
    ax_rsi.fill_between(df.index, 70, 100, color="#dc2626", alpha=0.08)
    ax_rsi.fill_between(df.index, 0, 30, color="#16a34a", alpha=0.08)
    ax_rsi.set_ylim(15, 85)
    ax_rsi.set_yticks([30, 50, 70])
    ax_rsi.set_ylabel(f"RSI (14)\n[{tf['name'] if is_zh else tf['code']}]", fontsize=12, fontweight="bold", color="#7c3aed", labelpad=8)
    ax_rsi.tick_params(axis="both", which="major", labelsize=11)
    ax_rsi.legend(loc="upper left", framealpha=0.95, fontsize=10, ncol=3)
    ax_rsi.grid(True, linestyle="--", alpha=0.5)

    badge_p3 = f"RSI 相对强弱 · {tf['name']}" if is_zh else f"[P3] Momentum RSI(14) · {tf['code']}"
    ax_rsi.text(0.988, 0.88, badge_p3, transform=ax_rsi.transAxes, ha="right", va="top",
                fontsize=10, fontweight="bold", color="#7c3aed",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.92))

    # 4. Dedicated MACD Panel
    macd_fast_label = f"MACD 快线 12, 26" if is_zh else f"MACD Fast (12,26)"
    macd_sig_label = f"信号线 9" if is_zh else f"Signal (9)"
    macd_hist_label = "动能柱" if is_zh else "MACD Hist"
    ax_macd.plot(df.index, df["MACD"], color="#0284c7", linewidth=1.8, label=macd_fast_label)
    ax_macd.plot(df.index, df["MACD_Signal"], color="#d946ef", linewidth=1.6, linestyle="--", label=macd_sig_label)
    macd_colors = np.where(df["MACD_Hist"] >= 0, "#16a34a", "#dc2626")
    ax_macd.bar(df.index, df["MACD_Hist"], color=macd_colors, alpha=0.55, width=0.85, label=macd_hist_label)
    ax_macd.axhline(0, color="#64748b", linestyle="-", linewidth=1.0, alpha=0.7)
    ax_macd.set_ylabel(f"MACD\n[{tf['name'] if is_zh else tf['code']}]", fontsize=12, fontweight="bold", color="#0284c7", labelpad=8)
    ax_macd.tick_params(axis="both", which="major", labelsize=11)
    ax_macd.legend(loc="upper left", framealpha=0.95, fontsize=10, ncol=3)
    ax_macd.grid(True, linestyle="--", alpha=0.5)

    badge_p4 = f"MACD 动量趋势 · {tf['name']}" if is_zh else f"[P4] MACD Trend · {tf['code']}"
    ax_macd.text(0.988, 0.88, badge_p4, transform=ax_macd.transAxes, ha="right", va="top",
                fontsize=10, fontweight="bold", color="#0284c7",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.92))

    ax_macd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m" if is_zh else "%b %Y"))
    ax_macd.tick_params(axis="x", which="major", labelsize=11)
    fig.autofmt_xdate()

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close()


def build_global_pe_ttm_series(ticker_sym: str, info: dict = None, df_history: pd.DataFrame = None) -> tuple:
    """
    Build up to 10 years of daily PE (TTM) series for global/US/HK equities.
    Uses 10y daily prices + quarterly Reported EPS (4-quarter rolling TTM) when available,
    falling back to price-implied PE history when quarterly EPS history is insufficient.
    Returns (dates_series, pe_series, data_source).
    """
    try:
        df_10y, ticker_obj = fetch_ticker_history(ticker_sym, "10y", interval="1d", max_retries=2)
    except Exception:
        df_10y, ticker_obj = pd.DataFrame(), None

    if df_10y is None or df_10y.empty:
        df_10y = df_history
    elif df_history is not None and not df_history.empty and len(df_history) > len(df_10y):
        df_10y = df_history

    if df_10y is None or df_10y.empty or "Close" not in df_10y.columns:
        return None, None, None

    price_df = pd.DataFrame({
        "date": pd.to_datetime(df_10y.index).tz_localize(None).normalize().astype("datetime64[ns]"),
        "close": pd.to_numeric(df_10y["Close"], errors="coerce").values,
    }).dropna().sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)

    if price_df.empty:
        return None, None, None

    # 1. Try true 10-year historical PE (TTM) from quarterly Reported EPS (with retry for Yahoo intermittent KeyError)
    ed_ticker = yf.Ticker(ticker_sym)
    for _attempt in range(3):
        try:
            ed = ed_ticker.get_earnings_dates(limit=48)
            if ed is not None and not ed.empty and "Reported EPS" in ed.columns:
                rep = ed["Reported EPS"].dropna()
                if len(rep) >= 4:
                    eps_df = pd.DataFrame({
                        "date": pd.to_datetime(rep.index).tz_localize(None).normalize().astype("datetime64[ns]"),
                        "eps_q": pd.to_numeric(rep.values, errors="coerce"),
                    }).dropna().sort_values("date").drop_duplicates(subset=["date"])
                    eps_df["ttm_eps"] = eps_df["eps_q"].rolling(4).sum()
                    eps_df = eps_df.dropna(subset=["ttm_eps"])
                    eps_df = eps_df[eps_df["ttm_eps"] > 0].reset_index(drop=True)
                    if not eps_df.empty:
                        merged = pd.merge_asof(price_df, eps_df[["date", "ttm_eps"]], on="date", direction="backward")
                        merged = merged.dropna(subset=["ttm_eps"])
                        merged["pe"] = merged["close"] / merged["ttm_eps"]
                        merged = merged[(merged["pe"] > 0) & (merged["pe"] < 2000)].reset_index(drop=True)
                        if len(merged) >= 20:
                            return merged["date"], merged["pe"], "10Y Historical PE (TTM)"
        except Exception:
            if _attempt < 2:
                time.sleep(1.5)

    # 1b. Secondary historical EPS path: annual Diluted/Basic EPS from income_stmt (4-5Y)
    try:
        inc = ed_ticker.income_stmt
        if inc is not None and not inc.empty:
            eps_row = None
            for label in ["Diluted EPS", "Basic EPS"]:
                if label in inc.index:
                    eps_row = inc.loc[label].dropna()
                    break
            if eps_row is not None and not eps_row.empty:
                ann_df = pd.DataFrame({
                    "date": pd.to_datetime(eps_row.index).tz_localize(None).normalize().astype("datetime64[ns]"),
                    "ttm_eps": pd.to_numeric(eps_row.values, errors="coerce"),
                }).dropna().sort_values("date").drop_duplicates(subset=["date"])
                ann_df = ann_df[ann_df["ttm_eps"] > 0].reset_index(drop=True)
                if not ann_df.empty:
                    merged = pd.merge_asof(price_df, ann_df[["date", "ttm_eps"]], on="date", direction="backward")
                    merged = merged.dropna(subset=["ttm_eps"])
                    merged["pe"] = merged["close"] / merged["ttm_eps"]
                    merged = merged[(merged["pe"] > 0) & (merged["pe"] < 2000)].reset_index(drop=True)
                    if len(merged) >= 20:
                        return merged["date"], merged["pe"], "Historical Annual EPS PE"
    except Exception:
        pass

    # 2. Fallback: Price-Implied PE history on up to 10y prices
    try:
        cur_pe = info.get("trailingPE") if info else None
        cur_price = (info.get("currentPrice") or info.get("regularMarketPrice")) if info else None
        if (not cur_price or cur_price <= 0):
            cur_price = float(price_df["close"].iloc[-1])
        if cur_pe and cur_pe > 0 and cur_price and cur_price > 0:
            eps = cur_price / cur_pe
            pe_vals = price_df["close"] / eps
            mask = pe_vals > 0
            if mask.sum() >= 20:
                return price_df.loc[mask, "date"].reset_index(drop=True), pe_vals.loc[mask].reset_index(drop=True), "Price-Implied History"
    except Exception:
        pass

    return None, None, None


def generate_pe_percentile_chart(ticker_sym: str, company_name: str, output_path: str, info: dict = None, df_history: pd.DataFrame = None, lang: str = "en") -> bool:
    """
    Generate institutional 2-panel 10-year (or max available) PE(TTM) valuation band & percentile oscillator chart.
    Panel 1: Historical PE(TTM) curve with 10%, 25%, 50%, 75%, 90% benchmark bands & shaded zones.
    Panel 2: Historical expanding/rolling percentile oscillator (%) with Deep Value and Overvalued zones.
    """
    is_zh = (lang == "zh")
    clean_sym = ticker_sym.upper().replace(".SS", "").replace(".SZ", "").replace(".BJ", "").strip()

    dates = None
    pe_series = None

    # 1. Primary path for A-Shares: Direct EastMoney daily valuation history
    if clean_sym.isdigit() and len(clean_sym) == 6:
        try:
            import akshare as ak
            val_df = ak.stock_value_em(symbol=clean_sym)
            if val_df is not None and not val_df.empty:
                date_cols = [c for c in val_df.columns if "日期" in c]
                pe_cols = [c for c in val_df.columns if "PE(TTM)" in c]
                if date_cols and pe_cols:
                    date_col = date_cols[0]
                    pe_col = pe_cols[0]
                    val_df[date_col] = pd.to_datetime(val_df[date_col])
                    val_df = val_df.sort_values(date_col).reset_index(drop=True)

                    cutoff_10y = val_df[date_col].max() - pd.DateOffset(years=10)
                    df_sub = val_df[val_df[date_col] >= cutoff_10y].dropna(subset=[pe_col])
                    df_sub = df_sub[df_sub[pe_col] > 0].reset_index(drop=True)
                    if len(df_sub) >= 20:
                        dates = df_sub[date_col]
                        pe_series = df_sub[pe_col]
        except Exception:
            pass

    # 2. Fallback for global equities or when akshare is unavailable
    if pe_series is None or pe_series.empty:
        g_dates, g_pe, _ = build_global_pe_ttm_series(ticker_sym, info=info, df_history=df_history)
        if g_dates is not None and g_pe is not None and not g_pe.empty:
            dates = g_dates
            pe_series = g_pe

    if pe_series is None or pe_series.empty:
        return False

    # Setup styles and fonts
    import matplotlib.font_manager as fm
    font_prop = fm.FontProperties(fname=YAHEI_REGULAR) if os.path.exists(YAHEI_REGULAR) else None
    font_prop_bold = fm.FontProperties(fname=YAHEI_BOLD) if os.path.exists(YAHEI_BOLD) else None

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI", "SimHei", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # Compute expanding rolling percentile
    rolling_pct = []
    for i in range(len(pe_series)):
        hist = pe_series.iloc[:i + 1]
        pct = (hist < pe_series.iloc[i]).mean() * 100
        rolling_pct.append(pct)

    p10 = float(np.percentile(pe_series, 10))
    p25 = float(np.percentile(pe_series, 25))
    p50 = float(np.percentile(pe_series, 50))
    p75 = float(np.percentile(pe_series, 75))
    p90 = float(np.percentile(pe_series, 90))
    cur_pe = float(pe_series.iloc[-1])
    cur_pct = float((pe_series < cur_pe).mean() * 100)
    max_pe = float(pe_series.max())

    last_date = dates.iloc[-1] if hasattr(dates, "iloc") else dates[-1]
    first_date = dates.iloc[0] if hasattr(dates, "iloc") else dates[0]

    total_days = max(1, (last_date - first_date).days)
    x_min = first_date - pd.Timedelta(days=int(total_days * 0.02))
    x_max = last_date + pd.Timedelta(days=int(total_days * 0.20))
    badge_date = x_max - pd.Timedelta(days=int(total_days * 0.01))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True, gridspec_kw={"height_ratios": [3.6, 1.8]})

    # Panel 1: Headroom guaranteed above max_pe
    ax1.set_ylim(0, max(max_pe, p90, cur_pe) * 1.30)
    ax1.set_xlim(x_min, x_max)

    pe_label = f"PE TTM 走势 · 当前 {cur_pe:.1f}倍" if is_zh else f"PE (TTM) History (Current: {cur_pe:.1f}x)"
    ax1.plot(dates, pe_series, color="#1d4ed8", linewidth=2.0, label=pe_label, zorder=4)

    # Horizontal benchmark lines
    ax1.axhline(p90, color="#dc2626", linestyle="--", linewidth=1.3, alpha=0.85, zorder=3)
    ax1.axhline(p75, color="#ea580c", linestyle=":", linewidth=1.3, alpha=0.85, zorder=3)
    ax1.axhline(p50, color="#0284c7", linestyle="--", linewidth=1.4, alpha=0.85, zorder=3)
    ax1.axhline(p25, color="#16a34a", linestyle=":", linewidth=1.3, alpha=0.85, zorder=3)
    ax1.axhline(p10, color="#059669", linestyle="--", linewidth=1.3, alpha=0.85, zorder=3)

    sh_mid = "25% - 75% 合理估值中枢区间" if is_zh else "25% - 75% Fair Valuation Band"
    sh_low = "10% - 25% 价值安全配置带" if is_zh else "10% - 25% Value Safety Margin"
    sh_hi = ">90% 估值高位警戒带" if is_zh else ">90% Overvaluation Hazard Band"

    ax1.fill_between(dates, p25, p75, color="#bae6fd", alpha=0.22, label=sh_mid)
    ax1.fill_between(dates, p10, p25, color="#bbf7d0", alpha=0.28, label=sh_low)
    ax1.fill_between(dates, p90, max(max_pe, p90, cur_pe) * 1.30, color="#fecaca", alpha=0.18, label=sh_hi)

    # Benchmark level badges on the far right spine
    benchmarks = [
        (p90, "#dc2626", "#fee2e2", "#fca5a5", f" P90: {p90:.1f}倍 · 90% " if is_zh else f" P90: {p90:.1f}x (90th) "),
        (p75, "#ea580c", "#ffedd5", "#fdba74", f" P75: {p75:.1f}倍 · 75% " if is_zh else f" P75: {p75:.1f}x (75th) "),
        (p50, "#0284c7", "#e0f2fe", "#7dd3fc", f" P50: {p50:.1f}倍 · 中位数 " if is_zh else f" P50: {p50:.1f}x (Median) "),
        (p25, "#16a34a", "#dcfce7", "#86efac", f" P25: {p25:.1f}倍 · 25% " if is_zh else f" P25: {p25:.1f}x (25th) "),
        (p10, "#059669", "#d1fae5", "#6ee7b7", f" P10: {p10:.1f}倍 · 10% " if is_zh else f" P10: {p10:.1f}x (10th) "),
    ]
    for val, text_col, bg_col, border_col, label_str in benchmarks:
        ax1.text(
            badge_date, val, label_str,
            color=text_col, ha="right", va="center",
            fontsize=8.5, fontproperties=font_prop_bold,
            bbox=dict(boxstyle="round,pad=0.25", facecolor=bg_col, edgecolor=border_col, alpha=0.95),
            zorder=7
        )

    # Current data point: Red dot + compact 1-line badge
    ax1.scatter([last_date], [cur_pe], color="#dc2626", s=80, zorder=6, edgecolors="#ffffff", linewidth=1.6)
    latest_lbl = f" 最新: {cur_pe:.1f}倍 " if is_zh else f" Current: {cur_pe:.1f}x "
    ax1.annotate(
        latest_lbl,
        xy=(last_date, cur_pe),
        xytext=(12, 0),
        textcoords="offset points",
        ha="left", va="center",
        fontsize=9.0,
        fontproperties=font_prop_bold,
        color="#dc2626",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff", edgecolor="#dc2626", linewidth=1.3, alpha=0.96),
        arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.0", color="#dc2626", lw=1.2),
        zorder=8
    )

    # Executive Valuation Card in the upper right headroom (Guaranteed NO COLLISION!)
    status_txt = (
        ("周期底部被动扩张" if cur_pct >= 80 else ("估值高位" if cur_pct >= 75 else ("合理区间" if cur_pct >= 25 else "深度低估")))
        if is_zh else
        ("Cyclical Trough Expansion" if cur_pct >= 80 else ("Elevated" if cur_pct >= 75 else ("Fair Value" if cur_pct >= 25 else "Deep Value")))
    )
    summary_card = (
        f"  最新估值核定\n"
        f"  • 当前 PE TTM: {cur_pe:.1f}倍，历史分位 {cur_pct:.1f}%\n"
        f"  • 估值中枢: {p50:.1f}倍   安全边际: {p10:.1f}倍 - {p25:.1f}倍\n"
        f"  • 研判状态: {status_txt}，防范盈利下行估值陷阱  "
        if is_zh else
        f"  [Valuation Assessment]\n"
        f"  • Current PE (TTM): {cur_pe:.1f}x   (Hist Percentile: {cur_pct:.1f}%)\n"
        f"  • Median Anchor: {p50:.1f}x   Margin of Safety: {p10:.1f}x - {p25:.1f}x\n"
        f"  • Assessment: {status_txt} (Beware Earnings Trough Traps)  "
    )
    ax1.text(
        0.985, 0.95, summary_card,
        transform=ax1.transAxes, fontsize=9.2, fontproperties=font_prop,
        color="#0f172a", ha="right", va="top",
        linespacing=1.35,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffffff", edgecolor="#94a3b8", linewidth=1.2, alpha=0.96),
        zorder=9
    )

    title_txt = (
        f"{company_name} {ticker_sym} · PE TTM 历史估值走势与分位数带宽"
        if is_zh else
        f"{company_name} ({ticker_sym}) 10-Year Historical PE (TTM) & Valuation Percentile Bands"
    )
    ax1.set_title(title_txt, fontsize=15, fontproperties=font_prop_bold, pad=12, color="#0f172a")
    ax1.set_ylabel("市盈率 PE TTM" if is_zh else "Trailing P/E Ratio", fontsize=11, fontproperties=font_prop_bold, color="#1e293b")
    leg1 = ax1.legend(loc="upper left", frameon=True, facecolor="#ffffff", framealpha=0.95, edgecolor="#cbd5e1", fontsize=9, ncol=2)
    if font_prop:
        for text in leg1.get_texts():
            text.set_fontproperties(font_prop)

    # Panel 2: Rolling Percentile
    ax2.set_ylim(-10, 122)
    pct_label = f"历史分位数走势 · 当前 {cur_pct:.1f}%" if is_zh else f"Rolling Percentile (Current: {cur_pct:.1f}%)"
    ax2.plot(dates, rolling_pct, color="#7c3aed", linewidth=1.8, label=pct_label, zorder=4)
    ax2.axhline(80, color="#ef4444", linestyle="--", linewidth=1.1, alpha=0.8, zorder=3)
    ax2.axhline(50, color="#64748b", linestyle=":", linewidth=1.1, alpha=0.7, zorder=3)
    ax2.axhline(20, color="#10b981", linestyle="--", linewidth=1.1, alpha=0.8, zorder=3)

    sh_ob = ">80% 估值高位压力区" if is_zh else ">80% Overvaluation Hazard"
    sh_os = "<20% 极致低估机会区" if is_zh else "<20% Deep Value Corridor"
    ax2.fill_between(dates, 80, 100, color="#fee2e2", alpha=0.35, label=sh_ob)
    ax2.fill_between(dates, 0, 20, color="#d1fae5", alpha=0.45, label=sh_os)

    # Right-aligned level badges for Panel 2
    p2_levels = [
        (80, "#ef4444", "#fee2e2", "#fca5a5", " 80% 警戒线 " if is_zh else " 80% Alert "),
        (50, "#64748b", "#f1f5f9", "#cbd5e1", " 50% 中位基准 " if is_zh else " 50% Median "),
        (20, "#10b981", "#dcfce7", "#86efac", " 20% 机会线 " if is_zh else " 20% Opp. "),
    ]
    for lvl, text_col, bg_col, border_col, l_str in p2_levels:
        ax2.text(
            badge_date, lvl, l_str,
            color=text_col, ha="right", va="center",
            fontsize=8.5, fontproperties=font_prop_bold,
            bbox=dict(boxstyle="round,pad=0.25", facecolor=bg_col, edgecolor=border_col, alpha=0.95),
            zorder=7
        )

    ax2.scatter([last_date], [cur_pct], color="#7c3aed", s=70, zorder=6, edgecolors="#ffffff", linewidth=1.5)

    # Compact 1-line annotation for current percentile
    ax2.annotate(
        f" 当前: {cur_pct:.1f}% " if is_zh else f" Current: {cur_pct:.1f}% ",
        xy=(last_date, cur_pct),
        xytext=(12, 0),
        textcoords="offset points",
        ha="left", va="center",
        fontsize=9.0,
        fontproperties=font_prop_bold,
        color="#6d28d9",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff", edgecolor="#7c3aed", linewidth=1.2, alpha=0.96),
        arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.0", color="#7c3aed", lw=1.2),
        zorder=8
    )

    badge_v2 = "历史百分位振荡带 (%)" if is_zh else "[V2] Valuation Percentile Oscillator (%)"
    ax2.text(
        0.985, 0.90, badge_v2,
        transform=ax2.transAxes, fontsize=9.5, fontproperties=font_prop_bold,
        color="#7c3aed", ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.95),
        zorder=7
    )

    ax2.set_ylabel("分位数 (%)" if is_zh else "Percentile (%)", fontsize=11, fontproperties=font_prop_bold, color="#1e293b")
    leg2 = ax2.legend(loc="upper left", frameon=True, facecolor="#ffffff", framealpha=0.95, edgecolor="#cbd5e1", fontsize=8.8, ncol=3)
    if font_prop:
        for text in leg2.get_texts():
            text.set_fontproperties(font_prop)

    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_minor_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate(rotation=0, ha="center")

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()
    return True


def calculate_trade_setup(technicals: dict, confluence: dict, asset_type: str = "EQUITY", currency: str = "USD", lang: str = "en") -> dict:
    """Calculate institutional tactical trade plan: bias, entry zone, stop loss, targets, and risk:reward."""
    is_zh = (lang == "zh")
    curr_sym = "¥" if currency in ["CNY", "CNH"] else ("HK$" if currency == "HKD" else "$")

    close = technicals["close"]
    atr = technicals.get("atr_14") or (close * 0.02)
    supp = technicals["nearest_support"]
    res = technicals["nearest_resistance"]
    high_52 = technicals["52_week_high"]
    sma_50 = technicals.get("sma_50")

    tech_score_val = int(confluence["technical_score"].split("/")[0])

    if tech_score_val >= 4:
        bias = "积极做多 / 逢回调布局" if is_zh else "Bullish / Buy on Pullbacks"
        bias_type = "bullish"
        entry_low = max(supp, round(close - atr * 0.8, 2))
        entry_high = round(close, 2)
        if entry_low >= entry_high:
            entry_low = round(close - atr * 0.5, 2)
        stop_loss = round(min(entry_low - atr * 1.2, supp * 0.97), 2)
        target_1 = round(max(res, close + atr * 1.5), 2)
        target_2 = round(max(high_52 * 1.05, target_1 + atr * 2.0), 2)
    elif tech_score_val >= 2:
        bias = "区间震荡 / 逢低蓄势" if is_zh else "Range-Bound / Neutral Accumulation"
        bias_type = "neutral"
        entry_low = round(supp, 2)
        entry_high = round(supp + atr * 0.7, 2)
        if close < entry_high:
            entry_high = round(close, 2)
        stop_loss = round(supp - atr * 1.0, 2)
        target_1 = round(res, 2)
        target_2 = round(max(res + atr * 1.5, high_52), 2)
    else:
        bias = "防御观望 / 破位规避" if is_zh else "Defensive / Wait for Base Formation"
        bias_type = "bearish"
        entry_low = round(supp, 2)
        entry_high = round(supp + atr * 0.5, 2)
        stop_loss = round(supp - atr * 1.0, 2)
        target_1 = round(sma_50 if sma_50 and sma_50 < res else res, 2)
        target_2 = round(res, 2)

    entry_mid = (entry_low + entry_high) / 2.0
    risk = max(entry_mid - stop_loss, 0.01)
    reward = max(target_1 - entry_mid, 0.01)
    rr_ratio = round(reward / risk, 2)

    return {
        "bias": bias,
        "bias_type": bias_type,
        "entry_zone": f"{curr_sym}{entry_low:.2f} - {curr_sym}{entry_high:.2f}",
        "entry_mid": entry_mid,
        "stop_loss": f"{curr_sym}{stop_loss:.2f}",
        "target_1": f"{curr_sym}{target_1:.2f}",
        "target_2": f"{curr_sym}{target_2:.2f}",
        "rr_ratio": f"1 : {rr_ratio:.2f}",
        "time_horizon": "2 - 8 周 · 波段/中线" if is_zh else "2 - 8 Weeks (Swing / Position)",
    }


def calculate_pe_percentile(ticker_sym: str, info: dict, df_history: pd.DataFrame = None) -> dict:
    """
    Compute 3-year and 5-year historical PE(TTM) percentile, min, max, median,
    and institutional valuation band classification.
    Supports A-Shares via EastMoney (akshare) and global equities via implied price-earnings series.
    """
    res = {
        "pe_ttm": None,
        "pe_3y_percentile": None,
        "pe_3y_min": None,
        "pe_3y_max": None,
        "pe_3y_median": None,
        "pe_5y_percentile": None,
        "pe_5y_min": None,
        "pe_5y_max": None,
        "pe_5y_median": None,
        "pe_10y_percentile": None,
        "pe_10y_min": None,
        "pe_10y_max": None,
        "pe_10y_median": None,
        "valuation_zone_zh": None,
        "valuation_zone_en": None,
        "sample_count_3y": 0,
        "sample_count_5y": 0,
        "sample_count_10y": 0,
        "data_source": None,
    }

    clean_sym = ticker_sym.upper().replace(".SS", "").replace(".SZ", "").replace(".BJ", "").strip()

    # 1. Primary path for A-Shares: Direct EastMoney daily valuation history
    if clean_sym.isdigit() and len(clean_sym) == 6:
        try:
            import akshare as ak
            val_df = ak.stock_value_em(symbol=clean_sym)
            if val_df is not None and not val_df.empty:
                date_cols = [c for c in val_df.columns if "日期" in c]
                pe_cols = [c for c in val_df.columns if "PE(TTM)" in c]
                if date_cols and pe_cols:
                    date_col = date_cols[0]
                    pe_col = pe_cols[0]
                    val_df[date_col] = pd.to_datetime(val_df[date_col])
                    val_df = val_df.sort_values(date_col)
                    max_date = val_df[date_col].max()

                    for years, prefix in [(3, "3y"), (5, "5y"), (10, "10y")]:
                        cutoff = max_date - pd.DateOffset(years=years)
                        sub = val_df[val_df[date_col] >= cutoff]
                        s = sub[pe_col].dropna()
                        s = s[s > 0]
                        if not s.empty:
                            cur = float(s.iloc[-1])
                            res["pe_ttm"] = round(cur, 2)
                            pct = round(float((s < cur).mean() * 100), 1)
                            res[f"pe_{prefix}_percentile"] = pct
                            res[f"pe_{prefix}_min"] = round(float(s.min()), 2)
                            res[f"pe_{prefix}_max"] = round(float(s.max()), 2)
                            res[f"pe_{prefix}_median"] = round(float(s.median()), 2)
                            res[f"sample_count_{prefix}"] = len(s)

                    res["data_source"] = "EastMoney (东方财富)"
        except Exception:
            pass

    # 2. Secondary fallback path (for global/US/HK stocks or if akshare unavailable):
    if res["pe_3y_percentile"] is None:
        g_dates, g_pe, g_src = build_global_pe_ttm_series(ticker_sym, info=info, df_history=df_history)
        if g_dates is not None and g_pe is not None and not g_pe.empty:
            max_date = g_dates.max()
            cur = float(g_pe.iloc[-1])
            res["pe_ttm"] = round(cur, 2)
            for years, prefix in [(3, "3y"), (5, "5y"), (10, "10y")]:
                cutoff = max_date - pd.DateOffset(years=years)
                s = g_pe[g_dates >= cutoff].dropna()
                s = s[s > 0]
                if not s.empty:
                    pct = round(float((s < cur).mean() * 100), 1)
                    res[f"pe_{prefix}_percentile"] = pct
                    res[f"pe_{prefix}_min"] = round(float(s.min()), 2)
                    res[f"pe_{prefix}_max"] = round(float(s.max()), 2)
                    res[f"pe_{prefix}_median"] = round(float(s.median()), 2)
                    res[f"sample_count_{prefix}"] = len(s)
            res["data_source"] = g_src

    # Determine valuation zone (clean without redundant percentage)
    pct = res["pe_10y_percentile"] if res.get("pe_10y_percentile") is not None else res.get("pe_3y_percentile")
    if pct is not None:
        if pct < 15:
            res["valuation_zone_zh"] = "极度低估区"
            res["valuation_zone_en"] = "Deep Value"
        elif pct < 35:
            res["valuation_zone_zh"] = "价值配置区"
            res["valuation_zone_en"] = "Undervalued / Accumulation"
        elif pct < 65:
            res["valuation_zone_zh"] = "合理中枢区"
            res["valuation_zone_en"] = "Fair Value"
        elif pct < 85:
            res["valuation_zone_zh"] = "估值偏高区"
            res["valuation_zone_en"] = "Elevated Valuation"
        else:
            res["valuation_zone_zh"] = "极度高估区"
            res["valuation_zone_en"] = "Extremely Overvalued"

    return res


def evaluate_confluence(technicals: dict, fundamentals: dict, asset_type: str = "EQUITY", lang: str = "en") -> dict:
    """Evaluate overall technical trend, fundamental health, and confluence verdict."""
    is_zh = (lang == "zh")
    tech_score = 0
    fund_score = 0

    # Technical Scoring
    close = technicals["close"]
    sma_50 = technicals.get("sma_50")
    sma_200 = technicals.get("sma_200")
    rsi = technicals.get("rsi_14")
    macd_hist = technicals.get("macd_hist")

    if sma_50 and close > sma_50:
        tech_score += 1
    if sma_200 and close > sma_200:
        tech_score += 1
    if sma_50 and sma_200 and sma_50 > sma_200:
        tech_score += 1  # Golden cross territory
    if rsi and 45 <= rsi <= 70:
        tech_score += 1  # Healthy bullish momentum
    if macd_hist and macd_hist > 0:
        tech_score += 1

    if is_zh:
        if tech_score >= 4:
            tech_verdict = "多头强势上行"
        elif tech_score >= 2:
            tech_verdict = "中性震荡整理"
        else:
            tech_verdict = "弱势空头下行"
    else:
        if tech_score >= 4:
            tech_verdict = "Bullish Uptrend"
        elif tech_score >= 2:
            tech_verdict = "Neutral / Consolidation"
        else:
            tech_verdict = "Bearish Downtrend"

    is_commodity_or_currency = asset_type in ["COMMODITY", "CURRENCY", "FUTURE", "CRYPTOCURRENCY"]

    if is_commodity_or_currency:
        fund_score_str = "宏观/不适用" if is_zh else "Macro/N/A"
        fund_verdict = (
            "宏观驱动: 实际利率、美元指数、央行储备"
            if is_zh else
            "Macro Driven (Real Yields, DXY, Central Bank Accumulation)"
        )
        if tech_score >= 4:
            confluence_verdict = "多头宏观共振 · 趋势向上" if is_zh else "Strong Bullish Macro & Technical Momentum (Uptrend Structure)"
        elif tech_score >= 2:
            confluence_verdict = "宏观震荡期 / 区间蓄势整理" if is_zh else "Macro Consolidation / Range-Bound Accumulation"
        else:
            confluence_verdict = "空头下行压力 · 逆风偏弱" if is_zh else "Bearish Trend Pressure (Dollar/Yield Headwinds)"
    else:
        roe = fundamentals.get("return_on_equity")
        debt_to_equity = fundamentals.get("debt_to_equity")
        op_margin = fundamentals.get("operating_margins")
        peg = fundamentals.get("peg_ratio")
        rev_growth = fundamentals.get("revenue_growth")
        total_debt = fundamentals.get("total_debt")
        pe_pct = fundamentals.get("pe_10y_percentile") if fundamentals.get("pe_10y_percentile") is not None else fundamentals.get("pe_3y_percentile")

        if roe and roe > 0.15:
            fund_score += 1
        if op_margin and op_margin > 0.15:
            fund_score += 1
        if rev_growth and rev_growth > 0.08:
            fund_score += 1
        if (debt_to_equity and debt_to_equity < 150) or total_debt == 0:
            fund_score += 1
        if (peg and 0 < peg < 2.0) or (pe_pct is not None and pe_pct < 40):
            fund_score += 1

        fund_score_str = f"{fund_score}/5"

        if is_zh:
            if fund_score >= 4:
                fund_verdict = "优质高成长 · 护城河宽阔"
            elif fund_score >= 2:
                fund_verdict = "基本面稳健"
            else:
                fund_verdict = "基本面偏弱 · 周期承压"

            if tech_score >= 4 and fund_score >= 4:
                confluence_verdict = "A类：高确定性复利标的 · 多头共振"
            elif tech_score >= 4 and fund_score < 2:
                confluence_verdict = "B类：短期投机/情绪波段"
            elif tech_score < 2 and fund_score >= 4:
                confluence_verdict = "C类：左侧价值观察区 · 底部蓄势"
            else:
                confluence_verdict = "D类：高风险双杀 · 建议规避"
        else:
            if fund_score >= 4:
                fund_verdict = "Strong (High Quality & Growth)"
            elif fund_score >= 2:
                fund_verdict = "Moderate (Solid Core, Some Headwinds)"
            else:
                fund_verdict = "Weak (Margin/Debt/Growth Pressure)"

            if tech_score >= 4 and fund_score >= 4:
                confluence_verdict = "Category A: High-Probability Compounder (Aligned Growth & Uptrend)"
            elif tech_score >= 4 and fund_score < 2:
                confluence_verdict = "Category B: Speculative Rally (Technical Momentum without Fundamental Support)"
            elif tech_score < 2 and fund_score >= 4:
                confluence_verdict = "Category C: Value Accumulation Watch (High Quality in Pullback / Base-Building)"
            else:
                confluence_verdict = "Category D: High Risk / Weak Fundamentals & Trend"

    return {
        "technical_score": f"{tech_score}/5",
        "technical_verdict": tech_verdict,
        "fundamental_score": fund_score_str,
        "fundamental_verdict": fund_verdict,
        "confluence_verdict": confluence_verdict,
    }


def build_fundamental_analysis_sections(meta: dict, fund: dict, is_zh: bool = True, curr_sym: str = "¥") -> dict:
    """Construct structured 3-part fundamental analysis:
    1. Industry Landscape, Competitive Positioning & Moat Analysis
    2. Multi-Year Business Performance Trend & Profitability Trajectory
    3. Valuation Multiples & Institutional Consensus Pricing
    """
    company_name = meta.get("company_name", "")
    ticker = meta.get("ticker", "")
    sector = meta.get("sector", "")
    industry = meta.get("industry", "")
    business_summary = meta.get("business_summary", "")
    is_commodity_or_currency = meta.get("asset_type") in ["COMMODITY", "CURRENCY", "FUTURE", "CRYPTOCURRENCY"]

    if is_commodity_or_currency:
        if is_zh:
            ind_analysis = (
                f"作为全球核心宏观资产，{company_name} 的大宗/货币属性受全球流动性格局与主权储备配置双重主导。"
            )
            perf_analysis = (
                "宏观基本面四重驱动支柱：\n"
                "1. 美债实际收益率 10Y TIPS：处于实际利率变动敏感期，实际利率中枢下行将显著提振无息资产溢价。\n"
                "2. 美元指数 DXY：以美元计价的大宗商品具有天然反向汇率挂钩属性，美元走弱提供强劲上行驱动。\n"
                "3. 全球央行战略购金与去美元化：以新兴市场央行为代表的物理储备积累构成坚不可摧的长期需求底线。\n"
                "4. 地缘政治溢价与主权信用风险：全球赤字扩张与地缘裂痕支撑结构性避险溢价。"
            )
            val_analysis = "宏观资产定价以内在信用对冲与长周期资产再平衡为锚，需重点跟踪美联储降息路径与流动性宽松节奏。"
            narrative_html = f"""
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">▌ 宏观资产定位与长周期驱动：</strong><br/>
            {ind_analysis}
        </div>
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">▌ 核心宏观因子驱动体系：</strong><br/>
            {perf_analysis.replace(chr(10), '<br/>')}
        </div>
        <div>
            <strong class="fund-section-title">▌ 估值锚定与流动性预期：</strong><br/>
            {val_analysis}
        </div>
"""
            narrative_md = f"""**▌ 宏观资产定位与长周期驱动**：
{ind_analysis}

**▌ 核心宏观因子驱动体系**：
{perf_analysis}

**▌ 估值锚定与流动性预期**：
{val_analysis}"""
        else:
            ind_analysis = f"As a prime global macro asset, {company_name} ({ticker}) is governed by global monetary policy and sovereign central bank asset allocation."
            perf_analysis = (
                "Core Macro Pillars:\n"
                "1. US 10-Year TIPS Real Yields: Declining real rates diminish opportunity cost and drive substantial capital inflows.\n"
                "2. US Dollar Index (DXY): The reciprocal relationship provides upward momentum during dollar consolidation or depreciation.\n"
                "3. Sovereign Central Bank Diversification: Structural de-dollarization establishes a resolute physical accumulation floor.\n"
                "4. Geopolitical & Debt Risk Premiums: Sovereign fiscal expansion and global fragmentation sustain elevated safe-haven bids."
            )
            val_analysis = "Valuation is anchored by sovereign credit risk hedge dynamics and macroeconomic liquidity easing cycles."
            narrative_html = f"""
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">[Macro Asset Profile & Secular Anchors]</strong><br/>
            {ind_analysis}
        </div>
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">[Core Macro Drivers & Transmission Channels]</strong><br/>
            {perf_analysis.replace(chr(10), '<br/>')}
        </div>
        <div>
            <strong class="fund-section-title">[Valuation & Sovereign Liquidity Horizon]</strong><br/>
            {val_analysis}
        </div>
"""
            narrative_md = f"""**[Macro Asset Profile & Secular Anchors]**
{ind_analysis}

**[Core Macro Drivers & Transmission Channels]**
{perf_analysis}

**[Valuation & Sovereign Liquidity Horizon]**
{val_analysis}"""
        return {
            "industry_analysis": ind_analysis,
            "performance_trend": perf_analysis,
            "valuation_conclusion": val_analysis,
            "narrative_md": narrative_md,
            "narrative_html": narrative_html,
        }

    hist_perf = fund.get("historical_performance", [])

    if is_zh:
        # 1. Industry Landscape & Moat Analysis
        ind_disp = f"{sector}" if sector else "相关细分领域"
        if industry and industry not in (sector or "") and not any(ch.isalpha() and ord(ch) < 128 for ch in industry):
            ind_disp += f" / {industry}"

        moat_keywords = []
        if "单项冠军" in business_summary:
            moat_keywords.append("工信部制造业单项冠军")
        if "特种" in business_summary or "高纯" in business_summary:
            moat_keywords.append("特种高技术壁垒")
        if "发动机" in business_summary or "燃气轮机" in business_summary or "航空" in business_summary:
            moat_keywords.append("国家重型战略动力装备核心总装资质与技术壁垒")
        if "内饰" in business_summary or "汽车" in business_summary or "座舱" in business_summary:
            moat_keywords.append("主流整车厂一级配套资质与客户高黏性")
        if "研发" in business_summary or "高新技术" in business_summary or "专利" in business_summary:
            moat_keywords.append("自主知识产权与技术创新壁垒")
        if "有机硅" in business_summary:
            moat_keywords.append("有机硅精细化工全产业链配套")

        moat_tag = f"，具备{'、'.join(moat_keywords[:2])}" if moat_keywords else ""

        if any(k in ind_disp for k in ["材料", "化工", "有机硅", "资源"]):
            cycle_txt = "当前所处行业受过去数年全行业产能集中释放及原料成本波动影响，处于供需深度调整与价格磨底阶段；未来中长期增长动能主要依托高附加值、电子级与新兴领域的进口替代与品类拓展。"
        elif any(k in ind_disp for k in ["航空", "军工", "装备", "机械", "国防"]):
            cycle_txt = "当前所处行业具备极高的国家战略准入资质与行业专营壁垒，受国防装备列装升级及自主可控推进驱动，中长期具备强确定性的长周期景气支撑。"
        elif any(k in ind_disp for k in ["汽车", "消费", "电子", "元器件", "零部件"]):
            cycle_txt = "当前所处行业紧跟新能源车渗透率持续提升与智能座舱升级浪潮，竞争格局呈现头部集中趋势，具备模块化配套与跨界新业务布局的企业抗周期能力突出。"
        else:
            cycle_txt = "行业竞争格局日趋集中，环保与技术合规壁垒持续提高，头部企业凭借技术与规模优势马太效应显著。"

        ind_analysis = f"{company_name}深耕 {ind_disp} 核心赛道{moat_tag}。{cycle_txt}"

        # 2. Performance Trend Analysis
        if len(hist_perf) >= 2:
            p_latest = hist_perf[-1]
            p_prev = hist_perf[-2]
            p_base = hist_perf[0] if len(hist_perf) >= 3 else None

            unit_nm, div_nm = get_unit_and_divisor(meta.get("currency", "USD"), is_zh=True)

            r_lat = p_latest.get('revenue', 0) / div_nm
            r_pre = p_prev.get('revenue', 0) / div_nm
            ni_lat = p_latest.get('net_income', 0) / div_nm
            ni_pre = p_prev.get('net_income', 0) / div_nm
            r_yoy = p_latest.get('revenue_yoy')
            ni_yoy = p_latest.get('net_income_yoy')
            gm_lat = p_latest.get('gross_margin')
            gm_pre = p_prev.get('gross_margin')
            nm_lat = p_latest.get('net_margin')
            roe_lat = p_latest.get('roe')
            ocf_lat = p_latest.get('ocf', 0) / div_nm

            cagr_rev_str = ""
            if p_base and p_base.get('revenue') and p_base['revenue'] > 0 and p_latest.get('revenue') and p_latest['revenue'] > 0:
                cagr = ((p_latest['revenue'] / p_base['revenue']) ** (1 / (len(hist_perf) - 1)) - 1) * 100
                cagr_rev_str = f"，2年营收复合增速 {cagr:+.1f}%"

            if r_yoy is not None and r_yoy > 0 and ni_yoy is not None and ni_yoy > 0:
                trend_verdict = "营业收入与净利润保持双向稳健增长，规模效应持续显现。"
            elif r_yoy is not None and r_yoy > 0 and ni_yoy is not None and ni_yoy < 0:
                trend_verdict = "营业收入延续温和扩张，但受成本端或产品价格波动影响，利润端出现阶段性承压调整。"
            elif r_yoy is not None and r_yoy < 0 and ni_yoy is not None and ni_yoy < 0:
                trend_verdict = "受行业周期景气度下行与终端去库存影响，营收与归母净利润均呈现阶段性收缩调整。"
            else:
                trend_verdict = "营收与盈利结构进入阶段性分化与重构期。"

            if gm_lat is not None and gm_pre is not None:
                gm_diff = gm_lat - gm_pre
                if gm_diff >= 1.0:
                    gm_verdict = f"毛利率由 {p_prev['year']}年的 {gm_pre:.1f}% 回升至 {gm_lat:.1f}%，较上年改善 {gm_diff:+.1f}%，盈利能力显著修复"
                elif gm_diff <= -1.0:
                    gm_verdict = f"毛利率由 {p_prev['year']}年的 {gm_pre:.1f}% 压缩至 {gm_lat:.1f}%，较上年承压 {gm_diff:+.1f}%，利润空间有所承压"
                else:
                    gm_verdict = f"毛利率在 {gm_lat:.1f}% 区间保持基本平稳，较上年微调 {gm_diff:+.1f}%，展现出底部抗压韧性"
            else:
                gm_verdict = f"最新毛利率录得 {gm_lat:.1f}%" if gm_lat is not None else ""

            roe_str = f"；净资产收益率 ROE 为 {roe_lat:.1f}%" if roe_lat is not None else ""

            if ocf_lat > 0 and ocf_lat >= ni_lat:
                cf_verdict = f"经营现金流 OCF 达 {curr_sym}{ocf_lat:.2f}{unit_nm}，保持净流入且高于同期净利，利润含金量较高，供应链造血健康。"
            elif ocf_lat > 0:
                cf_verdict = f"经营现金流保持正向流入 {curr_sym}{ocf_lat:.2f}{unit_nm}，整体流动性具备抗周期韧性。"
            else:
                cf_verdict = f"经营现金流为 {curr_sym}{ocf_lat:.2f}{unit_nm}，受交付结算节点或重大项目备货占用，需持续跟踪账期回款节奏。"

            r_yoy_str = f"{r_yoy:+.1f}%" if r_yoy is not None else "N/A"
            ni_yoy_str = f"{ni_yoy:+.1f}%" if ni_yoy is not None else "N/A"

            perf_analysis = (
                f"近3年财务轨迹显示，公司 {p_latest['year']}年营收 {curr_sym}{r_lat:.2f}{unit_nm}，同比 {r_yoy_str}{cagr_rev_str}；"
                f"归母净利润 {curr_sym}{ni_lat:.2f}{unit_nm}，同比 {ni_yoy_str}。{trend_verdict}"
                f"{gm_verdict}{roe_str}。{cf_verdict}"
            )
        else:
            rev_g = fund.get('revenue_growth', 0) * 100
            roe_v = fund.get('return_on_equity', 0) * 100
            perf_analysis = f"最新财报显示，公司营业收入增速为 {rev_g:+.1f}%，ROE为 {roe_v:.1f}%，整体经营表现与所处行业景气周期保持同步。"

        # 3. Valuation & Consensus Conclusion
        pe_val = fund.get("trailing_pe")
        pe_pct_10y = fund.get("pe_10y_percentile") if fund.get("pe_10y_percentile") is not None else fund.get("pe_3y_percentile")
        pe_zone = fund.get("valuation_zone_zh", "合理中枢区")
        pe_pct_str = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else "N/A"
        pe_str = f"{pe_val:.1f}倍" if pe_val else "N/A"
        target_mean = fund.get("analyst_target_mean")
        target_str = f"{curr_sym}{format_analyst_target(target_mean)}" if target_mean else "N/A"
        rec_zh = format_recommendation_zh(fund.get("recommendation_key"))

        if pe_pct_10y is not None and pe_pct_10y > 75:
            pe_interp = "在行业周期底部呈现典型的被动高估值特征，随着未来供需重塑及业绩企稳，估值倍数具备被动消化契机；"
        elif pe_pct_10y is not None and pe_pct_10y < 25:
            pe_interp = "估值处于历史绝对低位区间，具备较高安全边际与修复弹性；"
        else:
            pe_interp = "当前估值与盈利增长中枢匹配度较好，下行安全边际充足；"

        val_analysis = (
            f"估值层面，当前 PE 报 {pe_str}，处于 10年历史分位 {pe_pct_str} · {pe_zone}。"
            f"{pe_interp}"
            f"卖方平均目标价为 {target_str}，机构评级为「{rec_zh}」，主流机构对其长期复利空间保持关注。"
        )

        narrative_html = f"""
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">▌ 行业格局与竞争壁垒剖析：</strong><br/>
            {ind_analysis}
        </div>
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">▌ 近3年业绩趋势与盈利研判：</strong><br/>
            {perf_analysis}
        </div>
        <div>
            <strong class="fund-section-title">▌ 估值定价与机构共识：</strong><br/>
            {val_analysis}
        </div>
"""
        narrative_md = f"""**▌ 行业格局与竞争壁垒剖析**：
{ind_analysis}

**▌ 近3年业绩趋势与盈利研判**：
{perf_analysis}

**▌ 估值定价与机构共识**：
{val_analysis}"""

    else:
        # English
        ind_disp_en = f"{sector}" if sector else "Core Sector"
        if industry and industry not in (sector or ""):
            ind_disp_en += f" / {industry}"

        moat_tags_en = []
        if "champion" in business_summary.lower() or "单项冠军" in business_summary:
            moat_tags_en.append("national manufacturing champion status")
        if "aerospace" in business_summary.lower() or "engine" in business_summary.lower() or "发动机" in business_summary:
            moat_tags_en.append("strategic defense assembly credentials & prime OEM moat")
        if "automotive" in business_summary.lower() or "interior" in business_summary.lower() or "内饰" in business_summary:
            moat_tags_en.append("Tier-1 automotive supplier qualification & customer stickiness")
        if "silicon" in business_summary.lower() or "有机硅" in business_summary:
            moat_tags_en.append("integrated functional silane market leadership")

        moat_tag_en = f" (characterized by {', '.join(moat_tags_en[:2])})" if moat_tags_en else ""

        if any(k in ind_disp_en.lower() for k in ["material", "chemical", "silicon"]):
            cycle_txt_en = "The industry is undergoing capacity consolidation and raw material cost absorption after previous expansion cycles; long-term growth is anchored by high-spec electronic-grade and import-substitution opportunities."
        elif any(k in ind_disp_en.lower() for k in ["aerospace", "defense", "machinery"]):
            cycle_txt_en = "Protected by high regulatory entry barriers and proprietary technology credentials, the sector benefits from secular defense modernization programs."
        elif any(k in ind_disp_en.lower() for k in ["auto", "consumer", "electronic"]):
            cycle_txt_en = "Supported by ongoing NEV penetration and smart cockpit upgrades, Tier-1 integrated suppliers demonstrate resilient pricing power across product cycles."
        else:
            cycle_txt_en = "Industry consolidation continues to reward established category leaders with superior scale and compliance capabilities."

        ind_analysis = f"{company_name} maintains a deep footprint within the [{ind_disp_en}] vertical{moat_tag_en}. {cycle_txt_en}"

        if len(hist_perf) >= 2:
            p_latest = hist_perf[-1]
            p_prev = hist_perf[-2]
            p_base = hist_perf[0] if len(hist_perf) >= 3 else None
            unit_nm_en = "B" if meta.get("currency") not in ["CNY", "CNH", "HKD"] else "亿"
            div_nm_en = 1e9 if meta.get("currency") not in ["CNY", "CNH", "HKD"] else 1e8

            r_lat = p_latest.get('revenue', 0) / div_nm_en
            ni_lat = p_latest.get('net_income', 0) / div_nm_en
            r_yoy = p_latest.get('revenue_yoy')
            ni_yoy = p_latest.get('net_income_yoy')
            gm_lat = p_latest.get('gross_margin')
            roe_lat = p_latest.get('roe')
            ocf_lat = p_latest.get('ocf', 0) / div_nm_en

            cagr_str_en = ""
            if p_base and p_base.get('revenue') and p_base['revenue'] > 0 and p_latest.get('revenue') and p_latest['revenue'] > 0:
                cagr = ((p_latest['revenue'] / p_base['revenue']) ** (1 / (len(hist_perf) - 1)) - 1) * 100
                cagr_str_en = f", 2Y Revenue CAGR of {cagr:+.1f}%"

            trend_txt_en = "both top-line revenue and net income demonstrated steady expansion." if (r_yoy and r_yoy > 0 and ni_yoy and ni_yoy > 0) else (
                "revenue maintained modest expansion while profitability experienced margin pressures." if (r_yoy and r_yoy > 0) else "cyclical destocking and pricing pressures led to phase-level contraction."
            )
            cf_txt_en = f"Operating cash flow ({curr_sym}{ocf_lat:.2f}{unit_nm_en}) remained healthy relative to net earnings." if ocf_lat > 0 else f"Operating cash flow reflected working capital cycles ({curr_sym}{ocf_lat:.2f}{unit_nm_en})."

            perf_analysis = (
                f"Multi-year financial trajectory shows {p_latest['year']} revenue of {curr_sym}{r_lat:.2f}{unit_nm_en} ({r_yoy:+.1f}% YoY{cagr_str_en}) "
                f"and net income of {curr_sym}{ni_lat:.2f}{unit_nm_en} ({ni_yoy:+.1f}% YoY); {trend_txt_en} "
                f"Gross margin stood at {gm_lat:.1f}% with ROE of {roe_lat:.1f}%. {cf_txt_en}"
            )
        else:
            perf_analysis = f"Latest filings record revenue growth of {fund.get('revenue_growth', 0)*100:+.1f}% and ROE of {fund.get('return_on_equity', 0)*100:.1f}%, moving in lockstep with sector fundamentals."

        pe_val = fund.get("trailing_pe")
        pe_pct_10y = fund.get("pe_10y_percentile") if fund.get("pe_10y_percentile") is not None else fund.get("pe_3y_percentile")
        pe_zone_en = fund.get("valuation_zone_en", "Fair Value")
        pe_pct_str_en = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else "N/A"
        pe_str_en = f"{pe_val:.1f}x" if pe_val else "N/A"
        target_mean = fund.get("analyst_target_mean")
        target_str_en = f"{curr_sym}{format_analyst_target(target_mean)}" if target_mean else "N/A"
        rec_en = fund.get("recommendation_key", "Hold/Neutral")

        val_analysis = (
            f"On valuation multiples, Trailing P/E sits at {pe_str_en} (10Y percentile: {pe_pct_str_en} · {pe_zone_en}). "
            f"Consensus analyst target price is {target_str_en} (rating: '{rec_en}'), signaling durable institutional sponsorship."
        )

        narrative_html = f"""
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">[Industry Landscape & Moat Analysis]: </strong><br/>
            {ind_analysis}
        </div>
        <div style="margin-bottom: 5px;">
            <strong class="fund-section-title">[Multi-Year Performance Trend & Profitability Trajectory]</strong><br/>
            {perf_analysis}
        </div>
        <div>
            <strong class="fund-section-title">[Valuation & Institutional Consensus]: </strong><br/>
            {val_analysis}
        </div>
"""
        narrative_md = f"""**[Industry Landscape & Moat Analysis]**
{ind_analysis}

**[Multi-Year Performance Trend & Profitability Trajectory]**
{perf_analysis}

**[Valuation & Institutional Consensus]**
{val_analysis}"""

    return {
        "industry_analysis": ind_analysis,
        "performance_trend": perf_analysis,
        "valuation_conclusion": val_analysis,
        "narrative_md": narrative_md,
        "narrative_html": narrative_html,
    }


def generate_analytical_narratives(meta: dict, tech: dict, fund: dict, conf: dict, trade: dict, lang: str = "en") -> dict:
    """Generate professional institutional investment research narratives."""
    is_zh = (lang == "zh")
    curr_sym = "¥" if meta["currency"] in ["CNY", "CNH"] else ("HK$" if meta["currency"] == "HKD" else "$")
    is_commodity_or_currency = meta.get("asset_type") in ["COMMODITY", "CURRENCY", "FUTURE", "CRYPTOCURRENCY"]

    close = tech["close"]
    drawdown_52w = tech.get("drawdown_from_52w_high", 0.0)
    rebound_52w = tech.get("rebound_from_52w_low", 0.0)
    supp = tech["nearest_support"]
    res = tech["nearest_resistance"]
    rsi = tech.get("rsi_14", 50.0)
    macd_hist = tech.get("macd_hist", 0.0)
    sma_20 = tech.get("sma_20")
    sma_50 = tech.get("sma_50")
    sma_200 = tech.get("sma_200")
    bias_color = "#16a34a" if trade.get("bias_type") == "bullish" else ("#dc2626" if trade.get("bias_type") == "bearish" else "#d97706")

    if is_zh:
        # 1. Executive Thesis: Simple & Easy to Read (One-Line Bottom Line + 3 Structured Takeaways)
        pe_val = fund.get("trailing_pe")
        pe_pct_10y = fund.get("pe_10y_percentile") if fund.get("pe_10y_percentile") is not None else fund.get("pe_3y_percentile")
        pe_zone = fund.get("valuation_zone_zh", "合理中枢")
        pe_str = f"{pe_val:.1f}倍" if pe_val else "N/A"
        pe_pct_str = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else "N/A"
        roe_val = fund.get("return_on_equity")
        roe_str = f"{roe_val * 100:.1f}%" if roe_val else "N/A"
        div_yield_str = format_dividend_yield(fund.get("dividend_yield"))

        rsi_state_short = "极度超卖" if rsi < 30 else ("超买警戒" if rsi > 70 else "中性健康")
        ma_alignment_desc = "价格运行于SMA 20/50/200均线上方，呈现标准多头排列" if (sma_50 and close > sma_50 and sma_200 and close > sma_200) else (
            "价格跌破主要均线系统，长期均线呈下压态势" if (sma_200 and close < sma_200) else "价格处于中短期均线粘合区域，处于震荡博弈阶段"
        )
        ma_status_short = "处于均线多头顺势排列通道" if (sma_50 and close > sma_50 and sma_200 and close > sma_200) else (
            "均线系统呈空头压制下行态势" if (sma_200 and close < sma_200) else "处于均线震荡粘合博弈期"
        )

        exec_thesis_summary = (
            f"**{meta['company_name']}** 机构综合评级为「**{conf['confluence_verdict']}**」，"
            f"战术操作定性为 **{trade['bias']}**。最新现价 **{curr_sym}{close}**，{ma_status_short}。"
        )

        tech_takeaway = (
            f"现价距52周高点已回撤 **{abs(drawdown_52w):.1f}%**，14日 RSI 报 **{rsi:.1f}** · {rsi_state_short}，"
            f"短期杀跌动能趋缓，首要紧盯下方关键支撑 **{curr_sym}{supp:.2f}** 的企稳承接信号。"
        )

        if not is_commodity_or_currency:
            # Fundamental Analysis Takeaway
            hist_perf = fund.get("historical_performance", [])
            unit_nm, div_nm = get_unit_and_divisor(meta.get("currency", "USD"), is_zh=True)

            moat_keywords = []
            biz_sum = meta.get("business_summary", "")
            if "单项冠军" in biz_sum:
                moat_keywords.append("工信部制造业单项冠军")
            if "特种" in biz_sum or "高纯" in biz_sum:
                moat_keywords.append("特种高技术壁垒")
            if "发动机" in biz_sum or "燃气轮机" in biz_sum or "航空" in biz_sum:
                moat_keywords.append("国家战略重型动力总装资质壁垒")
            if "内饰" in biz_sum or "汽车" in biz_sum or "座舱" in biz_sum:
                moat_keywords.append("整车厂一级配套资质与高黏性壁垒")
            if "研发" in biz_sum or "高新技术" in biz_sum or "专利" in biz_sum:
                moat_keywords.append("自主核心技术与研发创新壁垒")
            if "有机硅" in biz_sum:
                moat_keywords.append("有机硅精细化工全产业链配套")

            moat_tag = f"，具备{'、'.join(moat_keywords[:2])}" if moat_keywords else ""

            sec_ind_disp = f"{meta.get('sector', '')}"
            if meta.get("industry") and meta["industry"] not in meta.get("sector", "") and not any(ch.isalpha() and ord(ch) < 128 for ch in meta["industry"]):
                sec_ind_disp += f" / {meta['industry']}"
            if not sec_ind_disp:
                sec_ind_disp = "核心主营领域"

            if len(hist_perf) >= 2:
                p_lat = hist_perf[-1]
                r_lat_v = p_lat.get('revenue', 0) / div_nm if p_lat.get('revenue') else None
                r_yoy_v = p_lat.get('revenue_yoy')
                ni_lat_v = p_lat.get('net_income', 0) / div_nm if p_lat.get('net_income') else None
                ni_yoy_v = p_lat.get('net_income_yoy')
                gm_v = p_lat.get('gross_margin')

                p_snips = []
                if r_lat_v is not None:
                    yoy_part = f"，同比 {r_yoy_v:+.1f}%" if r_yoy_v is not None else ""
                    p_snips.append(f"最新营收 {curr_sym}{r_lat_v:.2f}{unit_nm}{yoy_part}")
                if ni_lat_v is not None:
                    yoy_part = f"，同比 {ni_yoy_v:+.1f}%" if ni_yoy_v is not None else ""
                    p_snips.append(f"归母净利润 {curr_sym}{ni_lat_v:.2f}{unit_nm}{yoy_part}")
                if gm_v is not None:
                    p_snips.append(f"毛利率保持在 {gm_v:.1f}%")

                p_str = "；".join(p_snips) if p_snips else "主营业务经营保持韧性"
                fund_analysis_takeaway = f"{meta['company_name']}深耕 {sec_ind_disp} 核心赛道{moat_tag}。{p_str}，整体具备扎实的产业链壁垒与抗风险能力。"
            else:
                rev_g_v = fund.get('revenue_growth')
                rev_g_txt = f"，营收增速 {rev_g_v * 100:+.1f}%" if rev_g_v is not None else ""
                fund_analysis_takeaway = f"{meta['company_name']}深耕 {sec_ind_disp} 核心赛道{moat_tag}{rev_g_txt}，主营业务与产业链需求景气周期保持同步。"

            fund_takeaway = (
                f"PE 报 **{pe_str}**，10年历史分位 **{pe_pct_str}** · {pe_zone}；"
                f"ROE 报 **{roe_str}**，股息率达 **{div_yield_str}**，整体财务结构稳健，现金储备与分红提供扎实安全垫。"
            )
        else:
            fund_analysis_takeaway = (
                f"作为全球核心宏观资产，定价受美债实际利率、美元指数走势及主权央行去美元化储备需求共振支撑，中长期具备较强战略配置价值。"
            )
            fund_takeaway = (
                f"宏观定价受实际利率中枢与美元信用扩张周期约束，主权资产再平衡与避险溢价提供坚固安全底线。"
            )

        trade_takeaway = (
            f"维持 **{trade['bias']}** 策略纪律，建议逢低布局关注区间 **{trade['entry_zone']}**，"
            f"坚决设守止损线 **{trade['stop_loss']}**，第一上行目标看向 **{trade['target_1']}**，预期盈亏比 **{trade['rr_ratio']}**。"
        )

        exec_thesis_md = (
            f"📌 **一句话研判**：\n"
            f"> {exec_thesis_summary}\n\n"
            f"🔍 **四维核心逻辑拆解**：\n"
            f"- **走势与形态**：{tech_takeaway}\n"
            f"- **基本面分析**：{fund_analysis_takeaway}\n"
            f"- **估值与质地**：{fund_takeaway}\n"
            f"- **战术与风控**：{trade_takeaway}"
        )

        exec_thesis_html = f"""
        <div class="thesis-header">核心投研观点</div>
        <div class="thesis-summary">
            <strong>{meta['company_name']}</strong> 机构综合评级为「<strong>{conf['confluence_verdict']}</strong>」，战术操作定性为 <strong style="color: {bias_color};">{trade['bias']}</strong>。最新现价 <strong>{curr_sym}{close}</strong>，{ma_status_short}。
        </div>
        <div class="thesis-points-title">核心逻辑拆解：</div>
        <ul class="thesis-points">
            <li><strong>走势与形态：</strong> 现价距52周高点已回撤 <strong>{abs(drawdown_52w):.1f}%</strong>，14日 RSI 报 <strong>{rsi:.1f}</strong> · {rsi_state_short}，短期杀跌动能趋缓，首要紧盯下方关键支撑 <strong>{curr_sym}{supp:.2f}</strong> 的企稳承接信号。</li>
            <li><strong>基本面分析：</strong> {fund_analysis_takeaway}</li>
            <li><strong>估值与质地：</strong> {f"PE 报 <strong>{pe_str}</strong>，10年历史分位 <strong>{pe_pct_str}</strong> · {pe_zone}；ROE 报 <strong>{roe_str}</strong>，股息率达 <strong>{div_yield_str}</strong>，整体财务结构稳健，现金储备与分红提供扎实安全垫。" if not is_commodity_or_currency else "宏观定价受实际利率中枢与美元信用扩张周期约束，主权资产再平衡与避险溢价提供坚固安全底线。"}</li>
            <li><strong>战术与风控：</strong> 维持 <strong>{trade['bias']}</strong> 策略纪律，建议逢低布局关注区间 <strong>{trade['entry_zone']}</strong>，坚决设守止损线 <strong>{trade['stop_loss']}</strong>，第一上行目标看向 <strong>{trade['target_1']}</strong>，预期盈亏比 <strong>{trade['rr_ratio']}</strong>。</li>
        </ul>
        """
        exec_thesis = exec_thesis_md

        # 2. Technical Narrative
        rsi_state = "处于健康强势区间 45-70，做多动能充沛且尚未进入极度超买" if (45 <= rsi <= 70) else (
            "处于极度超卖区 30以下，短期下行动能衰竭，技术性反弹动能正在积聚" if rsi < 30 else (
                "进入超买警戒区 70以上，追高风险收益比降低，需警惕短期震荡获利了结" if rsi > 70 else "处于中性均衡区间 30-45"
            )
        )
        macd_state = "MACD动能柱红柱向上发散，买盘处于主导控制地位" if macd_hist > 0 else "MACD动能柱绿柱向下，表明短期空方仍有控盘压力"
        vol_state = "最新成交量明显放量，显示机构资金积极换手参与" if (tech.get("volume_sma_20") and tech["volume_latest"] > tech["volume_sma_20"]) else "最新成交量缩量整理，表明筹码结构较为稳定，洗盘蓄势特征明显"

        tech_narrative = (
            f"从市场微观结构剖析，{meta['company_name']} 呈现典型波段博弈特征。均线系统方面，{ma_alignment_desc}。"
            f"动能指标方面，14日RSI当前读数为 {rsi:.1f}，{rsi_state}；{macd_state}。"
            f"布林带当前上轨位于 {curr_sym}{tech.get('bollinger_upper', 'N/A')}，下轨位于 {curr_sym}{tech.get('bollinger_lower', 'N/A')}，"
            f"带宽反应波动率处于可控常态水平。成交量维度，{vol_state}。"
            f"当前价格上方首要结构性阻力位为 {curr_sym}{res}，下方多头防御安全垫关键支撑为 {curr_sym}{supp}。"
        )

        # 3. Fundamental Narrative (Structured Industry, Performance Trend & Valuation)
        fund_sections = build_fundamental_analysis_sections(meta, fund, is_zh=is_zh, curr_sym=curr_sym)
        fund_narrative = fund_sections["narrative_md"]

        # 4. Bull & Bear Scenarios
        bull_case = [
            f"**技术突破确立**：价格放量突破阻力位 {curr_sym}{res:.2f}，且维持在20日均线上方运行，打开向第一目标 {trade['target_1']} 及52周高点 {curr_sym}{tech['52_week_high']} 的上攻空间。",
            f"**基本面与盈利催化**：核心业务收入与利润率超预期释放，FCF现金流加速，机构估值模型向远期上修。",
            f"**宏观/流动性共振**：行业流动性改善，板块估值修复，多头共振推动估值与盈利双击。"
        ]
        bear_case = [
            f"**关键支撑失守破位**：价格有效跌破支撑位 {curr_sym}{supp:.2f}，触发止损底线 {trade['stop_loss']}，均线系统转向死叉空头压制。",
            f"**基本面增速放缓**：下游需求疲软或竞争加剧导致毛利率与ROE承压，卖方下调盈利预测导致估值去泡沫化。",
            f"**宏观系统性冲击**：流动性紧缩或利率维持高位，压制整体市场风险偏好，引发资金流出回调至52周低位 {curr_sym}{tech['52_week_low']}。"
        ]

        # 5. Key Catalysts
        key_catalysts = [
            f"跟踪关键结构阻力位 {curr_sym}{res:.2f} 突破情况及量能配合度；",
            f"关注防守止损线 {trade['stop_loss']} 及 50/200 日关键均线动态支撑；",
            f"密切留意下一次财报业绩披露或宏观利率决议动向；",
            f"监控行业政策周期变化与主流卖方研报评级调整。"
        ]

    else:
        # English Narrative
        # 1. Executive Thesis: Simple & Structured
        pe_val = fund.get("trailing_pe")
        pe_pct_10y = fund.get("pe_10y_percentile") if fund.get("pe_10y_percentile") is not None else fund.get("pe_3y_percentile")
        pe_zone_en = fund.get("valuation_zone_en", "Fair Value")
        pe_str = f"{pe_val:.1f}x" if pe_val else "N/A"
        pe_pct_str = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else "N/A"
        roe_val = fund.get("return_on_equity")
        roe_str = f"{roe_val * 100:.1f}%" if roe_val else "N/A"
        div_yield_str = format_dividend_yield(fund.get("dividend_yield"))

        rsi_state_short = "deeply oversold" if rsi < 30 else ("overbought" if rsi > 70 else "neutral range")
        ma_desc = "trading above all major moving averages (20, 50, 200 SMA), confirming an intact secular bullish momentum structure" if (sma_50 and close > sma_50 and sma_200 and close > sma_200) else (
            "trading below key institutional trendlines (200 SMA), indicating persistent overhead supply pressure" if (sma_200 and close < sma_200) else "consolidating around intermediate moving averages with neutral momentum"
        )
        ma_status_short = "in an intact secular bullish trend structure" if (sma_50 and close > sma_50 and sma_200 and close > sma_200) else (
            "under overhead moving average resistance" if (sma_200 and close < sma_200) else "consolidating around intermediate moving averages"
        )

        exec_thesis_summary = (
            f"**{meta['company_name']} ({meta['ticker']})** is categorized as '**{conf['confluence_verdict']}**' "
            f"with a tactical bias of [**{trade['bias']}**]. Current price is **{curr_sym}{close}**, {ma_status_short}."
        )

        tech_takeaway = (
            f"Price is down **{abs(drawdown_52w):.1f}%** from 52-week highs; 14-day RSI reads **{rsi:.1f}** ({rsi_state_short}), "
            f"signaling decelerating downside pressure. Critical tactical support rests at **{curr_sym}{supp:.2f}**."
        )

        if not is_commodity_or_currency:
            fund_takeaway = (
                f"P/E (TTM) stands at **{pe_str}**, 10Y percentile **{pe_pct_str}** · {pe_zone_en}; "
                f"ROE is **{roe_str}** and Dividend Yield is **{div_yield_str}**, offering balance sheet durability and dividend support."
            )
        else:
            fund_takeaway = (
                f"Valuation is anchored by real yields, DXY dynamics, and sovereign physical reserve accumulation."
            )

        trade_takeaway = (
            f"Maintain disciplined [**{trade['bias']}**] posture; accumulation zone identified at **{trade['entry_zone']}**, "
            f"hard stop loss floor at **{trade['stop_loss']}**, and primary price target at **{trade['target_1']}** (R:R **{trade['rr_ratio']}**)."
        )

        exec_thesis_md = (
            f"📌 **Executive Bottom Line**:\n"
            f"> {exec_thesis_summary}\n\n"
            f"🔍 **Key Thesis Pillars (3-Point Takeaway)**:\n"
            f"- **Trend & Momentum**: {tech_takeaway}\n"
            f"- **Valuation & Quality**: {fund_takeaway}\n"
            f"- **Tactics & Risk Management**: {trade_takeaway}"
        )

        exec_thesis_html = f"""
        <div class="thesis-header">[Executive Investment Thesis]</div>
        <div class="thesis-summary">
            <strong>{meta['company_name']} ({meta['ticker']})</strong> is categorized as '<strong>{conf['confluence_verdict']}</strong>' with a tactical bias of [<strong style="color: {bias_color};">{trade['bias']}</strong>]. Current price is <strong>{curr_sym}{close}</strong>, {ma_status_short}.
        </div>
        <div class="thesis-points-title">Key Thesis Pillars (3-Point Takeaway):</div>
        <ul class="thesis-points">
            <li><strong>Trend & Momentum:</strong> Price is down <strong>{abs(drawdown_52w):.1f}%</strong> from 52-week highs; 14-day RSI reads <strong>{rsi:.1f}</strong> ({rsi_state_short}), with primary tactical support at <strong>{curr_sym}{supp:.2f}</strong>.</li>
            <li><strong>Valuation & Quality:</strong> {f"P/E (TTM) stands at <strong>{pe_str}</strong>, 10Y percentile <strong>{pe_pct_str}</strong> · {pe_zone_en}; ROE is <strong>{roe_str}</strong> and Dividend Yield is <strong>{div_yield_str}</strong>." if not is_commodity_or_currency else "Valuation is anchored by TIPS real yields, DXY dynamics, and central bank reserves."}</li>
            <li><strong>Tactics & Risk Management:</strong> Maintain [<strong>{trade['bias']}</strong>] positioning; accumulation range at <strong>{trade['entry_zone']}</strong>, hard stop floor at <strong>{trade['stop_loss']}</strong>, primary target at <strong>{trade['target_1']}</strong> (R:R <strong>{trade['rr_ratio']}</strong>).</li>
        </ul>
        """
        exec_thesis = exec_thesis_md

        rsi_state = "in a healthy bullish momentum corridor (45-70) without immediate overbought exhaustion" if (45 <= rsi <= 70) else (
            "deeply oversold (<30), indicating heavy seller exhaustion and high probability of mean-reversion" if rsi < 30 else (
                "overbought (>70), cautioning against chasing momentum at current extended levels" if rsi > 70 else "in a balanced neutral zone (30-45)"
            )
        )
        macd_state = "MACD histogram shows expanding positive momentum bars, confirming buyers maintain control" if macd_hist > 0 else "MACD histogram sits in negative territory, highlighting short-term distribution"
        vol_state = "Recent volume outpaces the 20-day average, signaling active institutional turnover" if (tech.get("volume_sma_20") and tech["volume_latest"] > tech["volume_sma_20"]) else "Volume is contracting on pullbacks, indicative of healthy supply absorption"

        tech_narrative = (
            f"Examining price structure, {meta['ticker']} exhibits well-defined technical boundaries. "
            f"Moving average alignment indicates that the asset is {ma_desc}. "
            f"Oscillator readings show 14-day RSI at {rsi:.1f}, {rsi_state}. "
            f"{macd_state}. Bollinger Bands (20, 2 std) range from lower support at {curr_sym}{tech.get('bollinger_lower', 'N/A')} "
            f"to upper resistance at {curr_sym}{tech.get('bollinger_upper', 'N/A')}. "
            f"{vol_state}. Primary overhead resistance rests at {curr_sym}{res:.2f}, with vital tactical support situated at {curr_sym}{supp:.2f}."
        )

        # 3. Fundamental Narrative (Structured Industry, Performance Trend & Valuation)
        fund_sections = build_fundamental_analysis_sections(meta, fund, is_zh=is_zh, curr_sym=curr_sym)
        fund_narrative = fund_sections["narrative_md"]

        bull_case = [
            f"**Technical Breakout**: High-volume expansion breaking above resistance {curr_sym}{res:.2f}, driving acceleration towards Target 1 ({trade['target_1']}) and 52-week peak {curr_sym}{tech['52_week_high']}.",
            f"**Earnings & Margin Expansion**: Superior top-line growth and margin leverage triggering positive analyst estimate revisions.",
            f"**Macro Tailwinds**: Lower interest rate trajectory and liquidity injection expanding sector valuation multiples."
        ]
        bear_case = [
            f"**Support Breakdown**: Loss of critical structural support at {curr_sym}{supp:.2f}, activating hard invalidation stop at {trade['stop_loss']}.",
            f"**Margin Compression**: Rising input costs or heightened competition eroding operating margins and return on equity.",
            f"**Macro De-Risking**: Hawkish monetary stance or spike in yields catalyzing multiple de-rating towards 52-week low floor {curr_sym}{tech['52_week_low']}."
        ]

        key_catalysts = [
            f"Monitor volume confirmation on testing key structural resistance at {curr_sym}{res:.2f};",
            f"Watch preservation of hard stop invalidation floor at {trade['stop_loss']};",
            f"Upcoming quarterly earnings release or major central bank policy statement;",
            f"Revisions in analyst consensus targets and institutional 13F ownership changes."
        ]

    return {
        "executive_thesis": exec_thesis,
        "executive_thesis_html": exec_thesis_html,
        "executive_thesis_summary": exec_thesis_summary,
        "technical_narrative": tech_narrative,
        "fundamental_narrative": fund_sections["narrative_md"],
        "fundamental_narrative_html": fund_sections["narrative_html"],
        "fundamental_industry": fund_sections["industry_analysis"],
        "fundamental_perf_trend": fund_sections["performance_trend"],
        "fundamental_valuation": fund_sections["valuation_conclusion"],
        "bull_case": bull_case,
        "bear_case": bear_case,
        "key_catalysts": key_catalysts,
    }


def generate_markdown_report(data: dict, report_path: str, lang: str = "en"):
    meta = data["metadata"]
    tech = data["technicals"]
    fund = data["fundamentals"]
    conf = data["confluence"]
    trade = data["trade_setup"]
    narrative = data["narratives"]

    is_zh = (lang == "zh")
    curr_sym = "¥" if meta["currency"] in ["CNY", "CNH"] else ("HK$" if meta["currency"] == "HKD" else "$")
    chart_rel = os.path.basename(meta.get("chart_image", ""))
    is_commodity = meta.get("asset_type") in ["COMMODITY", "CURRENCY", "FUTURE", "CRYPTOCURRENCY"]

    unit_name, divisor = get_unit_and_divisor(meta["currency"], is_zh)
    na_str = "暂无" if is_zh else "N/A"

    pe_pct_3y = fund.get("pe_3y_percentile")
    pe_pct_5y = fund.get("pe_5y_percentile")
    pe_pct_10y = fund.get("pe_10y_percentile")
    pe_pct_3y_str = f"{pe_pct_3y:.1f}%" if pe_pct_3y is not None else "N/A"
    pe_pct_5y_str = f"{pe_pct_5y:.1f}%" if pe_pct_5y is not None else "N/A"
    pe_pct_10y_str = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else (pe_pct_3y_str if pe_pct_3y_str != "N/A" else "N/A")
    pe_zone_str = fund.get("valuation_zone_zh", "N/A") if is_zh else fund.get("valuation_zone_en", "N/A")
    pe_zone_en_str = fund.get("valuation_zone_en", "N/A")
    pe_3y_min_str = f"{fund.get('pe_3y_min', 'N/A')}"
    pe_3y_max_str = f"{fund.get('pe_3y_max', 'N/A')}"
    pe_3y_med_str = f"{fund.get('pe_3y_median', 'N/A')}"
    pe_10y_min_str = f"{fund.get('pe_10y_min', fund.get('pe_3y_min', 'N/A'))}"
    pe_10y_max_str = f"{fund.get('pe_10y_max', fund.get('pe_3y_max', 'N/A'))}"
    pe_10y_med_str = f"{fund.get('pe_10y_median', fund.get('pe_3y_median', 'N/A'))}"
    pe_val_str = f"{fund['trailing_pe']:.1f}倍" if is_zh and fund.get("trailing_pe") else (f"{fund['trailing_pe']:.1f}x" if fund.get("trailing_pe") else "N/A")

    roe_str = f"{fund['return_on_equity'] * 100:.1f}%" if fund.get("return_on_equity") else "N/A"
    op_m_str = f"{fund['operating_margins'] * 100:.1f}%" if fund.get("operating_margins") else "N/A"
    rev_g_str = f"{fund['revenue_growth'] * 100:.1f}%" if fund.get("revenue_growth") else "N/A"
    div_yield_str = format_dividend_yield(fund.get("dividend_yield"))
    business_summary = meta.get("business_summary") or ("暂无主营业务详细描述。" if is_zh else "No business profile available.")

    if is_zh:
        bull_bullets = "\n".join([f"- {b}" for b in narrative["bull_case"]])
        bear_bullets = "\n".join([f"- {b}" for b in narrative["bear_case"]])
        cat_bullets = "\n".join([f"- {c}" for c in narrative["key_catalysts"]])

        timeframe_disp = "日线级别" if "1d" in meta.get("interval", "1d") else ("周线级别" if "1wk" in meta.get("interval", "") else ("月线级别" if "1mo" in meta.get("interval", "") else meta.get("timeframe_name", "日线级别")))
        period_disp = format_period_zh(meta.get("period", "1y"))
        currency_disp = format_currency_zh(meta.get("currency", "CNY"))
        sector_industry_disp = meta.get("sector", "")
        if meta.get("industry") and meta["industry"] not in meta.get("sector", "") and not any(ch.isalpha() and ord(ch) < 128 for ch in meta["industry"]):
            sector_industry_disp = f"{meta['sector']} / {meta['industry']}"

        content = f"""# 深度投研报告: {meta['company_name']} {meta['ticker']}

*投研日期: {meta['analysis_date']} | 时间级别: {timeframe_disp} | 数据周期: {period_disp} | 板块/行业: {sector_industry_disp} | 结算货币: {currency_disp}*

---

## 0. 公司主营业务概况

> **🏢 主营业务与核心赛道**:
> {business_summary}

---

## 一、核心结论与投研观点

### 1. 核心指标速览
| 核心指标 | 当前数值 | 机构对标与安全边际 |
| :--- | :--- | :--- |
| **最新现价** | **{curr_sym}{tech['close']}** ({tech['change_pct']:+.2f}%) | 距52周最高点: {tech['drawdown_from_52w_high']:.1f}% \\| 距52周最低点: +{tech['rebound_from_52w_low']:.1f}% |
| **技术面研判** | **{conf['technical_verdict']}** ({conf['technical_score']}) | 均线、动能、量能全维量化评分 |
| **基本面研判** | **{conf['fundamental_verdict']}** ({conf['fundamental_score']}) | 盈利质量、护城河与负债健康度评估 |
| **机构共振评级** | **{conf['confluence_verdict']}** | 多维共振定位体系 |
| **市盈率与历史分位** | **{pe_val_str}** (10年分位: {pe_pct_10y_str}) | {pe_zone_str} |
| **资本回报与股东分红** | ROE: **{roe_str}** \\| 股息率: **{div_yield_str}** | 营业利润率: {op_m_str} \\| 营收增速: {rev_g_str} |
| **关键支撑 / 阻力** | 最近支撑位: **{curr_sym}{tech['nearest_support']}** | 最近阻力位: **{curr_sym}{tech['nearest_resistance']}** |
| **52周价格区间** | 最低: {curr_sym}{tech['52_week_low']} | 最高: {curr_sym}{tech['52_week_high']} |

### 2. 核心投资逻辑阐述

{narrative['executive_thesis']}

---

## 二、战术交易计划与执行矩阵

| 交易参数 | 建议执行区间 / 点位 | 战术解读与风控原则 |
| :--- | :--- | :--- |
| **战术操作倾向** | **{trade['bias']}** | 基于技术面与基本面多空共振的策略定性 |
| **建议逢低布局区间** | **{trade['entry_zone']}** | 关键支撑位上方或均线回调吸收密集区 |
| **防守止损线** | **{trade['stop_loss']}** | 结构失效点：有效跌破立即离场，严控下行风险 |
| **第一目标位** | **{trade['target_1']}** | 最近强阻力区：建议逢高锁定利润 |
| **第二目标位** | **{trade['target_2']}** | 趋势延伸目标位 / 52周新高突破目标 |
| **战术盈亏比** | **{trade['rr_ratio']}** | 基于第一目标位计算的风险回报比 |
| **持仓周期预期** | **{trade['time_horizon']}** | 适合中线波段与机构建仓周期 |

---

## 三、基本面估值、盈利质量与护城河

### 1. 行业格局、业绩趋势与护城河深度解析
{narrative['fundamental_narrative']}

### 2. 核心财务与估值矩阵
"""
        if not is_commodity:
            mkt_cap_str = f"{curr_sym}{fund['market_cap'] / divisor:.2f}{unit_name}" if fund.get("market_cap") else "暂无"
            ev_str = f"{curr_sym}{fund['enterprise_value'] / divisor:.2f}{unit_name}" if fund.get("enterprise_value") else "暂无"
            fcf_str = f"{curr_sym}{fund['free_cash_flow'] / divisor:.2f}{unit_name}" if fund.get("free_cash_flow") else "暂无"
            fcf_yield_str = f"{fund['fcf_yield']:.2f}%" if fund.get("fcf_yield") is not None else "暂无"
            rev_g_str = f"{fund['revenue_growth'] * 100:.1f}%" if fund.get("revenue_growth") else "暂无"
            roe_str = f"{fund['return_on_equity'] * 100:.1f}%" if fund.get("return_on_equity") else "暂无"
            op_m_str = f"{fund['operating_margins'] * 100:.1f}%" if fund.get("operating_margins") else "暂无"
            gm_str = f"{fund['gross_margins'] * 100:.1f}%" if fund.get("gross_margins") else "暂无"
            pe_str = f"{fund['trailing_pe']:.1f}倍" if fund.get("trailing_pe") else "暂无"
            f_pe_str = f"{fund['forward_pe']:.1f}倍" if fund.get("forward_pe") else "暂无"
            peg_str = f"{fund['peg_ratio']:.2f}" if fund.get("peg_ratio") else "暂无"
            ps_str = f"{fund['price_to_sales']:.2f}倍" if fund.get("price_to_sales") else "暂无"
            pb_str = f"{fund['price_to_book']:.2f}倍" if fund.get("price_to_book") else "暂无"
            ev_ebitda_str = f"{fund['ev_to_ebitda']:.2f}倍" if fund.get("ev_to_ebitda") else "暂无"
            div_yield_str = format_dividend_yield(fund.get("dividend_yield"))
            d2e_val = fund.get("debt_to_equity")
            if d2e_val is not None:
                d2e_str = f"{float(d2e_val):.1f}%"
            elif fund.get("total_debt") == 0:
                d2e_str = "0.0% · 零有息负债"
            else:
                d2e_str = "暂无"
            tgt_raw = fund.get("analyst_target_mean")
            rec_str_zh = format_recommendation_zh(fund.get("recommendation_key"))
            analyst_disp_zh = f"{curr_sym}{format_analyst_target(tgt_raw)} · {rec_str_zh}" if tgt_raw else f"暂无目标价 · {rec_str_zh}"

            content += f"""
| 财务与估值指标 | 实际数值 | 机构标准与健康度 |
| :--- | :--- | :--- |
| **总市值 / 企业价值** | {mkt_cap_str} / {ev_str} | 市场规模与企业整体收购价值 |
| **滚动市盈率 / 动态市盈率** | {pe_str} / {f_pe_str} | 评估盈利估值倍数与历史分位数 |
| **市盈率历史分位 (3年 / 5年 / 10年)** | {pe_pct_3y_str} / {pe_pct_5y_str} / **{pe_pct_10y_str}** | 10年区间: [{pe_10y_min_str} - {pe_10y_max_str}] 中位数: {pe_10y_med_str} · {pe_zone_str} |
| **市盈率相对盈利增长比率** | {peg_str} | < 1.0 低估, 1.0 - 2.0 合理, > 2.0 溢价 |
| **市销率 / 市净率** | {ps_str} / {pb_str} | 收入转化与净资产溢价衡量 |
| **企业价值倍数** | {ev_ebitda_str} | 跨资本结构估值倍数 |
| **毛利率 / 营业利润率** | {gm_str} / {op_m_str} | > 15% 代表具备较强定价权与议价能力 |
| **净资产收益率** | {roe_str} | > 15% 衡量资本复利效率的核心指标 |
| **自由现金流 / 自由现金流收益率** | {fcf_str} · 收益率: {fcf_yield_str} | 扣除资本开支后的真实现金流入 |
| **营业收入同比增速** | {rev_g_str} | 业务扩张与成长动能持续性 |
| **资产负债率** | {d2e_str} | 偿债能力与财务杠杆稳健度 |
| **股息率** | {div_yield_str} | 现金分红股东回报能力 |
| **卖方分析师共识与目标价** | {analyst_disp_zh} | 机构分析师平均目标均价与综合评级 |
"""
            # Past 2-Year Performance Comparison Table
            hist_perf = fund.get("historical_performance", [])
            perf_md, _ = format_historical_performance_table(hist_perf, currency=meta["currency"], is_zh=is_zh)
            if perf_md:
                content += f"""
### 3. 近3年核心经营业绩与财务对比

{perf_md}
"""

            pe_chart_rel = os.path.basename(meta.get("pe_chart_image", "")) if meta.get("pe_chart_image") else ""
            if pe_chart_rel:
                sub_idx = "4" if perf_md else "3"
                content += f"""
### {sub_idx}. PE (TTM) 历史估值走势与分位数带宽图 (近10年/上市至今)
![PE历史走势与分位数带宽图]({pe_chart_rel})
"""
        else:
            content += """
*资产类别：大宗商品 / 汇率。企业财务利润率与 PE 估值不适用。*
核心宏观驱动因子与定价逻辑：
- **美债实际收益率 (10Y TIPS)**：持有非生息黄金/资产的机会成本基准，实际利率下行构成核心上涨驱动。
- **美元指数 (DXY)**：以美元计价的大宗商品反向汇率定价逻辑。
- **央行战略储备与去美元化**：主权基金如中国央行、印度央行等构建实物储备托底。
- **地缘政治与主权债务风险**：避险情绪与财政赤字推升长期风险溢价。
"""

        content += f"""
---

## 四、多周期技术分析图表 · {timeframe_disp}
![技术形态全维分析图]({chart_rel})

---

## 五、技术面深度剖析与微观量价结构

### 1. 结构与动能分析
> **📊 盘口结构与量价研判**:
> {narrative['technical_narrative']}

### 2. 关键量化指标明细表
| 技术指标 | 计算数值 | 状态与市场信号解读 |
| :--- | :--- | :--- |
| **20日均线 · 月线** | {tech['sma_20'] if tech['sma_20'] is not None else '暂无'} | {'价格位于均线上方 · 短线偏多' if tech['sma_20'] and tech['close'] > tech['sma_20'] else '价格位于均线下方 · 承压'} |
| **50日均线 · 季线** | {tech['sma_50'] if tech['sma_50'] is not None else '暂无'} | {'突破中期均线防线 · 机构买盘支撑' if tech['sma_50'] and tech['close'] > tech['sma_50'] else '中期趋势偏弱'} |
| **200日均线 · 牛熊线** | {tech['sma_200'] if tech['sma_200'] is not None else '暂无'} | {'处于长线牛市宏观区间' if tech['sma_200'] and tech['close'] > tech['sma_200'] else '长线熊市空头承压'} |
| **9日 / 21日指数均线** | {tech['ema_9']} / {tech['ema_21']} | {'短线多头动能金叉排列' if tech['ema_9'] and tech['ema_21'] and tech['ema_9'] > tech['ema_21'] else '短线空头死叉向下'} |
| **14日相对强弱指标** | {tech['rsi_14']} | {'极度超卖 < 30 · 蓄势反弹' if tech['rsi_14'] and tech['rsi_14'] < 30 else ('超买警戒 > 70' if tech['rsi_14'] and tech['rsi_14'] > 70 else '中性健康区间 30-70')} |
| **指数平滑异同平均线 (差离/信号/柱值)** | {tech['macd']} / {tech['macd_signal']} / {tech['macd_hist']} | {'红柱做多动能充沛' if tech['macd_hist'] and tech['macd_hist'] > 0 else '绿柱空方动能主导'} |
| **布林通道 (20, 2σ)** | 下轨: {tech['bollinger_lower']} / 上轨: {tech['bollinger_upper']} | {'跌破下轨 · 极限超卖' if tech['bollinger_lower'] and tech['close'] < tech['bollinger_lower'] else ('突破上轨 · 强势拉升' if tech['bollinger_upper'] and tech['close'] > tech['bollinger_upper'] else '通道内正常震荡')} |
| **14日真实波幅** | {tech['atr_14']} | 日均预期波动点数 · 用于仓位管理与止损 |
| **成交量 · 最新 / 20日均量** | {tech['volume_latest']:,} / {f"{tech['volume_sma_20']:,}" if tech['volume_sma_20'] else '暂无'} | {'放量异动 · 高于20日均量' if tech['volume_sma_20'] and tech['volume_latest'] > tech['volume_sma_20'] else '缩量整理 · 换手平稳'} |
"""

        content += f"""
---

## 六、多空情景假设与推演

### 乐观情景 - 上行触发与催化
{bull_bullets}

### 悲观情景 - 下行风险与破位防守
{bear_bullets}

---

## 七、关键催化事件与跟踪清单
{cat_bullets}

---

## 八、免责声明
*免责声明：本投研分析报告由量化投研模型自动生成，融合量化技术指标与财务报表数据，仅供学习、研究与交流讨论，不构成任何投资建议、买卖要约或推荐。金融市场具有高波动性与本金损失风险，投资需独立审慎决策。*
"""

    else:
        # English Markdown
        bull_bullets = "\n".join([f"- {b}" for b in narrative["bull_case"]])
        bear_bullets = "\n".join([f"- {b}" for b in narrative["bear_case"]])
        cat_bullets = "\n".join([f"- {c}" for c in narrative["key_catalysts"]])

        content = f"""# Equity Research Report: {meta['ticker']} ({meta['company_name']})

*Analysis Date: {meta['analysis_date']} | Timeframe: {meta.get('timeframe_name', 'Daily Timeframe (1D)')} | Period: {meta['period']} | Sector/Asset: {meta['sector']} | Currency: {meta['currency']}*

---

## 0. Company Business Profile

> **🏢 Core Business & Industry Focus**:
> {business_summary}

---

## 1. Executive Summary & Investment Thesis

### 1. Key Metrics Overview
| Metric | Value | Institutional Context |
| :--- | :--- | :--- |
| **Current Price** | **${tech['close']}** ({tech['change_pct']:+.2f}%) | 52W High Drawdown: {tech['drawdown_from_52w_high']:.1f}% \\| 52W Low Rebound: +{tech['rebound_from_52w_low']:.1f}% |
| **Technical Verdict** | **{conf['technical_verdict']}** ({conf['technical_score']}) | Quantitative Trend & Momentum Alignment |
| **Fundamental Verdict** | **{conf['fundamental_verdict']}** ({conf['fundamental_score']}) | Business Quality, Profitability & Balance Sheet Health |
| **Confluence Verdict** | **{conf['confluence_verdict']}** | Multi-Factor Synthesis |
| **P/E & Percentile** | **{pe_val_str}** (10Y Percentile: {pe_pct_10y_str}) | {pe_zone_en_str} |
| **Capital Efficiency & Yield** | ROE: **{roe_str}** \\| Div Yield: **{div_yield_str}** | Operating Margin: {op_m_str} \\| Rev Growth: {rev_g_str} |
| **Key Support / Resistance** | Support: **${tech['nearest_support']}** | Resistance: **${tech['nearest_resistance']}** |
| **52-Week Range** | Low: ${tech['52_week_low']} | High: ${tech['52_week_high']} |

### 2. Core Investment Thesis

{narrative['executive_thesis']}

---

## 2. Tactical Trade Setup & Execution Plan

| Trade Parameter | Execution Level / Zone | Tactical Rational & Risk Management |
| :--- | :--- | :--- |
| **Tactical Bias** | **{trade['bias']}** | Directional setup derived from fundamental/technical confluence |
| **Recommended Accumulation Zone** | **{trade['entry_zone']}** | Support retest or moving average pullback consolidation zone |
| **Hard Invalidation Stop** | **{trade['stop_loss']}** | Structural breakdown level where trade thesis is invalidated |
| **Price Target 1 (Primary)** | **{trade['target_1']}** | Immediate resistance or prior consolidation high (take partial profit) |
| **Price Target 2 (Runner)** | **{trade['target_2']}** | Extended trend continuation or 52-week breakout objective |
| **Risk-to-Reward Ratio (R:R)** | **{trade['rr_ratio']}** | Calculated reward-to-risk ratio based on Target 1 |
| **Time Horizon** | **{trade['time_horizon']}** | Institutional positioning and swing duration |

---

## 3. Fundamental Quality, Valuation & Moat Analysis

### 1. Industry Landscape, Performance Trend & Moat Deep-Dive
{narrative['fundamental_narrative']}

### 2. Comprehensive Financial Scorecard
"""
        if not is_commodity:
            mkt_cap_str = f"${fund['market_cap'] / 1e9:.2f}B" if fund.get("market_cap") else "N/A"
            ev_str = f"${fund['enterprise_value'] / 1e9:.2f}B" if fund.get("enterprise_value") else "N/A"
            fcf_str = f"${fund['free_cash_flow'] / 1e9:.2f}B" if fund.get("free_cash_flow") else "N/A"
            fcf_yield_str = f"{fund['fcf_yield']:.2f}%" if fund.get("fcf_yield") is not None else "N/A"
            rev_g_str = f"{fund['revenue_growth'] * 100:.1f}%" if fund.get("revenue_growth") else "N/A"
            roe_str = f"{fund['return_on_equity'] * 100:.1f}%" if fund.get("return_on_equity") else "N/A"
            op_m_str = f"{fund['operating_margins'] * 100:.1f}%" if fund.get("operating_margins") else "N/A"
            gm_str = f"{fund['gross_margins'] * 100:.1f}%" if fund.get("gross_margins") else "N/A"
            pe_str = f"{fund['trailing_pe']:.1f}x" if fund.get("trailing_pe") else "N/A"
            f_pe_str = f"{fund['forward_pe']:.1f}x" if fund.get("forward_pe") else "N/A"
            peg_str = f"{fund['peg_ratio']:.2f}" if fund.get("peg_ratio") else "N/A"
            ps_str = f"{fund['price_to_sales']:.2f}x" if fund.get("price_to_sales") else "N/A"
            pb_str = f"{fund['price_to_book']:.2f}x" if fund.get("price_to_book") else "N/A"
            ev_ebitda_str = f"{fund['ev_to_ebitda']:.2f}x" if fund.get("ev_to_ebitda") else "N/A"
            div_yield_str = format_dividend_yield(fund.get("dividend_yield"))

            content += f"""
| Metric | Value | Institutional Context & Health |
| :--- | :--- | :--- |
| **Market Cap / Enterprise Value** | {mkt_cap_str} / {ev_str} | Equity valuation and debt-inclusive enterprise capitalization |
| **Trailing P/E / Forward P/E** | {pe_str} / {f_pe_str} | Current vs next twelve months valuation multiples |
| **P/E Historical Percentile (3Y / 5Y / 10Y)** | {pe_pct_3y_str} / {pe_pct_5y_str} / **{pe_pct_10y_str}** | 10Y Band: [{pe_10y_min_str} - {pe_10y_max_str}] Median: {pe_10y_med_str} ({pe_zone_en_str}) |
| **PEG Ratio** | {peg_str} | < 1.0 (Undervalued), 1.0-2.0 (Fair), > 2.0 (Premium) |
| **Price / Sales & Price / Book** | {ps_str} / {pb_str} | Revenue multiple and balance sheet net asset premium |
| **EV / EBITDA** | {ev_ebitda_str} | Capital-structure neutral cash earnings multiple |
| **Gross Margin / Operating Margin** | {gm_str} / {op_m_str} | > 15% demonstrates sustainable pricing power and competitive moat |
| **Return on Equity (ROE)** | {roe_str} | > 15% benchmark for high-quality capital compounders |
| **Free Cash Flow (FCF) / Yield** | {fcf_str} (Yield: {fcf_yield_str}) | True cash generated after capital expenditures |
| **Revenue Growth (YoY)** | {rev_g_str} | Top-line expansion momentum |
| **Debt to Equity** | {fund.get('debt_to_equity', 'N/A')} | Leverage ratio and financial solvency cushion |
| **Dividend Yield** | {div_yield_str} | Direct cash return to shareholders |
| **Analyst Consensus & Target** | ${format_analyst_target(fund.get('analyst_target_mean'))} ({fund.get('recommendation_key', 'N/A')}) | Wall Street consensus mean target price |
"""
            pe_chart_rel = os.path.basename(meta.get("pe_chart_image", "")) if meta.get("pe_chart_image") else ""
            if pe_chart_rel:
                content += f"""
### 3. Historical PE (TTM) & Valuation Percentile Bands (10-Year / Since Listing)
![Historical PE Percentile Chart]({pe_chart_rel})
"""
        else:
            content += """
*Asset Class: Commodity / Forex / Futures. Corporate accounting multiples do not apply.*
Key fundamental macro drivers:
- **Real Yields (US 10Y TIPS)**: Higher real yields elevate opportunity cost; declining yields catalyze strong rallies.
- **US Dollar Index (DXY)**: Dollar appreciation creates price friction; weakening dollar expands global commodity purchasing power.
- **Central Bank Accumulation**: Sovereign reserve diversification (PBoC, RBI) establishes a durable physical demand floor.
- **Geopolitical & Fiscal Debt Risk**: Safe-haven hedge against ballooning sovereign debt and fiscal deficits.
"""

        content += f"""
---

## 4. Technical Chart
![Technical Chart]({chart_rel})

---

## 5. Technical Analysis & Market Structure

### 1. Price Action & Momentum Analysis
> **📊 Price Action & Momentum Assessment**:
> {narrative['technical_narrative']}

### 2. Quantitative Indicators Summary
| Indicator | Calculated Value | Signal & Market Interpretation |
| :--- | :--- | :--- |
| **SMA 20** | {tech['sma_20']} | {'Price Above (Short-term Bullish)' if tech['sma_20'] and tech['close'] > tech['sma_20'] else 'Price Below (Short-term Pressure)'} |
| **SMA 50** | {tech['sma_50']} | {'Price Above (Institutional Support Intact)' if tech['sma_50'] and tech['close'] > tech['sma_50'] else 'Intermediate Trend Weak'} |
| **SMA 200** | {tech['sma_200']} | {'Secular Bullish Regime' if tech['sma_200'] and tech['close'] > tech['sma_200'] else 'Secular Bearish Pressure'} |
| **EMA 9 / EMA 21** | {tech['ema_9']} / {tech['ema_21']} | {'Bullish Fast Momentum Stack' if tech['ema_9'] and tech['ema_21'] and tech['ema_9'] > tech['ema_21'] else 'Bearish Momentum Alignment'} |
| **RSI (14)** | {tech['rsi_14']} | {'Oversold (< 30, Mean-Reversion Potential)' if tech['rsi_14'] and tech['rsi_14'] < 30 else ('Overbought (> 70)' if tech['rsi_14'] and tech['rsi_14'] > 70 else 'Neutral Healthy Range (30-70)')} |
| **MACD / Signal / Hist** | {tech['macd']} / {tech['macd_signal']} / {tech['macd_hist']} | {'Bullish Momentum Expansion' if tech['macd_hist'] and tech['macd_hist'] > 0 else 'Bearish Momentum Contraction'} |
| **Bollinger Bands (20, 2 std)** | Lower: {tech['bollinger_lower']} / Upper: {tech['bollinger_upper']} | {'Lower Band Tag (Oversold extension)' if tech['bollinger_lower'] and tech['close'] < tech['bollinger_lower'] else ('Upper Band Breakout' if tech['bollinger_upper'] and tech['close'] > tech['bollinger_upper'] else 'Inside Normal Band Range')} |
| **ATR (14)** | {tech['atr_14']} | Expected daily price volatility range |
| **Volume (Latest / 20 SMA)** | {tech['volume_latest']:,} / {f"{tech['volume_sma_20']:,}" if tech['volume_sma_20'] else 'N/A'} | {'Above 20-Day Average (Active Turnover)' if tech['volume_sma_20'] and tech['volume_latest'] > tech['volume_sma_20'] else 'Below 20-Day Average (Orderly Consolidation)'} |
"""

        content += f"""
---

## 6. Scenario Planning: Bull vs. Bear Case

### Bull Case - Upside Catalysts & Expansion
{bull_bullets}

### Bear Case - Downside Risks & Invalidation
{bear_bullets}

---

## 7. Key Catalysts & Monitoring Checklist
{cat_bullets}

---

## 8. Disclaimer
*Disclaimer: This research report was generated automatically by a quantitative equity model integrating technical price action and public financial filings. It is provided for educational and informational purposes only and does not constitute financial, investment, or trading advice.*
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


def generate_html_report(data: dict, html_path: str, chart_path: str, lang: str = "en") -> str:
    """Generate modern, responsive HTML report with embedded chart and language support."""
    meta = data["metadata"]
    tech = data["technicals"]
    fund = data["fundamentals"]
    conf = data["confluence"]
    trade = data["trade_setup"]
    narrative = data["narratives"]

    is_zh = (lang == "zh")
    curr_sym = "¥" if meta["currency"] in ["CNY", "CNH"] else ("HK$" if meta["currency"] == "HKD" else "$")
    is_commodity = meta.get("asset_type") in ["COMMODITY", "CURRENCY", "FUTURE", "CRYPTOCURRENCY"]

    chart_b64 = ""
    if os.path.exists(chart_path):
        with open(chart_path, "rb") as img_f:
            chart_b64 = base64.b64encode(img_f.read()).decode("utf-8")

    pe_chart_b64 = ""
    pe_chart_path = meta.get("pe_chart_image")
    if pe_chart_path and os.path.exists(pe_chart_path):
        with open(pe_chart_path, "rb") as img_f:
            pe_chart_b64 = base64.b64encode(img_f.read()).decode("utf-8")

    t_verdict = conf["technical_verdict"]
    t_color = "#16a34a" if ("Bullish" in t_verdict or "多头" in t_verdict) else ("#dc2626" if ("Bearish" in t_verdict or "空头" in t_verdict) else "#d97706")
    
    f_verdict = conf["fundamental_verdict"]
    f_color = "#16a34a" if ("Strong" in f_verdict or "优质" in f_verdict) else ("#dc2626" if ("Weak" in f_verdict or "偏弱" in f_verdict) else "#2563eb")

    bias_color = "#16a34a" if trade["bias_type"] == "bullish" else ("#dc2626" if trade["bias_type"] == "bearish" else "#d97706")

    font_defs = []
    if os.path.exists(YAHEI_REGULAR):
        font_defs.append("""
        @font-face {
            font-family: 'YaHei';
            src: url('msyh.ttc');
            font-weight: normal;
            font-style: normal;
        }
        """)
    if os.path.exists(YAHEI_BOLD):
        font_defs.append("""
        @font-face {
            font-family: 'YaHei';
            src: url('msyhbd.ttc');
            font-weight: bold;
            font-style: normal;
        }
        """)
    if os.path.exists(SEGOE_REGULAR):
        font_defs.append("""
        @font-face {
            font-family: 'SegoeUI';
            src: url('segoeui.ttf');
            font-weight: normal;
            font-style: normal;
        }
        """)
    if os.path.exists(SEGOE_BOLD):
        font_defs.append("""
        @font-face {
            font-family: 'SegoeUI';
            src: url('segoeuib.ttf');
            font-weight: bold;
            font-style: normal;
        }
        """)
    font_css = "\n".join(font_defs)

    font_family = "'YaHei', 'Microsoft YaHei', 'SegoeUI', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif"

    unit_name, divisor = get_unit_and_divisor(meta["currency"], is_zh)
    na_str = "暂无" if is_zh else "N/A"

    mkt_cap_str = f"{curr_sym}{fund['market_cap'] / divisor:.2f}{unit_name}" if fund.get("market_cap") else na_str
    ev_str = f"{curr_sym}{fund['enterprise_value'] / divisor:.2f}{unit_name}" if fund.get("enterprise_value") else na_str
    fcf_str = f"{curr_sym}{fund['free_cash_flow'] / divisor:.2f}{unit_name}" if fund.get("free_cash_flow") else na_str
    fcf_yield_str = f"{fund['fcf_yield']:.2f}%" if fund.get("fcf_yield") is not None else na_str
    pe_str = f"{fund['trailing_pe']:.1f}倍" if is_zh and fund.get("trailing_pe") else (f"{fund['trailing_pe']:.1f}x" if fund.get("trailing_pe") else na_str)
    f_pe_str = f"{fund['forward_pe']:.1f}倍" if is_zh and fund.get("forward_pe") else (f"{fund['forward_pe']:.1f}x" if fund.get("forward_pe") else na_str)
    peg_str = f"{fund['peg_ratio']:.2f}" if fund.get("peg_ratio") else na_str
    roe_str = f"{fund['return_on_equity'] * 100:.1f}%" if fund.get("return_on_equity") else na_str
    op_m_str = f"{fund['operating_margins'] * 100:.1f}%" if fund.get("operating_margins") else na_str
    gm_str = f"{fund['gross_margins'] * 100:.1f}%" if fund.get("gross_margins") else na_str
    rev_g_str = f"{fund['revenue_growth'] * 100:.1f}%" if fund.get("revenue_growth") else na_str
    div_yield_str = format_dividend_yield(fund.get("dividend_yield"))
    business_summary = meta.get("business_summary") or ("暂无主营业务详细描述。" if is_zh else "No business profile available.")

    pe_pct_3y = fund.get("pe_3y_percentile")
    pe_pct_5y = fund.get("pe_5y_percentile")
    pe_pct_10y = fund.get("pe_10y_percentile")
    pe_pct_3y_str = f"{pe_pct_3y:.1f}%" if pe_pct_3y is not None else na_str
    pe_pct_5y_str = f"{pe_pct_5y:.1f}%" if pe_pct_5y is not None else na_str
    pe_pct_10y_str = f"{pe_pct_10y:.1f}%" if pe_pct_10y is not None else (pe_pct_3y_str if pe_pct_3y_str != na_str else na_str)
    pe_zone_str = fund.get("valuation_zone_zh", na_str) if is_zh else fund.get("valuation_zone_en", na_str)
    pe_zone_en_str = fund.get("valuation_zone_en", na_str)
    pe_3y_min_str = f"{fund.get('pe_3y_min', na_str)}"
    pe_3y_max_str = f"{fund.get('pe_3y_max', na_str)}"
    pe_3y_med_str = f"{fund.get('pe_3y_median', na_str)}"
    pe_10y_min_str = f"{fund.get('pe_10y_min', fund.get('pe_3y_min', na_str))}"
    pe_10y_max_str = f"{fund.get('pe_10y_max', fund.get('pe_3y_max', na_str))}"
    pe_10y_med_str = f"{fund.get('pe_10y_median', fund.get('pe_3y_median', na_str))}"

    bull_items_html = "".join([f"<li>{re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', b)}</li>" for b in narrative["bull_case"]])
    bear_items_html = "".join([f"<li>{re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', b)}</li>" for b in narrative["bear_case"]])
    cat_items_html = "".join([f"<li>{re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', c)}</li>" for c in narrative["key_catalysts"]])

    timeframe_disp = "日线级别" if "1d" in meta.get("interval", "1d") else ("周线级别" if "1wk" in meta.get("interval", "") else ("月线级别" if "1mo" in meta.get("interval", "") else meta.get("timeframe_name", "日线级别")))
    timeframe_badge = "日线" if "1d" in meta.get("interval", "1d") else ("周线" if "1wk" in meta.get("interval", "") else ("月线" if "1mo" in meta.get("interval", "") else meta.get("timeframe_code", "1D")))
    period_disp = format_period_zh(meta.get("period", "1y"))
    currency_disp = format_currency_zh(meta.get("currency", "CNY"))
    sector_industry_disp = meta.get("sector", "")
    if meta.get("industry") and meta["industry"] not in meta.get("sector", "") and not any(ch.isalpha() and ord(ch) < 128 for ch in meta["industry"]):
        sector_industry_disp = f"{meta['sector']} / {meta['industry']}"

    html = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if is_zh else 'en'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{meta['company_name']} ({meta['ticker']}) - {'深度投研报告' if is_zh else 'Research Report'}</title>
<style>
    @page {{
        size: letter;
        margin: 8mm;
    }}
    {font_css}
    body, h1, h2, h3, h4, p, table, th, td, span, div, li, ul {{
        font-family: {font_family};
    }}
    body {{
        color: #0f172a;
        background-color: #f1f5f9;
        margin: 0;
        padding: 20px;
        font-size: 15.5px;
        line-height: 1.7;
    }}
    .fund-section-title {{
        font-size: 15.5px;
        font-weight: 700;
        color: #1e40af;
    }}
    .report-container {{
        max-width: 960px;
        margin: 0 auto;
        background: #ffffff;
        border: 1.5px solid #cbd5e1;
        border-radius: 8px;
        padding: 32px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);
    }}
    .header-banner {{
        background: #0f172a;
        color: #ffffff;
        padding: 20px 24px;
        border-radius: 8px;
        margin-bottom: 22px;
    }}
    .header-banner h1 {{
        margin: 0 0 8px 0;
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.3px;
        color: #ffffff;
    }}
    .header-banner .meta-row {{
        font-size: 13.5px;
        color: #cbd5e1;
        line-height: 1.6;
    }}
    .badges {{
        margin-top: 12px;
        display: flex;
        gap: 10px;
    }}
    .badge {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 6px 14px;
        line-height: 1.2;
        border-radius: 4px;
        font-size: 13px;
        font-weight: 700;
        color: #ffffff;
    }}
    .kpi-table {{
        width: 100%;
        margin-bottom: 22px;
        border-collapse: separate;
        border-spacing: 12px;
    }}
    .kpi-card {{
        background: #f8fafc;
        border: 1.5px solid #cbd5e1;
        border-radius: 8px;
        padding: 16px 18px;
        vertical-align: top;
        width: 25%;
    }}
    .kpi-title {{
        font-size: 12.5px;
        color: #475569;
        text-transform: uppercase;
        font-weight: 700;
        margin-bottom: 8px;
        letter-spacing: 0.5px;
    }}
    .kpi-value {{
        font-size: 25px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 8px;
    }}
    .kpi-sub {{
        font-size: 13px;
        color: #334155;
        line-height: 1.6;
        font-weight: 500;
    }}
    .confluence-box {{
        background: #eff6ff;
        border-left: 6px solid #2563eb;
        padding: 16px 20px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 22px;
    }}
    .confluence-box h3 {{
        margin: 0 0 6px 0;
        font-size: 16px;
        font-weight: 800;
        color: #1e40af;
    }}
    .confluence-box p {{
        margin: 0;
        font-size: 15.5px;
        font-weight: 600;
        color: #0f172a;
        line-height: 1.65;
    }}
    .company-profile-box {{
        background: #f8fafc;
        border: 1.5px solid #cbd5e1;
        border-left: 5px solid #2563eb;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 22px;
    }}
    .profile-title {{
        font-size: 15px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .profile-text {{
        font-size: 14.5px;
        color: #334155;
        line-height: 1.7;
    }}
    .thesis-box {{
        background: #f8fafc;
        border: 1.5px solid #cbd5e1;
        border-left: 5px solid #0f172a;
        border-radius: 8px;
        padding: 18px 22px;
        margin-bottom: 24px;
    }}
    .thesis-header {{
        font-size: 16px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 10px;
        letter-spacing: 0.3px;
    }}
    .thesis-summary {{
        font-size: 15.5px;
        color: #1e293b;
        line-height: 1.7;
        margin-bottom: 12px;
        padding-bottom: 10px;
        border-bottom: 1px dashed #cbd5e1;
    }}
    .thesis-points-title {{
        font-size: 14.5px;
        font-weight: 700;
        color: #475569;
        margin-bottom: 6px;
        text-transform: uppercase;
    }}
    .thesis-points {{
        margin: 0;
        padding-left: 20px;
        font-size: 15px;
        color: #334155;
        line-height: 1.75;
    }}
    .thesis-points li {{
        margin-bottom: 8px;
    }}
    .trade-setup-card {{
        background: #f8fafc;
        border: 2px solid #94a3b8;
        border-radius: 8px;
        padding: 18px 22px;
        margin-bottom: 24px;
    }}
    .trade-setup-card h3 {{
        margin: 0 0 12px 0;
        font-size: 16.5px;
        font-weight: 800;
        color: #0f172a;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
    }}
    .trade-grid-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14.5px;
    }}
    .trade-grid-table th, .trade-grid-table td {{
        padding: 10px 14px;
        border: 1px solid #cbd5e1;
        text-align: left;
        line-height: 1.6;
    }}
    .trade-grid-table th {{
        background: #e2e8f0;
        color: #0f172a;
        font-weight: 700;
        font-size: 15px;
    }}
    h2 {{
        font-size: 19px;
        font-weight: 800;
        color: #0f172a;
        margin: 28px 0 14px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #cbd5e1;
    }}
    table.data-table {{
        width: 100%;
        margin-bottom: 24px;
        font-size: 14.5px;
        border-collapse: collapse;
        border: 1.5px solid #cbd5e1;
    }}
    table.data-table th, table.data-table td {{
        padding: 10px 14px;
        text-align: left;
        border: 1px solid #cbd5e1;
        line-height: 1.6;
    }}
    table.data-table th {{
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 700;
        font-size: 15px;
    }}
    table.data-table tr:nth-child(even) {{
        background-color: #f8fafc;
    }}
    table.data-table td strong {{
        color: #0f172a;
        font-size: 15px;
    }}
    .chart-container {{
        text-align: center;
        margin: 20px 0;
        border: 1.5px solid #cbd5e1;
        border-radius: 8px;
        padding: 10px;
        background: #ffffff;
    }}
    .chart-container img {{
        max-width: 100%;
        height: auto;
    }}
    .scenario-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 12px;
        margin-bottom: 24px;
    }}
    .scenario-card {{
        border-radius: 8px;
        padding: 16px 18px;
        vertical-align: top;
        font-size: 14.5px;
        line-height: 1.65;
        width: 50%;
    }}
    .bull-card {{
        background: #f0fdf4;
        border: 1.5px solid #86efac;
        border-left: 5px solid #16a34a;
    }}
    .bull-card h4 {{
        margin: 0 0 10px 0;
        color: #14532d;
        font-size: 15px;
        font-weight: 800;
    }}
    .bear-card {{
        background: #fef2f2;
        border: 1.5px solid #fca5a5;
        border-left: 5px solid #dc2626;
    }}
    .bear-card h4 {{
        margin: 0 0 10px 0;
        color: #7f1d1d;
        font-size: 15px;
        font-weight: 800;
    }}
    ul.checklist {{
        padding-left: 22px;
        margin: 12px 0;
        font-size: 15px;
        color: #1e293b;
    }}
    ul.checklist li {{
        margin-bottom: 8px;
        line-height: 1.7;
    }}
    .disclaimer {{
        font-size: 12.5px;
        color: #64748b;
        margin-top: 38px;
        padding-top: 16px;
        border-top: 1px solid #cbd5e1;
        text-align: center;
        line-height: 1.65;
    }}
    .page-break {{
        page-break-after: always;
    }}
</style>
</head>
<body>
<div class="report-container">

    <!-- Header Banner -->
    <div class="header-banner">
        <h1>{f"{meta['company_name']} {meta['ticker']}" if is_zh else f"{meta['ticker']} - {meta['company_name']}"}</h1>
        <div class="meta-row">
            {'板块/行业' if is_zh else 'Sector/Industry'}: <strong>{sector_industry_disp if is_zh else f"{meta['sector']} ({meta['industry']})"}</strong> &bull; 
            {'结算货币' if is_zh else 'Currency'}: <strong>{currency_disp if is_zh else meta['currency']}</strong> &bull; 
            {'分析日期' if is_zh else 'Date'}: <strong>{meta['analysis_date']}</strong> &bull; 
            {'数据周期' if is_zh else 'Period'}: <strong>{period_disp if is_zh else meta['period']}</strong> &bull; 
            {'时间级别' if is_zh else 'Timeframe'}: <strong>{timeframe_disp if is_zh else meta.get('timeframe_name', 'Daily')}</strong>
        </div>
        <div class="badges">
            <span class="badge" style="background-color: {t_color};">{'技术面' if is_zh else 'Technical'}: {t_verdict} · {conf['technical_score']}</span>
            <span class="badge" style="background-color: {f_color};">{'基本面' if is_zh else 'Fundamental'}: {f_verdict} · {conf['fundamental_score']}</span>
            <span class="badge" style="background-color: {bias_color};">{'战术定性' if is_zh else 'Tactical Bias'}: {trade['bias']}</span>
        </div>
    </div>

    <!-- Company Business Profile Box -->
    <div class="company-profile-box">
        <div class="profile-title">{'公司主营业务概况' if is_zh else 'Company Business Profile'}</div>
        <div class="profile-text">{business_summary}</div>
    </div>

    <!-- 4-Card KPI Strip -->
    <table class="kpi-table">
        <tr>
            <td class="kpi-card">
                <div class="kpi-title">{'最新价格 & 涨跌' if is_zh else 'Last Price & Change'}</div>
                <div class="kpi-value">{curr_sym}{tech['close']}</div>
                <div class="kpi-sub">{'日涨跌' if is_zh else 'Daily'}: <strong>{tech['change_pct']:+.2f}%</strong></div>
                <div class="kpi-sub">{'52周高位回撤' if is_zh else '52W Drawdown'}: {tech['drawdown_from_52w_high']:.1f}%</div>
            </td>
            <td class="kpi-card">
                <div class="kpi-title">{'估值与历史分位' if is_zh else 'Valuation & Historical Percentile'}</div>
                <div class="kpi-value">{('市盈率 ' + pe_str) if (is_zh and pe_str != '暂无') else pe_str}</div>
                <div class="kpi-sub">{'10年PE分位' if is_zh else '10Y PE Percentile'}: <strong>{pe_pct_10y_str}</strong></div>
                <div class="kpi-sub">{'估值水位' if is_zh else 'Valuation Zone'}: <strong>{pe_zone_str}</strong></div>
            </td>
            <td class="kpi-card">
                <div class="kpi-title">{'资本回报与质量' if is_zh else 'Capital Efficiency'}</div>
                <div class="kpi-value">{roe_str}</div>
                <div class="kpi-sub">{'营业利润率' if is_zh else 'Operating Margin'}: <strong>{op_m_str}</strong></div>
                <div class="kpi-sub">{'营收增速' if is_zh else 'Rev Growth'}: <strong>{rev_g_str}</strong></div>
                <div class="kpi-sub">{'股息率' if is_zh else 'Dividend Yield'}: <strong>{div_yield_str}</strong></div>
            </td>
            <td class="kpi-card">
                <div class="kpi-title">{'动能与波动率' if is_zh else 'Trend & Volatility'}</div>
                <div class="kpi-value">RSI {tech['rsi_14']}</div>
                <div class="kpi-sub">{'真实波幅 ATR(14)' if is_zh else 'ATR (14)'}: <strong>{tech['atr_14']}</strong></div>
                <div class="kpi-sub">{'支撑' if is_zh else 'Supp'}: {curr_sym}{tech['nearest_support']} | {'阻力' if is_zh else 'Res'}: {curr_sym}{tech['nearest_resistance']}</div>
            </td>
        </tr>
    </table>

    <!-- Institutional Confluence Callout -->
    <div class="confluence-box">
        <h3>{'机构多空共振定性' if is_zh else 'Institutional Confluence Synthesis'}</h3>
        <p><strong>{conf['confluence_verdict']}</strong></p>
    </div>

    <!-- Executive Thesis -->
    <div class="thesis-box">
        {narrative.get('executive_thesis_html') or f"<strong>{'核心投研观点' if is_zh else 'Executive Investment Thesis'}</strong><br/>{narrative['executive_thesis']}"}
    </div>

    <!-- Tactical Trade Setup -->
    <div class="trade-setup-card">
        <h3>{'战术交易计划与执行矩阵' if is_zh else 'Tactical Trade Setup & Execution Plan'}</h3>
        <table class="trade-grid-table">
            <tr>
                <th style="width: 28%;">{'交易参数' if is_zh else 'Parameter'}</th>
                <th style="width: 32%;">{'建议执行点位 / 区间' if is_zh else 'Execution Level / Zone'}</th>
                <th style="width: 40%;">{'战术逻辑与风控要点' if is_zh else 'Tactical Context & Risk Management'}</th>
            </tr>
            <tr>
                <td><strong>{'操作倾向' if is_zh else 'Tactical Bias'}</strong></td>
                <td><strong style="color: {bias_color};">{trade['bias']}</strong></td>
                <td>{'多空共振量化评分定性' if is_zh else 'Directional bias from multi-factor confluence'}</td>
            </tr>
            <tr>
                <td><strong>{'逢低布局区间' if is_zh else 'Accumulation Zone'}</strong></td>
                <td><strong>{trade['entry_zone']}</strong></td>
                <td>{'依托支撑位或中短期均线回踩区间' if is_zh else 'Key support or moving average retracement'}</td>
            </tr>
            <tr>
                <td><strong>{'防守止损线' if is_zh else 'Hard Invalidation Stop'}</strong></td>
                <td><strong style="color: #dc2626;">{trade['stop_loss']}</strong></td>
                <td>{'结构失效点，跌破立即离场，严控下行风险' if is_zh else 'Structural thesis invalidation level'}</td>
            </tr>
            <tr>
                <td><strong>{'第一目标位' if is_zh else 'Target 1 (Primary)'}</strong></td>
                <td><strong style="color: #16a34a;">{trade['target_1']}</strong></td>
                <td>{'最近阻力位：建议逢高减仓' if is_zh else 'Immediate overhead resistance (trim & lock gains)'}</td>
            </tr>
            <tr>
                <td><strong>{'第二目标位' if is_zh else 'Target 2 (Runner)'}</strong></td>
                <td><strong>{trade['target_2']}</strong></td>
                <td>{'趋势延续或52周高点突破目标' if is_zh else 'Extended trend runner / 52W high breakout'}</td>
            </tr>
            <tr>
                <td><strong>{'战术盈亏比' if is_zh else 'Risk-to-Reward Ratio'}</strong></td>
                <td><strong>{trade['rr_ratio']}</strong></td>
                <td>{'基于第一目标位的风险回报比率' if is_zh else 'Reward-to-risk ratio based on Target 1'}</td>
            </tr>
            <tr>
                <td><strong>{'预期持仓周期' if is_zh else 'Time Horizon'}</strong></td>
                <td>{trade['time_horizon']}</td>
                <td>{'适合波段交易与中线建仓' if is_zh else 'Ideal for swing or multi-week positioning'}</td>
            </tr>
        </table>
    </div>

    <div class="page-break"></div>

    <!-- Fundamental Valuation & Moat -->
    <h2>{'三、基本面估值、盈利质量与护城河' if is_zh else '3. Fundamental Valuation, Quality & Moat'}</h2>
    <div class="thesis-box" style="margin-bottom: 10px;">
        {narrative.get('fundamental_narrative_html', narrative['fundamental_narrative'])}
    </div>

"""
    if not is_commodity:
        mult_sfx = "倍" if is_zh else "x"
        ps_str = f"{fund['price_to_sales']:.2f}{mult_sfx}" if fund.get("price_to_sales") else na_str
        pb_str = f"{fund['price_to_book']:.2f}{mult_sfx}" if fund.get("price_to_book") else na_str
        ev_ebitda_str = f"{fund['ev_to_ebitda']:.2f}{mult_sfx}" if fund.get("ev_to_ebitda") else na_str
        div_yield_str = format_dividend_yield(fund.get("dividend_yield"))
        d2e_val = fund.get("debt_to_equity")
        if d2e_val is not None:
            d2e_str = f"{float(d2e_val):.1f}%"
        elif fund.get("total_debt") == 0:
            d2e_str = "0.0% · 零有息负债" if is_zh else "0.0% (Debt-Free)"
        else:
            d2e_str = na_str
        tgt_raw = fund.get("analyst_target_mean")
        if is_zh:
            rec_str_disp = format_recommendation_zh(fund.get("recommendation_key"))
            analyst_html_disp = f"{curr_sym}{format_analyst_target(tgt_raw)} · {rec_str_disp}" if tgt_raw else f"暂无目标价 · {rec_str_disp}"
        else:
            rec_str_disp = fund.get("recommendation_key") or "N/A"
            analyst_html_disp = f"{curr_sym}{format_analyst_target(tgt_raw)} · {rec_str_disp}" if tgt_raw else f"N/A · {rec_str_disp}"

        html += f"""
    <table class="data-table">
        <thead><tr><th>{'核心财务指标' if is_zh else 'Metric'}</th><th>{'数值' if is_zh else 'Value'}</th><th>{'机构对标与安全边际' if is_zh else 'Institutional Benchmark / Health'}</th></tr></thead>
        <tbody>
            <tr><td><strong>{'总市值 / 企业价值' if is_zh else 'Market Cap / EV'}</strong></td><td>{mkt_cap_str}</td><td>{'企业价值: ' + ev_str if is_zh else 'EV: ' + ev_str}</td></tr>
            <tr><td><strong>{'滚动市盈率 / 动态市盈率' if is_zh else 'Trailing P/E / Forward P/E'}</strong></td><td>{pe_str} / {f_pe_str}</td><td>{'历史估值区间对比' if is_zh else 'Historical multiple context'}</td></tr>
            <tr><td><strong>{'市盈率历史分位 3年 / 5年 / 10年' if is_zh else 'P/E Historical Percentile (3Y / 5Y / 10Y)'}</strong></td><td>{pe_pct_3y_str} / {pe_pct_5y_str} / <strong>{pe_pct_10y_str}</strong></td><td>{'10年区间: ' + pe_10y_min_str + ' - ' + pe_10y_max_str + ' · 中位数 ' + pe_10y_med_str + ' · ' + pe_zone_str if is_zh else '10Y Band: [' + pe_10y_min_str + ' - ' + pe_10y_max_str + '] Median: ' + pe_10y_med_str + ' (' + pe_zone_en_str + ')'}</td></tr>
            <tr><td><strong>{'市盈率相对盈利增长比率' if is_zh else 'PEG Ratio'}</strong></td><td>{peg_str}</td><td>&lt; 1.0 {'低估' if is_zh else 'Undervalued'}, 1.0-2.0 {'合理' if is_zh else 'Fair'}, &gt; 2.0 {'溢价' if is_zh else 'Premium'}</td></tr>
            <tr><td><strong>{'市销率 / 市净率' if is_zh else 'P/S & P/B'}</strong></td><td>{ps_str} / {pb_str}</td><td>{'营收与净资产估值溢价' if is_zh else 'Sales and book value multiples'}</td></tr>
            <tr><td><strong>{'企业价值倍数' if is_zh else 'EV / EBITDA'}</strong></td><td>{ev_ebitda_str}</td><td>{'跨资本结构现金盈利倍数' if is_zh else 'Capital-structure neutral cash earnings multiple'}</td></tr>
            <tr><td><strong>{'毛利率 / 营业利润率' if is_zh else 'Gross & Operating Margin'}</strong></td><td>{gm_str} / {op_m_str}</td><td>&gt; 15% {'显示出色的产业链议价能力与护城河' if is_zh else 'indicates strong pricing power & moat'}</td></tr>
            <tr><td><strong>{'净资产收益率' if is_zh else 'Return on Equity (ROE)'}</strong></td><td>{roe_str}</td><td>&gt; 15% {'资本复利回报标杆' if is_zh else 'demonstrates high capital efficiency'}</td></tr>
            <tr><td><strong>{'自由现金流 / 自由现金流收益率' if is_zh else 'Free Cash Flow / Yield'}</strong></td><td>{fcf_str + ' · 收益率: ' + fcf_yield_str if is_zh else fcf_str + ' (Yield: ' + fcf_yield_str + ')'}</td><td>{'扣除资本开支后的真实现金流入' if is_zh else 'Cash conversion quality'}</td></tr>
            <tr><td><strong>{'营业收入同比增速' if is_zh else 'Revenue Growth (YoY)'}</strong></td><td>{rev_g_str}</td><td>{'主营业务扩张势头' if is_zh else 'Top-line expansion rate'}</td></tr>
            <tr><td><strong>{'资产负债率' if is_zh else 'Balance Sheet (Debt/Equity)'}</strong></td><td>{d2e_str}</td><td>{'财务杠杆与安全缓冲垫' if is_zh else 'Leverage & solvency buffer'}</td></tr>
            <tr><td><strong>{'股息率' if is_zh else 'Dividend Yield'}</strong></td><td>{div_yield_str}</td><td>{'直接现金分红回报' if is_zh else 'Direct cash return to shareholders'}</td></tr>
            <tr><td><strong>{'分析师目标价与共识' if is_zh else 'Analyst Target / Consensus'}</strong></td><td>{analyst_html_disp}</td><td>{'卖方分析师平均目标价' if is_zh else 'Wall Street target consensus'}</td></tr>
        </tbody>
    </table>
"""
        # Past 2-Year Performance Comparison Table
        hist_perf = fund.get("historical_performance", [])
        _, perf_html = format_historical_performance_table(hist_perf, currency=meta["currency"], is_zh=is_zh)
        if perf_html:
            table_title = "近3年核心经营业绩与财务对比" if is_zh else "3-Year Historical Performance & Financial Comparison"
            html += f"""
    <div style="margin-top: 24px; margin-bottom: 22px;">
        <h3>{table_title}</h3>
        {perf_html}
    </div>
"""

        if pe_chart_b64:
            chart_title = 'PE TTM 历史估值走势与分位数带宽' if is_zh else '10-Year Historical PE (TTM) & Valuation Percentile Bands'
            html += f"""
    <!-- PE Valuation Bands Section -->
    <div class="pe-chart-section" style="margin-top: 22px;">
        <h3>{chart_title}</h3>
        <div class="chart-container">
            <img src="data:image/png;base64,{pe_chart_b64}" alt="PE Historical Percentile Chart" width="760" />
        </div>
    </div>
"""
    else:
        if is_zh:
            html += """
    <p><em>资产类别：大宗商品 / 汇率。不适用企业财务利润率与 PE 估值。</em></p>
    <table class="data-table">
        <thead><tr><th>核心宏观因子</th><th>因子属性与长周期逻辑</th></tr></thead>
        <tbody>
            <tr><td><strong>美债实际收益率 (10Y TIPS)</strong></td><td>非生息资产机会成本的核心锚位，实际利率下行是牛市核心驱动。</td></tr>
            <tr><td><strong>美元指数 (DXY)</strong></td><td>以美元计价的大宗商品反向汇率波动逻辑。</td></tr>
            <tr><td><strong>主权央行实物储备</strong></td><td>全球战略去美元化如主权央行实物储备构建坚固物理底线。</td></tr>
            <tr><td><strong>地缘冲突与主权信用风险</strong></td><td>抗通胀与主权债务违约对冲的终极硬通货。</td></tr>
        </tbody>
    </table>
"""
        else:
            html += """
    <p><em>Asset Class: Commodity / Currency / Forex. Corporate accounting metrics (P/E, ROE, FCF) do not apply.</em></p>
    <table class="data-table">
        <thead><tr><th>Macro Fundamental Factor</th><th>Description & Influence on Valuation</th></tr></thead>
        <tbody>
            <tr><td><strong>Real Interest Rates (US 10Y TIPS)</strong></td><td>Primary opportunity cost benchmark; falling yields catalyze rallies.</td></tr>
            <tr><td><strong>US Dollar Index (DXY)</strong></td><td>Inverse currency correlation; dollar appreciation creates price friction.</td></tr>
            <tr><td><strong>Central Bank Accumulation</strong></td><td>Sovereign reserve diversification establishes a durable physical floor.</td></tr>
            <tr><td><strong>Geopolitical & Debt Sustainability</strong></td><td>Safe-haven sovereign risk premium against ballooning sovereign debt.</td></tr>
        </tbody>
    </table>
"""

    html += f"""
    <div class="page-break"></div>

    <!-- Technical Chart -->
    <h2>{'四、多周期技术分析图表 · ' + (timeframe_disp if is_zh else meta.get('timeframe_name', '日线级别')) if is_zh else '4. Technical Multi-Pane Chart'}</h2>
    <div class="chart-container">
        <img src="data:image/png;base64,{chart_b64}" alt="Technical Analysis Chart" width="760" />
    </div>

    <!-- Technical Analysis Narrative & Indicators -->
    <h2>{'五、技术面深度剖析与微观量价结构' if is_zh else '5. Technical Market Structure & Indicators'}</h2>
    <div class="thesis-box" style="margin-bottom: 14px;">
        {narrative['technical_narrative']}
    </div>
    <table class="data-table">
        <thead>
            <tr><th>{'指标名称' if is_zh else 'Indicator'}</th><th>{'计算数值' if is_zh else 'Calculated Value'}</th><th>{'信号与状态解读' if is_zh else 'Status / Market Interpretation'}</th></tr>
        </thead>
        <tbody>
            <tr><td><strong>{'20日均线 · 月线' if is_zh else 'SMA 20'}</strong></td><td>{tech['sma_20'] if tech['sma_20'] is not None else na_str}</td><td>{(('价格位于均线上方 · 多头' if tech['close'] > tech['sma_20'] else '价格位于均线下方 · 空头') if is_zh else ('Price Above (+)' if tech['close'] > tech['sma_20'] else 'Price Below (-)')) if tech['sma_20'] is not None else ('样本不足' if is_zh else 'Insufficient History')}</td></tr>
            <tr><td><strong>{'50日均线 · 季线' if is_zh else 'SMA 50'}</strong></td><td>{tech['sma_50'] if tech['sma_50'] is not None else na_str}</td><td>{(('突破中期防线' if tech['close'] > tech['sma_50'] else '中期趋势偏弱') if is_zh else ('Price Above (+)' if tech['close'] > tech['sma_50'] else 'Price Below (-)')) if tech['sma_50'] is not None else ('样本不足' if is_zh else 'Insufficient History')}</td></tr>
            <tr><td><strong>{'200日均线 · 牛熊线' if is_zh else 'SMA 200'}</strong></td><td>{tech['sma_200'] if tech['sma_200'] is not None else na_str}</td><td>{(('长线牛市宏观区间' if tech['close'] > tech['sma_200'] else '长线熊市空头承压') if is_zh else ('Bullish Regime (+)' if tech['close'] > tech['sma_200'] else 'Bearish Regime (-)')) if tech['sma_200'] is not None else ('长线样本积累中' if is_zh else 'Insufficient History (<200 periods)')}</td></tr>
            <tr><td><strong>{'9日 / 21日指数均线' if is_zh else 'EMA 9 / EMA 21'}</strong></td><td>{tech['ema_9']} / {tech['ema_21']}</td><td>{('短线多头金叉排列' if tech['ema_9'] and tech['ema_21'] and tech['ema_9'] > tech['ema_21'] else '短线空头死叉排列') if is_zh else ('Bullish Momentum Stack' if tech['ema_9'] and tech['ema_21'] and tech['ema_9'] > tech['ema_21'] else 'Bearish Momentum Stack')}</td></tr>
            <tr><td><strong>{'14日相对强弱指标' if is_zh else 'RSI (14)'}</strong></td><td>{tech['rsi_14']}</td><td>{('极度超卖 < 30 · 反弹蓄势' if tech['rsi_14'] and tech['rsi_14'] < 30 else ('超买警戒 > 70' if tech['rsi_14'] and tech['rsi_14'] > 70 else '中性波动区间 30-70')) if is_zh else ('Oversold (< 30)' if tech['rsi_14'] and tech['rsi_14'] < 30 else ('Overbought (> 70)' if tech['rsi_14'] and tech['rsi_14'] > 70 else 'Neutral Range (30-70)'))}</td></tr>
            <tr><td><strong>{'指数平滑异同平均线' if is_zh else 'MACD / Signal / Hist'}</strong></td><td>{tech['macd']} / {tech['macd_signal']} / {tech['macd_hist']}</td><td>{('红柱向上 · 买方发散' if tech['macd_hist'] and tech['macd_hist'] > 0 else '绿柱向下 · 空方主导') if is_zh else ('Positive Momentum' if tech['macd_hist'] and tech['macd_hist'] > 0 else 'Negative Momentum')}</td></tr>
            <tr><td><strong>{'布林通道 20, 2σ' if is_zh else 'Bollinger Bands (20, 2 std)'}</strong></td><td>{f"下轨: {tech['bollinger_lower']} | 上轨: {tech['bollinger_upper']}" if is_zh else f"Lower: {tech['bollinger_lower']} | Upper: {tech['bollinger_upper']}"}</td><td>{('跌破下轨 · 极限超卖' if tech['bollinger_lower'] and tech['close'] < tech['bollinger_lower'] else ('突破上轨 · 加速拉升' if tech['bollinger_upper'] and tech['close'] > tech['bollinger_upper'] else '通道内震荡')) if is_zh else ('Band Breakdown' if tech['bollinger_lower'] and tech['close'] < tech['bollinger_lower'] else ('Band Breakout' if tech['bollinger_upper'] and tech['close'] > tech['bollinger_upper'] else 'Inside Bands'))}</td></tr>
            <tr><td><strong>{'成交量 · 最新 / 20日均量' if is_zh else 'Volume (Latest / 20 SMA)'}</strong></td><td>{f"{tech['volume_latest']:,} · {'20日均量' if is_zh else '20 SMA'}: {tech['volume_sma_20']:,}" if tech['volume_sma_20'] else f"{tech['volume_latest']:,}"}</td><td>{('明显放量' if tech['volume_sma_20'] and tech['volume_latest'] > tech['volume_sma_20'] else '正常缩量 / 平量') if is_zh else ('Volume Surge' if tech['volume_sma_20'] and tech['volume_latest'] > tech['volume_sma_20'] else 'Normal / Below Avg')}</td></tr>
        </tbody>
    </table>
"""

    html += f"""
    <!-- Bull vs Bear Scenario Box -->
    <h2>{'六、多空情景假设与推演' if is_zh else '6. Scenario Planning: Bull vs. Bear Case'}</h2>
    <table class="scenario-table">
        <tr>
            <td class="scenario-card bull-card">
                <h4>{'乐观情景 · 上行催化' if is_zh else 'Bull Case - Upside Catalysts'}</h4>
                <ul class="checklist">
                    {bull_items_html}
                </ul>
            </td>
            <td class="scenario-card bear-card">
                <h4>{'悲观情景 · 下行风险' if is_zh else 'Bear Case - Downside Risks'}</h4>
                <ul class="checklist">
                    {bear_items_html}
                </ul>
            </td>
        </tr>
    </table>

    <!-- Key Catalysts -->
    <h2>{'七、关键催化事件与跟踪清单' if is_zh else '7. Key Catalysts & Monitoring Checklist'}</h2>
    <ul class="checklist">
        {cat_items_html}
    </ul>

    <!-- Disclaimer -->
    <div class="disclaimer">
        {'免责声明：本投研报告由量化投研模型自动生成，融合量化技术指标与财务报表数据。<br/>仅供学习、研究与交流讨论，不构成任何投资建议、买卖要约或推荐。<br/>金融市场具有高波动性与本金损失风险，投资需独立审慎决策。' if is_zh else 'Disclaimer: This report was generated automatically for educational, research, and informational purposes only<br/>and does not constitute financial, investment, or trading advice.'}
    </div>

</div>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html.strip())
    return html


def patch_xhtml2pdf_word_wrap():
    """Patch xhtml2pdf/reportlab CJK line-breaking so English words never split mid-word across lines."""
    if not HAS_PISA:
        return
    try:
        from xhtml2pdf import reportlab_paragraph as rp
        from reportlab.lib import textsplit as rl_textsplit
        if getattr(rp, "_word_safe_cjk_patched", False):
            return

        def _is_ascii_word_char(ch: str) -> bool:
            return bool(ch) and ord(ch) < 0x3000 and not ch.isspace() and ch not in "([{\"'“‘"

        def _word_safe_cjkFragSplit(frags, maxWidths, calcBounds, encoding="utf8"):
            U = []
            for f in frags:
                text = f.text
                if not isinstance(text, str):
                    text = text.decode(encoding)
                if text:
                    U.extend([rp.cjkU(t, f, encoding) for t in text])
                else:
                    U.append(rp.cjkU(text, f, encoding))

            lines = []
            i = 0
            lineStartPos = 0
            widthUsed = 0
            maxWidth = maxWidths[0]
            nU = len(U)
            while i < nU:
                u = U[i]
                if hasattr(u.frag, "lineBreak"):
                    lines.append(rp.makeCJKParaLine(U[lineStartPos:i], maxWidth - widthUsed, calcBounds))
                    i += 1
                    lineStartPos = i
                    widthUsed = 0
                    try:
                        maxWidth = maxWidths[len(lines)]
                    except IndexError:
                        maxWidth = maxWidths[-1]
                    continue

                w = u.width
                if widthUsed + w > maxWidth + rp._FUZZ and i > lineStartPos:
                    split_idx = i
                    if _is_ascii_word_char(U[split_idx]):
                        bt = split_idx
                        while bt > lineStartPos and _is_ascii_word_char(U[bt - 1]):
                            bt -= 1
                        if bt > lineStartPos:
                            split_idx = bt
                        elif U[split_idx] in rp.ALL_CANNOT_START and split_idx + 1 < nU:
                            split_idx += 1
                    elif U[split_idx] in rp.ALL_CANNOT_START and split_idx + 1 < nU:
                        split_idx += 1

                    # Trim trailing spaces at end of line if splitting at a word boundary
                    end_idx = split_idx
                    while end_idx > lineStartPos and U[end_idx - 1].isspace():
                        end_idx -= 1
                    line_width = sum(x.width for x in U[lineStartPos:end_idx])
                    lines.append(rp.makeCJKParaLine(U[lineStartPos:end_idx], maxWidth - line_width, calcBounds))
                    lineStartPos = split_idx
                    while lineStartPos < nU and U[lineStartPos].isspace():
                        lineStartPos += 1
                    i = lineStartPos
                    widthUsed = 0
                    try:
                        maxWidth = maxWidths[len(lines)]
                    except IndexError:
                        maxWidth = maxWidths[-1]
                    continue

                widthUsed += w
                i += 1

            if lineStartPos < nU:
                line_width = sum(x.width for x in U[lineStartPos:])
                lines.append(rp.makeCJKParaLine(U[lineStartPos:], maxWidth - line_width, calcBounds))

            return rp.ParaLines(kind=1, lines=lines)

        def _word_safe_dumbSplit(word, widths, maxWidths):
            if not isinstance(maxWidths, (list, tuple)):
                maxWidths = [maxWidths]
            lines = []
            i = 0
            lineStartPos = 0
            widthUsed = 0
            maxWidth = maxWidths[0]
            nW = len(word)
            while i < nW:
                w = widths[i]
                if widthUsed + w > maxWidth + rl_textsplit._FUZZ and i > lineStartPos:
                    split_idx = i
                    if _is_ascii_word_char(word[split_idx]):
                        bt = split_idx
                        while bt > lineStartPos and _is_ascii_word_char(word[bt - 1]):
                            bt -= 1
                        if bt > lineStartPos:
                            split_idx = bt
                        elif word[split_idx] in rl_textsplit.ALL_CANNOT_START and split_idx + 1 < nW:
                            split_idx += 1
                    elif word[split_idx] in rl_textsplit.ALL_CANNOT_START and split_idx + 1 < nW:
                        split_idx += 1

                    chunk = word[lineStartPos:split_idx].rstrip()
                    chunk_w = sum(widths[lineStartPos:lineStartPos + len(chunk)])
                    lines.append([maxWidth - chunk_w, chunk])
                    lineStartPos = split_idx
                    while lineStartPos < nW and word[lineStartPos].isspace():
                        lineStartPos += 1
                    i = lineStartPos
                    widthUsed = 0
                    try:
                        maxWidth = maxWidths[len(lines)]
                    except IndexError:
                        maxWidth = maxWidths[-1]
                    continue
                widthUsed += w
                i += 1
            if lineStartPos < nW:
                rem = word[lineStartPos:]
                rem_w = sum(widths[lineStartPos:])
                lines.append([maxWidth - rem_w, rem])
            return lines

        rp.cjkFragSplit = _word_safe_cjkFragSplit
        rl_textsplit.dumbSplit = _word_safe_dumbSplit
        rp._word_safe_cjk_patched = True
    except Exception:
        pass


def transform_html_for_mobile_pdf(html: str, chart_path: str = None, pe_chart_path: str = None) -> str:
    """Transform desktop HTML layout into a mobile-first layout optimized for smartphone PDF viewing with zero orphan slivers and compact gap-free flow."""
    # 1. Replace title with ASCII for xhtml2pdf PDF metadata font compatibility
    html = re.sub(r'<title>.*?</title>', '<title>Equity Research Report</title>', html)

    # 2. Replace Base64 images with relative filenames and set width for mobile PDF
    if chart_path and os.path.exists(chart_path):
        cf = os.path.basename(chart_path)
        html = re.sub(r'src="data:image/png;base64,[^"]+" alt="Technical Analysis Chart"', f'src="{cf}" alt="Technical Analysis Chart" width="320"', html)
    if pe_chart_path and os.path.exists(pe_chart_path):
        pf = os.path.basename(pe_chart_path)
        html = re.sub(r'src="data:image/png;base64,[^"]+" alt="PE Historical Percentile Chart"', f'src="{pf}" alt="PE Historical Percentile Chart" width="355"', html)

    # Replace remaining hardcoded image widths with 355 for perfect fit on 112mm mobile page
    html = re.sub(r'width="760"', 'width="355"', html)

    # 2.5 Transform Header Badges into vertically stacked table for mobile layout
    def badges_to_table(match):
        badges_inner = match.group(1)
        badge_spans = re.findall(r'<span class="badge"[^>]*>.*?</span>', badges_inner)
        rows = "".join([f'<tr><td style="padding: 1.5px 0;">{b}</td></tr>' for b in badge_spans])
        return f'<table style="width: 100%; margin-top: 4px; border: none;">{rows}</table>'

    html = re.sub(r'<div class="badges">(.*?)</div>', badges_to_table, html, flags=re.DOTALL)

    # 3. Transform 4-Card KPI Strip into 2x2 grid for mobile
    kpi_pattern = r'<table class="kpi-table">\s*<tr>\s*(<td class="kpi-card">.*?</td>)\s*(<td class="kpi-card">.*?</td>)\s*(<td class="kpi-card">.*?</td>)\s*(<td class="kpi-card">.*?</td>)\s*</tr>\s*</table>'
    kpi_replacement = r"""<table class="kpi-table" style="width: 100%;">
        <tr>
            \1
            \2
        </tr>
        <tr>
            \3
            \4
        </tr>
    </table>"""
    html = re.sub(kpi_pattern, kpi_replacement, html, flags=re.DOTALL)

    # 4. Transform Scenario table (1x2) into vertically stacked cards
    scen_pattern = r'<table class="scenario-table">\s*<tr>\s*(<td class="scenario-card bull-card">.*?</td>)\s*(<td class="scenario-card bear-card">.*?</td>)\s*</tr>\s*</table>'
    scen_replacement = r"""<table class="scenario-table" style="width: 100%;">
        <tr>
            \1
        </tr>
        <tr><td style="height: 5px;"></td></tr>
        <tr>
            \2
        </tr>
    </table>"""
    html = re.sub(scen_pattern, scen_replacement, html, flags=re.DOTALL)

    # 5. Clean up any leftover Markdown bold asterisks (**...**)
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)

    # 6. Continuous gap-free mobile PDF flow (no forced page breaks):
    html = html.replace('<div class="page-break"></div>', '')
    html = re.sub(r'<div style="page-break-before:\s*always;\s*"></div>', '', html)

    # Compact inline margins for smooth mobile flow with generous section separation
    html = re.sub(r'margin-top:\s*2[0-9]px;\s*margin-bottom:\s*2[0-9]px;', 'margin-top: 14px; margin-bottom: 6px;', html)
    html = re.sub(r'margin-top:\s*2[0-9]px;', 'margin-top: 14px;', html)

    # 7. Extract @font-face rules
    font_faces = re.findall(r'@font-face\s*\{[^}]*\}', html)
    font_face_str = "\n".join(font_faces)

    # 8. Mobile-adapted CSS (112mm x 220mm vertical mobile aspect ratio)
    is_zh_doc = ('lang="zh' in html) or bool(re.search(r'[\u4e00-\u9fff]', html))
    cjk_wrap_rule = "-pdf-word-wrap: CJK;\n        " if is_zh_doc else ""
    mobile_css = """
    @page {
        size: 112mm 220mm;
        margin: 4mm 5mm 4mm 5mm;
    }
    * {
        __CJK_WRAP__word-wrap: break-word;
    }
    body, div, p, span, td, th, li {
        font-family: 'YaHei', 'Microsoft YaHei', 'SegoeUI', sans-serif;
        __CJK_WRAP__word-wrap: break-word;
    }
    body {
        font-size: 9.8pt;
        line-height: 1.42;
        background-color: #ffffff;
        color: #0f172a;
        padding: 0;
        margin: 0;
    }
    .fund-section-title {
        font-size: 9.3pt;
        font-weight: 700;
        color: #1e40af;
    }
    .report-container {
        max-width: 100%;
        width: 100%;
        margin: 0;
        padding: 0;
        border: none;
        background: #ffffff;
    }
    .header-banner {
        background: #0f172a;
        color: #ffffff;
        padding: 8px 11px;
        margin-bottom: 6px;
        border-radius: 6px;
    }
    .header-banner h1 {
        margin: 0 0 2px 0;
        font-size: 13.5pt;
        font-weight: 800;
        color: #ffffff;
    }
    .header-banner .meta-row {
        font-size: 8.0pt;
        color: #cbd5e1;
        line-height: 1.35;
    }
    .badges {
        margin-top: 4px;
    }
    .badge {
        display: inline-block;
        padding: 3.4px 8px 1.5px 8px;
        line-height: 1.0;
        border-radius: 3px;
        font-size: 7.5pt;
        font-weight: 700;
        color: #ffffff;
        vertical-align: middle;
        margin-right: 2px;
        margin-bottom: 2px;
    }
    .company-profile-box {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-left: 4px solid #2563eb;
        border-radius: 6px;
        padding: 6px 8px;
        margin-bottom: 6px;
        page-break-inside: avoid;
    }
    .profile-title {
        font-size: 9.4pt;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 2px;
    }
    .profile-text {
        font-size: 9.0pt;
        color: #334155;
        line-height: 1.38;
    }
    .kpi-table {
        width: 100%;
        margin-bottom: 6px;
        page-break-inside: avoid;
    }
    .kpi-card {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 4px 6px;
        vertical-align: top;
        width: 50% !important;
    }
    .kpi-title {
        font-size: 7.2pt;
        color: #475569;
        font-weight: 700;
        margin-bottom: 1px;
    }
    .kpi-value {
        font-size: 13pt;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 1px;
    }
    .kpi-sub {
        font-size: 7.5pt;
        color: #334155;
        line-height: 1.32;
    }
    .confluence-box {
        background: #eff6ff;
        border-left: 4px solid #2563eb;
        padding: 6px 8px;
        border-radius: 0 6px 6px 0;
        margin-bottom: 6px;
        page-break-inside: avoid;
    }
    .confluence-box h3 {
        margin: 0 0 2px 0;
        font-size: 9.2pt;
        font-weight: 800;
        color: #1e40af;
    }
    .confluence-box p {
        margin: 0;
        font-size: 9.0pt;
        font-weight: 600;
        color: #0f172a;
        line-height: 1.36;
    }
    .thesis-box {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-left: 4px solid #0f172a;
        border-radius: 6px;
        padding: 6px 8px;
        margin-bottom: 6px;
        font-size: 9.0pt;
        line-height: 1.4;
        page-break-inside: avoid;
    }
    .thesis-header {
        font-size: 9.6pt;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 2px;
    }
    .thesis-summary {
        font-size: 8.9pt;
        color: #1e293b;
        line-height: 1.38;
        margin-bottom: 3px;
        padding-bottom: 3px;
        border-bottom: 1px dashed #cbd5e1;
    }
    .thesis-points-title {
        font-size: 8.9pt;
        font-weight: 700;
        color: #475569;
        margin-bottom: 2px;
    }
    .thesis-points {
        margin: 0;
        padding-left: 12px;
        font-size: 8.8pt;
        color: #334155;
        line-height: 1.38;
    }
    .thesis-points li {
        margin-bottom: 2px;
    }
    .trade-setup-card {
        background: #f8fafc;
        border: 1.5px solid #94a3b8;
        border-radius: 6px;
        padding: 4px 6px;
        margin-bottom: 8px;
        page-break-inside: avoid;
    }
    .trade-setup-card h3 {
        margin: 0 0 3px 0;
        font-size: 9.5pt;
        font-weight: 800;
        color: #0f172a;
        border-bottom: 1.5px solid #e2e8f0;
        padding-bottom: 2px;
    }
    .trade-grid-table {
        width: 100%;
        font-size: 7.8pt;
    }
    .trade-grid-table th, .trade-grid-table td {
        padding: 1.8px 3px;
        border: 1px solid #cbd5e1;
        text-align: left;
        line-height: 1.24;
    }
    .trade-grid-table th {
        background: #e2e8f0;
        color: #0f172a;
        font-weight: 700;
        font-size: 8.0pt;
    }
    h1, h2, h3, h4 {
        page-break-after: avoid;
    }
    h2 {
        font-size: 10.2pt;
        font-weight: 800;
        color: #0f172a;
        margin: 16px 0 5px 0;
        padding-top: 4px;
        padding-bottom: 2px;
        border-bottom: 1.5px solid #cbd5e1;
    }
    h3 {
        font-size: 9.0pt;
        font-weight: 800;
        margin: 12px 0 4px 0;
    }
    table.data-table {
        width: 100%;
        margin-bottom: 4px;
        font-size: 7.3pt;
        border: 1px solid #cbd5e1;
    }
    table.data-table th, table.data-table td {
        padding: 1.8px 3px;
        text-align: left;
        border: 1px solid #cbd5e1;
        line-height: 1.24;
    }
    table.data-table th {
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 700;
        font-size: 7.6pt;
    }
    table.data-table tr:nth-child(even) {
        background-color: #f8fafc;
    }
    table.data-table td strong {
        color: #0f172a;
        font-size: 7.5pt;
    }
    .chart-container {
        text-align: center;
        margin: 3px 0;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 2px;
        background: #ffffff;
        page-break-inside: avoid;
    }
    .chart-container img, img {
        page-break-inside: avoid;
    }
    .scenario-table {
        width: 100%;
        margin-bottom: 5px;
        page-break-inside: avoid;
    }
    .scenario-card {
        border-radius: 6px;
        padding: 5px 8px;
        vertical-align: top;
        font-size: 8.8pt;
        line-height: 1.38;
        width: 100% !important;
    }
    .bull-card {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-left: 4px solid #16a34a;
    }
    .bull-card h4 {
        margin: 0 0 2px 0;
        color: #14532d;
        font-size: 9.4pt;
        font-weight: 800;
    }
    .bear-card {
        background: #fef2f2;
        border: 1px solid #fca5a5;
        border-left: 4px solid #dc2626;
    }
    .bear-card h4 {
        margin: 0 0 2px 0;
        color: #7f1d1d;
        font-size: 9.4pt;
        font-weight: 800;
    }
    ul.checklist {
        padding-left: 13px;
        margin: 2px 0;
        font-size: 8.8pt;
        color: #1e293b;
    }
    ul.checklist li {
        margin-bottom: 2px;
        line-height: 1.38;
    }
    .disclaimer {
        font-size: 6.8pt;
        color: #64748b;
        margin-top: 16px;
        padding-top: 8px;
        border-top: 1px solid #cbd5e1;
        text-align: center;
        line-height: 1.35;
    }
    """
    mobile_css = mobile_css.replace("__CJK_WRAP__", cjk_wrap_rule)

    html = re.sub(r'<style>.*?</style>', f'<style>\n{font_face_str}\n{mobile_css}\n</style>', html, flags=re.DOTALL)
    return html

def generate_pdf_report(html_content: str, pdf_path: str, chart_path: str = None, pe_chart_path: str = None) -> bool:
    """Generate mobile-adapted smartphone PDF report from HTML using xhtml2pdf."""
    if not HAS_PISA:
        print("Note: 'xhtml2pdf' not installed. To generate PDF, run with: uv run --with xhtml2pdf ...")
        return False
    try:
        patch_xhtml2pdf_word_wrap()
        mobile_html = transform_html_for_mobile_pdf(html_content, chart_path=chart_path, pe_chart_path=pe_chart_path)

        def link_callback(uri, rel):
            fname = os.path.basename(uri)
            target = os.path.join(FONT_DIR, fname)
            if os.path.exists(target):
                return target
            # Check PE chart before technical chart to prevent partial substring match
            if pe_chart_path and (fname == os.path.basename(pe_chart_path) or "pe" in fname.lower()):
                return pe_chart_path
            if chart_path and (fname == os.path.basename(chart_path) or "chart" in fname.lower()):
                return chart_path
            if os.path.exists(uri):
                return uri
            if "msyhbd" in uri.lower():
                return YAHEI_BOLD
            if "msyh" in uri.lower() or "yahei" in uri.lower():
                return YAHEI_REGULAR
            if "segoeuib" in uri.lower():
                return SEGOE_BOLD
            if "segoe" in uri.lower():
                return SEGOE_REGULAR
            if "simhei" in uri.lower():
                return os.path.join(FONT_DIR, "simhei.ttf")
            return uri

        from contextlib import nullcontext
        try:
            from xhtml2pdf.config.resources import ResourceAccessPolicy, use_policy
            policy_ctx = lambda: use_policy(ResourceAccessPolicy(allow_local_outside_base=True))
        except ImportError:
            policy_ctx = nullcontext

        target_save_path = pdf_path
        try:
            with policy_ctx(), open(target_save_path, "wb") as f:
                pisa_status = pisa.CreatePDF(mobile_html, dest=f, link_callback=link_callback, encoding="utf-8")
        except PermissionError:
            target_save_path = pdf_path.replace(".pdf", " (最新排版).pdf")
            print(f"提示: 原PDF文件正被阅读器占用锁定，新版无空隙PDF已自动保存至: {target_save_path}")
            with policy_ctx(), open(target_save_path, "wb") as f:
                pisa_status = pisa.CreatePDF(mobile_html, dest=f, link_callback=link_callback, encoding="utf-8")
        if pisa_status.err:
            print(f"Warning: PDF generation encountered {pisa_status.err} errors.", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"Error during PDF generation: {e}", file=sys.stderr)
        return False


def fetch_ticker_history(symbol: str, period: str, interval: str = "1d", max_retries: int = 4):
    """Fetch ticker history with automatic retries, backoff, and yf.download fallback."""
    from datetime import timedelta

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    ticker_obj = yf.Ticker(symbol, session=session)
    for attempt in range(max_retries):
        try:
            df = ticker_obj.history(period=period, interval=interval)
            if not df.empty:
                return df, ticker_obj
        except Exception as e:
            print(f"Attempt {attempt + 1} for '{symbol}' encountered error: {e}")
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))

    # Secondary attempt using yf.download with period
    for attempt in range(2):
        try:
            df = yf.download(symbol, period=period, interval=interval, session=session, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty:
                return df, ticker_obj
        except Exception:
            pass
        time.sleep(2)

    # Tertiary attempt using explicit start/end dates
    try:
        days_map = {"3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825, "10y": 3652}
        days = days_map.get(period, 365)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = yf.download(symbol, start=start_date, interval=interval, session=session, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            return df, ticker_obj
    except Exception:
        pass

    return pd.DataFrame(), ticker_obj


def main():
    args = parse_arguments()
    ticker_input = args.ticker.strip()
    ticker_sym = normalize_ticker(ticker_input)
    if ticker_sym != ticker_input.upper():
        print(f"Mapped symbol '{ticker_input}' -> '{ticker_sym}'")

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Fetching live data for {ticker_sym} (Period: {args.period}, Interval: {args.interval})...")
    df, ticker = fetch_ticker_history(ticker_sym, args.period, interval=args.interval)

    if df.empty and ticker_input in ["XAUUSD", "GOLD", "XAU-USD", "XAU/USD"]:
        print("Retrying with GLD (SPDR Gold Shares) as benchmark...")
        ticker_sym = "GLD"
        df, ticker = fetch_ticker_history(ticker_sym, args.period, interval=args.interval)

    if df.empty:
        print(f"No price history found for ticker '{ticker_sym}'. Please verify the symbol.", file=sys.stderr)
        sys.exit(1)

    # Clean index
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Repair missing OHLC rows on China A-Shares (common Yahoo Finance latest-bar NaN glitch) via AkShare
    clean_ashare = ticker_sym.upper().replace(".SS", "").replace(".SZ", "").replace(".BJ", "").strip()
    if ticker_sym.upper().endswith((".SS", ".SZ", ".BJ")) and clean_ashare.isdigit() and len(clean_ashare) == 6 and args.interval == "1d":
        if df["Close"].isna().any():
            try:
                import akshare as ak
                start_dt = (df.index.min() - pd.Timedelta(days=10)).strftime("%Y%m%d")
                ak_df = ak.stock_zh_a_hist(symbol=clean_ashare, period="daily", start_date=start_dt, adjust="qfq")
                if ak_df is not None and not ak_df.empty and "日期" in ak_df.columns:
                    ak_df["日期"] = pd.to_datetime(ak_df["日期"])
                    ak_map = ak_df.set_index("日期")
                    for idx in df[df["Close"].isna()].index:
                        dt_key = pd.Timestamp(idx.date())
                        if dt_key in ak_map.index:
                            row_ak = ak_map.loc[dt_key]
                            df.loc[idx, "Open"] = float(row_ak["开盘"])
                            df.loc[idx, "High"] = float(row_ak["最高"])
                            df.loc[idx, "Low"] = float(row_ak["最低"])
                            df.loc[idx, "Close"] = float(row_ak["收盘"])
                            if pd.isna(df.loc[idx, "Volume"]) or df.loc[idx, "Volume"] == 0:
                                df.loc[idx, "Volume"] = float(row_ak["成交量"]) * 100
            except Exception:
                pass

    # Drop any remaining incomplete rows with NaN Close so rolling indicators never poison to NaN
    df = df.dropna(subset=["Close"]).copy()
    if df.empty:
        print(f"No valid closing price history found for ticker '{ticker_sym}'.", file=sys.stderr)
        sys.exit(1)

    df = calculate_technical_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    # Extract company info
    info = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    # Determine language: match stock name language (English -> en, Chinese -> zh)
    if args.lang == "auto":
        if args.name and args.name.strip():
            is_zh = any("\u4e00" <= ch <= "\u9fff" for ch in args.name.strip())
        elif any("\u4e00" <= ch <= "\u9fff" for ch in ticker_input):
            is_zh = True
        else:
            is_zh = is_chinese_market(ticker_sym, ticker_input, info)
        lang = "zh" if is_zh else "en"
    else:
        lang = args.lang
        is_zh = (lang == "zh")

    if is_zh:
        print("Language Mode: Chinese (zh) [Detected Chinese Market asset or explicit setting]")
    else:
        print("Language Mode: English (en)")

    quote_type = str(info.get("quoteType", "")).upper()
    if ticker_sym in ["GC=F", "SI=F", "CL=F", "HG=F", "NG=F"] or "COMMODITY" in quote_type:
        asset_type = "COMMODITY"
    elif "CURRENCY" in quote_type or ticker_sym.endswith("=X"):
        asset_type = "CURRENCY"
    elif "CRYPTO" in quote_type or ticker_sym.endswith("-USD"):
        asset_type = "CRYPTOCURRENCY"
    elif "ETF" in quote_type:
        asset_type = "ETF"
    else:
        asset_type = "EQUITY"

    # Resolve company name: For Chinese stocks, prefer authentic Chinese name over English/Pinyin
    explicit_name = getattr(args, "name", None)
    if explicit_name and explicit_name.strip():
        company_name = explicit_name.strip()
    elif any("\u4e00" <= ch <= "\u9fff" for ch in ticker_input):
        company_name = ticker_input.strip()
    elif is_zh:
        c_name = fetch_chinese_stock_name(ticker_sym)
        if c_name:
            company_name = c_name
        else:
            company_name = info.get("shortName") or info.get("longName") or ticker_input
    else:
        company_name = info.get("shortName") or info.get("longName") or (
            "Gold Spot / Futures (USD)" if ticker_sym in ["GC=F", "XAUUSD=X"] else ticker_input
        )
    company_name = str(company_name).strip()

    sector_raw = info.get("sector", asset_type)
    industry_raw = info.get("industry", asset_type)
    if is_zh:
        sector = SECTOR_MAP_ZH.get(sector_raw, sector_raw)
        industry = INDUSTRY_MAP_ZH.get(industry_raw, "")
    else:
        sector = sector_raw
        industry = industry_raw
    currency = info.get("currency", "USD")
    curr_sym = "¥" if currency in ["CNY", "CNH"] else ("HK$" if currency == "HKD" else "$")

    close_val = round(float(latest["Close"]), 2)
    high_52 = round(float(df["High"].max()), 2)
    low_52 = round(float(df["Low"].min()), 2)
    drawdown_52w = round((close_val - high_52) / high_52 * 100, 2)
    rebound_52w = round((close_val - low_52) / low_52 * 100, 2)

    # Technicals dict
    nearest_supp, nearest_res = detect_support_resistance(df)
    technicals = {
        "close": close_val,
        "change_pct": round(float((latest["Close"] - prev["Close"]) / prev["Close"] * 100), 2),
        "sma_20": round(float(latest["SMA_20"]), 2) if pd.notna(latest["SMA_20"]) else None,
        "sma_50": round(float(latest["SMA_50"]), 2) if pd.notna(latest["SMA_50"]) else None,
        "sma_200": round(float(latest["SMA_200"]), 2) if pd.notna(latest["SMA_200"]) else None,
        "ema_9": round(float(latest["EMA_9"]), 2) if pd.notna(latest["EMA_9"]) else None,
        "ema_21": round(float(latest["EMA_21"]), 2) if pd.notna(latest["EMA_21"]) else None,
        "rsi_14": round(float(latest["RSI_14"]), 2) if pd.notna(latest["RSI_14"]) else None,
        "macd": round(float(latest["MACD"]), 2) if pd.notna(latest["MACD"]) else None,
        "macd_signal": round(float(latest["MACD_Signal"]), 2) if pd.notna(latest["MACD_Signal"]) else None,
        "macd_hist": round(float(latest["MACD_Hist"]), 2) if pd.notna(latest["MACD_Hist"]) else None,
        "bollinger_upper": round(float(latest["BB_Upper"]), 2) if pd.notna(latest["BB_Upper"]) else None,
        "bollinger_lower": round(float(latest["BB_Lower"]), 2) if pd.notna(latest["BB_Lower"]) else None,
        "atr_14": round(float(latest["ATR_14"]), 2) if pd.notna(latest["ATR_14"]) else None,
        "volume_latest": int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0,
        "volume_sma_20": int(latest["Volume_SMA_20"]) if pd.notna(latest["Volume_SMA_20"]) else None,
        "nearest_support": nearest_supp,
        "nearest_resistance": nearest_res,
        "52_week_high": high_52,
        "52_week_low": low_52,
        "drawdown_from_52w_high": drawdown_52w,
        "rebound_from_52w_low": rebound_52w,
    }

    # Fundamentals dict
    mkt_cap = info.get("marketCap")
    fcf = info.get("freeCashflow")
    fcf_yield = round((fcf / mkt_cap * 100), 2) if (fcf and mkt_cap and mkt_cap > 0) else None

    # Extract 3-year historical performance (comparison with past 2 years)
    hist_perf = []
    if asset_type == "EQUITY":
        try:
            hist_perf = extract_historical_performance(ticker)
        except Exception as e:
            print(f"Warning extracting historical performance: {e}")

    # Calculate Historical PE Percentile
    pe_stats = calculate_pe_percentile(ticker_sym, info, df)
    if pe_stats.get("data_source") and "EastMoney" in str(pe_stats.get("data_source")) and pe_stats.get("pe_ttm"):
        trailing_pe = pe_stats.get("pe_ttm")
    else:
        trailing_pe = info.get("trailingPE") or pe_stats.get("pe_ttm")

    fundamentals = {
        "market_cap": mkt_cap,
        "enterprise_value": info.get("enterpriseValue"),
        "trailing_pe": trailing_pe,
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio"),
        "pe_stats": pe_stats,
        "pe_3y_percentile": pe_stats.get("pe_3y_percentile"),
        "pe_5y_percentile": pe_stats.get("pe_5y_percentile"),
        "pe_10y_percentile": pe_stats.get("pe_10y_percentile"),
        "pe_3y_min": pe_stats.get("pe_3y_min"),
        "pe_3y_max": pe_stats.get("pe_3y_max"),
        "pe_3y_median": pe_stats.get("pe_3y_median"),
        "pe_5y_min": pe_stats.get("pe_5y_min"),
        "pe_5y_max": pe_stats.get("pe_5y_max"),
        "pe_5y_median": pe_stats.get("pe_5y_median"),
        "pe_10y_min": pe_stats.get("pe_10y_min"),
        "pe_10y_max": pe_stats.get("pe_10y_max"),
        "pe_10y_median": pe_stats.get("pe_10y_median"),
        "valuation_zone_zh": pe_stats.get("valuation_zone_zh"),
        "valuation_zone_en": pe_stats.get("valuation_zone_en"),
        "pe_data_source": pe_stats.get("data_source"),
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "price_to_book": info.get("priceToBook"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "gross_margins": info.get("grossMargins"),
        "operating_margins": info.get("operatingMargins"),
        "profit_margins": info.get("profitMargins"),
        "return_on_equity": info.get("returnOnEquity"),
        "return_on_assets": info.get("returnOnAssets"),
        "total_debt": info.get("totalDebt"),
        "total_cash": info.get("totalCash"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "free_cash_flow": fcf,
        "fcf_yield": fcf_yield,
        "operating_cash_flow": info.get("operatingCashflow"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "historical_performance": hist_perf,
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "analyst_target_mean": info.get("targetMeanPrice"),
        "recommendation_key": info.get("recommendationKey"),
    }

    confluence = evaluate_confluence(technicals, fundamentals, asset_type=asset_type, lang=lang)
    trade_setup = calculate_trade_setup(technicals, confluence, asset_type=asset_type, currency=currency, lang=lang)

    # Dedicated subfolder for this ticker/analysis
    if args.subfolder:
        subfolder_name = args.subfolder
    elif is_zh and company_name and company_name != ticker_input:
        clean_name = re.sub(r'[\\/*?:"<>|]', '', company_name).strip()
        subfolder_name = f"{clean_name} {ticker_sym}"
    else:
        subfolder_name = ticker_input.replace("/", "_")
    target_dir = os.path.join(args.output_dir, subfolder_name)
    os.makedirs(target_dir, exist_ok=True)

    safe_name = ticker_sym.lower().replace("=", "_").replace("/", "_").replace("^", "")
    chart_filename = f"{safe_name}_chart.png"
    chart_path = os.path.join(target_dir, chart_filename)
    pe_chart_filename = f"{safe_name}_pe_percentile_chart.png"
    pe_chart_path = os.path.join(target_dir, pe_chart_filename)
    json_filename = f"{safe_name}_data.json"
    json_path = os.path.join(target_dir, json_filename)
    # Resolve report filename base with stock name (e.g. "新亚强" -> "新亚强.html")
    report_base = getattr(args, "report_name", None)
    if report_base and report_base.strip():
        clean_stock_name = re.sub(r'[\\/*?:"<>|]', '', report_base).strip().strip(".")
    elif company_name and company_name.strip():
        clean_stock_name = re.sub(r'[\\/*?:"<>|]', '', company_name).strip().strip(".")
    else:
        clean_stock_name = safe_name

    if not clean_stock_name:
        clean_stock_name = safe_name

    report_md_filename = f"{clean_stock_name}.md"
    report_html_filename = f"{clean_stock_name}.html"
    report_pdf_filename = f"{clean_stock_name}.pdf"

    report_md_path = os.path.join(target_dir, report_md_filename)
    report_html_path = os.path.join(target_dir, report_html_filename)
    report_pdf_path = os.path.join(target_dir, report_pdf_filename)

    tf_info = get_timeframe_info(df, args.interval, lang=lang)

    pe_chart_ok = False
    if asset_type == "EQUITY" and fundamentals.get("trailing_pe"):
        print(f"Generating 10-year PE percentile chart to: {pe_chart_path}...")
        pe_chart_ok = generate_pe_percentile_chart(ticker_sym, company_name, pe_chart_path, info=info, df_history=df, lang=lang)

    business_summary = fetch_company_description(ticker_sym, info, lang=lang)

    metadata = {
        "ticker": ticker_sym,
        "company_name": company_name,
        "business_summary": business_summary,
        "sector": sector,
        "industry": industry,
        "asset_type": asset_type,
        "currency": currency,
        "language": lang,
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "period": args.period,
        "interval": args.interval,
        "timeframe_code": tf_info["code"],
        "timeframe_name": tf_info["full_name"],
        "timeframe_bar": tf_info["bar_desc"],
        "output_dir": target_dir,
        "chart_image": chart_path,
        "pe_chart_image": pe_chart_path if pe_chart_ok else None,
        "report_md": report_md_path,
        "report_html": report_html_path,
        "report_pdf": report_pdf_path,

        "report_name": clean_stock_name,
    }

    narratives = generate_analytical_narratives(metadata, technicals, fundamentals, confluence, trade_setup, lang=lang)

    print(f"Generating high-resolution chart to: {chart_path}...")
    generate_chart(df, ticker_sym, company_name, chart_path, currency=currency, lang=lang, interval=args.interval, period=args.period)

    output_data = {
        "metadata": metadata,
        "trade_setup": trade_setup,
        "technicals": technicals,
        "fundamentals": fundamentals,
        "confluence": confluence,
        "narratives": narratives,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, default=str)

    print("Generating comprehensive Markdown report...")
    generate_markdown_report(output_data, report_md_path, lang=lang)

    print("Generating institutional HTML report...")
    html_content = generate_html_report(output_data, report_html_path, chart_path, lang=lang)

    print("Generating printable PDF report...")
    pdf_ok = generate_pdf_report(html_content, report_pdf_path, chart_path=chart_path, pe_chart_path=pe_chart_path if pe_chart_ok else None)



    # Note: Duplicate report.html / report.md / report.pdf generation disabled per user request.
    # Output reports are strictly named after the asset (e.g. 新亚强.html, 新亚强.pdf, 新亚强.md).

    print("\n" + "=" * 65)
    if is_zh:
        print(f"投研全维分析报告: {company_name} {ticker_sym}")
        print("=" * 65)
        print(f"时间级别:   {tf_info['full_name']} (历史跨度: {format_period_zh(args.period)}) | 结算货币: {format_currency_zh(currency)}")
        print(f"最新现价:   {curr_sym}{technicals['close']} ({technicals['change_pct']:+.2f}%)")
        print(f"战术操作:   {trade_setup['bias']} (布局区间: {trade_setup['entry_zone']} | 止损: {trade_setup['stop_loss']})")
        print(f"目标价位:   第一目标: {trade_setup['target_1']} | 第二目标: {trade_setup['target_2']} (盈亏比: {trade_setup['rr_ratio']})")
        print(f"共振评级:   {confluence['confluence_verdict']}")
        pe_pct_10y_disp = fundamentals.get("pe_10y_percentile") if fundamentals.get("pe_10y_percentile") is not None else fundamentals.get("pe_3y_percentile", "N/A")
        pe_print_str = f"{fundamentals['trailing_pe']:.1f}倍 (10年分位: {pe_pct_10y_disp}%)" if fundamentals.get("trailing_pe") else "N/A"
        print(f"估值分位:   PE (TTM): {pe_print_str} | 水位: {fundamentals.get('valuation_zone_zh', 'N/A')}")
        print("-" * 65)
        print(f"输出目录:   {target_dir}")
        print(f"技术图表:   {chart_path}")
        if pe_chart_ok:
            print(f"估值图表:   {pe_chart_path}")
        print(f"量化数据:   {json_path}")
        print(f"Markdown:   {report_md_path}")
        print(f"HTML报告:   {report_html_path}")
        if pdf_ok:
            print(f"PDF报告:    {report_pdf_path}")
    else:
        print(f"EQUITY RESEARCH REPORT: {ticker_sym} ({company_name})")
        print("=" * 65)
        print(f"Timeframe:  {tf_info['full_name']} (Period: {args.period})")
        print(f"Price:      {curr_sym}{technicals['close']} ({technicals['change_pct']:+.2f}%)")
        print(f"Tactical:   {trade_setup['bias']} (Entry: {trade_setup['entry_zone']} | Stop: {trade_setup['stop_loss']})")
        print(f"Targets:    Target 1: {trade_setup['target_1']} | Target 2: {trade_setup['target_2']} (R:R: {trade_setup['rr_ratio']})")
        print(f"Confluence: {confluence['confluence_verdict']}")
        pe_pct_10y_disp = fundamentals.get("pe_10y_percentile") if fundamentals.get("pe_10y_percentile") is not None else fundamentals.get("pe_3y_percentile", "N/A")
        pe_print_str = f"{fundamentals['trailing_pe']:.1f}x (10Y Percentile: {pe_pct_10y_disp}%)" if fundamentals.get("trailing_pe") else "N/A"
        print(f"Valuation:  PE (TTM): {pe_print_str} | Zone: {fundamentals.get('valuation_zone_en', 'N/A')}")
        print("-" * 65)
        print(f"Output:     {target_dir}")
        print(f"Chart:      {chart_path}")
        if pe_chart_ok:
            print(f"PE Chart:   {pe_chart_path}")
        print(f"Data JSON:  {json_path}")
        print(f"Report MD:  {report_md_path}")
        print(f"Report HTML:{report_html_path}")
        if pdf_ok:
            print(f"Report PDF: {report_pdf_path}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
