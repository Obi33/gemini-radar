"""Frontier Horizon â€” evidence-first AI markets and personal decision dashboard.
Run: pip install streamlit requests pandas plotly ; streamlit run frontier_horizon.py
Public Polymarket Gamma data; no API key required. Forecast journal is local to this
Streamlit session unless exported and later imported.
"""

import json
import math
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Frontier Horizon Â· Signals, not certainty", page_icon="â—ˆ", layout="wide", initial_sidebar_state="collapsed")

SEEDS = {
    "Google": [
        "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068",
        "next-google-gemini-pro-model-released-byptptpt",
        "next-gemini-flash-model-3pt9-released-byptptpt",
        "next-google-gemini-flash-lite-model-3pt6-released-byptptpt",
    ],
    "Anthropic": [
        "claude-6-released-byptptpt",
        "next-claude-sonnet-released-byptptpt-20260701203831153",
        "next-claude-haiku-released-byptptpt-20260701205353326",
        "next-fable-model-5pt2-released-byptptpt",
    ],
    "OpenAI": [
        "gpt-7-released-byptptpt",
        "gpt-astra-6pt1-released-byptptpt",
        "next-openai-gpt-terra-5pt7-released-byptptpt",
    ],
    "Cross-lab": ["which-company-has-best-ai-model-end-of-2026"],
}

st.markdown("""
<style>
:root{color-scheme:dark}
.stApp{background:radial-gradient(ellipse at 80% -10%,#20394b 0%,transparent 38%),#09131d;color:#e6f1f4}
.block-container{max-width:1220px;padding-top:1.1rem;padding-bottom:4rem}
h1,h2,h3{letter-spacing:-.025em}
h1{font-size:clamp(2.05rem,5vw,4.2rem)!important;line-height:1.03!important}
[data-testid="stMetric"]{background:#12232e;border:1px solid #31505d;border-radius:18px;padding:14px;min-height:112px}
[data-testid="stMetricValue"]{font-size:clamp(1.3rem,3vw,2.1rem)}
div.stButton>button{min-height:44px;border-radius:12px}
.hero{padding:clamp(18px,4vw,34px);border:1px solid #345766;border-radius:24px;background:linear-gradient(130deg,#122a36,#10202b 65%,#183432);margin:0 0 1rem}
.kicker{font-size:.76rem;letter-spacing:.18em;color:#66dac7;text-transform:uppercase;font-weight:700}
.hero p{color:#b7cad0;max-width:720px;margin-bottom:0}
.badge{display:inline-block;background:#163c39;color:#a7f1db;padding:5px 10px;border-radius:20px;font-size:.78rem;margin-top:12px}
a{color:#8de8d1!important;overflow-wrap:anywhere}
@media(max-width:640px){.block-container{padding-left:1rem;padding-right:1rem;padding-top:.6rem}.hero{border-radius:16px}[data-testid="stMetric"]{min-height:95px}div[data-testid="stHorizontalBlock"]{gap:.55rem}}
</style>
""", unsafe_allow_html=True)


def as_array(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (ValueError, TypeError):
        return []


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def date_label(value):
    if not value:
        return "â€”"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return "â€”"


def event_link(slug):
    return "https://polymarket.com/event/" + quote(slug, safe="")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_event(slug):
    try:
        response = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=8,
                                headers={"Accept": "application/json", "User-Agent": "FrontierHorizon/2.0"})
        response.raise_for_status()
        events = response.json()
        if not isinstance(events, list) or not events:
            return {"slug": slug, "error": "Event not found"}
        event = next((e for e in events if e.get("slug") == slug), None)
        if event is None:
            return {"slug": slug, "error": "No exact slug match"}
        return event
    except (requests.RequestException, ValueError) as exc:
        return {"slug": slug, "error": f"Data unavailable ({type(exc).__name__})"}


