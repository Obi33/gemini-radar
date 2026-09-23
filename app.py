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

MARKET_SLUGS = [
    "when-will-the-next-google-gemini-pro-model-be-released",
    "next-google-gemini-pro-model-released-on",
    "next-google-gemini-pro-model-released-by",
    "next-gemini-pro-model-released-on",
    "gemini-40-released-by",
    "will-the-next-google-gemini-pro-model-be-released-by-october-31-2026",
    "will-there-be-no-next-google-gemini-pro-model-release-by-october-31-2026",
    "will-there-be-no-next-google-gemini-pro-model-release-by-september-30-2026"
]

def fetch_polymarket_books():
    base_url = "https://gamma-api.polymarket.com/markets"
    gathered = []
    for slug in MARKET_SLUGS:
        try:
            res = requests.get(f"{base_url}?slug={slug}", timeout=8)
            if res.status_code == 200:
                payload = res.json()
                data = payload[0] if isinstance(payload, list) and payload else payload
                if data:
                    prices = json.loads(data.get("outcomePrices", '["0.0", "0.0"]'))
                    outcomes = json.loads(data.get("outcomes", '["Yes", "No"]'))
                    gathered.append({
                        "question": data.get("question", slug),
                        "volume_usd": round(float(data.get("volumeNum", 0)), 2),
                        "prices": dict(zip(outcomes, prices))
                    })
        except Exception:
            continue
    return gathered

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

@st.cache_data(ttl=3600)
def compute_distributions():
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    raw_market_data = fetch_polymarket_books()
    if not raw_market_data:
        return {"error": "Failed to pull live Polymarket contract data."}

    client = genai.Client(api_key=api_key)

    start_date = date(2026, 9, 23)
    end_date = date(2026, 10, 31)
    date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_date - start_date).days + 1)]
    date_list.append("Post-October 31")

    prompt = f"""
    You are a quantitative prediction market mathematician.
    Analyze live Polymarket data tracking next-gen Gemini releases:
    {json.dumps(raw_market_data, indent=2)}

    Context:
    - Today is late September 2026.
    - Google releases model tiers in phased cadences (Flash/Flash-Lite often accompany or lead Pro).
    - Liquid cumulative and weekly markets carry ground truth; thin daily markets have illiquidity noise.

    Required Task:
    1. Calculate a calibrated discrete probability distribution for every single entry in this list:
       {json.dumps(date_list)}
    2. Provide distributions for three upcoming models:
       - Gemini Flash-Lite
       - Gemini Flash
       - Gemini Pro
    3. Mathematical Constraint: Probabilities across all entries for each model MUST sum to exactly 100.00%.

    Return strict JSON ONLY with this schema:
    {{
      "most_likely_dates": {{
        "flash_lite": {{"date": "YYYY-MM-DD", "probability": 0.0}},
        "flash": {{"date": "YYYY-MM-DD", "probability": 0.0}},
        "pro": {{"date": "YYYY-MM-DD", "probability": 0.0}}
      }},
      "daily_distributions": [
        {{
          "date": "YYYY-MM-DD",
          "flash_lite_pct": 0.0,
          "flash_pct": 0.0,
          "pro_pct": 0.0
        }}
      ],
      "rationale": "2-3 sentences explaining market anchoring and tier sequencing."
    }}
    """

    # Dynamic model discovery: Query Google AI Studio for active models on this key
    models_to_try = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
    try:
        discovered = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", []) or []
            if not actions or "generateContent" in actions:
                clean_name = m.name.replace("models/", "")
                discovered.append(clean_name)
        
        # Prioritize flash text models
        flash_discovered = [m for m in discovered if "flash" in m and "image" not in m]
        if flash_discovered:
            models_to_try = flash_discovered + models_to_try
    except Exception:
        pass

    response = None
    last_err = None
    active_model_used = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                active_model_used = model_name
                break
        except Exception as e:
            last_err = e
            continue

    if not response or not response.text:
        return {"error": f"API call failed across models {models_to_try}. Details: {str(last_err)}"}

    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as parse_err:
        return {"error": f"JSON parsing failed: {str(parse_err)}. Raw model output: {response.text[:250]}"}

    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    result["raw_markets"] = raw_market_data
    result["model_used"] = active_model_used
    return result

st.title("⚡ Next-Gen Gemini Release Distribution Engine")
st.caption("Live prediction market consensus updated hourly via Gemini Free API.")

with st.spinner("Processing live order books and computing mathematical distributions..."):
    data = compute_distributions()

if "error" in data:
    st.error(data["error"])
    st.stop()

st.subheader("🎯 Most Probable Release Date by Tier")
col1, col2, col3 = st.columns(3)

with col1:
    m_lite = data["most_likely_dates"]["flash_lite"]
    st.metric("Gemini Flash-Lite", m_lite["date"], f"{m_lite['probability']}% peak mass")

with col2:
    m_flash = data["most_likely_dates"]["flash"]
    st.metric("Gemini Flash", m_flash["date"], f"{m_flash['probability']}% peak mass")

with col3:
    m_pro = data["most_likely_dates"]["pro"]
    st.metric("Gemini Pro", m_pro["date"], f"{m_pro['probability']}% peak mass")

st.info(data.get("rationale", ""))

st.subheader("📈 Probability Density Functions (Daily)")
df = pd.DataFrame(data["daily_distributions"])

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["date"], y=df["flash_lite_pct"], mode="lines+markers", name="Flash-Lite", line=dict(color="#38bdf8", width=2)))
fig.add_trace(go.Scatter(x=df["date"], y=df["flash_pct"], mode="lines+markers", name="Flash", line=dict(color="#34d399", width=2)))
fig.add_trace(go.Scatter(x=df["date"], y=df["pro_pct"], mode="lines+markers", name="Pro", line=dict(color="#f43f5e", width=2)))

fig.update_layout(
    template="plotly_dark",
    xaxis_title="Date",
    yaxis_title="Implied Probability (%)",
    hovermode="x unified",
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Discrete Calendar Probability Breakdown (~40 Days)")

sum_lite = df["flash_lite_pct"].sum()
sum_flash = df["flash_pct"].sum()
sum_pro = df["pro_pct"].sum()

st.caption(f"Checksums: Flash-Lite {sum_lite:.1f}% | Flash {sum_flash:.1f}% | Pro {sum_pro:.1f}%")

styled_df = df.rename(columns={
    "date": "Date",
    "flash_lite_pct": "Flash-Lite (%)",
    "flash_pct": "Flash (%)",
    "pro_pct": "Pro (%)"
})
st.dataframe(styled_df, use_container_width=True, height=500)

st.caption(f"Engine: {data.get('model_used', 'Gemini Free')} | Last updated: {data['refreshed_at']}")
if st.button("Force Immediate Refresh"):
    st.cache_data.clear()
    st.rerun()
