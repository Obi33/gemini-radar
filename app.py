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

# The exact 7 Polymarket event URLs you provided
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
    """Queries Polymarket Gamma API events endpoint to harvest all nested markets and options."""
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
                    event_title = ev.get("title", slug)
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
                        
                        # Fix the Inversion Bug: Explicitly resolve "No release" contracts
                        is_negative_contract = False
                        combined_text = (q + " " + item_title).lower()
                        if "no release" in combined_text or "will there be no" in combined_text:
                            is_negative_contract = True
                            # If "No release by Sep 30" is 92%, release probability is 1 - 0.92 = 8%
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
                        "event_title": event_title,
                        "slug": slug,
                        "markets": sub_markets
                    })
        except Exception as e:
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
        return {"error": "Failed to pull live Polymarket event data. Verify internet connection."}

    client = genai.Client(api_key=api_key)

    # Generate complete list of ~40 discrete calendar entries
    start_date = date(2026, 9, 23)
    end_date = date(2026, 10, 31)
    date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_date - start_date).days + 1)]
    date_list.append("no release before october 31")

    prompt = f"""
    You are a quantitative prediction market arbiter.
    Here is the live, pre-processed data harvested directly from 7 Polymarket events:
    {json.dumps(harvested_events, indent=2)}

    CRITICAL RULES:
    1. 'implied_release_prob' has already inverted negative contracts (e.g. 'No release by Sep 30' at 92% is correctly 8% release chance). Do NOT spike September 30.
    2. Model Tier Dynamics:
       - Gemini Flash-Lite (3.6+): Follows its designated Flash-Lite market. It has early probability density in late Sept / early Oct.
       - Gemini Flash (3.9+): Follows its designated Flash market. Releases alongside or slightly ahead of Pro.
       - Gemini Pro: Bound by the $1.34M cumulative market and weekly blocks. Peak mass is heavily concentrated in the October 12-18 window.
    3. Calculate discrete probability mass percentages for EACH entry in this date list:
       {json.dumps(date_list)}

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
      "synthesis": "2 sentences explaining the true macro distribution based on the 7 markets."
    }}
    """

    # Dynamic model selection for Google AI Studio Free Tier
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
        return {"error": f"Model inference failed across candidate models. Details: {str(last_err)}"}

    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as pe:
        return {"error": f"JSON parsing failed: {str(pe)}. Response: {response.text[:200]}"}

    # Deterministic Python Mathematical Normalization: Force exact 100.00% sums
    distributions = result.get("daily_distributions", [])
    if distributions:
        for key in ["flash_lite_pct", "flash_pct", "pro_pct"]:
            total = sum(item.get(key, 0.0) for item in distributions)
            if total > 0:
                for item in distributions:
                    item[key] = round((item.get(key, 0.0) / total) * 100, 2)
                # Eliminate floating point rounding discrepancy on the tail entry
                diff = round(100.00 - sum(item[key] for item in distributions), 2)
                distributions[-1][key] = round(distributions[-1][key] + diff, 2)

    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    result["raw_events"] = harvested_events
    return result

# --- UI Rendering ---
st.title("⚡ Gemini Model Release Radar")
st.caption("Deterministic multi-market prediction synthesis powered by live Polymarket order books.")

with st.spinner("Harvesting 7 Polymarket events and calibrating distribution..."):
    data = compute_calibrated_radar()

if "error" in data:
    st.error(data["error"])
    st.stop()

# 1. Top Cards
st.subheader("🎯 Most Likely Release Date by Tier")
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

# 2. Daily Probability Density Chart
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

# 3. Discrete Breakdown Table
st.subheader("📋 Discrete Calendar Probability Breakdown (~40 Days)")

sum_lite = df["flash_lite_pct"].sum()
sum_flash = df["flash_pct"].sum()
sum_pro = df["pro_pct"].sum()

st.caption(f"Mathematical Checksums (Strict Normalization): Flash-Lite: {sum_lite:.2f}% | Flash: {sum_flash:.2f}% | Pro: {sum_pro:.2f}%")

styled_df = df.rename(columns={
    "date": "Calendar Date",
    "flash_lite_pct": "Flash-Lite (%)",
    "flash_pct": "Flash (%)",
    "pro_pct": "Pro (%)"
})
st.dataframe(styled_df, use_container_width=True, height=500)

# 4. Live Polymarket Contract Inspection
with st.expander("🔍 Inspect Harvested Polymarket Events & Inversion Check"):
    for ev in data.get("raw_events", []):
        st.markdown(f"### {ev['event_title']}")
        st.caption(f"Slug: `{ev['slug']}`")
        market_rows = []
        for m in ev["markets"]:
            market_rows.append({
                "Option / Date": m["option_name"],
                "Yes Price": f"${m['yes_price']:.2f}",
                "Implied Release Prob": f"{m['implied_release_prob'] * 100:.1f}%",
                "Negative Inverted?": "✅ Yes" if m["is_negative_contract"] else "No",
                "Volume": f"${m['volume_usd']:,}"
            })
        st.table(pd.DataFrame(market_rows))

st.caption(f"Auto-refresh interval: 60 minutes | Last calibrated: {data['refreshed_at']}")
if st.button("Force Live Data Re-calculation"):
    st.cache_data.clear()
    st.rerun()