def normalize_event(event, lab):
    slug = event["slug"]
    title = str(event.get("title") or slug)
    rows = []
    for market in event.get("markets") or []:
        outcomes = as_array(market.get("outcomes"))
        prices = as_array(market.get("outcomePrices"))
        yes = next((finite_number(prices[i]) for i, outcome in enumerate(outcomes)
                    if str(outcome).casefold() == "yes" and i < len(prices)), None)
        if yes is not None and not 0 <= yes <= 1:
            yes = None
        bid, ask = finite_number(market.get("bestBid")), finite_number(market.get("bestAsk"))
        spread = (ask - bid) * 100 if bid is not None and ask is not None and 0 <= bid <= ask <= 1 else None
        volume = finite_number(market.get("volumeNum"))
        if volume is None:
            volume = finite_number(market.get("volume"))
        liquidity = finite_number(market.get("liquidityNum"))
        if liquidity is None:
            liquidity = finite_number(market.get("liquidity"))
        closed = bool(event.get("closed") or market.get("closed"))
        rows.append({
            "Lab": lab, "Event": title, "Contract": str(market.get("groupItemTitle") or market.get("question") or "Untitled"),
            "Question": str(market.get("question") or ""), "YES %": round(yes * 100, 1) if yes is not None else None,
            "Volume USD": volume, "Liquidity USD": liquidity, "Bidâ€“ask pp": round(spread, 2) if spread is not None else None,
            "Status": "Closed" if closed else ("Active" if market.get("active", event.get("active", False)) else "Inactive"),
            "Closes": date_label(market.get("endDate") or event.get("endDate")),
            "Updated": date_label(market.get("updatedAt") or event.get("updatedAt")),
            "Event slug": slug, "Market ID": str(market.get("id") or ""), "URL": event_link(slug),
            "Definition": str(market.get("description") or event.get("description") or ""),
        })
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def load_events(slugs_by_lab):
    rows, failures, events = [], [], []
    for lab, slugs in slugs_by_lab.items():
        for slug in slugs:
            event = fetch_event(slug)
            if "error" in event:
                failures.append({"Lab": lab, "Slug": slug, "Reason": event["error"]})
                continue
            events.append(event)
            rows.extend(normalize_event(event, lab))
    return rows, failures, events, datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def signal(row):
    if row["Status"] != "Active" or row["YES %"] is None:
        return "Not actionable"
    if (row["Liquidity USD"] is not None and row["Liquidity USD"] < 1000) or (row["Bidâ€“ask pp"] is not None and row["Bidâ€“ask pp"] > 10):
        return "Thin / wide spread"
    if row["Bidâ€“ask pp"] is None or row["Liquidity USD"] is None:
        return "Depth unknown"
    return "Quote available"


def table(rows):
    columns = ["Lab", "Event", "Contract", "YES %", "Status", "Signal", "Volume USD", "Liquidity USD", "Bidâ€“ask pp", "Closes", "URL"]
    frame = pd.DataFrame([{**row, "Signal": signal(row)} for row in rows])
    return frame.reindex(columns=columns)


def plot_rows(rows):
    ranked = sorted((r for r in rows if r["YES %"] is not None and r["Status"] == "Active"),
                    key=lambda r: r["YES %"], reverse=True)[:14]
    if not ranked:
        return None
    ranked.reverse()
    colors = {"Google": "#52c3ff", "Anthropic": "#ffa765", "OpenAI": "#7ae6af", "Cross-lab": "#c7abff", "Custom": "#e9da80"}
    fig = go.Figure(go.Bar(x=[r["YES %"] for r in ranked], y=[(r["Contract"][:34] + "â€¦") if len(r["Contract"]) > 35 else r["Contract"] for r in ranked],
                           orientation="h", marker_color=[colors.get(r["Lab"], "#75dcca") for r in ranked],
                           customdata=[[r["Lab"], r["Event"]] for r in ranked],
                           hovertemplate="%{customdata[0]} Â· %{customdata[1]}<br>%{y}: %{x:.1f}% YES<extra></extra>"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=8, r=12, t=8, b=25), height=max(280, 39 * len(ranked)),
                      xaxis=dict(title="Current YES quote (%)", range=[0, 100], gridcolor="#27404a"),
                      yaxis=dict(automargin=True), font=dict(size=12))
    return fig


if "slugs" not in st.session_state:
    st.session_state.slugs = []
if "journal" not in st.session_state:
    st.session_state.journal = []

