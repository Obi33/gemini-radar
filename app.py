import streamlit as st
import requests
import json
import os
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta, timezone
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
from google import genai

st.set_page_config(
    page_title="Frontier Horizon | FIRE, LEV & Intelligence Acceleration", 
    page_icon="🧬", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark ergonomic styling locked for mobile and desktop
st.markdown("""
<style>
    .metric-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 0.75rem;
        padding: 1.15rem;
        margin-bottom: 0.75rem;
    }
    .metric-title {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin-bottom: 0.2rem;
    }
    .metric-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #f3f4f6;
    }
    .metric-delta {
        font-size: 0.78rem;
        font-weight: 500;
        color: #10b981;
    }
    .countdown-box {
        background: linear-gradient(135deg, #111827 0%, #1e1b4b 100%);
        border: 1px solid #3730a3;
        border-radius: 0.75rem;
        padding: 1rem;
        text-align: center;
        margin-bottom: 0.75rem;
    }
    .countdown-num {
        font-size: 1.75rem;
        font-weight: 800;
        color: #a5b4fc;
        font-variant-numeric: tabular-nums;
    }
    .countdown-sub {
        font-size: 0.72rem;
        color: #c7d2fe;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.1rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.92rem;
        font-weight: 600;
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
    }
</style>
""", unsafe_allow_html=True)

def get_budapest_now():
    try:
        tz = zoneinfo.ZoneInfo("Europe/Budapest")
        return datetime.now(tz)
    except Exception:
        return datetime.now(timezone(timedelta(hours=2)))

POLYMARKET_EVENTS = [
    {"slug": "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "entity": "Google", "label": "Gemini Pro"},
    {"slug": "next-google-gemini-pro-model-released-byptptpt", "entity": "Google", "label": "Gemini Pro Cumulative"},
    {"slug": "next-google-gemini-pro-model-released-onptptpt-20260817141404356", "entity": "Google", "label": "Gemini Pro Daily"},
    {"slug": "gemini-4pt0-released-by-june-30-2026", "entity": "Google", "label": "Gemini 4.0 Flash"},
    {"slug": "next-gemini-flash-model-3pt9-released-byptptpt", "entity": "Google", "label": "Gemini Flash 3.9+"},
    {"slug": "next-google-gemini-flash-lite-model-3pt6-released-byptptpt", "entity": "Google", "label": "Gemini Flash-Lite 3.6+"},
    {"slug": "next-gemini-pro-model-released-onptptpt-20260922131618444", "entity": "Google", "label": "Gemini Pro Oct Window"},
    {"slug": "next-openai-gpt-terra-5pt7-released-byptptpt", "entity": "OpenAI", "label": "GPT-Terra 5.7"},
    {"slug": "gpt-astra-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Astra 6.1"},
    {"slug": "next-gpt-sol-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Sol 6.1"},
    {"slug": "next-gpt-luna-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Luna 6.1"},
    {"slug": "gpt-7-released-byptptpt", "entity": "OpenAI", "label": "GPT-7 (Frontier)"},
    {"slug": "next-claude-sonnet-released-byptptpt-20260701203831153", "entity": "Anthropic", "label": "Next Claude Sonnet"},
    {"slug": "next-claude-sonnet-released-onptptpt-20260921225443", "entity": "Anthropic", "label": "Claude Sonnet Daily"},
    {"slug": "next-claude-haiku-released-byptptpt-20260701205353326", "entity": "Anthropic", "label": "Next Claude Haiku"},
    {"slug": "next-claude-opus-released-byptptpt-20260923144500000", "entity": "Anthropic", "label": "Next Claude Opus"},
    {"slug": "next-fable-model-5pt2-released-byptptpt", "entity": "Anthropic", "label": "Claude Fable 5.2"},
    {"slug": "claude-6-released-byptptpt", "entity": "Anthropic", "label": "Claude 6 (Frontier)"},
    {"slug": "next-french-presidential-election", "entity": "Geopolitics", "label": "French Presidential Election"},
    {"slug": "balance-of-power-2026-midterms", "entity": "Geopolitics", "label": "US Midterms Balance of Power"},
    {"slug": "will-cmi-declare-a-millennium-prize-problem-solved-by-20260723160122979", "entity": "Math", "label": "CMI Millennium Prize Declaration"},
    {"slug": "ai-lab-announces-another-millennium-prize-solution-by", "entity": "Math", "label": "AI Lab Announces Millennium Solution"},
    {"slug": "openai-announces-another-millennium-prize-solution-by", "entity": "Math", "label": "OpenAI Announces Millennium Solution"},
    {"slug": "which-millennium-prize-problem-will-ai-solve-next", "entity": "Math", "label": "Which Millennium Problem Next"},
    {"slug": "how-many-more-millennium-prize-problems-will-ai-solve-in-2026", "entity": "Math", "label": "Total Millennium Problems Solved 2026"},
    {"slug": "anthropic-announces-a-millennium-prize-solution-byptptpt", "entity": "Math", "label": "Anthropic Announces Millennium Solution"},
    {"slug": "which-math-problems-will-ai-solve-in-2026", "entity": "Math", "label": "Math Problems Solved 2026"}
]

STATIC_ALAN_50_INDICATORS = [
    {"id": 1, "name": "Formal Proof of Navier-Stokes Singularity Formation", "category": "Mathematics", "status": "Achieved", "date": "2026-09"},
    {"id": 2, "name": "Self-Supervised De Novo Protein Rejuvenation Sequence", "category": "Biomedicine", "status": "Achieved", "date": "2026-07"},
    {"id": 3, "name": "Autonomous End-to-End Compiler Optimization (C/Rust)", "category": "Software", "status": "Achieved", "date": "2026-08"},
    {"id": 4, "name": "Direct In Silico Small Molecule Drug Target Hit (>99% Affinity)", "category": "Biomedicine", "status": "Achieved", "date": "2026-05"},
    {"id": 5, "name": "Superhuman Competitive Programming (IOI Gold Level)", "category": "Software", "status": "Achieved", "date": "2025-12"},
    {"id": 6, "name": "Autonomous Erdos Conjecture Settlement (Disproof/Proof)", "category": "Mathematics", "status": "Achieved", "date": "2026-06"},
    {"id": 7, "name": "High-Density Universal Robot World Model Zero-Shot Transfer", "category": "Robotics", "status": "Achieved", "date": "2026-08"},
    {"id": 8, "name": "Automated Bug Bounding & Kernel Exploit Zero-Day Synthesis", "category": "Software", "status": "Achieved", "date": "2026-07"},
    {"id": 9, "name": "Continuous Test-Time Compute Self-Correction Loop", "category": "Reasoning", "status": "Achieved", "date": "2026-09"},
    {"id": 10, "name": "Autonomous Material Lattice Superconductor Screening", "category": "Physics", "status": "Achieved", "date": "2026-08"},
    {"id": 11, "name": "Hodge Conjecture Sub-Case Formalization in Lean 4", "category": "Mathematics", "status": "In Progress", "date": "2026-11"},
    {"id": 12, "name": "Whole-Cell Epigenetic Aging Clock Reversal Simulation", "category": "Longevity", "status": "In Progress", "date": "2026-12"},
    {"id": 13, "name": "Full Codebase Autonomous Architecture Refactoring (10M+ LOC)", "category": "Software", "status": "In Progress", "date": "2026-10"},
    {"id": 14, "name": "Birch & Swinnerton-Dyer Rank Parity Verification", "category": "Mathematics", "status": "In Progress", "date": "2027-02"},
    {"id": 15, "name": "Self-Directed Wet-Lab Chemistry Synthesis API Loop", "category": "Biochemistry", "status": "In Progress", "date": "2026-12"},
    {"id": 16, "name": "Superhuman Cross-Disciplinary Grant Hypothesis Synthesis", "category": "Science", "status": "In Progress", "date": "2027-01"},
    {"id": 17, "name": "Mitochondrial DNA Mutation Repair Modeling", "category": "Longevity", "status": "In Progress", "date": "2027-03"},
    {"id": 18, "name": "Continuous Recursive Model Alignment & Oversight Agents", "category": "Alignment", "status": "In Progress", "date": "2026-11"},
    {"id": 19, "name": "Zero-Human Input Hardware Architecture Schematic Design", "category": "Hardware", "status": "In Progress", "date": "2027-04"},
    {"id": 20, "name": "Autonomous Microeconomic Arbitrage & Supply Chain Optimization", "category": "Economy", "status": "In Progress", "date": "2026-12"},
    {"id": 21, "name": "Complete In Vitro Neural Connectome Dynamic Simulation", "category": "Neuroscience", "status": "In Progress", "date": "2027-06"},
    {"id": 22, "name": "Universal Mathematical Translation & Lean Autoformalization", "category": "Mathematics", "status": "In Progress", "date": "2027-01"},
    {"id": 23, "name": "Automated Clinical Trial Synthetic Cohort Modeling", "category": "Medicine", "status": "In Progress", "date": "2027-04"},
    {"id": 24, "name": "Self-Synthesizing Autonomous Machine Learning Engineer", "category": "Software", "status": "In Progress", "date": "2026-11"},
    {"id": 25, "name": "Quantum Chromodynamics Lattice Mass Gap Simulation", "category": "Physics", "status": "In Progress", "date": "2027-08"},
    {"id": 26, "name": "Senolytic Molecule Target Discovery & Toxicity Filter", "category": "Longevity", "status": "In Progress", "date": "2027-03"},
    {"id": 27, "name": "Autonomous Space Mission Orbit & Trajectory Optimizer", "category": "Astrophysics", "status": "Pending", "date": "2027-09"},
    {"id": 28, "name": "Riemann Hypothesis Zero-Density Critical Strip Proof", "category": "Mathematics", "status": "Pending", "date": "2028-02"},
    {"id": 29, "name": "Telomere Lengthening Transcriptional Factor Cocktail Design", "category": "Longevity", "status": "Pending", "date": "2027-11"},
    {"id": 30, "name": "Fully Unsupervised Scientific Paper Review & Flaw Finder", "category": "Science", "status": "Pending", "date": "2027-05"},
    {"id": 31, "name": "Autonomous Robot Surgery Precision Benchmark (Micron-Scale)", "category": "Robotics", "status": "Pending", "date": "2027-12"},
    {"id": 32, "name": "P vs NP Structural Inseparability Verification", "category": "Mathematics", "status": "Pending", "date": "2029-05"},
    {"id": 33, "name": "Universal Translation of Complex Non-Human Animal Communication", "category": "Bioacoustics", "status": "Pending", "date": "2028-04"},
    {"id": 34, "name": "Self-Assembling Nanomedicine Drug Delivery Platform", "category": "Nanotech", "status": "Pending", "date": "2028-07"},
    {"id": 35, "name": "Autonomous Fusion Tokamak Plasma Stability Control (100h+)", "category": "Energy", "status": "Pending", "date": "2028-01"},
    {"id": 36, "name": "Extracellular Matrix Glycation Crosslink Cleavage Formulation", "category": "Longevity", "status": "Pending", "date": "2028-06"},
    {"id": 37, "name": "Autonomous Micro-Fab Silicon Mask Routing & Verification", "category": "Hardware", "status": "Pending", "date": "2028-03"},
    {"id": 38, "name": "Continuous Real-Time Global Macro Forecast (Beat IMF/Fed)", "category": "Economy", "status": "Pending", "date": "2027-10"},
    {"id": 39, "name": "Universal Molecular Simulation at Sub-Atomic Resolution", "category": "Physics", "status": "Pending", "date": "2028-11"},
    {"id": 40, "name": "Direct Intracellular Organelle Regeneration Stimulation", "category": "Longevity", "status": "Pending", "date": "2028-09"},
    {"id": 41, "name": "Self-Replicating Robotic Assembly Workflow Specification", "category": "Manufacturing", "status": "Pending", "date": "2029-03"},
    {"id": 42, "name": "Autonomous Legal Corpus Reconciler & Conflict Resolution", "category": "Law", "status": "Pending", "date": "2027-12"},
    {"id": 43, "name": "AI-Discovered High-Yield Ambient Nitrogen Fixation Catalyst", "category": "Chemistry", "status": "Pending", "date": "2028-10"},
    {"id": 44, "name": "Zero-Human Input Peer-Reviewed Top-Tier Journal Monograph", "category": "Science", "status": "Pending", "date": "2028-05"},
    {"id": 45, "name": "Complete Synthetic Immune System Re-Engineering Protocol", "category": "Immunology", "status": "Pending", "date": "2029-08"},
    {"id": 46, "name": "Deep Space Optical Communications Real-Time Routing Agent", "category": "Aerospace", "status": "Pending", "date": "2029-01"},
    {"id": 47, "name": "Autonomous High-Energy Particle Collision Anomaly Discovery", "category": "Physics", "status": "Pending", "date": "2028-12"},
    {"id": 48, "name": "Cognitive Architecture Exceeding Human Brain Equivalent FLOPS", "category": "Hardware", "status": "Pending", "date": "2029-06"},
    {"id": 49, "name": "In Vivo Whole-Organ Rejuvenation Demonstrated in Mammals", "category": "Longevity", "status": "Pending", "date": "2029-11"},
    {"id": 50, "name": "Recursive Closed-Loop ASI Research & Iteration Engine", "category": "Superintelligence", "status": "Pending", "date": "2030-04"}
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

def fetch_all_polymarket_parallel(progress_callback=None):
    records = []
    total = len(POLYMARKET_EVENTS)
    completed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_event, item) for item in POLYMARKET_EVENTS]
        for f in as_completed(futures):
            res = f.result()
            if res:
                records.append(res)
            completed += 1
            if progress_callback:
                progress_callback(completed / total)
    return records

def get_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.environ.get("GEMINI_API_KEY")

def execute_gemini_with_fallback(client, prompt):
    # Rule 2: Try primary model up to 3 times, then fall back to 3.6-flash
    primary_model = "gemini-3.8-flash"
    fallback_model = "gemini-3.6-flash"
    
    last_err = None
    
    # 3 attempts on primary model
    for attempt in range(1, 4):
        try:
            if hasattr(client, "interactions"):
                interaction = client.interactions.create(
                    model=primary_model,
                    input=prompt
                )
                text = getattr(interaction, "output_text", None)
                if not text and hasattr(interaction, "outputs") and interaction.outputs:
                    text = interaction.outputs[-1].text
                if text:
                    return text, f"{primary_model} (Interactions API)"
            resp = client.models.generate_content(
                model=primary_model,
                contents=prompt
            )
            if resp and resp.text:
                return resp.text, f"{primary_model} (GenerateContent API)"
        except Exception as e:
            last_err = e
            time.sleep(0.5)

    # Fallback to secondary model
    try:
        if hasattr(client, "interactions"):
            interaction = client.interactions.create(
                model=fallback_model,
                input=prompt
            )
            text = getattr(interaction, "output_text", None)
            if not text and hasattr(interaction, "outputs") and interaction.outputs:
                text = interaction.outputs[-1].text
            if text:
                return text, f"{fallback_model} (Fallback Interactions API)"
        resp = client.models.generate_content(
            model=fallback_model,
            contents=prompt
        )
        if resp and resp.text:
            return resp.text, f"{fallback_model} (Fallback GenerateContent API)"
    except Exception as e:
        last_err = e

    raise RuntimeError(f"All candidate endpoints failed after 3 retries on {primary_model}. Please verify model availability and API key quota. Error: {str(last_err)}")

def build_discrete_density(peak_date_str, spread_days, tail_pct, start_d, end_d):
    try:
        p_date = datetime.strptime(peak_date_str, "%Y-%m-%d").date()
    except Exception:
        p_date = start_d + timedelta(days=15)
        
    num_days = (end_d - start_d).days + 1
    available_mass = max(0.5, 100.0 - float(tail_pct))
    
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

def execute_pipeline(progress_bar, status_text):
    api_key = get_api_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY secret not found in Streamlit Secrets."}

    # Step 1: Parallel Polymarket Harvest
    status_text.markdown("⚡ **[1/5] Ingesting 27 Polymarket contract order books in parallel...**")
    def update_poly_progress(ratio):
        progress_bar.progress(int(ratio * 30))
    poly_data = fetch_all_polymarket_parallel(update_poly_progress)
    if not poly_data:
        return {"error": "Failed to pull live Polymarket market data."}

    # Step 2: Model Calibration via Gemini 3.8 Flash
    status_text.markdown("🧠 **[2/5] Synthesizing order books with Gemini 3.8 Flash (Headless Engine)...**")
    progress_bar.progress(45)

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are a headless quantitative engine.
    Current Date: Late September 2026.
    User Profile: European / Hungarian investor (holding TBSZ / VUAA global equity index ETF, targeting perpetual FIRE and biological Longevity Escape Velocity LEV).

    LIVE POLYMARKET MARKET DATA:
    {json.dumps(poly_data, indent=2)}

    MANDATORY QUANTITATIVE CONSTRAINTS:
    1. Google: Gemini Pro (peaks Oct 15-17, tail 15%), Flash (peaks Oct 8-10, tail 14%), Flash-Lite (peaks Oct 2-5, tail 12%).
    2. Anthropic: Next Sonnet (peaks Sep 30 - Oct 3, tail 10%), Next Haiku (peaks Oct 6-9, tail 12%), Next Opus (peaks Oct 22-28, tail 25%), Claude Fable 5.2 (peaks Oct 15-20, tail 18%), Claude 6 (tail_pct >= 96.0%).
    3. OpenAI: GPT-Terra (peaks Oct 8-12, tail 42%), GPT-Astra (peaks Oct 16-20, tail 45%), GPT-Sol (peaks Oct 22-27, tail 48%), GPT-Luna (peaks Oct 26-30, tail 50%), GPT-7 (tail_pct >= 97.5%).
    4. Net Personal Effect (-100% to +100%): Quantify personal life impact (FIRE compounding, cost of living software deflation, LEV biological acceleration) for:
       - French Presidential Election scenarios (Bardella / RN vs Centrist Coalition vs Left NFP)
       - US 2026 Midterm scenarios (Split Gridlock vs GOP Sweep vs Dem Sweep)
       - Each of the 13 AI model releases
    5. Personal Life Compression Multipliers:
       - fire_compression_months: Months pulled forward on the user's late 2031 FIRE target (integer 0 to 24).
       - lev_compression_months: Months pulled forward on the user's October 2037 LEV horizon (integer 0 to 36).
    6. Millennium Prize & Frontier Math: Most probable calendar date that a credible solution is publicly published for:
       Navier-Stokes, Hodge Conjecture, Birch and Swinnerton-Dyer, Riemann Hypothesis, Yang-Mills, P vs NP, and General Frontier Math.

    Return ONLY raw valid JSON matching this schema, without backticks or markdown:
    {{
      "executive_metrics": {{
        "fire_deflation_score": 86,
        "lev_acceleration_score": 79,
        "fire_compression_months": 10,
        "lev_compression_months": 14,
        "alan_agi_pct": 99.0,
        "alan_agi_completion_date": "2026-12-15"
      }},
      "model_anchors": {{
        "gemini_flash_lite": {{"peak_date": "2026-10-04", "spread_days": 4.5, "tail_pct": 12.0, "net_personal_effect": 18}},
        "gemini_flash": {{"peak_date": "2026-10-09", "spread_days": 4.0, "tail_pct": 14.0, "net_personal_effect": 22}},
        "gemini_pro": {{"peak_date": "2026-10-16", "spread_days": 3.0, "tail_pct": 15.0, "net_personal_effect": 55}},
        "claude_sonnet": {{"peak_date": "2026-10-01", "spread_days": 3.0, "tail_pct": 10.0, "net_personal_effect": 48}},
        "claude_haiku": {{"peak_date": "2026-10-07", "spread_days": 4.0, "tail_pct": 12.0, "net_personal_effect": 15}},
        "claude_opus": {{"peak_date": "2026-10-24", "spread_days": 4.5, "tail_pct": 25.0, "net_personal_effect": 42}},
        "claude_fable": {{"peak_date": "2026-10-17", "spread_days": 4.0, "tail_pct": 18.0, "net_personal_effect": 26}},
        "claude_6": {{"peak_date": "2027-04-15", "spread_days": 8.0, "tail_pct": 96.5, "net_personal_effect": 78}},
        "gpt_terra": {{"peak_date": "2026-10-10", "spread_days": 6.0, "tail_pct": 42.0, "net_personal_effect": 16}},
        "gpt_astra": {{"peak_date": "2026-10-18", "spread_days": 6.5, "tail_pct": 45.0, "net_personal_effect": 30}},
        "gpt_sol": {{"peak_date": "2026-10-24", "spread_days": 6.5, "tail_pct": 48.0, "net_personal_effect": 24}},
        "gpt_luna": {{"peak_date": "2026-10-28", "spread_days": 7.0, "tail_pct": 50.0, "net_personal_effect": 20}},
        "gpt_7": {{"peak_date": "2027-06-30", "spread_days": 8.0, "tail_pct": 97.5, "net_personal_effect": 85}}
      }},
      "geopolitics_scenarios": [
        {{"event": "French Presidential Election", "outcome": "National Rally / Bardella Victory", "probability_pct": 46.0, "net_personal_effect": -24, "transmission": "EU budget friction, EUR weakness vs USD, trade friction impacting Hungarian exports and currency stability."}},
        {{"event": "French Presidential Election", "outcome": "Centrist / Pro-European Coalition", "probability_pct": 38.0, "net_personal_effect": 18, "transmission": "Single market integrity preserved, defense procurement compounding, stable EU tech framework."}},
        {{"event": "French Presidential Election", "outcome": "New Popular Front (Left Coalition)", "probability_pct": 16.0, "net_personal_effect": -12, "transmission": "Increased corporate wealth taxes on CAC 40 multinationals, regulatory caution on compute infrastructure."}},
        {{"event": "US 2026 Midterms", "outcome": "Split Congress (Gridlock: GOP Senate / Dem House)", "probability_pct": 52.0, "net_personal_effect": 22, "transmission": "Peak regulatory stability: no disruptive tax hikes or antitrust breakups, optimal for continuous VUAA compounding."}},
        {{"event": "US 2026 Midterms", "outcome": "Republican Unified Sweep", "probability_pct": 32.0, "net_personal_effect": 12, "transmission": "Corporate tax reductions and deregulated compute buildouts offset by aggressive tariff pressure on European trade."}},
        {{"event": "US 2026 Midterms", "outcome": "Democratic Unified Sweep", "probability_pct": 14.0, "net_personal_effect": -8, "transmission": "Aggressive frontier model liability frameworks and antitrust scrutiny on hyperscalers."}}
      ],
      "millennium_math_solutions": [
        {{"problem": "Navier-Stokes Singularity Formation", "credible_solution_date": "2026-11-15", "probability_pct": 92.0, "primary_contender": "OpenAI / Independent Hybrid Proof", "breakthrough_impact": "Fluid dynamics, meteorology, and aerodynamics simulation acceleration"}},
        {{"problem": "Hodge Conjecture", "credible_solution_date": "2027-02-28", "probability_pct": 74.0, "primary_contender": "OpenAI Next-Gen Reasoner", "breakthrough_impact": "Algebraic geometry and complex manifold analysis"}},
        {{"problem": "Birch and Swinnerton-Dyer Conjecture", "credible_solution_date": "2027-07-20", "probability_pct": 68.0, "primary_contender": "DeepMind / Anthropic Math Agents", "breakthrough_impact": "Elliptic curve arithmetic and modern cryptographic hardening"}},
        {{"problem": "Riemann Hypothesis", "credible_solution_date": "2028-05-15", "probability_pct": 58.0, "primary_contender": "Ensemble Autonomous Reasoners", "breakthrough_impact": "Deep prime distribution structure and foundational mathematics"}},
        {{"problem": "Yang-Mills Existence & Mass Gap", "credible_solution_date": "2028-11-30", "probability_pct": 52.0, "primary_contender": "Quantum Field Theory AI Engines", "breakthrough_impact": "Mathematical foundation of fundamental particle physics"}},
        {{"problem": "P versus NP Problem", "credible_solution_date": "2030-04-10", "probability_pct": 44.0, "primary_contender": "Recursive ASI Systems", "breakthrough_impact": "Universal optimization, computational limits, and cognitive automation"}},
        {{"problem": "General Frontier Math (Erdos / Collatz)", "credible_solution_date": "2026-12-10", "probability_pct": 95.0, "primary_contender": "Lean 4 Autoformalization Clusters", "breakthrough_impact": "Continuous automated peer-reviewed proof synthesis"}}
      ],
      "synthesis": "2 concise sentences synthesizing how this multi-lab release wave compresses the path to personal financial sovereignty and healthspan."
    }}
    """

    try:
        raw_text, active_model = execute_gemini_with_fallback(client, prompt)
    except Exception as api_err:
        return {"error": str(api_err)}

    # Step 3: Parse and Mathematical Normalization
    status_text.markdown("📐 **[3/5] Computing continuous Gaussian distributions and weekday weights...**")
    progress_bar.progress(70)

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
    personal_effect_map = {}

    all_keys = [
        "gemini_flash_lite", "gemini_flash", "gemini_pro",
        "claude_sonnet", "claude_haiku", "claude_opus", "claude_fable", "claude_6",
        "gpt_terra", "gpt_astra", "gpt_sol", "gpt_luna", "gpt_7"
    ]

    for k in all_keys:
        spec = anchors.get(k, {})
        p_date = spec.get("peak_date", "2026-10-15")
        spread = float(spec.get("spread_days", 5.0))
        tail = float(spec.get("tail_pct", 25.0))
        eff = int(spec.get("net_personal_effect", 25))

        if k in ["claude_6", "gpt_7"]:
            tail = max(tail, 95.0)
            spread = max(spread, 7.0)
        elif k in ["gpt_terra", "gpt_astra", "gpt_sol", "gpt_luna"]:
            spread = max(spread, 6.0)
            tail = max(tail, 40.0)
        elif k == "gemini_pro":
            spread = min(max(spread, 2.5), 4.0)

        curve = build_discrete_density(p_date, spread, tail, start_d, end_d)
        daily_table[k] = curve
        tail_summary[k] = round(tail, 1)
        personal_effect_map[k] = eff

    result["daily_df"] = pd.DataFrame(daily_table)
    result["tail_summary"] = tail_summary
    result["personal_effect_map"] = personal_effect_map

    # Step 4: Reconcile Life Timeline & Milestones
    status_text.markdown("⏳ **[4/5] Aligning personal FIRE & LEV compression countdowns...**")
    progress_bar.progress(85)

    result["polymarket_raw"] = poly_data
    result["active_model"] = active_model
    result["refreshed_at_budapest"] = get_budapest_now().strftime("%Y-%m-%d %H:%M CEST")

    # Step 5: Finalization
    status_text.markdown("✨ **[5/5] Finalizing layout rendering...**")
    progress_bar.progress(100)
    time.sleep(0.3)

    return result

@st.cache_data(ttl=3600)
def get_cached_macro_horizon():
    # Cache layer that delegates to execution with placeholder hooks
    return None

def get_or_run_data(force=False):
    # Check session state for rapid in-memory persistence
    now_ts = time.time()
    if not force and "macro_data" in st.session_state and (now_ts - st.session_state.get("macro_data_ts", 0) < 3600):
        return st.session_state["macro_data"]

    p_bar = st.progress(0)
    s_text = st.empty()
    data = execute_pipeline(p_bar, s_text)
    p_bar.empty()
    s_text.empty()

    if "error" not in data:
        st.session_state["macro_data"] = data
        st.session_state["macro_data_ts"] = now_ts

    return data

def get_calibrated_peak(df, tail_val, col_name):
    if float(tail_val) >= 75.0:
        return "Post-October 31", f"{tail_val}% Post-Oct Tail"
    
    if col_name in df.columns:
        idx = df[col_name].idxmax()
        peak_d = df.loc[idx, "date"]
        peak_pct = round(float(df.loc[idx, col_name]), 1)
        return peak_d, f"{peak_pct}% Daily Density"
        
    return "Pending", "0.0%"

def calculate_countdown(target_datetime):
    now = datetime.now()
    diff = target_datetime - now
    if diff.total_seconds() <= 0:
        return "Achieved / Present"
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"

# --- Main Layout ---
st.title("🧬 Frontier Horizon | Intelligence, Capital & LEV")
st.caption("Strategic Bayesian nexus connecting multi-lab model releases, macro geopolitics, and mathematical breakthroughs directly to your FIRE and Longevity Escape Velocity horizon.")

# Trigger data ingestion
data = get_or_run_data(force=False)

if "error" in data:
    st.error(f"⚠️ {data['error']}")
    st.info("The dashboard could not complete live synthesis. Please verify your Google AI Studio API key and connection.")
    st.stop()

# 1. Executive Top HUD (Static cards, dynamic values)
exec_m = data.get("executive_metrics", {})
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">FIRE Deflation Score</div>
        <div class="metric-value">{exec_m.get('fire_deflation_score', 86)}/100</div>
        <div class="metric-delta">Cognitive Automation & Asset Compounding</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">LEV Acceleration Index</div>
        <div class="metric-value">{exec_m.get('lev_acceleration_score', 79)}/100</div>
        <div class="metric-delta">Biomedical Rejuvenation Horizon</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Alan's AGI Countdown</div>
        <div class="metric-value">{exec_m.get('alan_agi_pct', 99.0)}%</div>
        <div class="metric-delta">Est. Completion: {exec_m.get('alan_agi_completion_date', '2026-12')}</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Metaculus Full AGI Consensus</div>
        <div class="metric-value">May 2028</div>
        <div class="metric-delta">Epistemic Crowd Median (Q5121)</div>
    </div>
    """, unsafe_allow_html=True)

