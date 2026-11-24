#!/usr/bin/env python3
"""
Multi-Stock Horizontal Comparison & Configuration Priority Report Generator
Generates standalone Markdown (.md), Desktop HTML (.html), Print/Mobile PDF (.pdf),
and structured JSON deliverables in a dedicated folder under stock_analysis_output/.
"""

import argparse
import base64
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

try:
    from xhtml2pdf import pisa
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_PISA = True
except ImportError:
    HAS_PISA = False

SKILL_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
FONT_DIR = SKILL_FONT_DIR if os.path.exists(SKILL_FONT_DIR) else "C:/Windows/Fonts"
YAHEI_REGULAR = os.path.join(FONT_DIR, "msyh.ttc") if os.path.exists(os.path.join(FONT_DIR, "msyh.ttc")) else "C:/Windows/Fonts/msyh.ttc"
YAHEI_BOLD = os.path.join(FONT_DIR, "msyhbd.ttc") if os.path.exists(os.path.join(FONT_DIR, "msyhbd.ttc")) else "C:/Windows/Fonts/msyhbd.ttc"
SEGOE_REGULAR = os.path.join(FONT_DIR, "segoeui.ttf") if os.path.exists(os.path.join(FONT_DIR, "segoeui.ttf")) else "C:/Windows/Fonts/segoeui.ttf"
SEGOE_BOLD = os.path.join(FONT_DIR, "segoeuib.ttf") if os.path.exists(os.path.join(FONT_DIR, "segoeuib.ttf")) else "C:/Windows/Fonts/segoeuib.ttf"


def register_cjk_fonts():
    if not HAS_PISA:
        return
    try:
        if os.path.exists(YAHEI_REGULAR):
            pdfmetrics.registerFont(TTFont("YaHei", YAHEI_REGULAR, subfontIndex=0))
        if os.path.exists(YAHEI_BOLD):
            pdfmetrics.registerFont(TTFont("YaHei-Bold", YAHEI_BOLD, subfontIndex=0))
        if os.path.exists(SEGOE_REGULAR):
            pdfmetrics.registerFont(TTFont("SegoeUI", SEGOE_REGULAR))
        if os.path.exists(SEGOE_BOLD):
            pdfmetrics.registerFont(TTFont("SegoeUI-Bold", SEGOE_BOLD))
    except Exception:
        pass
    try:
        from xhtml2pdf import reportlab_paragraph as rp
        from reportlab.lib import textsplit as rl_textsplit
        if not getattr(rp, "_word_safe_cjk_patched", False):
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


def parse_score(score_str: str) -> float:
    if not score_str:
        return 0.0
    m = re.match(r"(\d+(?:\.\d+)?)\s*/\s*(\d+)", str(score_str))
    if m:
        return float(m.group(1))
    return 0.0


def parse_rr(rr_str: str) -> float:
    if not rr_str:
        return 0.0
    m = re.search(r"1\s*:\s*(\d+(?:\.\d+)?)", str(rr_str))
    if m:
        return float(m.group(1))
    return 0.0


def normalize_div_yield(fund: dict, tech: dict) -> float:
    """Return accurate dividend yield in percentage points."""
    dy = fund.get("dividend_yield")
    if dy is None:
        return 0.0
    try:
        return float(dy)
    except (ValueError, TypeError):
        return 0.0


def get_curr_sym(item_or_curr) -> str:
    if isinstance(item_or_curr, dict):
        curr = item_or_curr.get("metadata", {}).get("currency", "USD")
    else:
        curr = str(item_or_curr or "USD")
    c = curr.upper()
    if c in ("CNY", "CNH"):
        return "¥"
    if c == "HKD":
        return "HK$"
    return "$"


def fmt_large_amt(val, currency: str = "CNY", is_zh: bool = True) -> str:
    if val is None:
        return "暂无" if is_zh else "N/A"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return "暂无" if is_zh else "N/A"
    c = str(currency or "CNY").upper()
    neg = v < 0
    abs_v = abs(v)
    sign = "-" if neg else ""
    if is_zh:
        if c in ("CNY", "CNH"):
            return f"{sign}¥{abs_v / 1e8:.2f}亿"
        if c == "HKD":
            return f"{sign}HK${abs_v / 1e8:.2f}亿"
        return f"{sign}${abs_v / 1e8:.2f}亿"
    sym = "¥" if c in ("CNY", "CNH") else ("HK$" if c == "HKD" else "$")
    return f"{sign}{sym}{abs_v / 1e9:.2f}B"


def get_currency_label_zh(items: list, is_zh: bool = True) -> str:
    currs = {str(it.get("metadata", {}).get("currency", "CNY")).upper() for it in items}
    if not is_zh:
        if len(currs) == 1:
            return next(iter(currs))
        return "Multi-Currency"
    if currs.issubset({"CNY", "CNH"}):
        return "人民币"
    if currs == {"USD"}:
        return "美元"
    if currs == {"HKD"}:
        return "港币"
    return "多币种"


def localize_tech_verdict(tv: str, is_zh: bool = True) -> str:
    if not is_zh:
        rev_map = {
            "多头强势上行": "Bullish Uptrend",
            "中性震荡整理": "Neutral / Consolidation",
            "弱势空头下行": "Bearish Downtrend",
        }
        return rev_map.get(tv, tv or "N/A")
    mapping = {
        "Bullish Uptrend": "多头强势上行",
        "Neutral / Consolidation": "中性震荡整理",
        "Bearish Downtrend": "弱势空头下行",
    }
    return mapping.get(tv, tv or "暂无")


def localize_confluence_verdict(cv: str, is_zh: bool = True) -> str:
    s = str(cv or "")
    if not is_zh:
        if s.startswith("A类"):
            return "Category A: High-Probability Compounder"
        if s.startswith("B类"):
            return "Category B: Speculative / Momentum Squeeze"
        if s.startswith("C类"):
            return "Category C: Potential Value Opportunity"
        if s.startswith("D类"):
            return "Category D: Value Trap / Capitulation"
        return s
    if s.startswith("Category A"):
        return "A类：高确定性复利标的 · 多头共振"
    if s.startswith("Category B"):
        return "B类：短期投机/情绪波段"
    if s.startswith("Category C"):
        return "C类：左侧价值观察区 · 底部蓄势"
    if s.startswith("Category D"):
        return "D类：趋势与估值博弈 · 审慎观望"
    return s


def localize_bias(bias: str, is_zh: bool = True) -> str:
    if not is_zh:
        rev_map = {
            "积极做多 / 逢回调布局": "Bullish / Buy on Pullbacks",
            "区间震荡 / 逢低蓄势": "Range-Bound / Neutral Accumulation",
            "防御观望 / 破位规避": "Defensive / Wait for Base Formation",
        }
        return rev_map.get(bias, bias or "N/A")
    mapping = {
        "Bullish / Buy on Pullbacks": "积极做多 / 逢回调布局",
        "Range-Bound / Neutral Accumulation": "区间震荡 / 逢低蓄势",
        "Defensive / Wait for Base Formation": "防御观望 / 破位规避",
    }
    return mapping.get(bias, bias or "暂无")


def localize_sector(sector: str, ticker: str = "", is_zh: bool = True) -> str:
    tk_u = str(ticker or "").upper()
    if not is_zh:
        if tk_u == "NVDA":
            return "Technology / AI Semiconductors"
        if tk_u in ("GOOGL", "GOOG"):
            return "Communication Services / Internet & Cloud"
        if tk_u == "SPCX":
            return "Industrials / Aerospace & Defense"
        return sector or "Core Sector"
    if tk_u == "NVDA":
        return "信息技术 / AI算力与半导体"
    if tk_u in ("GOOGL", "GOOG"):
        return "通信服务 / 互联网与AI云"
    if tk_u == "SPCX":
        return "工业制造 / 商业航天与国防"
    s_map = {
        "Technology": "信息技术 / AI算力与半导体",
        "Communication Services": "通信服务 / 互联网与AI云",
        "Industrials": "工业制造 / 商业航天与国防",
        "Basic Materials": "基础材料 / 精细化工",
        "Consumer Cyclical": "非必需消费品 / 汽车家电",
        "Consumer Defensive": "必需消费品 / 食品饮料",
        "Energy": "能源 / 石油煤炭",
        "Financial Services": "金融服务 / 银行非银",
        "Healthcare": "医疗健康 / 医药生物",
        "Real Estate": "房地产",
        "Utilities": "公用事业 / 电力环保",
    }
    return s_map.get(sector, sector or "核心主营赛道")


def extract_moat_and_track(item: dict, is_zh: bool = True) -> tuple:
    meta = item.get("metadata", {})
    tk = str(meta.get("ticker", "")).upper()
    name = meta.get("company_name", "")
    name_u = name.upper()
    biz = meta.get("business_summary", "")
    sector = meta.get("sector", "Core Sector" if not is_zh else "核心主营赛道")

    if not is_zh:
        if tk == "NVDA" or "NVIDIA" in name_u:
            return ("AI Compute & Accelerated Computing Platform", "CUDA Ecosystem Monopoly + Data Center GPU Dominance")
        if tk in ("GOOGL", "GOOG") or "ALPHABET" in name_u or "GOOGLE" in name_u:
            return ("Global Search & Digital Ads + Google Cloud & AI", "Search Monopoly + Custom TPU & Gemini Full-Stack AI")
        if tk == "SPCX" or "SPACE EXPLORATION" in name_u or "SPACEX" in name_u:
            return ("Commercial Launch + Starlink + xAI", "Reusable Rockets (Falcon/Starship) + LEO Satellite Moat")
        loc_sec = localize_sector(sector, tk, is_zh=False)
        short_biz = biz.split(".")[0][:48] if biz else f"{loc_sec} Competitive Moat"
        return (loc_sec, short_biz)

    if tk == "NVDA" or "NVIDIA" in name_u:
        return ("AI算力芯片与全栈加速计算平台", "CUDA生态垄断 + 数据中心GPU绝对统治力")
    if tk in ("GOOGL", "GOOG") or "ALPHABET" in name_u or "GOOGLE" in name_u:
        return ("全球搜索与数字广告 + Google Cloud云与AI", "搜索生态垄断 + 自研TPU与Gemini全栈AI壁垒")
    if tk == "SPCX" or "SPACE EXPLORATION" in name_u or "SPACEX" in name_u:
        return ("商业航天发射 + Starlink星链通信 + xAI/Grok", "可回收火箭(Falcon/Starship)垄断 + 全球低轨卫星星座壁垒")

    if "旷达" in name or "内饰" in biz or "座舱" in biz:
        return ("汽车内饰/座舱系统 + 射频滤波器", "整车厂一级配套 + 株洲国资战略入主")
    if "新亚强" in name or "有机硅" in biz or "硅" in biz:
        return ("有机硅精细化学品", "功能性助剂单项冠军 + 全产业链配套")
    if "航发" in name or "航空发动机" in biz or "燃气轮机" in biz:
        return ("军民用大中型航空发动机/燃气轮机", "国家战略重型动力唯一总装基地")

    loc_sec = localize_sector(sector, tk, is_zh=True)
    has_zh = any("\u4e00" <= ch <= "\u9fff" for ch in biz)
    short_biz = biz.split("。")[0][:28] if (biz and has_zh) else f"{loc_sec}核心龙头壁垒"
    return (loc_sec, short_biz)


