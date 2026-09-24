import streamlit as st
import requests
import json
import os
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
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

def fetch_single_event(item):
    slug = item["slug"]
    base_url = "https://gamma-api.polymarket.com/events?slug="
    try:
        res = requests.get(f"{base_url}{slug}", timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                ev = data[0]
                extracted = []
                for m in ev.get("markets", []):
                    q = m.get("question", "")
                    title = m.get("groupItemTitle", "") or q
                    prices_raw = m.get("outcomePrices", '["0.5", "0.5"]')
                    try:
                        yes_price = float(json.loads(prices_raw)[0])
                    except Exception:
                        yes_price = 0.5
                    vol = float(m.get("volumeNum", 0) or m.get("volume", 0) or 0)
                    
                    if "no release" in (q + " " + title).lower():
                        implied = round(1.0 - yes_price, 4)
                    else:
                        implied = round(yes_price, 4)
                        
                    extracted.append({
                        "option": title,
                        "implied_prob": implied,
                        "raw_yes": yes_price,
                        "volume": vol
                    })
                return {
                    "label": item["label"],
                    "entity": item["entity"],
                    "slug": slug,
                    "options": extracted
                }
    except Exception:
        pass
    return None

def fetch_all_polymarket_data():
    records = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_single_event, item) for item in POLYMARKET_EVENTS]
        for f in as_completed(futures):
            res = f.result()
            if res:
                records.append(res)
    return records

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

def execute_gemini_interactions(client, prompt):
    candidate_models = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    
    if hasattr(client, "interactions"):
        for m in candidate_models:
            try:
                interaction = client.interactions.create(
                    model=m,
                    input=prompt,
                    response_format={"type": "text", "mime_type": "application/json"},
                    generation_config={"thinking_level": "low"}
                )
                text = getattr(interaction, "output_text", None)
                if not text and hasattr(interaction, "outputs") and interaction.outputs:
                    text = interaction.outputs[-1].text
                if text:
                    return text, f"{m} (Interactions API)"
            except Exception:
                continue

    for m in candidate_models:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            if resp and resp.text:
                return resp.text, f"{m} (GenerateContent API)"
        except Exception:
            continue

    raise RuntimeError("All candidate endpoints failed. Verify API key status.")

def build_discrete_density(peak_date_str, spread_days, tail_pct, start_d, end_d):
    """Calculates continuous density across calendar days without artificial edge cliffs."""
    try:
        p_date = datetime.strptime(peak_date_str, "%Y-%m-%d").date()
    except Exception:
        p_date = start_d + timedelta(days=15)
        
    num_days = (end_d - start_d).days + 1
    available_mass = max(0.5, 100.0 - float(tail_pct))
    
    # Models with tail >= 90% (e.g. Claude 6, GPT-7) spread low residual mass evenly
    if float(tail_pct) >= 90.0:
        base_daily = round(available_mass / num_days, 3)
        return [base_daily] * num_days
    
    raw_weights = []
    for i in range(num_days):
        curr_d = start_d + timedelta(days=i)
        diff = (curr_d - p_date).days
        base_w = math.exp(-0.5 * ((diff / max(1.5, spread_days)) ** 2))
        
        weekday = curr_d.weekday()
        if weekday in [1, 2, 3]:    # Tue, Wed, Thu
            w_factor = 1.0
        elif weekday == 0:          # Mon
            w_factor = 0.75
        elif weekday == 4:          # Fri
            w_factor = 0.60
        else:                       # Sat, Sun
            w_factor = 0.15
            
        raw_weights.append(base_w * w_factor)
        
    sum_w = sum(raw_weights)
    if sum_w > 0:
        daily_pcts = [round((w / sum_w) * available_mass, 2) for w in raw_weights]
    else:
        daily_pcts = [round(available_mass / num_days, 2)] * num_days
        
    return daily_pcts

