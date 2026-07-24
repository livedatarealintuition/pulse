"""
Pulse Core — AI prompt builder and LLM provider caller.
No Flask/Supabase dependencies — pure functions.
"""
from typing import Dict, List, Any
import requests
from requests.exceptions import Timeout as ReqTimeout
from requests.exceptions import ConnectionError as ReqConnectionError


# ----- Prompt Templates -----
_PROMPT_STRICT = """You are a strict risk-focused portfolio auditor. Be blunt about problems. Recommend concrete sell/stop-loss actions. Report in {lang}. Use markdown.

Portfolio Summary: {summary}
Allocation: {alloc}

Holdings:
{holdings}

Required Sections:
1. Risk Audit — Flag EVERY danger, stop-loss violation, concentration issue
2. Stop-Loss Compliance — Which holdings violated stops? Immediate actions required
3. Sell Recommendations — Which positions to exit NOW and why
4. Max 3 Hold/Buy picks with brief justification

Be direct. No sugar-coating."""

_PROMPT_RELAXED = """You are an optimistic growth-focused portfolio coach. Highlight strengths and future potential. Suggest adding to winners. Report in {lang}. Use markdown.

Portfolio Summary: {summary}
Allocation: {alloc}

Holdings:
{holdings}

Required Sections:
1. Growth Outlook — Market trends and tailwinds benefiting the portfolio
2. Strength Analysis — What each holding is doing RIGHT
3. Opportunity Spotting — Undervalued positions, add-more candidates
4. Portfolio Expansion — New sectors or themes to consider

Be encouraging. Focus on upside."""

_PROMPT_BALANCED = """You are a professional portfolio analyst. Provide a comprehensive portfolio analysis report in {lang}. Use markdown formatting with clear section headers.

## Portfolio Overview
- Total Market Value: ${total_mv_usd:,.2f} USD
- Total Cost Basis: ${total_open_cost_usd:,.2f} USD
- Total P&L: ${total_pnl:+,.2f} USD ({total_roi:+.2f}%)
- Number of Holdings: {num_holdings}

## Market Allocation
{alloc}

## Holdings Detail
{holdings}

## Required Analysis Sections
1. Overall Assessment
2. Per-Stock Analysis
3. Risk Alerts
4. Actionable Suggestions

Keep it concise. Use a summary table."""


def build_ai_prompt(
    open_stocks: List[Dict],
    total_mv_usd: float,
    total_open_cost_usd: float,
    total_pnl: float = None,
    total_roi: float = None,
    lang: str = "Traditional Chinese (繁體中文)",
    prompt_level: str = "balanced",
    custom_prompt: str = "",
    prompt_mode: str = "style",
    allocation_str: str = "",
) -> str:
    """
    Build the AI audit prompt string.

    Args:
        open_stocks: List of processed holdings from calculate_portfolio_matrix() (status='OPEN' only)
        total_mv_usd, total_open_cost_usd: Portfolio totals
        lang: Language name for the LLM (e.g. "Traditional Chinese (繁體中文)")
        prompt_level: "strict", "balanced", "relaxed"
        custom_prompt: Custom prompt template with {summary}, {holdings}, {alloc}, {lang}
        prompt_mode: "style" or "custom"
        allocation_str: Pre-built allocation string (multiline)

    Returns:
        Prompt string ready to send to LLM
    """
    if total_pnl is None:
        total_pnl = total_mv_usd - total_open_cost_usd
    if total_roi is None:
        total_roi = (total_pnl / total_open_cost_usd * 100) if total_open_cost_usd > 0 else 0

    num_holdings = len(open_stocks)

    # Build holding lines
    holding_lines = []
    for s in open_stocks:
        danger = " ⚠️ STOP-LOSS TRIGGERED" if s.get("is_danger") else ""
        holding_lines.append(
            f"${s['ticker']} [{s.get('market', 'US')}] | Shares: {s['total_shares']} | "
            f"Avg Cost: ${s['avg_buy_price']} | Current: ${s['current_price']} | "
            f"P&L: {s['pnl_usd_str']} | ROI: {s['roi_str']}{danger}"
        )
    holdings_str = "\n".join(holding_lines)

    # Build summary/alloc strings for custom prompt
    summary_str = (
        f"Total MV: ${total_mv_usd:,.2f}, Cost: ${total_open_cost_usd:,.2f}, "
        f"PnL: ${total_pnl:+,.2f} ({total_roi:+.2f}%), Holdings: {num_holdings}"
    )
    alloc_compact = allocation_str.replace("\n", "; ") if allocation_str else "N/A"

    if prompt_mode == "custom" and custom_prompt.strip():
        prompt_text = custom_prompt.replace("{summary}", summary_str)
        prompt_text = prompt_text.replace("{holdings}", holdings_str)
        prompt_text = prompt_text.replace("{alloc}", alloc_compact)
        if "{lang}" in custom_prompt:
            prompt_text = prompt_text.replace("{lang}", lang)
        else:
            prompt_text += f"\n\nRespond in {lang}."
        return prompt_text

    if prompt_level == "strict":
        return _PROMPT_STRICT.format(
            lang=lang, summary=summary_str, alloc=allocation_str,
            holdings=holdings_str,
        )
    elif prompt_level == "relaxed":
        return _PROMPT_RELAXED.format(
            lang=lang, summary=summary_str, alloc=allocation_str,
            holdings=holdings_str,
        )
    else:  # balanced
        return _PROMPT_BALANCED.format(
            lang=lang,
            total_mv_usd=total_mv_usd,
            total_open_cost_usd=total_open_cost_usd,
            total_pnl=total_pnl,
            total_roi=total_roi,
            num_holdings=num_holdings,
            alloc=allocation_str,
            holdings=holdings_str,
        )


def call_ai_provider(
    prompt_text: str,
    provider: str = "gemini",
    model_name: str = "gemini-2.5-flash",
    api_key: str = "",
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/models/",
    timeout: int = 60,
) -> tuple:
    """
    Call the AI provider and return (success: bool, content: str or error_message: str).
    """
    try:
        if provider == "gemini":
            if not base_url.endswith("/"):
                base_url += "/"
            url = f"{base_url}{model_name}:generateContent?key={api_key}"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt_text}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            report = data["candidates"][0]["content"]["parts"][0]["text"]
            return True, report
        else:
            # OpenAI-compatible (DeepSeek, Ollama, vLLM, LM Studio, etc.)
            url = base_url
            if not url.endswith("/chat/completions"):
                if not url.endswith("/"):
                    url += "/"
                url += "chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": model_name, "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.3}
            res = requests.post(url, json=payload, headers=headers, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            report = data["choices"][0]["message"]["content"]
            return True, report
    except ReqTimeout:
        return False, "Request timed out. Try increasing the timeout in Settings → AI Model."
    except ReqConnectionError:
        return False, "Cannot connect to AI server. Check your API URL in Settings → AI Model."
    except Exception as e:
        return False, f"AI call failed: {str(e)[:200]}"
