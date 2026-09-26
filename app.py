"""Frontier Horizon, an evidence-first forecasting and FIRE dashboard.

Deploy with: streamlit run app.py
Optional secrets.toml:
POLYMARKET_SLUGS = "comma,separated,event,slugs"
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Frontier Horizon | Evidence-first", page_icon="📊", layout="wide")

TARGET_HUF = 60_000_000
DEFAULT_EVENTS = [
    {
        "topic": "AI model releases",
        "claim": "Exact release dates are not reliably forecastable without a liquid, correctly-worded market.",
        "probability": None,
        "source": "No default forecast",
        "source_url": "",
        "resolution_date": None,
        "status": "Needs evidence",
    },
    {
        "topic": "Longevity escape velocity",
        "claim": "There is no validated date forecast for personal longevity escape velocity.",
        "probability": None,
        "source": "No default forecast",
        "source_url": "",
        "resolution_date": None,
        "status": "Not forecastable",
    },
]


def budapest_today() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Budapest")).date()
    except Exception:
        return date.today()


def configured_slugs() -> list[str]:
    try:
        raw = st.secrets.get("POLYMARKET_SLUGS", os.environ.get("POLYMARKET_SLUGS", ""))
    except Exception:
        raw = os.environ.get("POLYMARKET_SLUGS", "")
    return [slug.strip() for slug in str(raw).split(",") if slug.strip()]


@st.cache_data(ttl=900, show_spinner=False)
def fetch_polymarket_event(slug: str) -> dict[str, Any]:
    """Fetch one event. It deliberately returns an error state instead of inventing data."""
    url = "https://gamma-api.polymarket.com/events"
    try:
        response = requests.get(url, params={"slug": slug}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return {"slug": slug, "error": "No event found"}
        event = payload[0]
        rows: list[dict[str, Any]] = []
        for market in event.get("markets", []):
            try:
                outcomes = json.loads(market.get("outcomes", "[]"))
                prices = json.loads(market.get("outcomePrices", "[]"))
            except (json.JSONDecodeError, TypeError):
                outcomes, prices = [], []
            for outcome, price in zip(outcomes, prices):
                try:
                    implied_probability = float(price) * 100
                except (TypeError, ValueError):
                    implied_probability = None
                rows.append(
                    {
                        "question": market.get("question", "Untitled market"),
                        "outcome": outcome,
                        "implied_probability_pct": implied_probability,
                        "volume_usd": float(market.get("volumeNum") or 0),
                        "liquidity_usd": float(market.get("liquidityNum") or 0),
                        "end_date": market.get("endDate"),
                    }
                )
        return {"slug": slug, "title": event.get("title", slug), "rows": rows}
    except requests.RequestException as exc:
        return {"slug": slug, "error": f"Data request failed: {exc.__class__.__name__}"}


def monthly_projection(
    opening_huf: float, monthly_contribution_huf: float, annual_nominal_return: float,
    annual_inflation: float, years: int,
) -> pd.DataFrame:
    monthly_return = (1 + annual_nominal_return / 100) ** (1 / 12) - 1
    monthly_inflation = (1 + annual_inflation / 100) ** (1 / 12) - 1
    balance = opening_huf
    rows = []
    for month in range(years * 12 + 1):
        real_balance = balance / ((1 + monthly_inflation) ** month)
        rows.append({"month": month, "nominal_huf": balance, "real_huf_today": real_balance})
        balance = (balance + monthly_contribution_huf) * (1 + monthly_return)
    return pd.DataFrame(rows)


def first_target_month(series: pd.Series, target: float) -> int | None:
    matches = series[series >= target]
    return None if matches.empty else int(matches.index[0])


st.title("📊 Frontier Horizon")
st.caption("Evidence-first probabilities and a Hungary-centred FIRE calculator. Not investment, medical, or political advice.")

with st.expander("Forecasting rules", expanded=True):
    st.markdown(
        """