def compute_Composite_Rank_Score(item: dict) -> float:
    """Compute composite ranking score to order stocks from top priority to lowest."""
    conf = item.get("confluence", {})
    tech = item.get("technicals", {})
    fund = item.get("fundamentals", {})
    trade = item.get("trade_setup", {})

    t_score = parse_score(conf.get("technical_score", "0/5"))
    f_score = parse_score(conf.get("fundamental_score", "0/5"))
    rr = min(parse_rr(trade.get("rr_ratio", "1 : 1.0")), 3.5)

    hist = fund.get("historical_performance", [])
    lat = hist[-1] if hist else {}
    rev_yoy = lat.get("revenue_yoy") or 0.0
    ni_yoy = lat.get("net_income_yoy") or 0.0
    lat_ni = lat.get("net_income")

    growth_bonus = 0.0
    if rev_yoy > 0 and ni_yoy > 0:
        growth_bonus += 2.5
    elif rev_yoy > 0 or ni_yoy > 0:
        growth_bonus += 1.0
    if lat_ni is not None and lat_ni < 0:
        growth_bonus -= 2.0

    pe = fund.get("trailing_pe")
    pe_10y = fund.get("pe_10y_percentile")
    val_bonus = 0.0
    if pe is not None and 0 < float(pe) < 60.0 and pe_10y is not None:
        val_bonus = max(0.0, (80.0 - float(pe_10y)) / 40.0)

    div_y = normalize_div_yield(fund, tech)
    debt_free_bonus = 1.0 if (fund.get("total_debt") == 0 or (fund.get("debt_to_equity") or 999) < 5.0) else 0.0

    return (t_score * 1.6) + (f_score * 1.2) + (rr * 1.2) + growth_bonus + val_bonus + (min(div_y, 5.0) * 0.25) + debt_free_bonus


def build_key_tech_observation(item: dict, is_zh: bool = True) -> str:
    c = get_curr_sym(item)
    tech = item.get("technicals", {})
    close = tech.get("close", 0)
    chg = tech.get("change_pct", 0)
    sma20 = tech.get("sma_20")
    sma50 = tech.get("sma_50")
    sma200 = tech.get("sma_200")
    ema9 = tech.get("ema_9")
    supp = tech.get("nearest_support")
    res = tech.get("nearest_resistance")
    vol = tech.get("volume_latest") or 0
    vol20 = tech.get("volume_sma_20") or 0
    macd_h = tech.get("macd_hist") or 0

    vol_ratio_pct = ((vol / vol20) - 1.0) * 100.0 if vol20 > 0 else 0.0
    sma20_txt = f"{c}{sma20:.2f}" if sma20 is not None else "N/A"
    sma50_txt = f"{c}{sma50:.2f}" if sma50 is not None else "N/A"
    supp_txt = f"{c}{supp:.2f}" if supp is not None else "N/A"
    res_txt = f"{c}{res:.2f}" if res is not None else "N/A"

    if not is_zh:
        if sma20 and sma50 and close > sma20 and close > sma50:
            up_tgt = f"200 SMA (`{c}{sma200:.2f}`)" if sma200 and close < sma200 else f"resistance (`{res_txt}`)"
            return f"Above 20 SMA (`{sma20_txt}`) & 50 SMA (`{sma50_txt}`), testing {up_tgt}"
        elif ema9 and close >= ema9:
            upper_ref = f"20 SMA (`{sma20_txt}`) & 200 SMA (`{c}{sma200:.2f}`)" if sma200 is not None else f"20 SMA (`{sma20_txt}`) & 50 SMA (`{sma50_txt}`)"
            return f"Reclaiming EMA9 (`{c}{ema9:.2f}`); watch `{supp_txt}` support vs {upper_ref}"
        else:
            if chg < -2.0 and vol_ratio_pct > 10:
                lo_ma = min(sma20 or close, sma50 or close)
                hi_ma = max(sma20 or close, sma50 or close)
                return f"Rejected near `{c}{lo_ma:.2f} - {c}{hi_ma:.2f}` on heavy volume (`{chg:+.2f}%`); watch `{supp_txt}` support"
            return f"Below 20/50 SMA (`{sma20_txt}` / `{sma50_txt}`); monitor `{supp_txt}` support hold"

    if sma20 and sma50 and close > sma20 and close > sma50:
        vol_txt = f"放量 `+{vol_ratio_pct:.1f}%` " if vol_ratio_pct > 15 else "稳步"
        macd_txt = "，MACD翻红" if macd_h > 0 else ""
        up_tgt = f"200日线 (`{c}{sma200:.2f}`)" if sma200 and close < sma200 else f"阻力位 (`{res_txt}`)"
        return f"{vol_txt}突破 20日线 (`{sma20_txt}`) 与 50日线 (`{sma50_txt}`){macd_txt}，上方挑战 {up_tgt}"
    elif ema9 and close >= ema9:
        vol_txt = "缩量反弹" if vol_ratio_pct < 0 else "放量反弹"
        upper_ref = f"20日线 (`{sma20_txt}`) 与 200日线 (`{c}{sma200:.2f}`)" if sma200 is not None else f"20日线 (`{sma20_txt}`) 与 50日线 (`{sma50_txt}`)"
        return f"{vol_txt}站上 EMA9 (`{c}{ema9:.2f}`)，紧盯 `{supp_txt}` 支撑承接及上方 {upper_ref} 阻力"
    else:
        if chg < -2.0 and vol_ratio_pct > 10:
            lo_ma = min(sma20 or close, sma50 or close)
            hi_ma = max(sma20 or close, sma50 or close)
            return f"受制于 `{c}{lo_ma:.2f} - {c}{hi_ma:.2f}`（50/20日线压制带）放量回落 `{chg:+.2f}%`，重点观察 `{supp_txt}` 前低支撑防守"
        return f"均线呈空头压制（20日线 `{sma20_txt}` / 50日线 `{sma50_txt}`），观察下方 `{supp_txt}` 支撑承接与放量企稳信号"


def should_align_ttm(items: list) -> bool:
    """Return True when compared stocks have heterogeneous latest fiscal years and TTM data is available."""
    fy_set = set()
    for it in items:
        hp = it.get("fundamentals", {}).get("historical_performance", [])
        if hp and hp[-1].get("year"):
            fy_set.add(str(hp[-1]["year"]))
    if len(fy_set) <= 1:
        return False
    return all(it.get("fundamentals", {}).get("total_revenue_ttm") is not None for it in items)