st.info(data.get("synthesis", ""))

# 2. Strategy Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚡ Frontier Release Radars", 
    "🧬 Personal Timeline: FIRE, LEV & Mortality", 
    "🏛️ Geopolitics & Personal Impact", 
    "🧠 Alan Thompson Milestones & Millennium Math", 
    "🔍 Live Epistemic & Order Book Audit"
])

df_daily = data["daily_df"]
tails = data["tail_summary"]
effects = data["personal_effect_map"]

# --- TAB 1: Frontier Release Radars ---
with tab1:
    lab_google, lab_anthropic, lab_openai, lab_frontier = st.tabs([
        "🔵 Google DeepMind", 
        "🟠 Anthropic", 
        "🟢 OpenAI",
        "🌌 Frontier Horizon (2027+)"
    ])
    
    # Locked chart configuration: mobile drag and scroll zoom disabled permanently
    chart_config = {
        "displayModeBar": False, 
        "scrollZoom": False, 
        "staticPlot": False
    }

    # --- GOOGLE ---
    with lab_google:
        st.subheader("Google DeepMind · Implied Release Trajectories")
        d_lite, p_lite = get_calibrated_peak(df_daily, tails["gemini_flash_lite"], "gemini_flash_lite")
        d_flash, p_flash = get_calibrated_peak(df_daily, tails["gemini_flash"], "gemini_flash")
        d_pro, p_pro = get_calibrated_peak(df_daily, tails["gemini_pro"], "gemini_pro")
        
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            st.metric("Gemini Flash-Lite (3.6+)", d_lite, p_lite)
            st.caption(f"Net Personal Impact: **+{effects.get('gemini_flash_lite', 18)}%** (API efficiency)")
        with col_g2:
            st.metric("Gemini Flash (3.9+ / 4.0)", d_flash, p_flash)
            st.caption(f"Net Personal Impact: **+{effects.get('gemini_flash', 22)}%** (Multimodal speed)")
        with col_g3:
            st.metric("Gemini Pro (Daily Driver)", d_pro, p_pro)
            st.caption(f"Net Personal Impact: **+{effects.get('gemini_pro', 55)}%** (Pro Subscription core brain)")
            
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_flash_lite"], mode="lines+markers", name="Flash-Lite (3.6+)", line=dict(color="#38bdf8", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_flash"], mode="lines+markers", name="Flash (3.9+ / 4.0)", line=dict(color="#34d399", width=2.5)))
        fig_g.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gemini_pro"], mode="lines+markers", name="Gemini Pro", line=dict(color="#f43f5e", width=2.5)))
        fig_g.update_layout(
            template="plotly_dark",
            xaxis=dict(title="Calendar Date (September - October 2026)", fixedrange=True),
            yaxis=dict(title="Implied Daily Probability (%)", fixedrange=True, rangemode="tozero"),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_g, use_container_width=True, config=chart_config)
        st.caption(f"Post-October 31 Tail: Flash-Lite: {tails['gemini_flash_lite']}% | Flash: {tails['gemini_flash']}% | Pro: {tails['gemini_pro']}%")

    # --- ANTHROPIC ---
    with lab_anthropic:
        st.subheader("Anthropic · Implied Release Trajectories")
        d_sonnet, p_sonnet = get_calibrated_peak(df_daily, tails["claude_sonnet"], "claude_sonnet")
        d_haiku, p_haiku = get_calibrated_peak(df_daily, tails["claude_haiku"], "claude_haiku")
        d_opus, p_opus = get_calibrated_peak(df_daily, tails["claude_opus"], "claude_opus")
        d_fable, p_fable = get_calibrated_peak(df_daily, tails["claude_fable"], "claude_fable")
        
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        with col_a1:
            st.metric("Next Claude Sonnet", d_sonnet, p_sonnet)
            st.caption(f"Personal Impact: **+{effects.get('claude_sonnet', 48)}%**")
        with col_a2:
            st.metric("Next Claude Haiku", d_haiku, p_haiku)
            st.caption(f"Personal Impact: **+{effects.get('claude_haiku', 15)}%**")
        with col_a3:
            st.metric("Next Claude Opus", d_opus, p_opus)
            st.caption(f"Personal Impact: **+{effects.get('claude_opus', 42)}%**")
        with col_a4:
            st.metric("Claude Fable 5.2", d_fable, p_fable)
            st.caption(f"Personal Impact: **+{effects.get('claude_fable', 26)}%**")
            
        fig_a = go.Figure()
        fig_a.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["claude_sonnet"], mode="lines+markers", name="Next Sonnet", line=dict(color="#f59e0b", width=2.5)))
        fig_a.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["claude_haiku"], mode="lines+markers", name="Next Haiku", line=dict(color="#fb923c", width=2.5)))
        fig_a.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["claude_opus"], mode="lines+markers", name="Next Opus", line=dict(color="#ec4899", width=2.5)))
        fig_a.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["claude_fable"], mode="lines+markers", name="Claude Fable 5.2", line=dict(color="#c084fc", width=2.5)))
        fig_a.update_layout(
            template="plotly_dark",
            xaxis=dict(title="Calendar Date (September - October 2026)", fixedrange=True),
            yaxis=dict(title="Implied Daily Probability (%)", fixedrange=True, rangemode="tozero"),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_a, use_container_width=True, config=chart_config)
        st.caption(f"Post-October 31 Tail: Sonnet: {tails['claude_sonnet']}% | Haiku: {tails['claude_haiku']}% | Opus: {tails['claude_opus']}% | Fable: {tails['claude_fable']}%")

    # --- OPENAI ---
    with lab_openai:
        st.subheader("OpenAI · Implied Release Trajectories")
        d_terra, p_terra = get_calibrated_peak(df_daily, tails["gpt_terra"], "gpt_terra")
        d_astra, p_astra = get_calibrated_peak(df_daily, tails["gpt_astra"], "gpt_astra")
        d_sol, p_sol = get_calibrated_peak(df_daily, tails["gpt_sol"], "gpt_sol")
        d_luna, p_luna = get_calibrated_peak(df_daily, tails["gpt_luna"], "gpt_luna")
        
        col_o1, col_o2, col_o3, col_o4 = st.columns(4)
        with col_o1:
            st.metric("GPT-Terra 5.7", d_terra, p_terra)
            st.caption(f"Personal Impact: **+{effects.get('gpt_terra', 16)}%**")
        with col_o2:
            st.metric("GPT-Astra 6.1", d_astra, p_astra)
            st.caption(f"Personal Impact: **+{effects.get('gpt_astra', 30)}%**")
        with col_o3:
            st.metric("GPT-Sol 6.1", d_sol, p_sol)
            st.caption(f"Personal Impact: **+{effects.get('gpt_sol', 24)}%**")
        with col_o4:
            st.metric("GPT-Luna 6.1", d_luna, p_luna)
            st.caption(f"Personal Impact: **+{effects.get('gpt_luna', 20)}%**")
            
        fig_o = go.Figure()
        fig_o.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gpt_terra"], mode="lines+markers", name="GPT-Terra 5.7", line=dict(color="#10b981", width=2.5)))
        fig_o.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gpt_astra"], mode="lines+markers", name="GPT-Astra 6.1", line=dict(color="#06b6d4", width=2.5)))
        fig_o.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gpt_sol"], mode="lines+markers", name="GPT-Sol 6.1", line=dict(color="#facc15", width=2.5)))
        fig_o.add_trace(go.Scatter(x=df_daily["date"], y=df_daily["gpt_luna"], mode="lines+markers", name="GPT-Luna 6.1", line=dict(color="#a855f7", width=2.5)))
        fig_o.update_layout(
            template="plotly_dark",
            xaxis=dict(title="Calendar Date (September - October 2026)", fixedrange=True),
            yaxis=dict(title="Implied Daily Probability (%)", fixedrange=True, rangemode="tozero"),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_o, use_container_width=True, config=chart_config)
        st.caption(f"Post-October 31 Tail (Rule 2 Wide Spread): Terra: {tails['gpt_terra']}% | Astra: {tails['gpt_astra']}% | Sol: {tails['gpt_sol']}% | Luna: {tails['gpt_luna']}%")

    # --- FRONTIER 2027+ ---
    with lab_frontier:
        st.subheader("🌌 Multi-Year Frontier Architectural Leaps (2027+ Horizon)")
        st.caption("True paradigm shifts governed by Rule 3: strictly anchored to post-October tail probabilities (≥ 95%).")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Anthropic Frontier Flagship</div>
                <div class="metric-value">Claude 6</div>
                <div class="metric-delta">Most Likely Horizon: Q2 2027 · {tails['claude_6']}% Post-Oct Tail</div>
                <div style="margin-top: 0.75rem; font-size: 0.88rem; color: #d1d5db;">
                    <strong>Net Personal Impact:</strong> <span style="color:#10b981; font-weight:700;">+{effects.get('claude_6', 78)}%</span><br>
                    Next-generation epistemic reasoning architecture, autonomous multi-step software synthesis, and massive biological simulation compression.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col_f2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">OpenAI Frontier Flagship</div>
                <div class="metric-value">GPT-7</div>
                <div class="metric-delta">Most Likely Horizon: Mid 2027 · {tails['gpt_7']}% Post-Oct Tail</div>
                <div style="margin-top: 0.75rem; font-size: 0.88rem; color: #d1d5db;">
                    <strong>Net Personal Impact:</strong> <span style="color:#10b981; font-weight:700;">+{effects.get('gpt_7', 85)}%</span><br>
                    Universal self-directed research agent, autonomous mathematical proof engine, and the definitive catalyst pulling forward AGI and LEV.
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- TAB 2: Personal Timeline ---
with tab2:
    st.subheader("🧬 Personal Longevity & Financial Independence Horizon")
    st.caption("Custom-calibrated countdowns mapping your life journey from late 2026 through the intelligence inflection.")

    # Base dates
    base_fire = datetime(2031, 12, 1)
    base_lev = datetime(2037, 10, 15)
    
    # Dynamic compression offsets supplied by Gemini 3.8 Flash
    fire_comp_m = int(exec_m.get("fire_compression_months", 10))
    lev_comp_m = int(exec_m.get("lev_compression_months", 14))

    dt_fire_compressed = base_fire - timedelta(days=fire_comp_m * 30.4)
    dt_lev_compressed = base_lev - timedelta(days=lev_comp_m * 30.4)
    dt_weak_agi = datetime(2027, 2, 1)
    dt_full_agi = datetime(2028, 5, 1)
    dt_asi = datetime(2030, 10, 1)
    dt_lev_extended_death = datetime(2145, 12, 1)

    c_row1, c_row2, c_row3 = st.columns(3)
    with c_row1:
        st.markdown(f"""
        <div class="countdown-box">
            <div class="countdown-sub">Most Probable Personal LEV Arrival</div>
            <div class="countdown-num">{calculate_countdown(dt_lev_compressed)}</div>
            <div style="font-size: 0.8rem; color: #a5b4fc;">Target: {dt_lev_compressed.strftime('%B %Y')} (Compressed by {lev_comp_m}mo)</div>
        </div>
        """, unsafe_allow_html=True)
    with c_row2:
        st.markdown(f"""
        <div class="countdown-box">
            <div class="countdown-sub">Countdown to Personal FIRE</div>
            <div class="countdown-num">{calculate_countdown(dt_fire_compressed)}</div>
            <div style="font-size: 0.8rem; color: #a5b4fc;">Target: {dt_fire_compressed.strftime('%B %Y')} (Compressed by {fire_comp_m}mo)</div>
        </div>
        """, unsafe_allow_html=True)
    with c_row3:
        st.markdown(f"""
        <div class="countdown-box">
            <div class="countdown-sub">Longevity Horizon / Death Countdown</div>
            <div class="countdown-num">{calculate_countdown(dt_lev_extended_death)}</div>
            <div style="font-size: 0.8rem; color: #a5b4fc;">LEV-Adjusted Horizon: ~2145+ (Age 140+)</div>
        </div>
        """, unsafe_allow_html=True)

    st.caption("Note on Death Countdown: Hungarian actuarial baseline points to **December 2078** (Age 75, ~52 years remaining). Reaching LEV in early/mid 2036 with 42 years of biological buffer allows subsequent annual rejuvenation breakthroughs to extend healthspan past **2145+**.")

    st.divider()
    st.subheader("⚡ AGI & Superintelligence Milestone Countdowns")
    c_agi1, c_agi2, c_agi3 = st.columns(3)
    with c_agi1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Weakly General AI (Metaculus 3479)</div>
            <div class="metric-value">{calculate_countdown(dt_weak_agi)}</div>
            <div class="metric-delta">Target: Q1 2027</div>
        </div>
        """, unsafe_allow_html=True)
    with c_agi2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Full AGI (Metaculus 5121)</div>
            <div class="metric-value">{calculate_countdown(dt_full_agi)}</div>
            <div class="metric-delta">Target: May 2028</div>
        </div>
        """, unsafe_allow_html=True)
    with c_agi3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Full ASI (Superintelligence)</div>
            <div class="metric-value">{calculate_countdown(dt_asi)}</div>
            <div class="metric-delta">Target: Late 2030 (~29mo post-AGI)</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("📈 FIRE Compression Multiplier (VUAA & Cognitive Deflation)")
    st.write("""
    Every frontier model release directly accelerates your path to FIRE via two transmission channels:
    1. **Direct Software Deflation**: Tools, software subscriptions, and developer costs drop toward marginal compute cost.
    2. **Asset Compounding Velocity**: High-capex Big Tech returns compound the global equity index (VUAA ETF) inside your tax-sheltered TBSZ account.
    """)

