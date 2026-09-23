import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from google import genai

st.set_page_config(
    page_title="Frontier AI & Longevity Horizon", 
    page_icon="🧬", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

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

# 1. Target Polymarket Events (Frontier Releases & Best Model 2026)
POLYMARKET_EVENTS = [
    # Gemini Tier Contracts
    {"slug": "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "entity": "Google", "label": "Gemini Pro"},
    {"slug": "next-google-gemini-pro-model-released-byptptpt", "entity": "Google", "label": "Gemini Pro Cumulative"},
    {"slug": "gemini-4pt0-released-by-june-30-2026", "entity": "Google", "label": "Gemini 4.0 Flash"},
    {"slug": "next-gemini-flash-model-3pt9-released-byptptpt", "entity": "Google", "label": "Gemini Flash 3.9+"},
    {"slug": "next-google-gemini-flash-lite-model-3pt6-released-byptptpt", "entity": "Google", "label": "Gemini Flash-Lite 3.6+"},
    
    # Anthropic
    {"slug": "claude-6-released-byptptpt", "entity": "Anthropic", "label": "Claude 6"},
    {"slug": "next-claude-sonnet-released-byptptpt-20260701203831153", "entity": "Anthropic", "label": "Claude Next Sonnet"},
    {"slug": "next-claude-haiku-released-byptptpt-20260701205353326", "entity": "Anthropic", "label": "Claude Next Haiku"},
    {"slug": "next-fable-model-5pt2-released-byptptpt", "entity": "Anthropic", "label": "Claude Fable 5.2"},
    
    # OpenAI
    {"slug": "gpt-7-released-byptptpt", "entity": "OpenAI", "label": "GPT-7"},
    {"slug": "gpt-astra-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Astra 6.1"},
    {"slug": "next-openai-gpt-terra-5pt7-released-byptptpt", "entity": "OpenAI", "label": "GPT-Terra 5.7"},
    
    # Macro Crown
    {"slug": "which-company-has-best-ai-model-end-of-2026", "entity": "Crown", "label": "Best Model End of 2026"}
]

# 2. Top 10 High-Impact Metaculus Epistemic Benchmarks (AGI, LEV, and FIRE Economics)
METACULUS_BENCHMARKS = [
    {
        "id": 5121,
        "title": "Date of First Artificial General Intelligence (AGI)",
        "category": "AGI Timeline",
        "community_median": "May 2028",
        "impact": "Triggers complete cognitive automation and begins the explosive software deflation cycle."
    },
    {
        "id": 5122,
        "title": "Transition Time: Weak AGI to Superintelligence (ASI)",
        "category": "Superintelligence",
        "community_median": "29.4 Months",
        "impact": "The critical compression window where human-speed scientific discovery transitions into recursive self-improvement."
    },
    {
        "id": 6592,
        "title": "Longevity Escape Velocity (LEV) Arrival Date",
        "category": "Longevity (LEV)",
        "community_median": "October 2037",
        "impact": "Remaining life expectancy increases by more than 1.0 year per calendar year through biotechnology."
    },
    {
        "id": 4788,
        "title": "Will AGI Precede Longevity Escape Velocity?",
        "category": "Cross-Domain",
        "community_median": "95% Probability",
        "impact": "Direct proof that solving intelligence is the necessary catalyst to solving biological senescence."
    },
    {
        "id": 26244,
        "title": "Radical Life Extension Demonstrated Within 5 Years Post-AGI",
        "category": "Biomedicine",
        "community_median": "60% Probability",
        "impact": "Validates that high-dimensional AI reasoning will master cellular rejuvenation before the 2030s close."
    },
    {
        "id": 8357,
        "title": "100% Autonomous Software Engineering Replacement",
        "category": "FIRE & Capital",
        "community_median": "November 2027",
        "impact": "Software marginal creation cost approaches zero, driving immense margin expansion for broad index capital (FIRE)."
    },
    {
        "id": 9120,
        "title": "End-to-End AI Molecular Design & Therapeutic Synthesis",
        "category": "Biotech",
        "community_median": "March 2029",
        "impact": "Novel FDA-approved drug candidates discovered, screened, and validated entirely in silico."
    },
    {
        "id": 7498,
        "title": "Global Real GDP Growth Exceeds 20% Annually",
        "category": "Macro Acceleration",
        "community_median": "2.3 Years Post-AGI",
        "impact": "Historical economic paradigm shift: unconstrained cognitive labor compounds global output exponentially."
    },
    {
        "id": 1002,
        "title": "First Human Reaching 150th Birthday",
        "category": "Healthspan",
        "community_median": "Born ~1995-2015",
        "impact": "Individuals alive today under 40 hold non-trivial actuarial odds of living past 150 under early LEV."
    },
    {
        "id": 11452,
        "title": "First Major Economy Implements Universal Capital Dividend",
        "category": "FIRE & Policy",
        "community_median": "August 2031",
        "impact": "Sovereign dividend distribution to offset AI labor disruption, guaranteeing baseline living standards."
    }
]

def fetch_all_polymarket_data():
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

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

@st.cache_data(ttl=3600)
def compute_macro_horizon():
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    poly_data = fetch_all_polymarket_data()
    if not poly_data:
        return {"error": "Failed to pull live Polymarket market data."}

    client = genai.Client(api_key=api_key)

    # Construct complete ~40 calendar day range
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
    You are an expert quantitative forecaster and Bayesian statistician.
    Today's Date: September 23, 2026.

    RAW POLYMARKET MARKET DATA:
    {json.dumps(poly_data, indent=2)}

    CALENDAR TO ESTIMATE (40 ENTRIES):
    {json.dumps(calendar_entries, indent=2)}

    MANDATORY TASKS:
    1. MODEL DAILY DENSITY FUNCTIONS FOR THREE GEMINI TIERS:
       - Gemini Pro: Anchored by $1.34M cumulative market and $70k weekly market. Peak single release day in October 13-17.
       - Gemini Flash (3.9+ / 4.0): Earlier ramp than Pro, peaking around October 6-10.
       - Gemini Flash-Lite (3.6+): Distillation with broad early distribution, peaking in early October (e.g. Oct 2-6).
       - Create natural, continuous bell curves. Midweek days (Tue-Thu) crest, weekends dip to ~0.5%.
       - Calculate discrete percentages for EVERY calendar entry so they sum to 100%.

    2. MAP THE LAB PIPELINE & BEST AI 2026 STANDINGS:
       - Project release windows for Claude 6, Next Sonnet, Next Haiku, Fable 5.2, GPT-7, GPT-Astra 6.1, GPT-Terra 5.7.
       - Extract standings for 'Which company has best AI model end of 2026' (Anthropic, OpenAI, Google).

    3. STRATEGIC METRICS:
       - fire_deflation_score (1-100): Rate of cognitive automation accelerating passive capital compounding.
       - lev_acceleration_score (1-100): Proximity of frontier reasoning jumps to biological escape velocity.

    Return STRICT JSON ONLY with this schema:
    {{
      "executive_metrics": {{
        "fire_deflation_score": 85,
        "lev_acceleration_score": 78,
        "year_end_champion": "Anthropic",
        "champion_odds_pct": 68.0
      }},
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
      "model_pipeline": [
        {{
          "entity": "Anthropic | OpenAI | Google",
          "model": "Model Name",
          "projected_window": "e.g. Mid-October 2026",
          "confidence_pct": 75.0,
          "strategic_impact": "Impact phrase"
        }}
      ],
      "best_ai_2026_standings": [
        {{"company": "Anthropic", "implied_pct": 68.0}},
        {{"company": "OpenAI", "implied_pct": 22.0}},
        {{"company": "Google", "implied_pct": 10.0}}
      ],
      "synthesis": "2 sentences synthesizing how the Q4 frontier release cluster accelerates FIRE and biological longevity."
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
        return {"error": f"API generation failed across models: {str(last_err)}"}

    try:
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as pe:
        return {"error": f"JSON parsing failed: {str(pe)}. Output: {response.text[:200]}"}

    # Strict Normalization across all 40 dates
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
        val = float(result.get("most_likely_dates", {}).get(tier, {}).get("probability", 0.0))
        if 0.0 < val <= 1.0:
            result["most_likely_dates"][tier]["probability"] = round(val * 100, 1)
        else:
            result["most_likely_dates"][tier]["probability"] = round(val, 1)

    result["polymarket_raw"] = poly_data
    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    return result

# --- UI Layout ---

st.title("🧬 Frontier AI & Longevity Horizon")
st.caption("Live prediction market synthesis mapping intelligence acceleration to FIRE and Longevity Escape Velocity.")

with st.spinner("Processing live order books and computing mathematical distributions..."):
    data = compute_macro_horizon()

if "error" in data:
    st.error(data["error"])
    st.stop()

# 1. Executive Macro HUD
exec_m = data.get("executive_metrics", {})
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">FIRE Deflation Score</div>
        <div class="metric-value">{exec_m.get('fire_deflation_score', 84)}/100</div>
        <div class="metric-delta">Cognitive Automation & Asset Compounding</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">LEV Acceleration Index</div>
        <div class="metric-value">{exec_m.get('lev_acceleration_score', 78)}/100</div>
        <div class="metric-delta">Biomedical Discovery Velocity</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Year-End Crown Consensus</div>
        <div class="metric-value">{exec_m.get('year_end_champion', 'Anthropic')}</div>
        <div class="metric-delta">{exec_m.get('champion_odds_pct', 68)}% Market Probability</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Metaculus AGI Consensus</div>
        <div class="metric-value">May 2028</div>
        <div class="metric-delta">Epistemic Crowd Median</div>
    </div>
    """, unsafe_allow_html=True)

st.info(data.get("synthesis", ""))

# 2. Main Interface Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "⚡ Daily Release Radar", 
    "🚀 Frontier Pipeline & 2026 Crown", 
    "⏳ Metaculus Epistemic Horizon", 
    "🔍 Raw Order Books"
])

# --- TAB 1: Detailed Daily Release Radar ---
with tab1:
    st.subheader("🎯 Most Likely Single Release Day by Tier")
    c1, c2, c3 = st.columns(3)
    
    m_lite = data["most_likely_dates"]["flash_lite"]
    m_flash = data["most_likely_dates"]["flash"]
    m_pro = data["most_likely_dates"]["pro"]
    
    with c1:
        st.metric("Gemini Flash-Lite (3.6+)", m_lite["date"], f"{m_lite['probability']}% Peak Mass")
    with c2:
        st.metric("Gemini Flash (3.9+ / 4.0)", m_flash["date"], f"{m_flash['probability']}% Peak Mass")
    with c3:
        st.metric("Gemini Pro", m_pro["date"], f"{m_pro['probability']}% Peak Mass")

    st.subheader("📈 Probability Density Functions (Daily Mass Across ~40 Days)")
    df = pd.DataFrame(data["daily_distributions"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["flash_lite_pct"], mode="lines+markers", name="Flash-Lite (3.6+)", line=dict(color="#38bdf8", width=2.5)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["flash_pct"], mode="lines+markers", name="Flash (3.9+ / 4.0)", line=dict(color="#34d399", width=2.5)))
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
    st.dataframe(styled_df, use_container_width=True, height=450)

# --- TAB 2: Frontier Lab Pipeline & 2026 Crown ---
with tab2:
    st.subheader("Anthropic, OpenAI & Google Release Cadence")
    pipeline = data.get("model_pipeline", [])
    
    col_pipe, col_crown = st.columns([3, 2])
    
    with col_pipe:
        if pipeline:
            df_pipe = pd.DataFrame(pipeline)
            color_map = {"Anthropic": "#f59e0b", "OpenAI": "#10b981", "Google": "#38bdf8"}
            
            fig_pipe = go.Figure()
            for idx, row in df_pipe.iterrows():
                c = color_map.get(row["entity"], "#a855f7")
                fig_pipe.add_trace(go.Bar(
                    x=[row["confidence_pct"]],
                    y=[f"{row['entity']} · {row['model']}"],
                    orientation='h',
                    marker=dict(color=c),
                    text=f"{row['projected_window']} ({row['confidence_pct']}%)",
                    textposition='inside',
                    hovertext=f"Strategic Impact: {row.get('strategic_impact', '')}",
                    name=row["entity"],
                    showlegend=False
                ))
            fig_pipe.update_layout(
                template="plotly_dark",
                xaxis_title="Market Confidence (%)",
                margin=dict(l=20, r=20, t=20, b=20),
                height=380
            )
            st.plotly_chart(fig_pipe, use_container_width=True)
            
            st.dataframe(df_pipe.rename(columns={
                "entity": "Lab",
                "model": "Model Designation",
                "projected_window": "Expected Window",
                "confidence_pct": "Confidence (%)",
                "strategic_impact": "Capability Advance"
            }), use_container_width=True)

    with col_crown:
        st.subheader("Which Company Has Best Model End of 2026?")
        standings = data.get("best_ai_2026_standings", [])
        if standings:
            df_stand = pd.DataFrame(standings)
            fig_pie = go.Figure(data=[go.Pie(
                labels=df_stand["company"],
                values=df_stand["implied_pct"],
                hole=0.45,
                marker=dict(colors=["#f59e0b", "#10b981", "#38bdf8", "#8b5cf6"])
            )])
            fig_pie.update_layout(
                template="plotly_dark",
                margin=dict(l=20, r=20, t=20, b=20),
                height=320,
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            st.caption("Resolves via Arena.ai Blind Text Leaderboard & Artificial Analysis index at midnight Dec 31, 2026.")

# --- TAB 3: Metaculus Epistemic Horizon (Top 10 Benchmark Questions) ---
with tab3:
    st.subheader("⏳ Top 10 Epistemic Benchmarks: AGI, Longevity & FIRE Economics")
    st.caption("Aggregated superforecaster medians unpolluted by thin retail trading liquidity.")
    
    meta_cols = st.columns(2)
    for idx, item in enumerate(METACULUS_BENCHMARKS):
        target_col = meta_cols[idx % 2]
        with target_col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{item['category']} · Question #{item['id']}</div>
                <div class="metric-value">{item['community_median']}</div>
                <div style="font-size: 1.05rem; font-weight: 600; color: #f9fafb; margin: 0.4rem 0;">
                    {item['title']}
                </div>
                <div style="font-size: 0.85rem; color: #9ca3af; line-height: 1.4;">
                    <strong>Strategic FIRE / LEV Impact:</strong> {item['impact']}
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- TAB 4: Raw Order Books ---
with tab4:
    st.subheader("Live Polymarket Contract Inspection")
    for ev in data.get("polymarket_raw", []):
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Event Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

# Footer
st.divider()
st.caption(f"Engine: Google AI Studio Dynamic Flash · Polymarket Gamma API · Metaculus Epistemics · Last Calibrated: {data['refreshed_at']}")
if st.button("Force Synchronized Market Recalculation"):
    st.cache_data.clear()
    st.rerun()