st.markdown('<div class="hero"><div class="kicker">â—ˆ Frontier Horizon / Intelligence desk</div>'
            '<h1>Signals, not certainty.</h1><p>Track verifiable AI prediction-market quotes, inspect their limits, '
            'and stress-test your financial runway. No synthetic AGI dates, invented longevity odds, or AI-generated probabilities.</p>'
            '<span class="badge">LIVE MARKET DATA Â· 5-MIN CACHE Â· NO API KEY</span></div>', unsafe_allow_html=True)

with st.expander("âš™ï¸ Sources and controls", expanded=False):
    st.caption("Starter event slugs are checked against the live API; missing or closed events are reported, never silently replaced. Add an exact Polymarket event slug or event URL.")
    with st.form("add_slug", clear_on_submit=True):
        entry = st.text_input("Event slug or Polymarket event link", placeholder="https://polymarket.com/event/â€¦")
        add = st.form_submit_button("Add event", use_container_width=True)
    if add:
        slug = entry.strip().split("?")[0].rstrip("/").split("/")[-1]
        if not re.fullmatch(r"[a-z0-9-]{3,160}", slug):
            st.warning("Enter a valid event slug or Polymarket event link.")
        elif slug not in st.session_state.slugs and slug not in sum(SEEDS.values(), []):
            st.session_state.slugs.append(slug)
            st.rerun()
        else:
            st.info("This event is already on the desk.")
    if st.session_state.slugs:
        remove = st.selectbox("Remove a custom event", st.session_state.slugs)
        if st.button("Remove selected event"):
            st.session_state.slugs.remove(remove)
            st.rerun()
    if st.button("â†» Refresh live quotes", use_container_width=True):
        fetch_event.clear()
        load_events.clear()
        st.rerun()

source_map = {**SEEDS, "Custom": st.session_state.slugs}
with st.spinner("Checking public market eventsâ€¦"):
    rows, failures, events, fetched_at = load_events(source_map)
active = [r for r in rows if r["Status"] == "Active" and r["YES %"] is not None]

nav = st.selectbox("Workspace", ["Overview", "Market explorer", "Capital lab", "Forecast journal", "Method & sources"],
                   help="One-column navigation stays usable on narrow screens.")

if nav == "Overview":
    st.subheader("Desk pulse")
    a, b, c = st.columns(3)
    a.metric("Active quoted contracts", len(active))
    b.metric("Events retrieved", len(events))
    c.metric("Unresolved sources", len(failures))
    st.caption(f"Fetched {fetched_at}. Quotes are market prices, not guarantees; refresh manually for a new snapshot.")
    if failures:
        st.warning(f"{len(failures)} starter/custom events could not be verified. Inspect Method & sources for details.")
    if active:
        selected_lab = st.selectbox("Focus lab", ["All", "Google", "Anthropic", "OpenAI", "Cross-lab", "Custom"])
        visible = active if selected_lab == "All" else [r for r in active if r["Lab"] == selected_lab]
        fig = plot_rows(visible)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Bars show current YES quotes across different contracts. They are not a coherent probability distribution and must not be summed.")
        st.dataframe(table(visible), use_container_width=True, hide_index=True, height=310)
    else:
        st.info("No active YES quotes retrieved. Check the source log or add a current event in Sources and controls.")

elif nav == "Market explorer":
    st.subheader("Market explorer")
    st.caption("Search the exact contracts and inspect definitions before interpreting any quote.")
    query = st.text_input("Search event, contract, or lab")
    labs = st.multiselect("Labs", list(source_map), default=list(source_map))
    only_active = st.checkbox("Active contracts only", value=True)
    subset = [r for r in rows if r["Lab"] in labs and (not only_active or r["Status"] == "Active")
              and query.casefold() in (r["Event"] + " " + r["Contract"] + " " + r["Lab"]).casefold()]
    if subset:
        display = table(subset)
        st.dataframe(display, use_container_width=True, hide_index=True, height=420,
                     column_config={"URL": st.column_config.LinkColumn("Source event", display_text="Open â†—"),
                                    "YES %": st.column_config.NumberColumn("YES %", format="%.1f%%"),
                                    "Volume USD": st.column_config.NumberColumn("Volume USD", format="$%.0f"),
                                    "Liquidity USD": st.column_config.NumberColumn("Liquidity USD", format="$%.0f")})
        st.download_button("â†“ Export visible contracts (CSV)", display.to_csv(index=False).encode("utf-8"),
                           file_name="frontier_market_snapshot.csv", mime="text/csv", use_container_width=True)
        names = [f"{i+1}. {r['Lab']} Â· {r['Contract'][:75]}" for i, r in enumerate(subset)]
        chosen = subset[names.index(st.selectbox("Inspect a contract", names))]
        st.markdown(f"### {escape(chosen['Contract'])}")
        st.write(chosen["Question"])
        st.caption(f"YES: {chosen['YES %'] if chosen['YES %'] is not None else 'unavailable'}% Â· {chosen['Status']} Â· {signal(chosen)} Â· Closes {chosen['Closes']}")
        st.write("Resolution wording / description:")
        st.write(chosen["Definition"] or "Not supplied by this API response; read the original event before relying on this quote.")
        st.link_button("Open original event â†—", chosen["URL"], use_container_width=True)
        if chosen["Bidâ€“ask pp"] is None:
            st.info("Bid/ask data is absent or invalid. The displayed YES quote may not be executable at that price.")
    else:
        st.info("No contracts match these filters. Try disabling 'Active contracts only' or adding a current event.")