def build_priority_recommendation(item: dict, rank_idx: int, total_count: int, is_zh: bool = True, align_ttm: bool = False) -> dict:
    meta = item.get("metadata", {})
    curr = meta.get("currency", "USD")
    c = get_curr_sym(curr)
    name = meta.get("company_name", "")
    ticker = meta.get("ticker", "")
    tech = item.get("technicals", {})
    fund = item.get("fundamentals", {})
    trade = item.get("trade_setup", {})
    hist = fund.get("historical_performance", [])
    lat = hist[-1] if hist else {}
    lat_year = "TTM" if align_ttm else lat.get("year", "最新")

    close = tech.get("close", 0)
    sma20 = tech.get("sma_20")
    sma50 = tech.get("sma_50")
    rsi = tech.get("rsi_14", 50)
    macd_h = tech.get("macd_hist", 0)
    rr = trade.get("rr_ratio", "N/A")

    if align_ttm:
        rev = fund.get("total_revenue_ttm")
        ni = fund.get("net_income_ttm")
        rev_yoy = (fund.get("revenue_growth") * 100.0) if fund.get("revenue_growth") is not None else lat.get("revenue_yoy")
        ni_yoy = (fund.get("earnings_growth") * 100.0) if fund.get("earnings_growth") is not None else lat.get("net_income_yoy")
        gm = (fund.get("gross_margins") * 100.0) if fund.get("gross_margins") is not None else lat.get("gross_margin")
        gm_chg = lat.get("gross_margin_change")
        ocf_raw = fund.get("operating_cash_flow") if fund.get("operating_cash_flow") is not None else lat.get("ocf")
    else:
        rev = lat.get("revenue")
        ni = lat.get("net_income")
        rev_yoy = lat.get("revenue_yoy")
        ni_yoy = lat.get("net_income_yoy")
        gm = lat.get("gross_margin") if lat.get("gross_margin") is not None else ((fund.get("gross_margins") or 0) * 100.0)
        gm_chg = lat.get("gross_margin_change")
        ocf_raw = lat.get("ocf") if lat.get("ocf") is not None else fund.get("operating_cash_flow")
    ocf_str = fmt_large_amt(ocf_raw, curr, is_zh=is_zh)

    pe = fund.get("trailing_pe")
    f_pe = fund.get("forward_pe")
    ps = fund.get("price_to_sales")
    pe_3y = fund.get("pe_3y_percentile")
    pe_5y = fund.get("pe_5y_percentile")
    pe_10y = fund.get("pe_10y_percentile")
    if pe_5y is None:
        pe_5y = pe_3y if pe_3y is not None else pe_10y
    fcf_y = fund.get("fcf_yield")
    div_y = normalize_div_yield(fund, tech)
    cash_raw = fund.get("total_cash") or 0
    cash_str = fmt_large_amt(cash_raw, curr, is_zh=is_zh)
    total_debt = fund.get("total_debt") or 0
    roe_pct = (fund.get("return_on_equity") or 0) * 100.0

    gm_str = f"{gm:.1f}%" if gm is not None else "N/A"
    gm_c_str = f"{gm_chg:+.1f}%" if gm_chg is not None else ("持平" if is_zh else "Flat")
    pe_str = f"{pe:.1f}倍" if (is_zh and pe is not None) else (f"{pe:.1f}x" if pe is not None else "N/A")
    p3_str = f"{pe_3y:.1f}%" if pe_3y is not None else "N/A"
    p5_str = f"{pe_5y:.1f}%" if pe_5y is not None else "N/A"
    p10_str = f"{pe_10y:.1f}%" if pe_10y is not None else "N/A"

    if not is_zh:
        if rank_idx == 0:
            role_title = f"Top Priority (Best Fundamental & Valuation Margin of Safety): {name}"
            bullet_label = "Key Advantages"
            fin_part = (
                f"Delivered {lat_year} **revenue ({rev_yoy:+.1f}% to {fmt_large_amt(rev, curr, is_zh=False)}), net income ({ni_yoy:+.1f}% to {fmt_large_amt(ni, curr, is_zh=False)}), "
                f"gross margin ({gm_c_str} to {gm_str}), and operating cash flow ({ocf_str}) expansion**; "
                if (rev_yoy is not None and rev_yoy > 0 and ni_yoy is not None and ni_yoy > 0)
                else f"Resilient fundamentals with {gm_str} gross margin and {ocf_str} OCF; "
            )
            val_part = f"P/E at `{pe_str}` (3Y/5Y/10Y percentiles: `{p3_str}` / `{p5_str}` / `{p10_str}`). "
            tech_part = f"Fundamental score `{item.get('confluence', {}).get('fundamental_score', 'N/A')}`, R:R `{rr}`; monitor accumulation zone `{trade.get('entry_zone')}` (stop `{trade.get('stop_loss')}`)."
            desc = fin_part + val_part + tech_part
        elif rank_idx == 1 or (total_count > 2 and rank_idx < total_count - 1):
            role_title = f"Secondary Focus (High-Growth / Pullback Opportunity): {name}"
            bullet_label = "Key Advantages"
            desc = (
                f"{lat_year} revenue {fmt_large_amt(rev, curr, is_zh=False)} ({rev_yoy:+.1f}% YoY) and net income {fmt_large_amt(ni, curr, is_zh=False)} ({ni_yoy:+.1f}% YoY), "
                f"with {gm_str} gross margin and {roe_pct:.1f}% ROE. Trailing P/E `{pe_str}` (10Y percentile `{p10_str}`), 14D RSI `{rsi:.1f}`, R:R `{rr}`; "
                f"watch `{trade.get('entry_zone')}` support (stop `{trade.get('stop_loss')}`, target `{trade.get('target_1')}`)."
                if (rev_yoy is not None and ni_yoy is not None)
                else f"Solid balance sheet (cash {cash_str}, dividend yield `{div_y:.2f}%`), P/E `{pe_str}`, R:R `{rr}`; monitor `{trade.get('entry_zone')}` (stop `{trade.get('stop_loss')}`)."
            )
        else:
            role_title = f"Cautious Watch (Strong Strategic Moat, Near-Term Valuation/Earnings Pressure): {name}"
            bullet_label = "Key Characteristics"
            desc = (
                f"Irreplaceable strategic moat with {gm_str} gross margin, but near-term earnings/valuation pressure keeps trailing P/E elevated at `{pe_str}`. "
                f"Wait for base confirmation around `{trade.get('entry_zone')}` or a high-volume breakout above resistance before adding."
            )
        return {
            "rank": rank_idx + 1,
            "company_name": name,
            "ticker": ticker,
            "role_title": role_title,
            "bullet_label": bullet_label,
            "description": desc,
        }

    if rank_idx == 0:
        role_title = f"首选关注（基本面与估值安全边际最优）：{name}"
        bullet_label = "核心优势"
        if rev_yoy is not None and rev_yoy > 0 and ni_yoy is not None and ni_yoy > 0:
            fin_part = (
                f"实现 {lat_year} 年**营收（`{rev_yoy:+.1f}%` 至 {fmt_large_amt(rev, curr)}）、归母净利（`{ni_yoy:+.1f}%` 至 {fmt_large_amt(ni, curr)}）、"
                f"毛利率（`{gm_c_str}` 至 `{gm_str}`）及经营现金流（至 {ocf_str}）全面正向增长**；"
            )
        else:
            fin_part = f"基本面经营韧性突出，最新年度毛利率保持在 `{gm_str}`，经营现金流 {ocf_str}；"

        val_part = f"PE (TTM) 报 `{pe_str}`（近3年/5年分位分别为 `{p3_str}` / `{p5_str}`，10年分位 `{p10_str}`）"
        if fcf_y and fcf_y > 0:
            val_part += f"，自由现金流收益率达 `{fcf_y:.2f}%`。"
        else:
            val_part += "。"

        if sma20 and sma50 and close > sma20 and close > sma50:
            tech_part = (
                f"技术面上已率先放量突破 20日（`{c}{sma20}`）与 50日均线（`{c}{sma50}`）压制，"
                f"14日 RSI 升至 `{rsi:.1f}`、MACD {'红柱转强' if macd_h > 0 else '动能改善'}，战术盈亏比达 `{rr}`，"
                f"建议围绕 20/50日均线回踩带（`{c}{min(sma20, sma50):.2f} - {c}{max(sma20, sma50):.2f}`）择机波段配置。"
            )
        else:
            f_score_str = item.get("confluence", {}).get("fundamental_score", "N/A")
            val_zone_zh = fund.get("valuation_zone_zh") or "合理区间"
            ma_break_txt = f"，或待放量突破 20日均线 `{c}{sma20:.2f}` 后右侧加仓" if sma20 else ""
            tech_part = f"目前基本面评分 `{f_score_str}` 且估值处于{val_zone_zh}，战术盈亏比达 `{rr}`，建议围绕 `{trade.get('entry_zone')}` 支撑区逢低分批关注（防守止损 `{trade.get('stop_loss')}`）{ma_break_txt}。"
        desc = fin_part + val_part + tech_part

    elif rank_idx == 1 or (total_count > 2 and rank_idx < total_count - 1):
        if rev_yoy is not None and rev_yoy > 20 and ni_yoy is not None and ni_yoy > 20:
            role_title = f"次选关注（高成长AI算力龙头与深度超跌配置）：{name}"
            bullet_label = "核心优势"
            net_cash_txt = f"净现金充裕（现金 {cash_str} 高于有息负债 {fmt_large_amt(total_debt, curr)}）" if cash_raw > total_debt else f"低负债稳健资产负债表（现金 {cash_str}）"
            fpe_txt = f"，Forward PE 仅 `{f_pe:.1f}倍`" if f_pe else ""
            rsi_txt = f"14日 RSI 已回落至 `{rsi:.1f}` 深度超跌区间" if rsi < 30 else f"14日 RSI 报 `{rsi:.1f}`"
            desc = (
                f"{lat_year} 财年实现营收 {fmt_large_amt(rev, curr)}（同比 `{rev_yoy:+.1f}%`）与归母净利 {fmt_large_amt(ni, curr)}（同比 `{ni_yoy:+.1f}%`）爆发式增长，"
                f"毛利率高达 `{gm_str}`、ROE 达 `{roe_pct:.1f}%` 且{net_cash_txt}。当前 PE (TTM) 报 `{pe_str}`（历史分位 `{p10_str}`{fpe_txt}）；"
                f"受短期技术面回撤影响（较过去一年高点回撤 `{tech.get('drawdown_from_52w_high', 0):.1f}%`，{rsi_txt}），"
                f"战术盈亏比 `{rr}`，建议紧盯 `{trade.get('entry_zone')}` 核心支撑带逢低分批关注（止损 `{trade.get('stop_loss')}`，目标 `{trade.get('target_1')}`）。"
            )
        else:
            role_title = f"次选防御（高股息与净现金周期反转）：{name}"
            bullet_label = "核心优势"
            debt_txt = "零有息负债" if total_debt == 0 else "低有息负债率"
            rev_q_growth = (fund.get("revenue_growth") or 0) * 100.0
            rev_q_txt = f"，最新单季营收已同比回升 `{rev_q_growth:+.1f}%`" if rev_q_growth > 0 else ""
            desc = (
                f"资产负债表极度稳健（**{debt_txt} + 约 {cash_str} 账面现金 + `{div_y:.2f}%` 股息率**），"
                f"在行业磨底期提供了坚实的下行安全垫。当前 `{pe_str}` PE (TTM)（10年分位 `{p10_str}`）系周期底部盈利基数压缩所致{rev_q_txt}；"
                f"近期股价报 `{c}{close}`，战术盈亏比 `{rr}`，适合作为高股息防御及行业周期复苏的左侧/波段配置标的（关注 `{trade.get('entry_zone')}` 承接，止损 `{trade.get('stop_loss')}`）。"
            )
    else:
        role_title = f"审慎观望（战略壁垒极高但短期财务与估值承压）：{name}"
        bullet_label = "核心特征"
        nm = lat.get("net_margin") if lat.get("net_margin") is not None else ((fund.get("profit_margins") or 0) * 100)
        nm_str = f"{nm:.1f}%" if nm is not None else "N/A"
        lo_ma = min(sma20 or close, sma50 or close)
        hi_ma = max(sma20 or close, sma50 or close)
        if nm is not None and nm < 0:
            fpe_part = f"、Forward PE `{f_pe:.1f}倍`" if f_pe else ""
            ps_part = f"、P/S `{ps:.2f}倍`" if ps else ""
            rev_part = f"{lat_year} 年营收仍维持 `{rev_yoy:+.1f}%` 高速扩张（毛利率提升至 `{gm_str}`）" if rev_yoy is not None else f"毛利率保持在 `{gm_str}`"
            desc = (
                f"具备全球不可替代的稀缺轨道发射与通信星座垄断壁垒，{rev_part}，"
                f"但高强度研发与星舰/星链资本开支导致 {lat_year} 年净利润录得 `{fmt_large_amt(ni, curr)}`（净利率 `{nm_str}`），"
                f"PE (TTM) 高企至 `{pe_str}`（{fpe_part.lstrip('、')}{ps_part}）。技术面上受制于 `{c}{lo_ma:.2f} - {c}{hi_ma:.2f}`（20/50日均线压制区），"
                f"当前不宜追高，建议耐心等待股价在 `{trade.get('entry_zone')}` 支撑带企稳或放量站上 `{c}{hi_ma:.2f}` 后再行右侧追踪。"
            )
        else:
            desc = (
                f"具备不可替代的行业战略准入与专营垄断壁垒，但短期受毛利率（`{gm_str}`）与净利率（`{nm_str}`）承压影响，"
                f"PE (TTM) 高达 `{pe_str}`（10年分位 `{p10_str}`）。技术面上受制于 `{c}{lo_ma:.2f} - {c}{hi_ma:.2f}`（50/20日均线粘合区）反压，"
                f"战术盈亏比 `{rr}` 偏低，建议耐心等待股价在 `{trade.get('entry_zone')}` 支撑带企稳或放量站上 `{c}{hi_ma:.2f}` 后再行右侧介入。"
            )

    return {
        "rank": rank_idx + 1,
        "company_name": name,
        "ticker": ticker,
        "role_title": role_title,
        "bullet_label": bullet_label,
        "description": desc,
    }