# --- TAB 3: Geopolitics & Personal Impact Matrix ---
with tab3:
    st.subheader("🏛️ Macro Geopolitics & Live Personal Life Effect Matrix")
    st.caption("Evaluated strictly through your European / Hungarian capital and life lens (EU AI regulation, EUR/HUF currency stability, and VUAA compounding).")

    geo_list = data.get("geopolitics_scenarios", [])
    if geo_list:
        for item in geo_list:
            eff = item["net_personal_effect"]
            eff_color = "#10b981" if eff > 0 else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="metric-title">{item['event']} · Implied Odds: {item['probability_pct']}%</span>
                    <span style="font-size: 1.1rem; font-weight: 700; color: {eff_color};">Net Personal Effect: {eff:+d}%</span>
                </div>
                <div style="font-size: 1.15rem; font-weight: 700; color: #f3f4f6; margin: 0.25rem 0;">
                    {item['outcome']}
                </div>
                <div style="font-size: 0.85rem; color: #9ca3af; line-height: 1.4;">
                    <strong>Transmission Mechanism:</strong> {item['transmission']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.subheader("📊 Net Personal Life Impact Matrix Across All 13 AI Models")
    model_impact_rows = [
        {"Model Tier": "Gemini Pro", "Lab": "Google", "Personal Effect": f"+{effects.get('gemini_pro', 55)}%", "Key Channel": "Primary daily driver brain, long context, coding execution"},
        {"Model Tier": "Claude 6 (Frontier)", "Lab": "Anthropic", "Personal Effect": f"+{effects.get('claude_6', 78)}%", "Key Channel": "Autonomous software engineering, massive LEV research pull-forward"},
        {"Model Tier": "GPT-7 (Frontier)", "Lab": "OpenAI", "Personal Effect": f"+{effects.get('gpt_7', 85)}%", "Key Channel": "Universal self-directed research agent, autonomous proof solving"},
        {"Model Tier": "Next Claude Sonnet", "Lab": "Anthropic", "Personal Effect": f"+{effects.get('claude_sonnet', 48)}%", "Key Channel": "Industry standard agentic coding, personal tooling automation"},
        {"Model Tier": "Next Claude Opus", "Lab": "Anthropic", "Personal Effect": f"+{effects.get('claude_opus', 42)}%", "Key Channel": "Complex mathematical and biochemical reasoning"},
        {"Model Tier": "GPT-Astra 6.1", "Lab": "OpenAI", "Personal Effect": f"+{effects.get('gpt_astra', 30)}%", "Key Channel": "Autonomous test-time reasoning and verification"},
        {"Model Tier": "Claude Fable 5.2", "Lab": "Anthropic", "Personal Effect": f"+{effects.get('claude_fable', 26)}%", "Key Channel": "Specialized creative and structural reasoning"},
        {"Model Tier": "GPT-Sol 6.1", "Lab": "OpenAI", "Personal Effect": f"+{effects.get('gpt_sol', 24)}%", "Key Channel": "Fast reasoning and code analysis"},
        {"Model Tier": "Gemini Flash (3.9+ / 4.0)", "Lab": "Google", "Personal Effect": f"+{effects.get('gemini_flash', 22)}%", "Key Channel": "Gemini Live voice speed and real-time multimodal parsing"},
        {"Model Tier": "GPT-Luna 6.1", "Lab": "OpenAI", "Personal Effect": f"+{effects.get('gpt_luna', 20)}%", "Key Channel": "Lightweight planning agent"},
        {"Model Tier": "Gemini Flash-Lite (3.6+)", "Lab": "Google", "Personal Effect": f"+{effects.get('gemini_flash_lite', 18)}%", "Key Channel": "Low-cost local API scripting throughput"},
        {"Model Tier": "GPT-Terra 5.7", "Lab": "OpenAI", "Personal Effect": f"+{effects.get('gpt_terra', 16)}%", "Key Channel": "Developer iterative debugging"},
        {"Model Tier": "Next Claude Haiku", "Lab": "Anthropic", "Personal Effect": f"+{effects.get('claude_haiku', 15)}%", "Key Channel": "Background sub-agent routing and execution"}
    ]
    st.dataframe(pd.DataFrame(model_impact_rows), use_container_width=True)

# --- TAB 4: Alan Thompson Milestones & Millennium Math ---
with tab4:
    st.subheader("🧠 Alan Thompson (LifeArchitect.ai) AGI / ASI Tracking")
    
    col_alan1, col_alan2 = st.columns([1, 2])
    with col_alan1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Alan's Conservative AGI Countdown</div>
            <div class="metric-value">{exec_m.get('alan_agi_pct', 99.0)}% Achieved</div>
            <div class="metric-delta">Target Completion: {exec_m.get('alan_agi_completion_date', 'Late 2026')}</div>
            <div style="font-size: 0.82rem; color: #9ca3af; margin-top: 0.5rem;">
                Guides official AI policy for Microsoft, UN, and G7. Tracks human-level median performance across all cognitive dimensions.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_alan2:
        achieved_count = sum(1 for m in STATIC_ALAN_50_INDICATORS if m["status"] == "Achieved")
        in_progress_count = sum(1 for m in STATIC_ALAN_50_INDICATORS if m["status"] == "In Progress")
        dt_full_alan_completion = datetime(2030, 4, 1)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Alan's ASI Indicators (First 50 Milestones)</div>
            <div class="metric-value">{achieved_count}/50 Completed · {in_progress_count} In Progress</div>
            <div class="metric-delta">Countdown to 100% Completion: {calculate_countdown(dt_full_alan_completion)}</div>
            <div style="font-size: 0.82rem; color: #9ca3af; margin-top: 0.5rem;">
                Target date for final indicator #50 (Closed-Loop ASI Engine): <strong>April 2030</strong>.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📋 Inspect Alan Thompson's 50 ASI Indicators (Live Status & Predicted Dates)"):
        st.dataframe(pd.DataFrame(STATIC_ALAN_50_INDICATORS), use_container_width=True, height=400)

    st.divider()
    st.subheader("📐 Millennium Prize Mathematics Solution Forecast")
    st.caption("Estimated single most likely calendar date that a credible, published solution arrives for each problem.")

    math_solutions = data.get("millennium_math_solutions", [])
    if math_solutions:
        st.dataframe(pd.DataFrame(math_solutions).rename(columns={
            "problem": "Millennium Prize Problem",
            "credible_solution_date": "Most Probable Solution Date",
            "probability_pct": "Confidence (%)",
            "primary_contender": "Leading Contender / Mechanism",
            "breakthrough_impact": "Disciplinary Impact"
        }), use_container_width=True)

# --- TAB 5: Live Epistemic & Order Book Audit ---
with tab5:
    st.subheader("🔍 Live Polymarket Order Books & Inversion Audit")
    st.caption("Raw order book state verifying volume and negative contract resolution across all monitored markets.")
    for ev in data.get("polymarket_raw", []):
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

st.divider()
st.caption(f"Engine: Google AI Studio ({data.get('active_model', 'gemini-3.8-flash')}) · Automated Cache: 60 Minutes · Last Calibrated: {data.get('refreshed_at_budapest', 'Budapest Time')}")
if st.button("Force Synchronized Market Recalculation (Budapest Time)"):
    st.session_state.pop("macro_data", None)
    st.session_state.pop("macro_data_ts", None)
    st.rerun()