@st.cache_data(ttl=3600)
def compute_macro_horizon():
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    poly_data = fetch_all_polymarket_data()
    if not poly_data:
        return {"error": "Failed to pull live Polymarket market data."}

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are an expert quantitative forecaster and Bayesian modeler.
    Current Date: Late September 2026.

    LIVE POLYMARKET MARKET DATA:
    {json.dumps(poly_data, indent=2)}

    MANDATORY QUANTITATIVE RULES:
    1. PEAK SPREAD CRITERIA:
       - Only assign a sharp near-term peak (spread_days <= 4.0) when market volume is high (> $50k) AND cumulative probability rises steeply in a 7-10 day window (e.g. Gemini Pro).
    2. OPENAI CADENCE PRIOR:
       - The full GPT-6 family (Astra, Sol, Luna) just completed deployment on September 22.
       - Any 'Terra 5.7' or 'Astra 6.1' contracts are thin point-release markets.
       - Give them wider spreads (spread_days >= 6.0) and elevated post-October tails (tail_pct >= 40.0).
    3. FRONTIER ARCHITECTURAL LEAPS:
       - Claude 6 and GPT-7 are multi-year frontier architectures (2027+ horizon).
       - tail_pct MUST be 95.0% or higher.
    4. MEDIAN ANCHORING:
       - Prefer medians implied by the cumulative 'by date' contracts (the date where cumulative probability crosses 50%) rather than inventing point peaks.
    5. UNCERTAINTY DEFAULT:
       - When volume is low or books are thin, widen the spread and raise the post-October tail.

    Return strict JSON ONLY with this schema:
    {{
      "executive_metrics": {{
        "fire_deflation_score": 85,
        "lev_acceleration_score": 78,
        "year_end_champion": "Anthropic",
        "champion_odds_pct": 68.0
      }},
      "model_anchors": {{
        "gemini_flash_lite": {{"peak_date": "YYYY-MM-DD", "spread_days": 4.5, "tail_pct": 20.0}},
        "gemini_flash": {{"peak_date": "YYYY-MM-DD", "spread_days": 4.0, "tail_pct": 18.0}},
        "gemini_pro": {{"peak_date": "YYYY-MM-DD", "spread_days": 3.0, "tail_pct": 15.0}},
        "claude_sonnet": {{"peak_date": "YYYY-MM-DD", "spread_days": 3.5, "tail_pct": 15.0}},
        "claude_haiku": {{"peak_date": "YYYY-MM-DD", "spread_days": 4.0, "tail_pct": 20.0}},
        "claude_fable": {{"peak_date": "YYYY-MM-DD", "spread_days": 5.0, "tail_pct": 30.0}},
        "claude_6": {{"peak_date": "2027-04-15", "spread_days": 8.0, "tail_pct": 96.5}},
        "gpt_terra": {{"peak_date": "YYYY-MM-DD", "spread_days": 6.0, "tail_pct": 45.0}},
        "gpt_astra": {{"peak_date": "YYYY-MM-DD", "spread_days": 6.5, "tail_pct": 48.0}},
        "gpt_7": {{"peak_date": "2027-06-30", "spread_days": 8.0, "tail_pct": 97.5}}
      }},
      "best_ai_2026_standings": [
        {{"company": "Anthropic", "implied_pct": 68.0}},
        {{"company": "OpenAI", "implied_pct": 22.0}},
        {{"company": "Google", "implied_pct": 10.0}}
      ],
      "synthesis": "2 concise sentences explaining the competitive release calibration."
    }}
    """

    try:
        raw_text, active_model = execute_gemini_interactions(client, prompt)
    except Exception as api_err:
        return {"error": f"API execution failed: {str(api_err)}"}

    try:
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean_text)
    except Exception as pe:
        return {"error": f"JSON parsing failed: {str(pe)}. Raw snippet: {raw_text[:200]}"}

    start_d = date(2026, 9, 23)
    end_d = date(2026, 10, 31)
    num_days = (end_d - start_d).days + 1
    date_labels = [(start_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]
    
    anchors = result.get("model_anchors", {})
    daily_table = {"date": date_labels}
    tail_summary = {}

    all_keys = [
        "gemini_flash_lite", "gemini_flash", "gemini_pro",
        "claude_sonnet", "claude_haiku", "claude_fable", "claude_6",
        "gpt_terra", "gpt_astra", "gpt_7"
    ]

    for k in all_keys:
        spec = anchors.get(k, {})
        p_date = spec.get("peak_date", "2026-10-15")
        spread = float(spec.get("spread_days", 5.0))
        tail = float(spec.get("tail_pct", 25.0))

        # Hardcoded quantitative enforcement of your 5 rules
        if k in ["claude_6", "gpt_7"]:
            tail = max(tail, 95.0)
            spread = max(spread, 7.0)
        elif k in ["gpt_terra", "gpt_astra"]:
            spread = max(spread, 6.0)
            tail = max(tail, 40.0)
        elif k == "gemini_pro":
            spread = min(max(spread, 2.5), 4.0)

        curve = build_discrete_density(p_date, spread, tail, start_d, end_d)
        daily_table[k] = curve
        tail_summary[k] = round(tail, 1)

    result["daily_df"] = pd.DataFrame(daily_table)
    result["tail_summary"] = tail_summary
    result["polymarket_raw"] = poly_data
    result["active_model"] = active_model
    result["refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    return result

def get_calibrated_peak(df, tail_val, col_name):
    if float(tail_val) >= 75.0:
        return "Post-October 31", f"{tail_val}% Post-Oct Tail"
    
    if col_name in df.columns:
        idx = df[col_name].idxmax()
        peak_d = df.loc[idx, "date"]
        peak_pct = round(float(df.loc[idx, col_name]), 1)
        return peak_d, f"{peak_pct}% Daily Density"
        
    return "Pending", "0.0%"

# --- UI Execution ---

st.title("🧬 Frontier AI & Longevity Horizon")
st.caption("Live multi-lab prediction market synthesis mapping intelligence acceleration to personal autonomy and healthspan.")

with st.spinner("Harvesting live order books in parallel and calibrating continuous distributions..."):
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

df_daily = data["daily_df"]
tails = data["tail_summary"]

# --- TAB 1: Daily Release Radars Across All 3 Labs ---
with tab1:
    lab_tab_google, lab_tab_anthropic, lab_tab_openai = st.tabs([
        "🔵 Google (Gemini)", 
        "🟠 Anthropic (Claude)", 
        "🟢 OpenAI (GPT)"
    ])
    
    # --- GOOGLE ---
    with lab_tab_google:
        st.subheader("Google DeepMind · Implied Release Windows")
        d_lite, p_lite = get_calibrated_peak(df_daily, tails["gemini_flash_lite"], "gemini_flash_lite")
        d_flash, p_flash = get_calibrated_peak(df_daily, tails["gemini_flash"], "gemini_flash")
        d_pro, p_pro = get_calibrated_peak(df_daily, tails["gemini_pro"], "gemini_pro")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Gemini Flash-Lite (3.6+)", d_lite, p_lite)
        with c2:
            st.metric("Gemini Flash (3.9+ / 4.0)", d_flash, p_flash)
        with c3:
            st.metric("Gemini Pro", d_pro, p_pro)
            
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_flash_lite"], mode="lines+markers", name="Flash-Lite (3.6+)", line=dict(color="#38bdf8", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_flash"], mode="lines+markers", name="Flash (3.9+ / 4.0)", line=dict(color="#34d399", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_pro"], mode="lines+markers", name="Gemini Pro", line=dict(color="#f43f5e", width=2.5)))
        fig_g.update_layout(
            template="plotly_dark",
            xaxis_title="Calendar Date (September - October 2026)",
            yaxis_title="Implied Daily Probability (%)",
        
