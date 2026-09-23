import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from google import genai

st.set_page_config(
    page_title="Frontier AI & Longevity Horizon", 
    page_icon="🧬", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for dark modern terminal aesthetics
st.markdown("""
<style>
    .metric-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 0.75rem;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }
    .metric-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin-bottom: 0.25rem;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #f3f4f6;
    }
    .metric-delta {
        font-size: 0.8rem;
        font-weight: 500;
        color: #10b981;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1rem;
        font-weight: 600;
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# 1. Target Polymarket Events
POLYMARKET_EVENTS = [
    # Anthropic
    {"slug": "claude-6-released-byptptpt", "entity": "Anthropic", "label": "Claude 6"},
    {"slug": "next-claude-sonnet-released-byptptpt-20260701203831153", "entity": "Anthropic", "label": "Claude Next Sonnet"},
    {"slug": "next-claude-haiku-released-byptptpt-20260701205353326", "entity": "Anthropic", "label": "Claude Next Haiku"},
    {"slug": "next-fable-model-5pt2-released-byptptpt", "entity": "Anthropic", "label": "Claude Fable 5.2"},
    
    # OpenAI
    {"slug": "gpt-7-released-byptptpt", "entity": "OpenAI", "label": "GPT-7"},
    {"slug": "gpt-astra-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Astra 6.1"},
    {"slug": "next-openai-gpt-terra-5pt7-released-byptptpt", "entity": "OpenAI", "label": "GPT-Terra 5.7"},
    
    # Google
    {"slug": "gemini-4pt0-released-by-june-30-2026", "entity": "Google", "label": "Gemini 4.0"},
    {"slug": "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "entity": "Google", "label": "Next Gemini Pro"},
    
    # Meta / Macro
    {"slug": "which-company-has-best-ai-model-end-of-2026", "entity": "Meta-Market", "label": "Best Model End of 2026"}
]

# 2. Key Metaculus Questions (AGI & Longevity Escape Velocity)
METACULUS_QUESTION_IDS = [
    {"id": 5121, "label": "Date of Artificial General Intelligence", "category": "AGI"},
    {"id": 8946, "label": "Longevity Escape Velocity Reached", "category": "LEV"}
]

def fetch_polymarket_data():
    base_url = "https://gamma-api.polymarket.com/events?slug="
    records = []
    
    for item in POLYMARKET_EVENTS:
        slug = item["slug"]
        try:
            res = requests.get(f"{base_url}{slug}", timeout=8)
            if res.status_code == 200:
                data = res.json()
                if data and isinstance(data, list):
                    ev = data[0]
                    markets = ev.get("markets", [])
                    extracted_options = []
                    
                    for m in markets:
                        q = m.get("question", "")
                        title = m.get("groupItemTitle", "") or q
                        prices_raw = m.get("outcomePrices", '["0.5", "0.5"]')
                        try:
                            prices = json.loads(prices_raw)
                            yes_price = float(prices[0])
                        except Exception:
                            yes_price = 0.5
                            
                        vol = float(m.get("volumeNum", 0) or m.get("volume", 0) or 0)
                        
                        # Inversion handling for negative contracts
                        if "no release" in (q + " " + title).lower():
                            implied = round(1.0 - yes_price, 4)
                        else:
                            implied = round(yes_price, 4)
                            
                        extracted_options.append({
                            "option": title,
                            "implied_prob": implied,
                            "raw_yes": yes_price,
                            "volume": vol
                        })
                    
                    records.append({
                        "label": item["label"],
                        "entity": item["entity"],
                        "slug": slug,
                        "options": extracted_options
                    })
        except Exception:
            continue
    return records

def fetch_metaculus_data():
    base_url = "https://www.metaculus.com/api2/questions/"
    results = []
    
    for item in METACULUS_QUESTION_IDS:
        q_id = item["id"]
        try:
            res = requests.get(f"{base_url}{q_id}/", timeout=8)
            if res.status_code == 200:
                data = res.json()
                comm_pred = data.get("community_prediction", {})
                
                # Format median forecast
                median_val = "Pending Calibration"
                if comm_pred and "history" in comm_pred and comm_pred["history"]:
                    latest = comm_pred["history"][-1]
                    val = latest.get("val")
                    if isinstance(val, (int, float)):
                        # If epoch timestamp
                        if val > 1000000000:
                            median_val = datetime.fromtimestamp(val).strftime("%Y-%m-%d")
                        else:
                            median_val = f"{round(val * 100, 1)}%"
                            
                results.append({
                    "id": q_id,
                    "label": item["label"],
                    "category": item["category"],
                    "community_median": median_val,
                    "title": data.get("title", item["label"])
                })
        except Exception:
            results.append({
                "id": q_id,
                "label": item["label"],
                "category": item["category"],
                "community_median": "API Inactive",
                "title": item["label"]
            })
    return results

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

@st.cache_data(ttl=3600)
def compute_macro_horizon():
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    poly_data = fetch_polymarket_data()
    meta_data = fetch_metaculus_data()

    if not poly_data:
        return {"error": "Failed to pull live Polymarket market data."}

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are a principal macroeconomic strategist and longevity-acceleration analyst.
    Current Date: September 23, 2026.
    
    Here is live prediction market data across Polymarket and Metaculus:
    
    POLYMARKET FRONTIER RELEASES & YEAR-END BEST MODEL:
    {json.dumps(poly_data, indent=2)}
    
    METACULUS MACRO HORIZON (AGI & LONGEVITY ESCAPE VELOCITY):
    {json.dumps(meta_data, indent=2)}
    
    TASK & STRATEGIC CALIBRATION:
    1. Determine the projected release window (or expected date) for:
       - Claude Next Sonnet, Claude 6, Claude Fable 5.2
       - GPT-Terra 5.7, GPT-Astra 6.1, GPT-7
       - Gemini Next Pro, Gemini 4.0
    2. Analyze the 'Which company has best AI model end of 2026' market. Extract implied winner probabilities.
    3. Calculate two quantitative velocity scores (1 to 100):
       - 'fire_deflation_score': Rate of intelligence-driven cognitive automation, software deflation, and productivity acceleration.
       - 'lev_acceleration_score': Proximity of frontier reasoning breakthroughs to biotech, biological aging simulation, and healthspan escape velocity.
    4. Provide actionable, concise 2-sentence takeaways connecting these release milestones to long-term compounding and health security.
    
    Return strict JSON ONLY with this schema:
    {{
      "executive_metrics": {{
        "fire_deflation_score": 85,
        "lev_acceleration_score": 78,
        "year_end_champion": "Anthropic",
        "champion_odds_pct": 68.0
      }},
      "model_pipeline": [
        {{
          "entity": "Anthropic | OpenAI | Google",
          "model": "Model Name",
          "projected_window": "e.g. Mid-October 2026",
          "confidence_pct": 75.0,
          "strategic_impact": "One short phrase on capability gain"
        }}
      ],
      "best_ai_2026_standings": [
        {{"company": "Anthropic", "implied_pct": 68.0}},
        {{"company": "OpenAI", "implied_pct": 22.0}},
        {{"company": "Google", "implied_pct": 10.0}}
      ],
      "strategic_memo": "2 sentences synthesizing how the Q4 2026 frontier cluster accelerates the path to personal autonomy and healthspan."
    }}
    """

    # Dynamic model discovery
    models_to_try = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.0-flash"]
    try:
        discovered = [m.name.replace("models/", "") for m in client.models.list() if "flash" in m.name.lower() and "image" not in m.name.lower()]
        if discovered:
            models_to_try = discovered + models_to_try
    except Exception:
        pass

    response = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                break
        except Exception:
            continue

    if not response or not response.text:
        return {"error": "API generation failed across available models."}

    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as pe:
        return {"error": f"JSON parsing failed: {str(pe)}. Output was: {response.text[:200]}"}

    result["polymarket_raw"] = poly_data
    result["metaculus_raw"] = meta_data
    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    return result

# --- UI Execution ---

st.title("🧬 Frontier AI & Longevity Horizon")
st.caption("Live prediction market synthesis mapping intelligence acceleration to FIRE and Longevity Escape Velocity.")

with st.spinner("Harvesting Polymarket books and Metaculus epistemic distributions..."):
    data = compute_macro_horizon()

if "error" in data:
    st.error(data["error"])
    st.stop()

# --- Section 1: Executive Macro HUD ---
exec_m = data["executive_metrics"]

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">FIRE Deflation Score</div>
        <div class="metric-value">{exec_m.get('fire_deflation_score', 80)}/100</div>
        <div class="metric-delta">Productivity & Capital Compounding</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">LEV Acceleration Index</div>
        <div class="metric-value">{exec_m.get('lev_acceleration_score', 75)}/100</div>
        <div class="metric-delta">Biomedical Discovery Velocity</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Year-End Model Leader</div>
        <div class="metric-value">{exec_m.get('year_end_champion', 'Anthropic')}</div>
        <div class="metric-delta">{exec_m.get('champion_odds_pct', 0)}% Market Consensus</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    # Metaculus AGI Median
    agi_date = "2027-2028"
    for m in data.get("metaculus_raw", []):
        if m["category"] == "AGI":
            agi_date = m["community_median"]
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Metaculus AGI Consensus</div>
        <div class="metric-value">{agi_date}</div>
        <div class="metric-delta">Epistemic Community Median</div>
    </div>
    """, unsafe_allow_html=True)

st.info(data.get("strategic_memo", ""))

# --- Section 2: Tabbed Intelligence Explorer ---
tab1, tab2, tab3, tab4 = st.tabs(["🚀 Frontier Pipeline", "🏆 Best AI 2026 Crown", "⏳ Metaculus Horizon", "🔍 Raw Order Books"])

with tab1:
    st.subheader("Expected Release Cadence by Frontier Lab")
    pipeline = data.get("model_pipeline", [])
    if pipeline:
        df_pipe = pd.DataFrame(pipeline)
        
        # Color coding by lab
        color_map = {"Anthropic": "#f59e0b", "OpenAI": "#10b981", "Google": "#38bdf8"}
        
        fig = go.Figure()
        for idx, row in df_pipe.iterrows():
            c = color_map.get(row["entity"], "#a855f7")
            fig.add_trace(go.Bar(
                x=[row["confidence_pct"]],
                y=[f"{row['entity']} · {row['model']}"],
                orientation='h',
                marker=dict(color=c),
                text=f"{row['projected_window']} ({row['confidence_pct']}%)",
                textposition='inside',
                hoverinfo='text',
                hovertext=f"Impact: {row.get('strategic_impact', '')}",
                name=row["entity"],
                showlegend=False
            ))
            
        fig.update_layout(
            template="plotly_dark",
            xaxis_title="Market Confidence (%)",
            margin=dict(l=20, r=20, t=20, b=20),
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(df_pipe.rename(columns={
            "entity": "Lab",
            "model": "Model Designation",
            "projected_window": "Expected Window",
            "confidence_pct": "Confidence (%)",
            "strategic_impact": "Capability Advance"
        }), use_container_width=True)

with tab2:
    st.subheader("Consensus: 'Which Company Has Best AI Model End of 2026?'")
    standings = data.get("best_ai_2026_standings", [])
    if standings:
        df_standings = pd.DataFrame(standings)
        
        fig_pie = go.Figure(data=[go.Pie(
            labels=df_standings["company"],
            values=df_standings["implied_pct"],
            hole=0.45,
            marker=dict(colors=["#f59e0b", "#10b981", "#38bdf8", "#8b5cf6"])
        )])
        fig_pie.update_layout(
            template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
            height=350
        )
        st.plotly_chart(fig_pie, use_container_width=True)

with tab3:
    st.subheader("Long-Horizon Metaculus Epistemic Benchmarks")
    st.caption("Crowdsourced probabilistic forecasts uncorrupted by thin retail betting liquidity.")
    
    col_meta1, col_meta2 = st.columns(2)
    meta_list = data.get("metaculus_raw", [])
    
    for idx, m_item in enumerate(meta_list):
        target_col = col_meta1 if idx % 2 == 0 else col_meta2
        with target_col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{m_item['category']} Focus · Question #{m_item['id']}</div>
                <div class="metric-value">{m_item['community_median']}</div>
                <div style="font-size: 0.95rem; color: #d1d5db; margin-top: 0.5rem;">{m_item['title']}</div>
            </div>
            """, unsafe_allow_html=True)

with tab4:
    st.subheader("Live Polymarket Contract Inspection")
    for ev in data.get("polymarket_raw", []):
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} contracts)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

# Footer
st.divider()
st.caption(f"Engine: Google AI Studio Dynamic Flash · Metaculus REST API · Last Calibrated: {data['refreshed_at']}")
if st.button("Force Synchronized Market Recalculation"):
    st.cache_data.clear()
    st.rerun()