- A market price is an **implied probability**, not a fact or a promise.
- The dashboard does not fabricate exact model-release dates, AGI/ASI dates, mathematics breakthroughs, or longevity outcomes.
- Forecasts need a resolvable question, source URL, observation date, and eventual outcome before accuracy can be scored.
- Thin markets, ambiguous resolution rules, and correlated sources should receive less weight.
        """
    )

forecast_tab, wealth_tab, audit_tab = st.tabs(["🔎 Forecasts", "💰 HUF FIRE scenario", "🧾 Audit log"])

with forecast_tab:
    st.subheader("Live prediction-market evidence")
    slugs = configured_slugs()
    if not slugs:
        st.info("No prediction-market slugs configured. Add `POLYMARKET_SLUGS` to Streamlit secrets or the environment. The dashboard will not substitute made-up odds.")
    else:
        for slug in slugs:
            event = fetch_polymarket_event(slug)
            if "error" in event:
                st.warning(f"{slug}: {event['error']}")
                continue
            st.markdown(f"#### {event['title']}")
            market_df = pd.DataFrame(event["rows"])
            if market_df.empty:
                st.warning("The event returned no readable market outcomes.")
            else:
                st.dataframe(market_df, hide_index=True, use_container_width=True)
                st.caption(f"Source: https://polymarket.com/event/{slug}. Refreshed {datetime.now().strftime('%Y-%m-%d %H:%M local time')}. ")

    st.subheader("Forecast register")
    st.caption("Enter claims with sources. Leave probability blank when the claim cannot be quantified responsibly.")
    register = st.data_editor(
        pd.DataFrame(DEFAULT_EVENTS),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "probability": st.column_config.NumberColumn("Probability (%)", min_value=0.0, max_value=100.0, format="%.1f"),
            "source_url": st.column_config.LinkColumn("Source URL"),
            "resolution_date": st.column_config.DateColumn("Resolution date"),
            "status": st.column_config.SelectboxColumn("Status", options=["Needs evidence", "Open", "Resolved", "Not forecastable"]),
        },
        key="forecast_register",
    )
    quantifiable = register.dropna(subset=["probability"])
    if not quantifiable.empty:
        st.caption(f"{len(quantifiable)} quantified claim(s). Do not aggregate them, they may be correlated or refer to different outcomes.")

with wealth_tab:
    st.subheader("60M HUF milestone, scenario analysis")
    st.caption("Nominal figures are converted to today’s HUF using your inflation assumption. TBSZ tax treatment depends on the account’s legal conditions and holding period, verify it with your provider or tax adviser.")
    left, right = st.columns([1, 2])
    with left:
        opening = st.number_input("Opening invested balance (HUF)", min_value=0, value=2_500_000, step=100_000)
        monthly = st.number_input("Monthly contribution (HUF)", min_value=0, value=120_000, step=10_000)
        nominal_return = st.slider("Annual nominal return assumption (%)", 0.0, 12.0, 7.0, 0.5)
        inflation = st.slider("Annual HUF inflation assumption (%)", 0.0, 12.0, 4.0, 0.5)
        horizon = st.slider("Projection horizon (years)", 5, 40, 20)
        target_mode = st.radio("Target definition", ["60M nominal HUF", "60M HUF in today’s purchasing power"])

    projection = monthly_projection(float(opening), float(monthly), nominal_return, inflation, horizon)
    target_series = projection["nominal_huf"] if target_mode == "60M nominal HUF" else projection["real_huf_today"]
    hit_month = first_target_month(target_series, TARGET_HUF)
    with right:
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=projection["month"] / 12, y=projection["nominal_huf"], name="Nominal HUF", line=dict(color="#22c55e", width=3)))
        figure.add_trace(go.Scatter(x=projection["month"] / 12, y=projection["real_huf_today"], name="Real HUF, today’s value", line=dict(color="#60a5fa", width=3)))
        figure.add_hline(y=TARGET_HUF, line_dash="dash", line_color="#f59e0b", annotation_text="60M HUF target")
        figure.update_layout(template="plotly_dark", xaxis_title="Years", yaxis_title="HUF", margin=dict(l=20, r=20, t=25, b=20), height=420)
        st.plotly_chart(figure, use_container_width=True)

    if hit_month is None:
        st.warning("The selected scenario does not reach the target within the chosen horizon.")
    else:
        years, months = divmod(hit_month, 12)
        st.success(f"Selected scenario reaches the 60M HUF target after approximately {years} years and {months} months.")
    real_return = ((1 + nominal_return / 100) / (1 + inflation / 100) - 1) * 100
    st.caption(f"Implied real return before costs and taxes: {real_return:.2f}% per year. This is an assumption, not a forecast of VUAA returns or EUR/HUF exchange rates.")

with audit_tab:
    st.subheader("What this version deliberately removed")
    st.markdown(
        """
- Unsupported precise release dates and Gaussian probability curves.
- Invented model names and claims presented as active market evidence.
- Exact AGI, ASI, LEV, death, and Millennium Prize solution countdowns.
- Personal-impact percentages with no observable definition or calibration history.

A dashboard becomes more useful when uncertainty is visible. Add only claims that can later be resolved and scored.
        """
    )
    st.subheader("How to score resolved forecasts")
    st.code("Brier score = (forecast_probability / 100 - outcome)^2\n# outcome is 1 if the claim resolved true, otherwise 0\n# lower is better, 0 is perfect, 0.25 equals a 50% forecast")
    st.caption(f"Dashboard date: {budapest_today().isoformat()} (Europe/Budapest where available).")