def format_stock_row_cells(items: list, is_zh: bool = True) -> list:
    """Build the 11 rows of Section 1 (Quantitative & Fundamental Comparison Matrix)."""
    rows = []

    align_ttm = should_align_ttm(items)
    # Check if stocks have heterogeneous latest fiscal years (e.g., 2025 vs 2026)
    fy_set = set()
    for it in items:
        hp = it["fundamentals"].get("historical_performance", [])
        if hp and hp[-1].get("year"):
            fy_set.add(str(hp[-1]["year"]))
    show_fy_tag = (len(fy_set) > 1) and not align_ttm

    # Row 1: 核心赛道与壁垒
    r1 = []
    for it in items:
        track, moat = extract_moat_and_track(it, is_zh=is_zh)
        r1.append((f"**{track}**", f"*{moat}*"))
    rows.append(("**核心赛道与壁垒**" if is_zh else "**Core Track & Moat**", r1))

    # Row 2: 最新现价 / 过去一年回撤
    r2 = []
    for it in items:
        c = get_curr_sym(it)
        t = it["technicals"]
        if is_zh:
            r2.append((f"**{c}{t['close']:.2f}**（当日 `{t['change_pct']:+.2f}%`）", f"*距过去一年高点 `{t['drawdown_from_52w_high']:.1f}%`*"))
        else:
            r2.append((f"**{c}{t['close']:.2f}** (`{t['change_pct']:+.2f}%`)", f"*From 52W High: `{t['drawdown_from_52w_high']:.1f}%`*"))
    rows.append(("**最新现价 / 过去一年回撤**" if is_zh else "**Price / 52W Drawdown**", r2))

    # Row 3: 技术面 / 基本面评分
    r3 = []
    for it in items:
        c = it["confluence"]
        ts = c["technical_score"]
        fs = c["fundamental_score"]
        tv = localize_tech_verdict(c["technical_verdict"], is_zh=is_zh)
        if is_zh:
            ts_disp = f"**{ts}**（{tv}）" if parse_score(ts) >= 2 else f"`{ts}`（{tv}）"
            fs_disp = f"**{fs}**" if parse_score(fs) >= 3 else f"`{fs}`"
            r3.append((f"技术面 {ts_disp}", f"基本面 {fs_disp}"))
        else:
            ts_disp = f"**{ts}** ({tv})" if parse_score(ts) >= 2 else f"`{ts}` ({tv})"
            fs_disp = f"**{fs}**" if parse_score(fs) >= 3 else f"`{fs}`"
            r3.append((f"Technical {ts_disp}", f"Fundamental {fs_disp}"))
    rows.append(("**技术面 / 基本面评分**" if is_zh else "**Technical / Fundamental Score**", r3))

    # Row 4: 机构共振评级
    r4 = [(f"**{localize_confluence_verdict(it['confluence']['confluence_verdict'], is_zh=is_zh)}**",) for it in items]
    rows.append(("**机构共振评级**" if is_zh else "**Confluence Rating**", r4))

    # Row 5: PE (TTM) 与10年分位
    r5 = []
    for it in items:
        f = it["fundamentals"]
        pe = f.get("trailing_pe")
        p10 = f.get("pe_10y_percentile")
        p3 = f.get("pe_3y_percentile")
        p5 = f.get("pe_5y_percentile")
        zone = f.get("valuation_zone_zh", "") if is_zh else f.get("valuation_zone_en", "")
        f_pe = f.get("forward_pe")
        ps = f.get("price_to_sales")

        if is_zh:
            line1 = f"**{pe:.1f}倍**（10年分位 **{p10:.1f}%** · {zone}）" if (pe and p10 is not None) else (f"**{pe:.1f}倍**" if pe else "暂无")
            if f_pe and ps:
                line2 = f"*动态 PE {f_pe:.1f}倍，P/S {ps:.2f}倍*"
            elif p3 is not None and p5 is not None and p3 < 35:
                line2 = f"*3年/5年分位仅 {p3:.1f}% / {p5:.1f}%*"
            elif p3 is not None and p5 is not None:
                line2 = f"*3年/5年分位 {p3:.1f}% / {p5:.1f}% · 周期底部盈利压缩*"
            elif p3 is not None:
                line2 = f"*近3年估值分位 {p3:.1f}%*"
            else:
                line2 = "*历史估值分位锚定*"
        else:
            line1 = f"**{pe:.1f}x** (10Y Pct: **{p10:.1f}%** · {zone})" if (pe and p10 is not None) else (f"**{pe:.1f}x**" if pe else "N/A")
            if f_pe and ps:
                line2 = f"*Fwd P/E {f_pe:.1f}x, P/S {ps:.2f}x*"
            elif p3 is not None and p5 is not None:
                line2 = f"*3Y/5Y Pct: {p3:.1f}% / {p5:.1f}%*"
            else:
                line2 = "*Historical Valuation Anchor*"
        r5.append((line1, line2))
    rows.append(("**PE (TTM) 与10年分位**" if is_zh else "**P/E (TTM) & 10Y Percentile**", r5))

    # Row 6: 市净率 P/B
    if is_zh:
        r6 = [(f"**{it['fundamentals']['price_to_book']:.2f}倍**",) if it["fundamentals"].get("price_to_book") else ("暂无",) for it in items]
        rows.append(("**市净率 P/B**", r6))
    else:
        r6 = [(f"**{it['fundamentals']['price_to_book']:.2f}x**",) if it["fundamentals"].get("price_to_book") else ("N/A",) for it in items]
        rows.append(("**Price / Book (P/B)**", r6))

    # Row 7: 最新年度 / TTM 营收及增速
    r7 = []
    for it in items:
        curr = it["metadata"].get("currency", "CNY")
        f = it["fundamentals"]
        hp = f.get("historical_performance", [])
        if align_ttm:
            r_ttm = f.get("total_revenue_ttm")
            amt_s = fmt_large_amt(r_ttm, curr, is_zh=is_zh)
            yoy = (f.get("revenue_growth") * 100.0) if f.get("revenue_growth") is not None else (hp[-1].get("revenue_yoy") if hp else None)
            r_23 = hp[0].get("revenue") or 0 if len(hp) >= 3 else 0
            r_lat = hp[-1].get("revenue") if len(hp) >= 3 else None
            cagr_txt = ""
            if r_23 > 0 and r_lat and r_lat > 0:
                cagr = ((r_lat / r_23) ** 0.5 - 1.0) * 100.0
                cagr_txt = f" ｜ 2Y复合 `{cagr:+.1f}%`" if is_zh else f" | 2Y CAGR `{cagr:+.1f}%`"
            yoy_txt = (f"同比 `{yoy:+.1f}%`" if is_zh else f"YoY `{yoy:+.1f}%`") if yoy is not None else ""
            sub = f"*{yoy_txt}{cagr_txt.lstrip(' ｜') if not yoy_txt else cagr_txt}*" if (yoy_txt or cagr_txt) else "*TTM*"
            r7.append((f"**{amt_s}** (TTM)", sub))
        elif len(hp) >= 3:
            r_23 = hp[0].get("revenue") or 0
            r_lat = hp[-1].get("revenue")
            yr = str(hp[-1].get("year", ""))
            fy_tag = f" (FY{yr[-2:]})" if (show_fy_tag and len(yr) >= 2) else ""
            yoy = hp[-1].get("revenue_yoy") or 0
            cagr = ((r_lat / r_23) ** 0.5 - 1.0) * 100.0 if (r_23 > 0 and r_lat and r_lat > 0) else 0.0
            amt_s = fmt_large_amt(r_lat, curr, is_zh=is_zh)
            if is_zh:
                r7.append((f"**{amt_s}**{fy_tag}", f"*同比 `{yoy:+.1f}%` ｜ 2Y复合 `{cagr:+.1f}%`*"))
            else:
                r7.append((f"**{amt_s}**{fy_tag}", f"*YoY `{yoy:+.1f}%` | 2Y CAGR `{cagr:+.1f}%`*"))
        elif len(hp) == 2:
            r_lat = hp[-1].get("revenue")
            yr = str(hp[-1].get("year", ""))
            fy_tag = f" (FY{yr[-2:]})" if (show_fy_tag and len(yr) >= 2) else ""
            yoy = hp[-1].get("revenue_yoy") or 0
            amt_s = fmt_large_amt(r_lat, curr, is_zh=is_zh)
            r7.append((f"**{amt_s}**{fy_tag}", f"*{'同比' if is_zh else 'YoY'} `{yoy:+.1f}%`*"))
        else:
            r7.append(("暂无" if is_zh else "N/A",))
    if align_ttm:
        rows.append(("**近12个月营收及增速 (TTM)**" if is_zh else "**Revenue & Growth (TTM)**", r7))
    else:
        rows.append(("**最新年度营收及增速**" if is_zh else "**Latest Annual Revenue & Growth**", r7))

    # Row 8: 最新年度 / TTM 归母净利及增速
    r8 = []
    for it in items:
        curr = it["metadata"].get("currency", "CNY")
        f = it["fundamentals"]
        hp = f.get("historical_performance", [])
        if align_ttm:
            ni_ttm = f.get("net_income_ttm")
            if ni_ttm is not None:
                yoy = (f.get("earnings_growth") * 100.0) if f.get("earnings_growth") is not None else None
                amt_s = fmt_large_amt(ni_ttm, curr, is_zh=is_zh)
                if ni_ttm < 0 and (yoy is None or abs(yoy) > 500):
                    note = "高强度研发与资本开支致亏损" if is_zh else "Heavy R&D & CapEx investment"
                    r8.append((f"**{amt_s}** (TTM)（{note}）" if is_zh else f"**{amt_s}** (TTM) ({note})",))
                elif yoy is not None:
                    r8.append((f"**{amt_s}** (TTM)（同比 `{yoy:+.1f}%`）" if is_zh else f"**{amt_s}** (TTM) (`{yoy:+.1f}%` YoY)",))
                else:
                    r8.append((f"**{amt_s}** (TTM)",))
            else:
                r8.append(("暂无" if is_zh else "N/A",))
        elif hp and hp[-1].get("net_income") is not None:
            ni_lat = hp[-1].get("net_income")
            yr = str(hp[-1].get("year", ""))
            fy_tag = f" (FY{yr[-2:]})" if (show_fy_tag and len(yr) >= 2) else ""
            yoy = hp[-1].get("net_income_yoy")
            amt_s = fmt_large_amt(ni_lat, curr, is_zh=is_zh)
            if ni_lat < 0 and (yoy is None or abs(yoy) > 500):
                note = "高强度研发与资本开支致亏损" if is_zh else "Heavy R&D & CapEx investment"
                r8.append((f"**{amt_s}**{fy_tag}（{note}）" if is_zh else f"**{amt_s}**{fy_tag} ({note})",))
            elif yoy is not None:
                r8.append((f"**{amt_s}**{fy_tag}（同比 `{yoy:+.1f}%`）" if is_zh else f"**{amt_s}**{fy_tag} (`{yoy:+.1f}%` YoY)",))
            else:
                r8.append((f"**{amt_s}**{fy_tag}",))
        else:
            r8.append(("暂无" if is_zh else "N/A",))
    if align_ttm:
        rows.append(("**近12个月归母净利及增速 (TTM)**" if is_zh else "**Net Income & Growth (TTM)**", r8))
    else:
        rows.append(("**最新年度归母净利及增速**" if is_zh else "**Latest Net Income & Growth**", r8))

    # Row 9: 毛利率 / 净资产收益率 ROE
    r9 = []
    for it in items:
        f = it["fundamentals"]
        hp = f.get("historical_performance", [])
        if align_ttm and f.get("gross_margins") is not None:
            gm = f["gross_margins"] * 100.0
        else:
            gm = hp[-1].get("gross_margin") if (hp and hp[-1].get("gross_margin") is not None) else ((f.get("gross_margins") or 0) * 100)
        gm_c = hp[-1].get("gross_margin_change") if hp else None
        roe = (f.get("return_on_equity") * 100.0) if f.get("return_on_equity") is not None else (hp[-1].get("roe") if (hp and hp[-1].get("roe") is not None) else None)
        roe_str = f"{roe:.1f}%" if roe is not None else ("暂无" if is_zh else "N/A")
        gm_c_txt = f"`{gm_c:+.1f}%`" if gm_c is not None else "`-`"
        if is_zh:
            r9.append((f"毛利率 **{gm:.1f}%**（{gm_c_txt}） ｜ ROE **{roe_str}**",))
        else:
            r9.append((f"Gross Margin **{gm:.1f}%** ({gm_c_txt}) | ROE **{roe_str}**",))
    if align_ttm:
        rows.append(("**毛利率 / 净资产收益率 ROE (TTM)**" if is_zh else "**Gross Margin / ROE (TTM)**", r9))
    else:
        rows.append(("**毛利率 / 净资产收益率 ROE**" if is_zh else "**Gross Margin / ROE**", r9))

    # Row 10: 经营现金流 OCF / 负债结构
    r10 = []
    for it in items:
        curr = it["metadata"].get("currency", "CNY")
        f = it["fundamentals"]
        hp = f.get("historical_performance", [])
        if align_ttm and f.get("operating_cash_flow") is not None:
            ocf_raw = f.get("operating_cash_flow")
        else:
            ocf_raw = hp[-1].get("ocf") if (hp and hp[-1].get("ocf") is not None) else f.get("operating_cash_flow")
        ocf_val = ocf_raw or 0
        ocf_str = fmt_large_amt(ocf_raw, curr, is_zh=is_zh)
        fcf_y = f.get("fcf_yield")
        td = f.get("total_debt") or 0
        d2e = f.get("debt_to_equity")
        cash_raw = f.get("total_cash") or 0
        cash_str = fmt_large_amt(cash_raw, curr, is_zh=is_zh)

        if is_zh:
            if ocf_val > 0 and fcf_y and fcf_y > 0:
                line1 = f"OCF **{ocf_str}**（FCF收益率 `{fcf_y:.2f}%`）"
            elif ocf_val > 0:
                line1 = f"OCF **{ocf_str}**（保持正流入）"
            else:
                line1 = f"OCF **{ocf_str}**（备货与结算占用）"

            if td == 0:
                line2 = f"*零有息负债（现金 {cash_str}）*"
            elif cash_raw > td and d2e is not None:
                line2 = f"*有息债务权益比 `{d2e:.1f}%`（账面现金 {cash_str}）*"
            elif d2e is not None and d2e < 10.0:
                line2 = f"*有息负债率仅 `{d2e:.1f}%`（现金 {cash_str}）*"
            elif d2e is not None:
                line2 = f"*有息债务权益比 `{d2e:.1f}%`（现金 {cash_str}）*"
            else:
                line2 = f"*账面现金 {cash_str}*"
        else:
            if ocf_val > 0 and fcf_y and fcf_y > 0:
                line1 = f"OCF **{ocf_str}** (FCF Yield `{fcf_y:.2f}%`)"
            elif ocf_val > 0:
                line1 = f"OCF **{ocf_str}** (Positive)"
            else:
                line1 = f"OCF **{ocf_str}**"

            if td == 0:
                line2 = f"*Debt-Free (Cash {cash_str})*"
            elif d2e is not None:
                line2 = f"*Debt/Equity `{d2e:.1f}%` (Cash {cash_str})*"
            else:
                line2 = f"*Cash {cash_str}*"
        r10.append((line1, line2))
    rows.append(("**经营现金流 OCF / 负债结构**" if is_zh else "**Operating Cash Flow / Debt**", r10))

    # Row 11: 股息率安全垫
    r11 = []
    for it in items:
        dy = normalize_div_yield(it["fundamentals"], it["technicals"])
        r11.append((f"**{dy:.2f}%**",))
    rows.append(("**股息率安全垫**" if is_zh else "**Dividend Yield**", r11))

    return rows