elif nav == "Capital lab":
    st.subheader("Capital lab Â· HUF")
    st.caption("Scenario arithmetic, not a return forecast. No AI-market signal is used to predict stock returns or longevity.")
    current = st.number_input("Invested capital (HUF)", min_value=0, value=0, step=100000)
    monthly = st.number_input("Monthly contribution (HUF)", min_value=0, value=100000, step=10000)
    years = st.slider("Horizon (years)", 1, 40, 15)
    inflation = st.slider("Assumed annual inflation (%)", 0.0, 20.0, 3.0, 0.5)
    goal = st.number_input("Target in today's HUF", min_value=1, value=60000000, step=1000000)
    with st.expander("Edit assumed annual nominal returns"):
        low = st.number_input("Conservative (%)", value=2.0, min_value=-50.0, max_value=50.0, step=0.5)
        mid = st.number_input("Balanced (%)", value=6.0, min_value=-50.0, max_value=50.0, step=0.5)
        high = st.number_input("Aggressive (%)", value=10.0, min_value=-50.0, max_value=50.0, step=0.5)
    trajectories = {}
    for label, rate in [("Conservative", low), ("Balanced", mid), ("Aggressive", high)]:
        balance = float(current)
        path = [balance]
        for month in range(1, years * 12 + 1):
            balance = balance * (1 + rate / 1200) + monthly
            if month % 12 == 0:
                path.append(balance / ((1 + inflation / 100) ** (month / 12)))
        trajectories[label] = path
    records = [{"Path": label, "Assumed nominal return": f"{rate:.1f}%", "Real ending value (today's HUF)": round(trajectories[label][-1]),
                "Real goal reached?": "Yes" if trajectories[label][-1] >= goal else "No", "Success probability": "Not estimated"}
               for label, rate in [("Conservative", low), ("Balanced", mid), ("Aggressive", high)]]
    st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    fig = go.Figure()
    for label, color in [("Conservative", "#6bc9ff"), ("Balanced", "#74e5bf"), ("Aggressive", "#ffac78")]:
        fig.add_trace(go.Scatter(x=list(range(years + 1)), y=trajectories[label], name=label, mode="lines", line=dict(color=color, width=3)))
    fig.add_hline(y=goal, line_dash="dot", line_color="#e9d98a", annotation_text="Today's-HUF target")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis_title="Years", yaxis_title="Purchasing power in today's HUF", legend=dict(orientation="h"),
                      margin=dict(l=8, r=8, t=20, b=10), height=380)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.info("Returns are user-controlled assumptions, not success probabilities. Inflation, tax, fees, FX, market drawdowns, and contribution changes can materially alter outcomes. The target is held fixed in today's purchasing power.")

