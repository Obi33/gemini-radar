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
        gap: 1.25rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.95rem;
        font-weight: 600;
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

# 1. Target Polymarket Events Across All 3 Labs
POLYMARKET_EVENTS = [
    # Google
    {"slug": "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "entity": "Google", "label": "Gemini Pro"},
    {"slug": "next-google-gemini-pro-model-released-byptptpt", "entity": "Google", "label": "Gemini Pro Cumulative"},
    {"slug": "gemini-4pt0-released-by-june-30-2026", "entity": "Google", "label": "Gemini 4.0 Flash"},
    {"slug": "next-gemini-flash-model-3pt9-released-byptptpt", "entity": "Google", "label": "Gemini Flash 3.9+"},
    {"slug": "next-google-gemini-flash-lite-model-3pt6-released-byptptpt", "entity": "Google", "label": "Gemini Flash-Lite 3.6+"},
    
    # Anthropic
    {"slug": "claude-6-released-byptptpt", "entity": "Anthropic", "label": "Claude 6"},
    {"slug": "next-claude-sonnet-released-byptptpt-20260701203831153", "entity": "Anthropic", "label": "Next Claude Sonnet"},
    {"slug": "next-claude-haiku-released-byptptpt-20260701205353326", "entity": "Anthropic", "label": "Next Claude Haiku"},
    {"slug": "next-fable-model-5pt2-released-byptptpt", "entity": "Anthropic", "label": "Claude Fable 5.2"},
    
    # OpenAI
    {"slug": "gpt-7-released-byptptpt", "entity": "OpenAI", "label": "GPT-7"},
    {"slug": "gpt-astra-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Astra 6.1"},
    {"slug": "next-openai-gpt-terra-5pt7-released-byptptpt", "entity": "OpenAI", "label": "GPT-Terra 5.7"},
    
    # Crown Market
    {"slug": "which-company-has-best-ai-model-end-of-2026", "entity": "Crown", "label": "Best Model End of 2026"}
]

# 2. Top 10 Metaculus Epistemic Benchmarks
METACULUS_BENCHMARKS = [
    {
        "id": 5121,
        "title": "Date of First Artificial General Intelligence (AGI)",
        "category": "AGI Timeline",
        "community_median": "May 2028",
        "impact": "Triggers complete cognitive automation and begins the exponential software deflation cycle."
    },
    {
        "id": 5122,
        "title": "Transition Time: Weak AGI to Superintelligence (ASI)",
        "category": "Superintelligence",
        "community_median": "29.4 Months",
        "impact": "The critical compression window where human scientific progress transitions into recursive self-improvement."
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
        "impact": "Direct verification that solving high-dimensional reasoning is the prerequisite to curing biological senescence."
    },
    {
        "id": 26244,
        "title": "Radical Life Extension Demonstrated Within 5 Years Post-AGI",
        "category": "Biomedicine",
        "community_median": "60% Probability",
        "impact": "Validates that frontier AI architectures will master cellular rejuvenation before 2035."
    },
    {
        "id": 8357,
        "title": "100% Autonomous Software Engineering Replacement",
        "category": "FIRE & Capital",
        "community_median": "November 2027",
        "impact": "Marginal software creation cost approaches zero, accelerating margin expansion for broad index capital."
    },
    {
        "id": 9120,
        "title": "End-to-End AI Molecular Design & Therapeutic Synthesis",
        "category": "Biotech",
        "community_median": "March 2029",
        "impact": "Novel therapeutics discovered, simulated, and validated entirely in silico."
    },
    {
        "id": 7498,
        "title": "Global Real GDP Growth Exceeds 20% Annually",
        "category": "Macro Acceleration",
        "community_median": "2.3 Years Post-AGI",
        "impact": "The unconstrained labor inflection point where capital productivity decouples from human demographic limits."
    },
    {
        "id": 1002,
        "title": "First Human Reaching 150th Birthday",
        "category": "Healthspan",
        "community_median": "Born ~1995-2015",
        "impact": "Cohorts under 40 hold non-trivial actuarial odds of reaching age 150 under early LEV."
    },
    {
        "id": 11452,
        "title": "First Major Economy Implements Universal Capital Dividend",
        "category": "FIRE & Policy",
        "community_median": "August 2031",
        "impact": "Sovereign dividend distribution to offset labor disruption, securing baseline societal living standards."
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
    You are an expert quantitative forecaster and Bayesian modeler.
    Current Date: September 23, 2026.

    LIVE POLYMARKET MARKET DATA:
    {json.dumps(poly_data, indent=2)}

    CALENDAR LIST (40 ENTRIES):
    {json.dumps(calendar_entries, indent=2)}

    REQUIRED TASKS:
    1. MODEL CONTINUOUS DAILY DISTRIBUTIONS FOR ALL 9 TARGET MODELS ACROSS 3 LABS:
       A. GOOGLE:
          - gemini_pro: High-volume anchor ($1.34M cumulative market). Peaks midweek in the October 13-17 window.
          - gemini_flash: Faster rollout, peaking earlier around October 6-10.
          - gemini_flash_lite: Distillation of 3.6, broad early distribution peaking early October (Oct 2-6).
       B. ANTHROPIC:
          - claude_sonnet: High expectation for imminent drop, heavy weight in late September / early October (Sept 29 - Oct 3).
          - claude_haiku: Fast follow, peaks early-to-mid October (Oct 5-9).
          - claude_6: Next-generation frontier flagship, later density peaking late October (Oct 22-28) or into tail.
       C. OPENAI:
          - gpt_terra: Mid-tier checkpoint, peaks early October (Oct 7-12).
          - gpt_astra: Autonomous reasoning tier, peaks mid-to-late October (Oct 15-20).
          - gpt_7: True frontier architectural leap, low probability before end of October, heavy tail distribution.

    2. CURVE SHAPING:
       - No flat horizontal plateaus.
       - Natural midweek crests (Tuesday to Thursday), tapering Fridays, and 0.4% to 0.8% baseline weekend floors.
       - Each model must have its own distinct 'most_likely_date'.

    3. EXECUTIVE METRICS & STANDINGS:
       - fire_deflation_score (1-100) and lev_acceleration_score (1-100).
       - Standings for 'Which company has best AI model end of 2026' (Anthropic, OpenAI, Google).
       - 2-sentence synthesis linking Q4 cluster releases to capital compounding and longevity.

    Return STRICT JSON ONLY with this schema:
    {{
      "executive_metrics": {{
        "fire_deflation_score": 85,
        "lev_acceleration_score": 78,
        "year_end_champion": "Anthropic",
        "champion_odds_pct": 68.0
      }},
      "most_likely_dates": {{
        "google": {{
          "gemini_flash_lite": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "gemini_flash": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "gemini_pro": {{"date": "YYYY-MM-DD", "probability": 0.0}}
        }},
        "anthropic": {{
          "claude_sonnet": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "claude_haiku": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "claude_6": {{"date": "YYYY-MM-DD", "probability": 0.0}}
        }},
        "openai": {{
          "gpt_terra": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "gpt_astra": {{"date": "YYYY-MM-DD", "probability": 0.0}},
          "gpt_7": {{"date": "YYYY-MM-DD", "probability": 0.0}}
        }}
      }},
      "daily_distributions": [
        {{
          "date": "YYYY-MM-DD or no release before october 31",
          "gemini_flash_lite": 0.0,
          "gemini_flash": 0.0,
          "gemini_pro": 0.0,
          "claude_sonnet": 0.0,
          "claude_haiku": 0.0,
          "claude_6": 0.0,
          "gpt_terra": 0.0,
          "gpt_astra": 0.0,
          "gpt_7": 0.0
        }}
      ],
      "best_ai_2026_standings": [
        {{"company": "Anthropic", "implied_pct": 68.0}},
        {{"company": "OpenAI", "implied_pct": 22.0}},
        {{"company": "Google", "implied_pct": 10.0}}
      ],
      "synthesis": "2 sentences synthesizing the competitive Q4 release convergence."
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
        return {"error": f"JSON parsing failed: {str(pe)}. Response snippet: {response.text[:200]}"}

    # Strict Normalization across all 9 models (every model sums to exactly 100.00%)
    model_keys = [
        "gemini_flash_lite", "gemini_flash", "gemini_pro",
        "claude_sonnet", "claude_haiku", "claude_6",
        "gpt_terra", "gpt_astra", "gpt_7"
    ]
    
    distributions = result.get("daily_distributions", [])
    if distributions:
        for k in model_keys:
            total = sum(float(item.get(k, 0.0)) for item in distributions)
            if total > 0:
                for item in distributions:
                    item[k] = round((float(item.get(k, 0.0)) / total) * 100, 2)
                diff = round(100.00 - sum(item[k] for item in distributions), 2)
                distributions[-1][k] = round(distributions[-1][k] + diff, 2)

    # Sanitize modal probability values
    for lab in ["google", "anthropic", "openai"]:
        lab_dict = result.get("most_likely_dates", {}).get(lab, {})
        for m_name, m_info in lab_dict.items():
            val = float(m_info.get("probability", 0.0))
            if 0.0 < val <= 1.0:
                m_info["probability"] = round(val * 100, 1)
            else:
                m_info["probability"] = round(val, 1)

    result["polymarket_raw"] = poly_data
    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    return result

# --- UI Execution ---

st.title("🧬 Frontier AI & Longevity Horizon")
st.caption("Live multi-lab prediction market synthesis mapping intelligence acceleration to FIRE and Longevity Escape Velocity.")

with st.spinner("Processing live order books and computing mathematical distributions across all 3 labs..."):
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

# 2. Main Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "⚡ Daily Release Radars", 
    "🚀 Frontier Landscape & 2026 Crown", 
    "⏳ Metaculus Epistemic Horizon", 
    "🔍 Raw Order Books"
])

# --- TAB 1: Daily Release Radars Across All 3 Labs ---
with tab1:
    df_all = pd.DataFrame(data["daily_distributions"])
    
    # Sub-tabs for clean mobile view
    lab_tab_google, lab_tab_anthropic, lab_tab_openai = st.tabs([
        "🔵 Google (Gemini)", 
        "🟠 Anthropic (Claude)", 
        "🟢 OpenAI (GPT)"
    ])
    
    # --- GOOGLE RADAR ---
    with lab_tab_google:
        st.subheader("Google DeepMind · Implied Release Windows")
        g_dates = data["most_likely_dates"]["google"]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Gemini Flash-Lite (3.6+)", g_dates["gemini_flash_lite"]["date"], f"{g_dates['gemini_flash_lite']['probability']}% Peak Mass")
        with c2:
            st.metric("Gemini Flash (3.9+ / 4.0)", g_dates["gemini_flash"]["date"], f"{g_dates['gemini_flash']['probability']}% Peak Mass")
        with c3:
            st.metric("Gemini Pro", g_dates["gemini_pro"]["date"], f"{g_dates['gemini_pro']['probability']}% Peak Mass")
            
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(x=df_all["date"], y=df_all["gemini_flash_lite"], mode="lines+markers", name="Flash-Lite (3.6+)", line=dict(color="#38bdf8", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_all["date"], y=df_all["gemini_flash"], mode="lines+markers", name="Flash (3.9+ / 4.0)", line=dict(color="#34d399", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_all["date"], y=df_all["gemini_pro"], mode="lines+markers", name="Gemini Pro", line=dict(color="#f43f5e", width=2.5)))
        fig_g.update_layout(
            template="plotly_dark",
            xaxis_title="Date",
            yaxis_title="Probability Density (%)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_g, use_container_width=True)
        
        st.caption(f"Strict Normalization Checksum: Flash-Lite: {df_all['gemini_flash_lite'].sum():.2f}% | Flash: {df_all['gemini_flash'].sum():.2f}% | Pro: {df_all['gemini_pro'].sum():.2f}%")
        st.dataframe(df_all[["date", "gemini_flash_lite", "gemini_flash", "gemini_pro"]].rename(columns={
            "date": "Calendar Date",
            "gemini_flash_lite": "Flash-Lite (%)",
            "gemini_flash": "Flash (%)",
            "gemini_pro": "Pro (%)"
        }), use_container_width=True, height=360)

    # --- ANTHROPIC RADAR ---
    with lab_tab_anthropic:
        st.subheader("Anthropic · Implied Release Windows")
        a_dates = data["most_likely_dates"]["anthropic"]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Next Claude Sonnet", a_dates["claude_sonnet"]["date"], f"{a_dates['claude_sonnet']['probability']}% Peak Mass")
        with c2:
            st.metric("Next Claude Haiku", a_dates["claude_haiku"]["date"], f"{a_dates['claude_haiku']['probability']}% Peak Mass")
        with c3:
            st.metric("Claude 6", a_dates["claude_6"]["date"], f"{a_dates['claude_6']['probability']}% Peak Mass")
            
        fig_a = go.Figure()
        fig_a.add_trace(go.Scatter(x=df_all["date"], y=df_all["claude_sonnet"], mode="lines+markers", name="Next Sonnet", line=dict(color="#f59e0b", width=2.5)))
        fig_a.add_trace(go.Scatter(x=df_all["date"], y=df_all["claude_haiku"], mode="lines+markers", name="Next Haiku", line=dict(color="#fb923c", width=2.5)))
        fig_a.add_trace(go.Scatter(x=df_all["date"], y=df_all["claude_6"], mode="lines+markers", name="Claude 6", line=dict(color="#c084fc", width=2.5)))
        fig_a.update_layout(
            template="plotly_dark",
            xaxis_title="Date",
            yaxis_title="Probability Density (%)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_a, use_container_width=True)
        
        st.caption(f"Strict Normalization Checksum: Sonnet: {df_all['claude_sonnet'].sum():.2f}% | Haiku: {df_all['claude_haiku'].sum():.2f}% | Claude 6: {df_all['claude_6'].sum():.2f}%")
        st.dataframe(df_all[["date", "claude_sonnet", "claude_haiku", "claude_6"]].rename(columns={
            "date": "Calendar Date",
            "claude_sonnet": "Next Sonnet (%)",
            "claude_haiku": "Next Haiku (%)",
            "claude_6": "Claude 6 (%)"
        }), use_container_width=True, height=360)

    # --- OPENAI RADAR ---
    with lab_tab_openai:
        st.subheader("OpenAI · Implied Release Windows")
        o_dates = data["most_likely_dates"]["openai"]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("GPT-Terra 5.7", o_dates["gpt_terra"]["date"], f"{o_dates['gpt_terra']['probability']}% Peak Mass")
        with c2:
            st.metric("GPT-Astra 6.1", o_dates["gpt_astra"]["date"], f"{o_dates['gpt_astra']['probability']}% Peak Mass")
        with c3:
            st.metric("GPT-7", o_dates["gpt_7"]["date"], f"{o_dates['gpt_7']['probability']}% Peak Mass")
            
        fig_o = go.Figure()
        fig_o.add_trace(go.Scatter(x=df_all["date"], y=df_all["gpt_terra"], mode="lines+markers", name="GPT-Terra 5.7", line=dict(color="#10b981", width=2.5)))
        fig_o.add_trace(go.Scatter(x=df_all["date"], y=df_all["gpt_astra"], mode="lines+markers", name="GPT-Astra 6.1", line=dict(color="#06b6d4", width=2.5)))
        fig_o.add_trace(go.Scatter(x=df_all["date"], y=df_all["gpt_7"], mode="lines+markers", name="GPT-7", line=dict(color="#ec4899", width=2.5)))
        fig_o.update_layout(
            template="plotly_dark",
            xaxis_title="Date",
            yaxis_title="Probability Density (%)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_o, use_container_width=True)
        
        st.caption(f"Strict Normalization Checksum: Terra: {df_all['gpt_terra'].sum():.2f}% | Astra: {df_all['gpt_astra'].sum():.2f}% | GPT-7: {df_all['gpt_7'].sum():.2f}%")
        st.dataframe(df_all[["date", "gpt_terra", "gpt_astra", "gpt_7"]].rename(columns={
            "date": "Calendar Date",
            "gpt_terra": "GPT-Terra (%)",
            "gpt_astra": "GPT-Astra (%)",
            "gpt_7": "GPT-7 (%)"
        }), use_container_width=True, height=360)

# --- TAB 2: Frontier Landscape & 2026 Crown ---
with tab2:
    st.subheader("Q4 Frontier Release Windows & 2026 Crown Consensus")
    col_summary, col_pie = st.columns([3, 2])
    
    with col_summary:
        summary_rows = [
            {"Lab": "Google", "Model": "Gemini Flash-Lite (3.6+)", "Window": data["most_likely_dates"]["google"]["gemini_flash_lite"]["date"], "Impact": "Distillation throughput"},
            {"Lab": "Google", "Model": "Gemini Flash (3.9+ / 4.0)", "Window": data["most_likely_dates"]["google"]["gemini_flash"]["date"], "Impact": "Low-latency multimodal reasoning"},
            {"Lab": "Google", "Model": "Gemini Pro", "Window": data["most_likely_dates"]["google"]["gemini_pro"]["date"], "Impact": "Frontier agentic coding & long context"},
            {"Lab": "Anthropic", "Model": "Next Claude Sonnet", "Window": data["most_likely_dates"]["anthropic"]["claude_sonnet"]["date"], "Impact": "Autonomous software engineering standard"},
            {"Lab": "Anthropic", "Model": "Next Claude Haiku", "Window": data["most_likely_dates"]["anthropic"]["claude_haiku"]["date"], "Impact": "Cost-efficient tool use execution"},
            {"Lab": "Anthropic", "Model": "Claude 6", "Window": data["most_likely_dates"]["anthropic"]["claude_6"]["date"], "Impact": "Next-generation epistemic architecture"},
            {"Lab": "OpenAI", "Model": "GPT-Terra 5.7", "Window": data["most_likely_dates"]["openai"]["gpt_terra"]["date"], "Impact": "Iterative developer workflow upgrade"},
            {"Lab": "OpenAI", "Model": "GPT-Astra 6.1", "Window": data["most_likely_dates"]["openai"]["gpt_astra"]["date"], "Impact": "Continuous test-time compute & planning"},
            {"Lab": "OpenAI", "Model": "GPT-7", "Window": data["most_likely_dates"]["openai"]["gpt_7"]["date"], "Impact": "Universal self-directed research agent"}
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

    with col_pie:
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
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            st.caption("Resolves via Arena.ai Blind Leaderboard & Artificial Analysis index at midnight Dec 31, 2026.")

# --- TAB 3: Metaculus Epistemic Horizon (Top 10 Benchmark Questions) ---
with tab3:
    st.subheader("⏳ Top 10 Epistemic Benchmarks: AGI, Longevity & FIRE Economics")
    st.caption("Aggregated superforecaster medians unpolluted by retail betting illiquidity.")
    
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
