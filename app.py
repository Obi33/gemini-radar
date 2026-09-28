import streamlit as st
import requests
import json
import os
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta, timezone
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
from google import genai
from google.genai import types

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

MODEL_METADATA = {
    "gemini_flash_lite": {"name": "Gemini Flash-Lite (3.6+)", "lab": "Google DeepMind", "color": "#38bdf8"},
    "gemini_flash": {"name": "Gemini Flash (3.9+ / 4.0)", "lab": "Google DeepMind", "color": "#34d399"},
    "gemini_pro": {"name": "Gemini Pro (Daily Driver)", "lab": "Google DeepMind", "color": "#f43f5e"},
    "claude_sonnet": {"name": "Next Claude Sonnet", "lab": "Anthropic", "color": "#f59e0b"},
    "claude_haiku": {"name": "Next Claude Haiku", "lab": "Anthropic", "color": "#fb923c"},
    "claude_opus": {"name": "Next Claude Opus", "lab": "Anthropic", "color": "#ec4899"},
    "claude_fable": {"name": "Claude Fable 5.2", "lab": "Anthropic", "color": "#c084fc"},
    "claude_6": {"name": "Claude 6 (Frontier Leap)", "lab": "Anthropic", "color": "#a855f7"},
    "gpt_terra": {"name": "GPT-Terra 5.7", "lab": "OpenAI", "color": "#10b981"},
    "gpt_astra": {"name": "GPT-Astra 6.1", "lab": "OpenAI", "color": "#06b6d4"},
    "gpt_sol": {"name": "GPT-Sol 6.1", "lab": "OpenAI", "color": "#facc15"},
    "gpt_luna": {"name": "GPT-Luna 6.1", "lab": "OpenAI", "color": "#e879f9"},
    "gpt_7": {"name": "GPT-7 (Frontier Leap)", "lab": "OpenAI", "color": "#f43f5e"}
}

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

def get_default_calibrated_payload():
    return {
        "executive_metrics": {
            "fire_deflation_score": 86,
            "lev_acceleration_score": 79,
            "fire_compression_months": 10,
            "lev_compression_months": 14,
            "alan_agi_pct": 99.0,
            "alan_agi_completion_date": "2026-12-15"
        },
        "model_anchors": {
            "gemini_flash_lite": {"peak_date": "2026-10-04", "spread_days": 4.5, "tail_pct": 12.0, "net_personal_effect": 18},
            "gemini_flash": {"peak_date": "2026-10-09", "spread_days": 4.0, "tail_pct": 14.0, "net_personal_effect": 22},
            "gemini_pro": {"peak_date": "2026-10-16", "spread_days": 3.0, "tail_pct": 15.0, "net_personal_effect": 55},
            "claude_sonnet": {"peak_date": "2026-10-01", "spread_days": 3.0, "tail_pct": 10.0, "net_personal_effect": 48},
            "claude_haiku": {"peak_date": "2026-10-07", "spread_days": 4.0, "tail_pct": 12.0, "net_personal_effect": 15},
            "claude_opus": {"peak_date": "2026-10-24", "spread_days": 4.5, "tail_pct": 25.0, "net_personal_effect": 42},
            "claude_fable": {"peak_date": "2026-10-17", "spread_days": 4.0, "tail_pct": 18.0, "net_personal_effect": 26},
            "claude_6": {"peak_date": "2027-04-15", "spread_days": 8.0, "tail_pct": 96.5, "net_personal_effect": 78},
            "gpt_terra": {"peak_date": "2026-10-10", "spread_days": 6.0, "tail_pct": 42.0, "net_personal_effect": 16},
            "gpt_astra": {"peak_date": "2026-10-18", "spread_days": 6.5, "tail_pct": 45.0, "net_personal_effect": 30},
            "gpt_sol": {"peak_date": "2026-10-24", "spread_days": 6.5, "tail_pct": 48.0, "net_personal_effect": 24},
            "gpt_luna": {"peak_date": "2026-10-28", "spread_days": 7.0, "tail_pct": 50.0, "net_personal_effect": 20},
            "gpt_7": {"peak_date": "2027-06-30", "spread_days": 8.0, "tail_pct": 97.5, "net_personal_effect": 85}
        },
        "geopolitics_scenarios": [
            {"event": "French Presidential Election", "outcome": "National Rally / Bardella Victory", "probability_pct": 46.0, "net_personal_effect": -24, "transmission": "EU budget friction, EUR weakness vs USD, trade friction impacting Hungarian exports and currency stability."},
            {"event": "French Presidential Election", "outcome": "Centrist / Pro-European Coalition", "probability_pct": 38.0, "net_personal_effect": 18, "transmission": "Single market integrity preserved, defense procurement compounding, stable EU tech framework."},
            {"event": "French Presidential Election", "outcome": "New Popular Front (Left Coalition)", "probability_pct": 16.0, "net_personal_effect": -12, "transmission": "Increased corporate wealth taxes on CAC 40 multinationals, regulatory caution on compute infrastructure."},
            {"event": "US 2026 Midterms", "outcome": "Split Congress (Gridlock: GOP Senate / Dem House)", "probability_pct": 52.0, "net_personal_effect": 22, "transmission": "Peak regulatory stability: no disruptive tax hikes or antitrust breakups, optimal for continuous VUAA compounding."},
            {"event": "US 2026 Midterms", "outcome": "Republican Unified Sweep", "probability_pct": 32.0, "net_personal_effect": 12, "transmission": "Corporate tax reductions and deregulated compute buildouts offset by aggressive tariff pressure on European trade."},
            {"event": "US 2026 Midterms", "outcome": "Democratic Unified Sweep", "probability_pct": 14.0, "net_personal_effect": -8, "transmission": "Aggressive frontier model liability frameworks and antitrust scrutiny on hyperscalers."}
        ],
        "millennium_math_solutions": [
            {"problem": "Navier-Stokes Singularity Formation", "credible_solution_date": "2026-11-15", "probability_pct": 92.0, "primary_contender": "OpenAI / Independent Hybrid Proof", "breakthrough_impact": "Fluid dynamics, meteorology, and aerodynamics simulation acceleration"},
            {"problem": "Hodge Conjecture", "credible_solution_date": "2027-02-28", "probability_pct": 74.0, "primary_contender": "OpenAI Next-Gen Reasoner", "breakthrough_impact": "Algebraic geometry and complex manifold analysis"},
            {"problem": "Birch and Swinnerton-Dyer Conjecture", "credible_solution_date": "2027-07-20", "probability_pct": 68.0, "primary_contender": "DeepMind / Anthropic Math Agents", "breakthrough_impact": "Elliptic curve arithmetic and modern cryptographic hardening"},
            {"problem": "Riemann Hypothesis", "credible_solution_date": "2028-05-15", "probability_pct": 58.0, "primary_contender": "Ensemble Autonomous Reasoners", "breakthrough_impact": "Deep prime distribution structure and foundational mathematics"},
            {"problem": "Yang-Mills Existence & Mass Gap", "credible_solution_date": "2028-11-30", "probability_pct": 52.0, "primary_contender": "Quantum Field Theory AI Engines", "breakthrough_impact": "Mathematical foundation of fundamental particle physics"},
            {"problem": "P versus NP Problem", "credible_solution_date": "2030-04-10", "probability_pct": 44.0, "primary_contender": "Recursive ASI Systems", "breakthrough_impact": "Universal optimization, computational limits, and cognitive automation"},
            {"problem": "General Frontier Math (Erdos / Collatz)", "credible_solution_date": "2026-12-10", "probability_pct": 95.0, "primary_contender": "Lean 4 Autoformalization Clusters", "breakthrough_impact": "Continuous automated peer-reviewed proof synthesis"}
        ],
        "synthesis": "The multi-lab release wave concentrates frontier reasoning in Q4 2026, pulling forward autonomous code generation and accelerating capital compounding inside tax-sheltered global equities."
    }