elif nav == "Forecast journal":
    st.subheader("Forecast journal")
    st.caption("Record personal probability estimates separately from market quotes; compare them after resolution. Entries persist only in this browser session unless exported.")
    with st.form("new_forecast"):
        label = st.text_input("Precisely worded event", max_chars=220)
        probability = st.slider("My probability (%)", 0, 100, 50)
        deadline = st.date_input("Resolution deadline")
        rationale = st.text_area("Evidence / disconfirmation trigger", max_chars=1000)
        submitted = st.form_submit_button("Record forecast", use_container_width=True)
    if submitted:
        if not label.strip():
            st.warning("Write a testable event statement first.")
        else:
            st.session_state.journal.append({"Event": label.strip(), "Probability %": probability,
                                             "Deadline": deadline.isoformat(), "Rationale": rationale.strip(), "Outcome": "Pending",
                                             "Recorded UTC": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            st.rerun()
    uploaded = st.file_uploader("Import a journal JSON file", type="json")
    if uploaded is not None and st.button("Import entries"):
        try:
            imported = json.load(uploaded)
            if not isinstance(imported, list) or len(imported) > 500 or any(
                not isinstance(x, dict) or not isinstance(x.get("Event"), str) or
                finite_number(x.get("Probability %")) is None or not 0 <= float(x["Probability %"]) <= 100 or
                x.get("Outcome") not in ("Pending", "Yes", "No") for x in imported):
                raise ValueError("Invalid journal format")
            st.session_state.journal = imported
            st.rerun()
        except (ValueError, UnicodeDecodeError, TypeError):
            st.error("Import failed: expected a valid exported forecast journal JSON file.")
    journal = st.session_state.journal
    if journal:
        st.dataframe(pd.DataFrame(journal), use_container_width=True, hide_index=True)
        selected = st.selectbox("Set resolution for entry", range(len(journal)), format_func=lambda i: f"{i+1}. {journal[i]['Event'][:85]}")
        outcome = st.selectbox("Observed outcome", ["Pending", "Yes", "No"], index=["Pending", "Yes", "No"].index(journal[selected]["Outcome"]))
        if st.button("Save outcome", use_container_width=True):
            journal[selected]["Outcome"] = outcome
            st.rerun()
        resolved = [x for x in journal if x["Outcome"] in ("Yes", "No")]
        if resolved:
            brier = sum((float(x["Probability %"]) / 100 - (x["Outcome"] == "Yes")) ** 2 for x in resolved) / len(resolved)
            st.metric("Personal mean Brier score (lower is better)", f"{brier:.3f}", help="Average squared error of your recorded probability against outcomes; 0 is perfect, 1 worst.")
        st.download_button("â†“ Export journal (JSON)", json.dumps(journal, indent=2, ensure_ascii=False),
                           file_name="frontier_forecast_journal.json", mime="application/json", use_container_width=True)
    else:
        st.info("No forecasts yet. Add a falsifiable question above.")

else:
    st.subheader("Method & sources")
    st.markdown("**Source:** [Polymarket Gamma public events API](https://docs.polymarket.com/market-data/overview). [Market definitions](https://docs.polymarket.com/concepts/markets-events). Each row links to its source event.")
    st.write("YES % is the price of the outcome explicitly named 'Yes' in the returned outcomes array; missing or invalid prices are shown as unavailable, never 50%. A 'No release' contract retains its original meaning; we do not invert it or call it a release forecast.")
    st.write("Volume is historical trading volume, not market depth. Liquidity and bidâ€“ask spread are separate diagnostics; missing quotes are not proof of liquidity. Prices may deviate from real-world probabilities due to fees, spreads, trader preferences, and market rules.")
    st.write("This app intentionally removes the previous hard-coded Metaculus medians, made-up AGI/LEV scores, unverified release claims, and Gaussian daily release curves. A snapshot of differently worded contracts cannot justify a daily probability density or investment-return forecast.")
    st.write("Medical longevity and AI progress are interesting research areas, but neither an AGI date nor a treatment outcome is established by a prediction-market quote. Verify primary biomedical evidence independently.")
    st.caption(f"Source fetch: {fetched_at} Â· Cache: 300 seconds Â· No authentication, AI model, trading, or tracking required.")
    if failures:
        st.write("Unavailable sources:")
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)
    else:
        st.success("All configured event slugs returned an exact match.")
    st.markdown("For broader forecasting research: [Metaculus](https://www.metaculus.com/). This app does not claim to show live Metaculus predictions.")

st.divider()
st.caption("â—ˆ Frontier Horizon Â· Evidence before narrative Â· Markets are not financial or medical advice")
