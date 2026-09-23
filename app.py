import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from google import genai

st.set_page_config(
    page_title="Gemini Release Radar", 
    page_icon="⚡", 
    layout="wide"
)

TARGET_EVENT_URLS = [
    "https://polymarket.com/event/gemini-4pt0-released-by-june-30-2026",
    "https://polymarket.com/event/next-google-gemini-pro-model-released-onptptpt-20260817141404356",
    "https://polymarket.com/event/next-google-gemini-pro-model-released-byptptpt",
    "https://polymarket.com/event/next-google-gemini-flash-lite-model-3pt6-released-byptptpt",
    "https://polymarket.com/event/when-will-the-next-google-gemini-pro-model-be-released-20260817144359068",
    "https://polymarket.com/event/next-gemini-flash-model-3pt9-released-byptptpt",
    "https://polymarket.com/event/next-gemini-pro-model-released-onptptpt-20260922131618444"
]

def fetch_all_polymarket_events():
    all_events_data = []
    for url in TARGET_EVENT_URLS:
        slug = url.strip().split("/event/")[-1].split("?")[0]
        api_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        try:
            res = requests.get(api_url, timeout=10)
            if res.status_code == 200:
                events = res.json()
                if events and isinstance(events, list):
                    ev = events[0]
                    markets = ev.get("markets", [])
                    sub_markets = []
                    for m in markets:
                        q = m.get("question", "")
                        item_title = m.get("groupItemTitle", "") or q
                        prices_raw = m.get("outcomePrices", '["0.5", "0.5"]')
                        try:
                            prices = json.loads(prices_raw)
                            yes_price = float(prices[0])
                        except Exception:
                            yes_price = 0.5

                        vol = float(m.get("volumeNum", 0) or m.get("volume", 0) or 0)
                        
                        is_negative_contract = False
                        combined_text = (q + " " + item_title).lower()
                        if "no release" in combined_text or "will there be no" in combined_text:
                            is_negative_contract = True
                            implied_prob = round(1.0 - yes_price, 4)
                        else:
                            implied_prob = round(yes_price, 4)

                        sub_markets.append({
                            "option_name": item_title,
                            "question": q,
                            "yes_price": yes_price,
                            "implied_release_prob": implied_prob,
                            "is_negative_contract": is_negative_contract,
                            "volume_usd": round(vol, 2)
                        })

                    all_events_data.append({
                        "event_title": ev.get("title", slug),
                        "slug": slug,
                        "markets": sub_markets
                    })
        except Exception:
            continue
    return all_events_data

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

@st.cache_data(ttl=3600)
def compute_calibrated_radar():
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    harvested_events = fetch_all_polymarket_events()
    if not harvested_events:
        return {"error": "Failed to pull live Polymarket event data."}

    client = genai.Client(api_key=api_key)

    start_date = date(2026, 9, 23)
    end_date = date(2026, 10, 31)
    
    calendar_entries = []
    curr = start_date
    while curr <= end_date:
        calendar_entries.append({
            "date": curr.strftime("%Y-%m-%d"),
            "weekday": curr.strftime("%A")
        })
        curr += timedelta(days=1)
    calendar_entries.append({"date": "no release before october 31", "weekday": "N/A"})

    prompt = f"""
    You are a quantitative AI release forecaster.
    Model continuous daily probability density functions for Google's next 3 model releases using this live Polymarket data:
    {json.dumps(harvested_events, indent=2)}

    CALENDAR TO ESTIMATE:
    {json.dumps(calendar_entries, indent=2)}

    CRITICAL MODEL DIFFERENTIATION (THE THREE CURVES MUST NOT BE IDENTICAL):
    1. GEMINI PRO:
       - Anchored to the $1.34M cumulative market (9% Sep 30, 45% Oct 9, 56% Oct 15, 85% Oct 23) and $70k weekly market (Oct 12-18 holds 31% volume).
       - Peak single release day MUST sit in the October 13-17 window (e.g. October 14, 16, or 17).
    
    2. GEMINI FLASH (4.0 / 3.9+):
       - Anchored to the $580k Gemini 4.0 market (8% Sep 30, 81% Oct 31).
       - Has an earlier release gradient than Pro. It should peak earlier than Pro, ideally in the October 6 to October 10 window.

    3. GEMINI FLASH-LITE (3.6+):
       - Distillation of Gemini 3.6 (which already released).
       - Downweight the illiquid 62% Sep 30 contract, but reflect that Flash-Lite has an earlier probability spread (late September to early October). 
       - Its curve should be broader and flatter, peaking in early October (e.g. October 2 to October 6).

    SHAPING & MATHEMATICAL CONSTRAINTS:
    - NO FLAT PLATEAUS: Consecutive business days must NEVER have the identical probability number. Create natural, continuous bell curves.
    - NO SQUARE WAVES: Do not crash abruptly to 0% on Saturday. Transition naturally: mid-week peak (Tuesday-Thursday) -> tapering Friday (2-3%) -> quiet weekend (0.4-0.8%) -> rising Monday (1.5-2.5%).
    - INDEPENDENT PEAKS: The 'most_likely_dates' for Flash-Lite, Flash, and Pro MUST BE DIFFERENT DATES. Do not output October 15 for all three.
    - All probability numbers must be percentages between 0.0 and 100.0.

    Return STRICT JSON ONLY matching this schema:
    {{
      "most_likely_dates": {{
        "flash_lite": {{"date": "YYYY-MM-DD", "probability": 0.0}},
        "flash": {{"date": "YYYY-MM-DD", "probability": 0.0}},
        "pro": {{"date": "YYYY-MM-DD", "probability": 0.0}}
      }},
      "daily_distributions": [
        {{
          "date": "YYYY-MM-DD or no release before october 31",
          "flash_lite_pct": 0.0,
          "flash_pct": 0.0,
          "pro_pct": 0.0
        }}
      ],
      "synthesis": "2 concise sentences explaining why the 3 models peak on different dates."
    }}
    """

    models_to_try = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.0-flash"]
    try:
        discovered = [m.name.replace("models/", "") for m in client.models.list() if "flash" in m.name.lower() and "image" not in m.name.lower()]
        if discovered:
            models_to_try = discovered + models_to_try
    except Exception:
        pass

    response = None
    last_err = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                break
        except Exception as e:
            last_err = e
            continue

    if not response or not response.text:
        return {"error": f"Model inference failed across candidate models: {str(last_err)}"}

    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as pe:
        return {"error": f"JSON parsing failed: {str(pe)}. Raw: {response.text[:200]}"}

    # Strict Normalization across all ~40 dates
    distributions = result.get("daily_distributions", [])
    if distributions:
        for key in ["flash_lite_pct", "flash_pct", "pro_pct"]:
            total = sum(float(item.get(key, 0.0)) for item in distributions)
            if total > 0:
                for item in distributions:
                    item[key] = round((float(item.get(key, 0.0)) / total) * 100, 2)
                diff = round(100.00 - sum(item[key] for item in distributions), 2)
                distributions[-1][key] = round(distributions[-1][key] + diff, 2)

    # Sanitize top metrics
    for tier in ["flash_lite", "flash", "pro"]:
        metric_val = float(result.get("most_likely_dates", {}).get(tier, {}).get("probability", 0.0))
        if 0.0 < metric_val <= 1.0:
            result["most_likely_dates"][tier]["probability"] = round(metric_val * 100, 1)
        else:
            result["most_likely_dates"][tier]["probability"] = round(metric_val, 1)

    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    result["raw_events"] = harvested_events
    return result