def generate_comparison_markdown(items: list, recs: list, rows: list, output_md_path: str, base_output_dir: str, is_zh: bool = True):
    names_str = ("、" if is_zh else ", ").join([it["metadata"]["company_name"] for it in items])
    analysis_date = items[0]["metadata"].get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
    curr_label = get_currency_label_zh(items, is_zh=is_zh)

    dim_hdr = "对比维度" if is_zh else "Dimension"
    headers = f"| {dim_hdr} | " + " | ".join([f"**{it['metadata']['company_name']}** (`{it['metadata']['ticker']}`)" for it in items]) + " |"
    sep = "| :--- | " + " | ".join([":---" for _ in items]) + " |"
    table1_lines = [headers, sep]
    for label, cells in rows:
        md_cells = ["<br>".join(c) if isinstance(c, tuple) else str(c) for c in cells]
        table1_lines.append(f"| {label} | " + " | ".join(md_cells) + " |")
    table1_md = "\n".join(table1_lines)

    if is_zh:
        t2_lines = [
            "| 标的 | 战术操作倾向 | 建议逢低关注区间 | 防守止损线 | 第一 / 第二目标位 | 战术盈亏比 | 关键技术观察点 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    else:
        t2_lines = [
            "| Ticker | Tactical Bias | Accumulation Zone | Stop Loss | Target 1 / Target 2 | R:R Ratio | Key Technical Watch |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    for idx, it in enumerate(items):
        name = it["metadata"]["company_name"]
        tr = it["trade_setup"]
        loc_bias = localize_bias(tr["bias"], is_zh=is_zh)
        bias = f"**{loc_bias}**" if idx == 0 and tr["bias_type"] != "bearish" else loc_bias
        obs = build_key_tech_observation(it, is_zh=is_zh)
        t2_lines.append(
            f"| **{name}** | {bias} | `{tr['entry_zone']}` | **{tr['stop_loss']}** | **{tr['target_1']} / {tr['target_2']}** | **{tr['rr_ratio']}** | {obs} |"
        )
    table2_md = "\n".join(t2_lines)

    rec_lines = []
    for r in recs:
        colon = "：" if is_zh else ": "
        rec_lines.append(f"{r['rank']}. **{r['role_title']}**\n   - **{r['bullet_label']}**{colon}{r['description']}")
    rec_md = "\n".join(rec_lines)

    file_lines = []
    for it in items:
        m = it["metadata"]
        nm = m["company_name"]
        tk = m["ticker"]
        tk_low = tk.lower()
        rep_nm = m.get("report_name") or nm
        rep_nm_url = rep_nm.replace(" ", "%20")

        sub_candidates = [
            os.path.join(base_output_dir, f"{nm} {tk}"),
            os.path.join(base_output_dir, tk),
        ]
        meta_out = m.get("output_dir")
        if meta_out:
            sub_candidates.append(meta_out)
            sub_candidates.append(os.path.join(base_output_dir, os.path.basename(os.path.normpath(meta_out))))
        abs_sub_dir = None
        for cand in sub_candidates:
            if cand and os.path.isdir(cand):
                abs_sub_dir = os.path.abspath(cand)
                break
        if not abs_sub_dir:
            abs_sub_dir = os.path.abspath(os.path.join(base_output_dir, tk))

        abs_sub = abs_sub_dir.replace("\\", "/")
        abs_sub_url = abs_sub.replace(" ", "%20")
        chart_lbl = "技术图表" if is_zh else "Technical Chart"
        pe_lbl = "PE分位图" if is_zh else "PE Percentile Chart"
        file_lines.append(
            f"- **{nm} (`{tk}`)**" + ("：" if is_zh else ": ") +
            f"📄 [{rep_nm}.html](file:///{abs_sub_url}/{rep_nm_url}.html) | "
            f"📱 [{rep_nm}.pdf](file:///{abs_sub_url}/{rep_nm_url}.pdf) | "
            f"📝 [{rep_nm}.md](file:///{abs_sub_url}/{rep_nm_url}.md) | "
            f"📊 [{chart_lbl}](file:///{abs_sub_url}/{tk_low}_chart.png) | "
            f"📈 [{pe_lbl}](file:///{abs_sub_url}/{tk_low}_pe_percentile_chart.png)"
        )
    files_md = "\n".join(file_lines)

    if is_zh:
        md_content = f"""# 投资对比研判报告: {names_str}

*投研日期: {analysis_date} | 时间级别: 日线级别 | 数据周期: 近1年 | 结算货币: {curr_label}*

---

## 一、核心量化与基本面横向对比矩阵

{table1_md}

---

## 二、战术交易点位与风控对比

{table2_md}

---

## 三、机构综合排序与配置建议

{rec_md}

---

## 四、各标的交付报告与图表文件清单

{files_md}

---

*免责声明：本投资对比研判报告由量化投研模型自动生成，融合量化技术指标与财务报表数据，仅供学习、研究与交流讨论，不构成任何投资建议、买卖要约或推荐。金融市场具有高波动性与本金损失风险，投资需独立审慎决策。*
"""
    else:
        md_content = f"""# Investment Comparison Report: {names_str}

*Analysis Date: {analysis_date} | Timeframe: Daily | Period: 1Y | Currency: {curr_label}*

---

## 1. Core Quantitative & Fundamental Comparison Matrix

{table1_md}

---

## 2. Tactical Trade Setup & Risk Control Comparison

{table2_md}

---

## 3. Institutional Priority Ranking & Allocation Recommendations

{rec_md}

---

## 4. Deliverable Reports & Charts

{files_md}

---

*Disclaimer: This investment comparison report was generated automatically by a quantitative research model integrating technical indicators and financial statement data for educational and research purposes only. It does not constitute investment advice. Financial markets carry high volatility and risk of loss.*
"""
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(md_content.strip() + "\n")
    return md_content


def md_inline_to_html(text: str) -> str:
    s = str(text).replace("\\|", "|")
    s = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.*?)\*", r'<span class="sub-note">\1</span>', s)
    s = re.sub(r"`(.*?)`", r'<strong class="code-val">\1</strong>', s)
    return s


def generate_comparison_html(items: list, recs: list, rows: list, output_html_path: str, base_output_dir: str, is_zh: bool = True) -> str:
    names_str = ("、" if is_zh else ", ").join([it["metadata"]["company_name"] for it in items])
    tickers_str = " / ".join([it["metadata"]["ticker"] for it in items])
    analysis_date = items[0]["metadata"].get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
    curr_label = get_currency_label_zh(items, is_zh=is_zh)

    # Top Priority Cards
    badge_colors = ["#16a34a", "#2563eb", "#d97706", "#64748b"]
    card_td_html = []
    width_pct = int(100 / max(len(items), 1))
    for idx, it in enumerate(items):
        m = it["metadata"]
        t = it["technicals"]
        f = it["fundamentals"]
        tr = it["trade_setup"]
        c = it["confluence"]
        c_sym = get_curr_sym(it)
        loc_sector = localize_sector(m.get("sector", ""), m.get("ticker", ""), is_zh=is_zh)
        color = badge_colors[min(idx, len(badge_colors) - 1)]
        if is_zh:
            role_prefix = recs[idx]["role_title"].split("（")[0] if idx < len(recs) else f"关注 · NO.{idx+1}"
            rank_label = f"{role_prefix} · NO.{idx+1}"
            pe_val = f"{f['trailing_pe']:.1f}倍" if f.get("trailing_pe") else "暂无"
            pe_10y = f"{f['pe_10y_percentile']:.1f}%" if f.get("pe_10y_percentile") is not None else "暂无"
            chg_color = "#16a34a" if t["change_pct"] >= 0 else "#dc2626"
            card_td_html.append(f"""
            <td class="kpi-card" style="width:{width_pct}%; border-top: 4px solid {color};">
                <div class="kpi-title" style="color:{color};">{rank_label} ｜ {loc_sector}</div>
                <div class="kpi-value">{m['company_name']} <span class="ticker-tag">{m['ticker']}</span></div>
                <div class="kpi-line">现价: <strong style="color:{chg_color};">{c_sym}{t['close']:.2f} ({t['change_pct']:+.2f}%)</strong> ｜ 盈亏比: <strong>{tr['rr_ratio']}</strong></div>
                <div class="kpi-line">评分: 技术面 <strong>{c['technical_score']}</strong> ｜ 基本面 <strong>{c['fundamental_score']}</strong></div>
                <div class="kpi-line">估值: PE (TTM) <strong>{pe_val}</strong> (10年分位 {pe_10y} · {f.get('valuation_zone_zh', '')})</div>
            </td>
        """)
        else:
            role_prefix = recs[idx]["role_title"].split(" (")[0] if idx < len(recs) else f"Rank #{idx+1}"
            rank_label = f"{role_prefix} · #{idx+1}"
            pe_val = f"{f['trailing_pe']:.1f}x" if f.get("trailing_pe") else "N/A"
            pe_10y = f"{f['pe_10y_percentile']:.1f}%" if f.get("pe_10y_percentile") is not None else "N/A"
            chg_color = "#16a34a" if t["change_pct"] >= 0 else "#dc2626"
            card_td_html.append(f"""
            <td class="kpi-card" style="width:{width_pct}%; border-top: 4px solid {color};">
                <div class="kpi-title" style="color:{color};">{rank_label} | {loc_sector}</div>
                <div class="kpi-value">{m['company_name']} <span class="ticker-tag">{m['ticker']}</span></div>
                <div class="kpi-line">Price: <strong style="color:{chg_color};">{c_sym}{t['close']:.2f} ({t['change_pct']:+.2f}%)</strong> | R:R: <strong>{tr['rr_ratio']}</strong></div>
                <div class="kpi-line">Score: Tech <strong>{c['technical_score']}</strong> | Fund <strong>{c['fundamental_score']}</strong></div>
                <div class="kpi-line">Valuation: P/E <strong>{pe_val}</strong> (10Y Pct {pe_10y} · {f.get('valuation_zone_en', '')})</div>
            </td>
        """)
    kpi_cards_html = "\n".join(card_td_html)

    # Table 1 HTML
    col_w = round(79.5 / max(len(items), 1), 1)
    th_cols = "".join([
        f"<th style='width:{col_w}%;'><div>{it['metadata']['company_name']}</div><div class='th-sub'>{it['metadata']['ticker']}</div></th>"
        for it in items
    ])
    t1_rows_html = []
    for label, cells in rows:
        td_list = []
        for c in cells:
            if isinstance(c, tuple):
                inner_divs = "".join([f"<div class='cell-line'>{md_inline_to_html(line)}</div>" for line in c])
            else:
                inner_divs = f"<div class='cell-line'>{md_inline_to_html(c)}</div>"
            td_list.append(f"<td style='width:{col_w}%;'>{inner_divs}</td>")
        tds = "".join(td_list)
        t1_rows_html.append(f"<tr><td style='width:20.5%;background-color:#f8fafc;'>{md_inline_to_html(label)}</td>{tds}</tr>")
    table1_html = "\n".join(t1_rows_html)

    # Table 2 HTML
    t2_rows_html = []
    for idx, it in enumerate(items):
        nm = it["metadata"]["company_name"]
        tr = it["trade_setup"]
        loc_bias = localize_bias(tr["bias"], is_zh=is_zh)
        obs = md_inline_to_html(build_key_tech_observation(it, is_zh=is_zh))
        bias_color = "#16a34a" if tr["bias_type"] == "bullish" else ("#d97706" if tr["bias_type"] == "neutral" else "#dc2626")
        t2_rows_html.append(f"""
            <tr>
                <td style="width:8.5%;"><strong>{nm}</strong></td>
                <td style="width:14.5%;"><strong style="color:{bias_color};">{loc_bias}</strong></td>
                <td style="width:13%;"><strong>{tr['entry_zone']}</strong></td>
                <td style="width:9%; color:#dc2626;"><strong>{tr['stop_loss']}</strong></td>
                <td style="width:14.5%; color:#16a34a;"><strong>{tr['target_1']} / {tr['target_2']}</strong></td>
                <td style="width:10%;"><strong>{tr['rr_ratio']}</strong></td>
                <td style="width:30.5%;">{obs}</td>
            </tr>
        """)
    table2_html = "\n".join(t2_rows_html)

    # Section 3 Priority Recommendations HTML (using 1-cell table for strict box containment in both HTML & PDF)
    rec_cards_html = []
    for idx, r in enumerate(recs):
        border_col = badge_colors[min(idx, len(badge_colors) - 1)]
        bg_col = "#f0fdf4" if idx == 0 else ("#eff6ff" if idx == 1 else "#fffbeb")
        rec_cards_html.append(f"""
        <table class="thesis-table">
            <tr>
                <td class="thesis-cell" style="border-left: 4px solid {border_col}; background-color: {bg_col};">
                    <div class="thesis-header">{r['rank']}. {r['role_title']}</div>
                    <div class="thesis-body">
                        <strong>{r['bullet_label']}{'：' if is_zh else ': '}</strong>{md_inline_to_html(r['description'])}
                    </div>
                </td>
            </tr>
        </table>
        """)
    recs_html = "\n".join(rec_cards_html)

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

    html = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if is_zh else 'en'}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{'投资对比研判报告' if is_zh else 'Investment Comparison Report'} - {names_str}</title>
    <style>
        {font_css}
        body {{
            font-family: 'YaHei', 'Microsoft YaHei', 'SegoeUI', 'Segoe UI', sans-serif;
            font-size: 14.5px;
            line-height: 1.65;
            background-color: #f1f5f9;
            color: #0f172a;
            margin: 0;
            padding: 24px;
        }}
        .report-container {{
            max-width: 1080px;
            margin: 0 auto;
            background: #ffffff;
            padding: 32px 38px;
            border-radius: 12px;
            border: 1px solid #cbd5e1;
        }}
        .header-banner {{
            background-color: #0f172a;
            color: #ffffff;
            padding: 20px 24px;
            border-radius: 10px;
            margin-bottom: 16px;
        }}
        .header-banner h1 {{
            margin: 0 0 4px 0;
            font-size: 23px;
            font-weight: 800;
            color: #ffffff;
        }}
        .header-stocks {{
            font-size: 17px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 6px;
            line-height: 1.35;
        }}
        .header-banner .meta-row {{
            font-size: 13px;
            color: #cbd5e1;
        }}
        .kpi-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 10px;
            margin-bottom: 18px;
        }}
        .kpi-card {{
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 12px 14px;
            vertical-align: top;
        }}
        .kpi-title {{
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 4px;
        }}
        .kpi-value {{
            font-size: 19px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 5px;
        }}
        .ticker-tag {{
            font-size: 12.5px;
            font-weight: 600;
            color: #64748b;
        }}
        .kpi-line {{
            font-size: 12.5px;
            color: #334155;
            line-height: 1.5;
            margin-bottom: 2px;
        }}
        h2 {{
            font-size: 18px;
            font-weight: 800;
            color: #0f172a;
            margin: 24px 0 10px 0;
            padding-bottom: 6px;
            border-bottom: 2px solid #cbd5e1;
        }}
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 18px;
            font-size: 13.5px;
            table-layout: fixed;
        }}
        table.data-table th, table.data-table td {{
            border: 1px solid #cbd5e1;
            padding: 9px 11px;
            text-align: left;
            vertical-align: top;
            line-height: 1.5;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        table.data-table th {{
            background-color: #f1f5f9;
            color: #0f172a;
            font-weight: 800;
            font-size: 14px;
        }}
        .th-sub {{
            font-size: 11.5px;
            font-weight: 600;
            color: #475569;
        }}
        .cell-line {{
            margin-bottom: 2px;
        }}
        .sub-note {{
            color: #475569;
            font-size: 12.5px;
        }}
        .code-val {{
            color: #0f172a;
            font-weight: 700;
        }}
        table.data-table tr:nth-child(even) {{
            background-color: #f8fafc;
        }}
        .thesis-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 10px;
            table-layout: fixed;
        }}
        .thesis-cell {{
            border: 1px solid #cbd5e1;
            padding: 12px 16px;
            vertical-align: top;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .thesis-header {{
            font-size: 15px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 5px;
        }}
        .thesis-body {{
            font-size: 13.8px;
            color: #1e293b;
            line-height: 1.65;
        }}
        .disclaimer {{
            font-size: 12px;
            color: #64748b;
            margin-top: 28px;
            padding-top: 12px;
            border-top: 1px solid #cbd5e1;
            text-align: center;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
<div class="report-container">
    <div class="header-banner">
        <h1>{'投资对比研判报告' if is_zh else 'Investment Comparison Report'}</h1>
        <div class="header-stocks">{names_str}</div>
        <div class="meta-row">
            {f'对比标的: {tickers_str} &nbsp;|&nbsp; 投研日期: {analysis_date} &nbsp;|&nbsp; 时间级别: 日线级别 &nbsp;|&nbsp; 数据周期: 近1年 &nbsp;|&nbsp; 结算货币: {curr_label}' if is_zh else f'Tickers: {tickers_str} &nbsp;|&nbsp; Date: {analysis_date} &nbsp;|&nbsp; Timeframe: Daily &nbsp;|&nbsp; Period: 1Y &nbsp;|&nbsp; Currency: {curr_label}'}
        </div>
    </div>

    <!-- Top Priority Ranking Strip -->
    <table class="kpi-table">
        <tr>
            {kpi_cards_html}
        </tr>
    </table>

    <!-- Section 1: Core Quantitative & Fundamental Comparison Matrix -->
    <h2>{'一、核心量化与基本面横向对比矩阵' if is_zh else '1. Core Quantitative & Fundamental Comparison Matrix'}</h2>
    <table class="data-table">
        <thead>
            <tr>
                <th style="width:20.5%;">{'对比维度' if is_zh else 'Dimension'}</th>
                {th_cols}
            </tr>
        </thead>
        <tbody>
            {table1_html}
        </tbody>
    </table>

    <!-- Section 2: Tactical Trade Setup & Risk Control Matrix -->
    <h2>{'二、战术交易点位与风控对比' if is_zh else '2. Tactical Trade Setup & Risk Control Comparison'}</h2>
    <table class="data-table">
        <thead>
            <tr>
                <th style="width:8.5%;">{'标的' if is_zh else 'Ticker'}</th>
                <th style="width:14.5%;">{'战术操作倾向' if is_zh else 'Tactical Bias'}</th>
                <th style="width:13%;">{'建议逢低关注区间' if is_zh else 'Accumulation Zone'}</th>
                <th style="width:9%;">{'防守止损线' if is_zh else 'Stop Loss'}</th>
                <th style="width:14.5%;">{'第一 / 第二目标位' if is_zh else 'Target 1 / Target 2'}</th>
                <th style="width:10%;">{'战术盈亏比' if is_zh else 'R:R Ratio'}</th>
                <th style="width:30.5%;">{'关键技术观察点' if is_zh else 'Key Technical Watch'}</th>
            </tr>
        </thead>
        <tbody>
            {table2_html}
        </tbody>
    </table>

    <!-- Section 3: Institutional Priority Ranking & Recommendations -->
    <h2>{'三、机构综合排序与配置建议' if is_zh else '3. Institutional Priority Ranking & Recommendations'}</h2>
    {recs_html}

    <div class="disclaimer">
        {('免责声明：本投资对比研判报告由量化投研模型自动生成，融合量化技术指标与财务报表数据。<br/>仅供学习、研究与交流讨论，不构成任何投资建议、买卖要约或推荐。金融市场具有高波动性与本金损失风险，投资需独立审慎决策。') if is_zh else ('Disclaimer: This investment comparison report was generated automatically by a quantitative research model integrating technical indicators and financial statement data.<br/>For educational and research purposes only; not investment advice. Financial markets carry high volatility and risk of loss.')}
    </div>
</div>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html.strip())
    return html


def _build_font_css() -> str:
    """Build @font-face CSS declarations for YaHei and SegoeUI."""
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
    return "\n".join(font_defs)


def generate_comparison_pdf(items: list, recs: list, rows: list, output_pdf_path: str, is_zh: bool = True) -> bool:
    if not HAS_PISA:
        return False
    register_cjk_fonts()

    names_str = ("、" if is_zh else ", ").join([it["metadata"]["company_name"] for it in items])
    tickers_str = " / ".join([it["metadata"]["ticker"] for it in items])
    analysis_date = items[0]["metadata"].get("analysis_date", datetime.now().strftime("%Y-%m-%d"))
    curr_label = get_currency_label_zh(items, is_zh=is_zh)
    badge_colors = ["#16a34a", "#2563eb", "#d97706", "#64748b"]

    # 1. Top Priority KPI Cards (Vertically Stacked for Mobile 112mm x 220mm)
    kpi_cards_html = []
    for idx, it in enumerate(items):
        m = it["metadata"]
        t = it["technicals"]
        f = it["fundamentals"]
        tr = it["trade_setup"]
        c = it["confluence"]
        c_sym = get_curr_sym(it)
        loc_sector = localize_sector(m.get("sector", ""), m.get("ticker", ""), is_zh=is_zh)
        color = badge_colors[min(idx, len(badge_colors) - 1)]
        chg_color = "#16a34a" if t["change_pct"] >= 0 else "#dc2626"
        if is_zh:
            role_prefix = recs[idx]["role_title"].split("（")[0] if idx < len(recs) else f"关注 · NO.{idx+1}"
            rank_label = f"{role_prefix} · NO.{idx+1}"
            pe_val = f"{f['trailing_pe']:.1f}倍" if f.get("trailing_pe") else "暂无"
            pe_10y = f"{f['pe_10y_percentile']:.1f}%" if f.get("pe_10y_percentile") is not None else "暂无"
            kpi_cards_html.append(f"""
            <table class="kpi-card-table">
                <tr>
                    <td class="kpi-card" style="border-left: 4px solid {color};">
                        <div class="kpi-title" style="color:{color};">{rank_label} ｜ {loc_sector}</div>
                        <div class="kpi-value">{m['company_name']} <span class="ticker-tag">{m['ticker']}</span></div>
                        <div class="kpi-line">现价: <strong style="color:{chg_color};">{c_sym}{t['close']:.2f} ({t['change_pct']:+.2f}%)</strong> ｜ 盈亏比: <strong>{tr['rr_ratio']}</strong></div>
                        <div class="kpi-line">评分: 技术面 <strong>{c['technical_score']}</strong> ｜ 基本面 <strong>{c['fundamental_score']}</strong></div>
                        <div class="kpi-line">估值: PE (TTM) <strong>{pe_val}</strong> (10年分位 {pe_10y} · {f.get('valuation_zone_zh', '')})</div>
                    </td>
                </tr>
            </table>
            """)
        else:
            role_prefix = recs[idx]["role_title"].split(" (")[0] if idx < len(recs) else f"Rank #{idx+1}"
            rank_label = f"{role_prefix} · #{idx+1}"
            pe_val = f"{f['trailing_pe']:.1f}x" if f.get("trailing_pe") else "N/A"
            pe_10y = f"{f['pe_10y_percentile']:.1f}%" if f.get("pe_10y_percentile") is not None else "N/A"
            kpi_cards_html.append(f"""
            <table class="kpi-card-table">
                <tr>
                    <td class="kpi-card" style="border-left: 4px solid {color};">
                        <div class="kpi-title" style="color:{color};">{rank_label} | {loc_sector}</div>
                        <div class="kpi-value">{m['company_name']} <span class="ticker-tag">{m['ticker']}</span></div>
                        <div class="kpi-line">Price: <strong style="color:{chg_color};">{c_sym}{t['close']:.2f} ({t['change_pct']:+.2f}%)</strong> | R:R: <strong>{tr['rr_ratio']}</strong></div>
                        <div class="kpi-line">Score: Tech <strong>{c['technical_score']}</strong> | Fund <strong>{c['fundamental_score']}</strong></div>
                        <div class="kpi-line">Valuation: P/E <strong>{pe_val}</strong> (10Y Pct {pe_10y} · {f.get('valuation_zone_en', '')})</div>
                    </td>
                </tr>
            </table>
            """)
    kpi_stack_html = "\n".join(kpi_cards_html)

    # 2. Section 1: Dimension-Grouped Vertical Comparison Blocks
    dim_blocks_html = []
    for label, cells in rows:
        stock_rows = []
        for idx, it in enumerate(items):
            nm = it["metadata"]["company_name"]
            color = badge_colors[min(idx, len(badge_colors) - 1)]
            c_val = cells[idx] if idx < len(cells) else ""
            if isinstance(c_val, tuple):
                inner_divs = "".join([f"<div class='cell-line'>{md_inline_to_html(line)}</div>" for line in c_val])
            else:
                inner_divs = f"<div class='cell-line'>{md_inline_to_html(c_val)}</div>"
            stock_rows.append(
                f"<tr>"
                f"<td class='dim-stock' style='width:25%; border-left: 3px solid {color};'>{nm}</td>"
                f"<td class='dim-val' style='width:75%;'>{inner_divs}</td>"
                f"</tr>"
            )
        dim_blocks_html.append(f"""
        <table class="dim-table">
            <tr><th colspan="2" class="dim-hdr">{md_inline_to_html(label)}</th></tr>
            {"".join(stock_rows)}
        </table>
        """)
    section1_html = "\n".join(dim_blocks_html)

    # 3. Section 2: Vertical Tactical Trade Cards
    trade_cards_html = []
    for idx, it in enumerate(items):
        m = it["metadata"]
        nm = m["company_name"]
        tk = m["ticker"]
        tr = it["trade_setup"]
        loc_bias = localize_bias(tr["bias"], is_zh=is_zh)
        obs = md_inline_to_html(build_key_tech_observation(it, is_zh=is_zh))
        bias_color = "#16a34a" if tr["bias_type"] == "bullish" else ("#d97706" if tr["bias_type"] == "neutral" else "#dc2626")
        lbl_entry = "建议逢低关注区间" if is_zh else "Accumulation Zone"
        lbl_stop = "防守止损线" if is_zh else "Stop Loss"
        lbl_tgt = "第一 / 第二目标位" if is_zh else "Target 1 / Target 2"
        lbl_rr = "战术盈亏比" if is_zh else "R:R Ratio"
        lbl_obs = "关键技术观察点：" if is_zh else "Key Technical Watch: "
        trade_cards_html.append(f"""
        <table class="trade-card-table">
            <tr>
                <th colspan="2" class="tc-hdr">
                    <strong>{nm}</strong> <span class="ticker-tag">{tk}</span> &nbsp;｜&nbsp; <strong style="color:{bias_color};">{loc_bias}</strong>
                </th>
            </tr>
            <tr>
                <td class="tc-cell" style="width:50%;">
                    <div class="tc-label">{lbl_entry}</div>
                    <div class="tc-val">{tr['entry_zone']}</div>
                </td>
                <td class="tc-cell" style="width:50%;">
                    <div class="tc-label">{lbl_stop}</div>
                    <div class="tc-val" style="color:#dc2626;">{tr['stop_loss']}</div>
                </td>
            </tr>
            <tr>
                <td class="tc-cell" style="width:50%;">
                    <div class="tc-label">{lbl_tgt}</div>
                    <div class="tc-val" style="color:#16a34a;">{tr['target_1']} / {tr['target_2']}</div>
                </td>
                <td class="tc-cell" style="width:50%;">
                    <div class="tc-label">{lbl_rr}</div>
                    <div class="tc-val">{tr['rr_ratio']}</div>
                </td>
            </tr>
            <tr>
                <td colspan="2" class="tc-obs-cell">
                    <div class="tc-obs"><strong>{lbl_obs}</strong>{obs}</div>
                </td>
            </tr>
        </table>
        """)
    section2_html = "\n".join(trade_cards_html)

    # 4. Section 3: Full-Width Priority Recommendation Cards
    rec_cards_html = []
    for idx, r in enumerate(recs):
        border_col = badge_colors[min(idx, len(badge_colors) - 1)]
        bg_col = "#f0fdf4" if idx == 0 else ("#eff6ff" if idx == 1 else "#fffbeb")
        rec_cards_html.append(f"""
        <table class="thesis-table">
            <tr>
                <td class="thesis-cell" style="border-left: 4px solid {border_col}; background-color: {bg_col};">
                    <div class="thesis-header">{r['rank']}. {r['role_title']}</div>
                    <div class="thesis-body">
                        <strong>{r['bullet_label']}{'：' if is_zh else ': '}</strong>{md_inline_to_html(r['description'])}
                    </div>
                </td>
            </tr>
        </table>
        """)
    section3_html = "\n".join(rec_cards_html)

    cjk_wrap_rule = "-pdf-word-wrap: CJK;\n        " if is_zh else ""
    font_face_str = _build_font_css()
    pdf_css = """
    @page {
        size: 112mm 220mm;
        margin: 4mm 5mm 4mm 5mm;
    }
    * {
        __CJK_WRAP__word-wrap: break-word;
    }
    body, h1, h2, h3, h4, div, p, span, td, th, li, strong {
        font-family: 'YaHei', 'Microsoft YaHei', 'SegoeUI', sans-serif;
        __CJK_WRAP__word-wrap: break-word;
    }
    body {
        font-size: 9.2pt;
        line-height: 1.42;
        background-color: #ffffff;
        color: #0f172a;
        margin: 0;
        padding: 0;
    }
    .header-banner {
        background-color: #0f172a;
        color: #ffffff;
        padding: 8px 10px;
        margin-bottom: 7px;
    }
    .header-banner h1 {
        margin: 0 0 2px 0;
        font-size: 12.5pt;
        font-weight: bold;
        color: #ffffff;
        line-height: 1.28;
    }
    .header-stocks {
        font-size: 10.8pt;
        font-weight: bold;
        color: #e2e8f0;
        margin-bottom: 4px;
        line-height: 1.32;
    }
    .header-banner .meta-row {
        font-size: 7.8pt;
        color: #cbd5e1;
        line-height: 1.38;
    }
    .kpi-card-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 6px;
        page-break-inside: avoid;
    }
    .kpi-card {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        padding: 7px 9px;
        vertical-align: top;
    }
    .kpi-title {
        font-size: 8.2pt;
        font-weight: bold;
        margin-bottom: 2px;
        line-height: 1.3;
    }
    .kpi-value {
        font-size: 12pt;
        font-weight: bold;
        color: #0f172a;
        margin-bottom: 3px;
    }
    .ticker-tag {
        font-size: 8.2pt;
        font-weight: normal;
        color: #64748b;
    }
    .kpi-line {
        font-size: 8.4pt;
        color: #334155;
        line-height: 1.38;
        margin-bottom: 1.5px;
    }
    h2 {
        font-size: 11pt;
        font-weight: bold;
        color: #0f172a;
        margin: 14px 0 6px 0;
        padding-top: 3px;
        padding-bottom: 3px;
        border-bottom: 1.5px solid #cbd5e1;
        page-break-after: avoid;
    }
    .dim-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 6px;
        page-break-inside: avoid;
    }
    .dim-hdr {
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: bold;
        font-size: 8.8pt;
        padding: 4.5px 7px;
        border: 1px solid #cbd5e1;
        text-align: left;
    }
    .dim-stock {
        background-color: #f8fafc;
        color: #0f172a;
        font-weight: bold;
        font-size: 8.3pt;
        padding: 4.5px 6px;
        border: 1px solid #cbd5e1;
        vertical-align: top;
        line-height: 1.38;
    }
    .dim-val {
        background-color: #ffffff;
        color: #1e293b;
        font-size: 8.3pt;
        padding: 4.5px 7px;
        border: 1px solid #cbd5e1;
        vertical-align: top;
        line-height: 1.38;
    }
    .cell-line {
        margin-bottom: 1.5px;
    }
    .sub-note {
        color: #475569;
        font-size: 7.7pt;
    }
    .code-val {
        color: #0f172a;
        font-weight: bold;
    }
    .trade-card-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 7px;
        page-break-inside: avoid;
    }
    .tc-hdr {
        background-color: #f1f5f9;
        color: #0f172a;
        font-size: 8.8pt;
        padding: 5px 7px;
        border: 1px solid #cbd5e1;
        text-align: left;
    }
    .tc-cell {
        background-color: #ffffff;
        padding: 4.5px 7px;
        border: 1px solid #cbd5e1;
        vertical-align: top;
    }
    .tc-label {
        font-size: 7.6pt;
        color: #64748b;
        margin-bottom: 1px;
    }
    .tc-val {
        font-size: 8.8pt;
        font-weight: bold;
        color: #0f172a;
        line-height: 1.32;
    }
    .tc-obs-cell {
        background-color: #f8fafc;
        padding: 5px 7px;
        border: 1px solid #cbd5e1;
    }
    .tc-obs {
        font-size: 8.2pt;
        color: #334155;
        line-height: 1.4;
    }
    .thesis-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 7px;
        page-break-inside: avoid;
    }
    .thesis-cell {
        border: 1px solid #cbd5e1;
        padding: 7px 9px;
        vertical-align: top;
    }
    .thesis-header {
        font-size: 9.4pt;
        font-weight: bold;
        color: #0f172a;
        margin-bottom: 3px;
        line-height: 1.35;
    }
    .thesis-body {
        font-size: 8.8pt;
        color: #1e293b;
        line-height: 1.46;
    }
    .disclaimer {
        font-size: 7.5pt;
        color: #64748b;
        margin-top: 12px;
        padding-top: 6px;
        border-top: 1px solid #cbd5e1;
        text-align: center;
        line-height: 1.4;
    }
    """
    pdf_css = pdf_css.replace("__CJK_WRAP__", cjk_wrap_rule)

    meta_line1 = f"对比标的: {tickers_str}" if is_zh else f"Tickers: {tickers_str}"
    meta_line2 = (
        f"投研日期: {analysis_date} ｜ 时间级别: 日线级别 ｜ 数据周期: 近1年 ｜ 结算货币: {curr_label}"
        if is_zh
        else f"Date: {analysis_date} | Timeframe: Daily | Period: 1Y | Currency: {curr_label}"
    )
    title_txt = "投资对比研判报告" if is_zh else "Investment Comparison Report"
    sec1_title = "一、核心量化与基本面对比矩阵" if is_zh else "1. Core Quantitative & Fundamental Matrix"
    sec2_title = "二、战术交易点位与风控对比" if is_zh else "2. Tactical Trade Setup & Risk Control"
    sec3_title = "三、机构综合排序与配置建议" if is_zh else "3. Institutional Priority Ranking & Recommendations"
    disclaimer_txt = (
        "免责声明：本投资对比研判报告由量化投研模型自动生成，融合量化技术指标与财务报表数据。<br/>仅供学习、研究与交流讨论，不构成任何投资建议、买卖要约或推荐。金融市场具有高波动性与本金损失风险，投资需独立审慎决策。"
        if is_zh
        else "Disclaimer: This investment comparison report was generated automatically by a quantitative research model integrating technical indicators and financial statement data.<br/>For educational and research purposes only; not investment advice. Financial markets carry high volatility and risk of loss."
    )

    pdf_html = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if is_zh else 'en'}">
<head>
    <meta charset="UTF-8">
    <title>Multi-Stock Comparison Report</title>
    <style>
{font_face_str}
{pdf_css}
    </style>
</head>
<body>
    <div class="header-banner">
        <h1>{title_txt}</h1>
        <div class="header-stocks">{names_str}</div>
        <div class="meta-row">{meta_line1}<br/>{meta_line2}</div>
    </div>

    {kpi_stack_html}

    <h2>{sec1_title}</h2>
    {section1_html}

    <h2>{sec2_title}</h2>
    {section2_html}

    <h2>{sec3_title}</h2>
    {section3_html}

    <div class="disclaimer">{disclaimer_txt}</div>
</body>
</html>"""

    def link_callback(uri, rel):
        fname = os.path.basename(uri)
        target = os.path.join(FONT_DIR, fname)
        if os.path.exists(target):
            return target
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
        return uri

    from contextlib import nullcontext
    try:
        from xhtml2pdf.config.resources import ResourceAccessPolicy, use_policy
        policy_ctx = lambda: use_policy(ResourceAccessPolicy(allow_local_outside_base=True))
    except ImportError:
        policy_ctx = nullcontext

    try:
        with policy_ctx(), open(output_pdf_path, "wb") as f:
            status = pisa.CreatePDF(pdf_html, dest=f, link_callback=link_callback, encoding="utf-8")
        return not status.err
    except Exception as e:
        print(f"PDF generation error: {e}", file=sys.stderr)
        return False


def locate_or_generate_stock_json(ticker_or_name: str, base_output_dir: str, period: str = "1y", interval: str = "1d") -> dict:
    """Find the most recent <ticker>_data.json in base_output_dir, or run analyze_stock.py if missing."""
    # Search existing folders matching ticker_or_name, preferring exact match or most recently modified JSON
    if os.path.exists(base_output_dir):
        candidates = []
        for entry in os.listdir(base_output_dir):
            full_sub = os.path.join(base_output_dir, entry)
            if os.path.isdir(full_sub) and (ticker_or_name.upper() in entry.upper() or ticker_or_name in entry):
                jsons = glob.glob(os.path.join(full_sub, "*_data.json"))
                for jp in jsons:
                    if os.path.basename(jp) == "comparison_data.json":
                        continue
                    candidates.append((entry.upper() == ticker_or_name.upper(), os.path.getmtime(jp), jp))
        if candidates:
            candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
            with open(candidates[0][2], "r", encoding="utf-8") as f:
                return json.load(f)

    # If not found, run analyze_stock.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    analyze_script = os.path.join(script_dir, "analyze_stock.py")
    cmd = [sys.executable, analyze_script, "--ticker", ticker_or_name, "--period", period, "--interval", interval, "--output-dir", base_output_dir]
    subprocess.run(cmd, check=True)

    for entry in os.listdir(base_output_dir):
        full_sub = os.path.join(base_output_dir, entry)
        if os.path.isdir(full_sub) and (ticker_or_name.upper() in entry.upper() or ticker_or_name in entry):
            jsons = glob.glob(os.path.join(full_sub, "*_data.json"))
            if jsons:
                with open(jsons[0], "r", encoding="utf-8") as f:
                    return json.load(f)
    raise FileNotFoundError(f"Could not find or generate data JSON for {ticker_or_name}")


def main():
    parser = argparse.ArgumentParser(description="Generate Multi-Stock Horizontal Comparison & Configuration Priority Report")
    parser.add_argument("--tickers", nargs="+", required=True, help="List of tickers or stock names to compare (e.g. 603155.SS 002516.SZ 600893.SS)")
    parser.add_argument("--output-dir", type=str, default="./stock_analysis_output", help="Base output directory")
    parser.add_argument("--subfolder", type=str, default=None, help="Custom subfolder name for the comparison report")
    parser.add_argument("--report-name", type=str, default=None, help="Custom base filename for the comparison report")
    parser.add_argument("--period", type=str, default="1y", help="Period if running analyze_stock.py")
    parser.add_argument("--interval", type=str, default="1d", help="Interval if running analyze_stock.py")
    parser.add_argument("--lang", type=str, default="auto", choices=["auto", "en", "zh"], help="Report language (auto detects from stock names/metadata)")
    args = parser.parse_args()

    raw_items = []
    for tk in args.tickers:
        data = locate_or_generate_stock_json(tk, args.output_dir, period=args.period, interval=args.interval)
        raw_items.append(data)

    if args.lang == "auto":
        is_zh = any(
            it.get("metadata", {}).get("language") == "zh"
            or any("\u4e00" <= ch <= "\u9fff" for ch in str(it.get("metadata", {}).get("company_name", "")))
            for it in raw_items
        )
    else:
        is_zh = (args.lang == "zh")

    # Sort items by composite priority score descending
    scored_items = sorted(raw_items, key=compute_Composite_Rank_Score, reverse=True)

    input_names = [it["metadata"]["company_name"] for it in raw_items]
    sorted_names = [it["metadata"]["company_name"] for it in scored_items]

    if is_zh:
        subfolder_name = args.subfolder or f"投资对比研判报告 - {'_'.join(input_names)}"
        report_base = args.report_name or f"{'_'.join(input_names)}_投资对比研判报告"
    else:
        subfolder_name = args.subfolder or f"Investment Comparison Report - {'_'.join(input_names)}"
        report_base = args.report_name or f"{'_'.join(input_names)}_Investment_Comparison_Report"

    target_dir = os.path.join(args.output_dir, subfolder_name)
    os.makedirs(target_dir, exist_ok=True)

    md_path = os.path.join(target_dir, f"{report_base}.md")
    html_path = os.path.join(target_dir, f"{report_base}.html")
    pdf_path = os.path.join(target_dir, f"{report_base}.pdf")
    json_path = os.path.join(target_dir, "comparison_data.json")

    align_ttm = should_align_ttm(scored_items)
    rows = format_stock_row_cells(scored_items, is_zh=is_zh)
    recs = [build_priority_recommendation(it, idx, len(scored_items), is_zh=is_zh, align_ttm=align_ttm) for idx, it in enumerate(scored_items)]

    generate_comparison_markdown(scored_items, recs, rows, md_path, args.output_dir, is_zh=is_zh)
    generate_comparison_html(scored_items, recs, rows, html_path, args.output_dir, is_zh=is_zh)
    generate_comparison_pdf(scored_items, recs, rows, pdf_path, is_zh=is_zh)

    comp_json = {
        "analysis_date": scored_items[0]["metadata"].get("analysis_date"),
        "input_stocks": input_names,
        "ranked_stocks": sorted_names,
        "recommendations": recs,
        "deliverables": {
            "output_dir": target_dir,
            "report_md": md_path,
            "report_html": html_path,
            "report_pdf": pdf_path,
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comp_json, f, ensure_ascii=False, indent=2)

    rank_order_str = " > ".join([f"{r['rank']}.{r['company_name']}" for r in recs])
    print("=================================================================")
    print(f"投资对比研判报告: {'、'.join(input_names)}")
    print("=================================================================")
    print(f"配置优先级排序: {rank_order_str}")
    print(f"输出目录:       {target_dir}")
    print(f"Markdown报告:   {md_path}")
    print(f"HTML交互报告:   {html_path}")
    print(f"PDF打印版报告:  {pdf_path}")
    print(f"结构化数据:     {json_path}")
    print("=================================================================")


if __name__ == "__main__":
    main()