def fetch_single_event(item):
    slug = item["slug"]
    base_url = "https://gamma-api.polymarket.com/events?slug="
    try:
        res = requests.get(f"{base_url}{slug}", timeout=3.0)
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

def call_gemini_worker(client, model_name, prompt):
    try:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level="medium")
        )
    except Exception:
        config = types.GenerateContentConfig(response_mime_type="application/json")
        
    resp = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config
    )
    if resp and resp.text:
        return resp.text
    return None

def execute_gemini_guaranteed(client, prompt):
    candidate_models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    
    for m in candidate_models:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_gemini_worker, client, m, prompt)
                result_text = future.result(timeout=18.0)
                if result_text:
                    return result_text, f"{m} (Medium Thinking · Google AI Studio)"
        except TimeoutError:
            continue
        except Exception:
            continue

    return None, "Calibrated Baseline Engine (Fast Failsafe)"

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

    status_text.markdown("⚡ **[1/5] Ingesting 27 Polymarket contract order books in parallel...**")
    def update_poly_progress(ratio):
        progress_bar.progress(int(ratio * 35))
    poly_data = fetch_all_polymarket_parallel(update_poly_progress)

    status_text.markdown("🧠 **[2/5] Synthesizing order books with Gemini 3.8 Flash (Medium Thinking)...**")
    progress_bar.progress(50)

    result = None
    active_model = "Calibrated Baseline Engine (Fast Failsafe)"

    if api_key:
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

        Return ONLY raw valid JSON matching this schema:
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
            {{"problem": "General Frontier Math (Erdos / Collatz)", "credible_solution_date": "2026-12-10", "probability_pct": 95.0, "primary_contender": "Lean 4 Autoformalization Clusters", "breakthrough_impact": "Continuous automated peer-reviewed proof synthesis"}
          ],
          "synthesis": "The multi-lab release wave concentrates frontier reasoning in Q4 2026, pulling forward autonomous code generation and accelerating capital compounding inside tax-sheltered global equities."
        }}
        """
        raw_text, detected_model = execute_gemini_guaranteed(client, prompt)
        if raw_text:
            try:
                clean_text = raw_text.replace("```json", "").replace("