# --- UI Rendering ---
st.title("⚡ Gemini Model Release Radar")
st.caption("Bayesian multi-market synthesis and discrete calendar density modeling.")

with st.spinner("Calibrating order books and computing continuous distributions..."):
    data = compute_calibrated_radar()

if "error" in data:
    st.error(data["error"])
    st.stop()

# 1. Top Metric Cards
st.subheader("🎯 Most Likely Single Release Day by Tier")
col1, col2, col3 = st.columns(3)

with col1:
    m_lite = data["most_likely_dates"]["flash_lite"]
    st.metric("Gemini Flash-Lite", m_lite["date"], f"{m_lite['probability']}% Peak Mass")

with col2:
    m_flash = data["most_likely_dates"]["flash"]
    st.metric("Gemini Flash", m_flash["date"], f"{m_flash['probability']}% Peak Mass")

with col3:
    m_pro = data["most_likely_dates"]["pro"]
    st.metric("Gemini Pro", m_pro["date"], f"{m_pro['probability']}% Peak Mass")

st.info(data.get("synthesis", ""))

# 2. Probability Density Functions Chart
st.subheader("📈 Probability Density Functions (Daily Mass)")
df = pd.DataFrame(data["daily_distributions"])

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["date"], y=df["flash_lite_pct"], mode="lines+markers", name="Flash-Lite (3.6+)", line=dict(color="#38bdf8", width=2.5)))
fig.add_trace(go.Scatter(x=df["date"], y=df["flash_pct"], mode="lines+markers", name="Flash (3.9+)", line=dict(color="#34d399", width=2.5)))
fig.add_trace(go.Scatter(x=df["date"], y=df["pro_pct"], mode="lines+markers", name="Pro", line=dict(color="#f43f5e", width=2.5)))

fig.update_layout(
    template="plotly_dark",
    xaxis_title="Date",
    yaxis_title="Probability Density (%)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# 3. Data Table
st.subheader("📋 Discrete Calendar Probability Breakdown (~40 Days)")

sum_lite = df["flash_lite_pct"].sum()
sum_flash = df["flash_pct"].sum()
sum_pro = df["pro_pct"].sum()

st.caption(f"Strict Normalization Checksums: Flash-Lite: {sum_lite:.2f}% | Flash: {sum_flash:.2f}% | Pro: {sum_pro:.2f}%")

styled_df = df.rename(columns={
    "date": "Calendar Date",
    "flash_lite_pct": "Flash-Lite (%)",
    "flash_pct": "Flash (%)",
    "pro_pct": "Pro (%)"
})
st.dataframe(styled_df, use_container_width=True, height=500)

# 4. Raw Inspection Drawer
with st.expander("🔍 Inspect Harvested Polymarket Events & Volumes"):
    for ev in data.get("raw_events", []):
        st.markdown(f"### {ev['event_title']}")
        st.caption(f"Slug: `{ev['slug']}`")
        market_rows = []
        for m in ev["markets"]:
            market_rows.append({
                "Option / Date": m["option_name"],
                "Yes Price": f"${m['yes_price']:.2f}",
                "Implied Prob": f"{m['implied_release_prob'] * 100:.1f}%",
                "Volume": f"${m['volume_usd']:,}"
            })
        st.table(pd.DataFrame(market_rows))

st.caption(f"Auto-refresh interval: 60 minutes | Last calibrated: {data['refreshed_at']}")
if st.button("Force Live Data Re-calculation"):
    st.cache_data.clear()
    st.rerun()
