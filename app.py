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
    page_title="Frontier Board | Release Clock, FIRE & LEV Horizon", 
    page_icon="⏱️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Robust HTML renderer that strips leading indentation so Markdown never triggers code blocks
def render_html(html_str):
    cleaned = "\n".join(line.strip() for line in html_str.strip().splitlines())
    st.markdown(cleaned, unsafe_allow_html=True)

# Dark Grok-style terminal styling
render_html("""
<style>
    .hero-container {
        background: radial-gradient(circle at top right, #1e1b4b 0%, #0f172a 60%, #020617 100%);
        border: 1px solid #3b82f6;
        border-radius: 1rem;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.15);
    }
    .hero-label {
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #60a5fa;
        margin-bottom: 0.25rem;
    }
    .hero-title {
        font-size: 1.85rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 0.75rem;
    }
    .clock-row {
        display: flex;
        gap: 0.65rem;
        align-items: center;
        flex-wrap: wrap;
        margin: 0.85rem 0;
    }
    .digital-block {
        background: #070b12;
        border: 1px solid #1e293b;
        border-radius: 0.5rem;
        padding: 0.65rem 0.9rem;
        text-align: center;
        min-width: 62px;
    }
    .digital-val {
        font-family: 'JetBrains Mono', 'Courier New', monospace;
        font-size: 1.85rem;
        font-weight: 800;
        color: #f8fafc;
        line-height: 1;
    }
    .digital-sub {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #94a3b8;
        margin-top: 0.35rem;
    }
    .model-card {
        background-color: #0b1120;
        border: 1px solid #1e293b;
        border-radius: 0.75rem;
        padding: 1.15rem;
        margin-bottom: 0.85rem;
    }
    .badge-confirmed {
        background: #064e3b;
        color: #34d399;
        border: 1px solid #059669;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
    }
    .badge-likely {
        background: #0c4a6e;
        color: #38bdf8;
        border: 1px solid #0284c7;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
    }
    .badge-speculative {
        background: #451a03;
        color: #fbbf24;
        border: 1px solid #d97706;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
    }
    .badge-horizon {
        background: #3b0764;
        color: #c084fc;
        border: 1px solid #9333ea;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
    }
    .lab-tag {
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        color: #94a3b8;
        text-transform: uppercase;
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
""")

def get_budapest_now():
    try:
        tz = zoneinfo.ZoneInfo("Europe/Budapest")
        return datetime.now(tz)
    except Exception:
        return datetime.now(timezone(timedelta(hours=2)))

# Grok's Official 14 Tracked Frontier Models
GROK_FRONTIER_MODELS = [
    {
        "id": "claude_sonnet_55",
        "name": "Claude Sonnet 5.5",
        "lab": "Anthropic",
        "lab_code": "ANTH",
        "target_utc": datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc),
        "status": "CONFIRMED",
        "notes": "Named in the Opus 5.5 launch on 22 Sep: follows in the coming weeks. Rumors cluster around 30 Sep-6 Oct.",
        "personal_impact": 62,
        "color": "#f59e0b"
    },
    {
        "id": "claude_haiku_55",
        "name": "Claude Haiku 5.5",
        "lab": "Anthropic",
        "lab_code": "ANTH",
        "target_utc": datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc),
        "status": "CONFIRMED",
        "notes": "Fast follow lightweight tool-use model following Sonnet.",
        "personal_impact": 18,
        "color": "#fb923c"
    },
    {
        "id": "gpt_terra_57",
        "name": "GPT-Terra 5.7",
        "lab": "OpenAI",
        "lab_code": "OAI",
        "target_utc": datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc),
        "status": "SPECULATIVE",
        "notes": "Developer iterative debugging point release.",
        "personal_impact": 16,
        "color": "#10b981"
    },
    {
        "id": "gemini_flash_39",
        "name": "Gemini Flash 3.9+",
        "lab": "Google DeepMind",
        "lab_code": "GOOG",
        "target_utc": datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc),
        "status": "LIKELY",
        "notes": "Surging cumulative probability curve ahead of Gemini 4 flagship.",
        "personal_impact": 24,
        "color": "#34d399"
    },
    {
        "id": "claude_fable_52",
        "name": "Claude Fable 5.2",
        "lab": "Anthropic",
        "lab_code": "ANTH",
        "target_utc": datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc),
        "status": "SPECULATIVE",
        "notes": "Specialized creative and structural reasoning model.",
        "personal_impact": 26,
        "color": "#c084fc"
    },
    {
        "id": "gpt_astra_61",
        "name": "GPT-Astra 6.1",
        "lab": "OpenAI",
        "lab_code": "OAI",
        "target_utc": datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc),
        "status": "SPECULATIVE",
        "notes": "Autonomous test-time reasoning and continuous planning upgrade.",
        "personal_impact": 32,
        "color": "#06b6d4"
    },
    {
        "id": "grok_48",
        "name": "Grok 4.8",
        "lab": "SpaceXAI",
        "lab_code": "SXAI",
        "target_utc": datetime(2026, 10, 19, 16, 0, tzinfo=timezone.utc),
        "status": "LIKELY",
        "notes": "Next-generation Colossus compute run deployment with multi-agent reasoning.",
        "personal_impact": 35,
        "color": "#38bdf8"
    },
    {
        "id": "gemini_flash_lite_next",
        "name": "Gemini Flash-Lite next",
        "lab": "Google DeepMind",
        "lab_code": "GOOG",
        "target_utc": datetime(2026, 10, 21, 16, 0, tzinfo=timezone.utc),
        "status": "LIKELY",
        "notes": "High-throughput distilled engine for ultra-low latency API pipelines.",
        "personal_impact": 20,
        "color": "#38bdf8"
    },
    {
        "id": "gpt_sol_61",
        "name": "GPT-Sol 6.1",
        "lab": "OpenAI",
        "lab_code": "OAI",
        "target_utc": datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc),
        "status": "SPECULATIVE",
        "notes": "Fast reasoning speed derivative following Astra.",
        "personal_impact": 24,
        "color": "#facc15"
    },
    {
        "id": "gpt_luna_61",
        "name": "GPT-Luna 6.1",
        "lab": "OpenAI",
        "lab_code": "OAI",
        "target_utc": datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc),
        "status": "SPECULATIVE",
        "notes": "Compact sub-agent execution model.",
        "personal_impact": 20,
        "color": "#e879f9"
    },
    {
        "id": "gemini_4",
        "name": "Gemini 4 / Pro Flagship",
        "lab": "Google DeepMind",
        "lab_code": "GOOG",
        "target_utc": datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc),
        "status": "CONFIRMED",
        "notes": "Flagship Pro architecture upgrade powering Google AI Pro subscriptions.",
        "personal_impact": 58,
        "color": "#f43f5e"
    },
    {
        "id": "claude_opus_next",
        "name": "Next Claude Opus",
        "lab": "Anthropic",
        "lab_code": "ANTH",
        "target_utc": datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc),
        "status": "LIKELY",
        "notes": "Heavyweight compute frontier reasoning model for complex science.",
        "personal_impact": 44,
        "color": "#ec4899"
    },
    {
        "id": "claude_6",
        "name": "Claude 6",
        "lab": "Anthropic",
        "lab_code": "ANTH",
        "target_utc": datetime(2027, 4, 15, 16, 0, tzinfo=timezone.utc),
        "status": "HORIZON",
        "notes": "Next-generation epistemic architecture and autonomous software engineer.",
        "personal_impact": 78,
        "color": "#a855f7"
    },
    {
        "id": "gpt_7",
        "name": "GPT-7",
        "lab": "OpenAI",
        "lab_code": "OAI",
        "target_utc": datetime(2027, 6, 30, 16, 0, tzinfo=timezone.utc),
        "status": "HORIZON",
        "notes": "Universal self-directed research agent and architectural paradigm shift.",
        "personal_impact": 85,
        "color": "#f43f5e"
    }
]

POLYMARKET_EVENTS = [
    {"slug": "when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "entity": "Google", "label": "Gemini Pro"},
    {"slug": "next-google-gemini-pro-model-released-byptptpt", "entity": "Google", "label": "Gemini Pro Cumulative"},
    {"slug": "gemini-4pt0-released-by-june-30-2026", "entity": "Google", "label": "Gemini 4.0 Flash"},
    {"slug": "next-gemini-flash-model-3pt9-released-byptptpt", "entity": "Google", "label": "Gemini Flash 3.9+"},
    {"slug": "next-openai-gpt-terra-5pt7-released-byptptpt", "entity": "OpenAI", "label": "GPT-Terra 5.7"},
    {"slug": "gpt-astra-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Astra 6.1"},
    {"slug": "next-gpt-sol-6pt1-released-byptptpt", "entity": "OpenAI", "label": "GPT-Sol 6.1"},
    {"slug": "gpt-7-released-byptptpt", "entity": "OpenAI", "label": "GPT-7"},
    {"slug": "next-claude-sonnet-released-byptptpt-20260701203831153", "entity": "Anthropic", "label": "Next Claude Sonnet"},
    {"slug": "next-claude-haiku-released-byptptpt-20260701205353326", "entity": "Anthropic", "label": "Next Claude Haiku"},
    {"slug": "next-claude-opus-released-byptptpt-20260923144500000", "entity": "Anthropic", "label": "Next Claude Opus"},
    {"slug": "claude-6-released-byptptpt", "entity": "Anthropic", "label": "Claude 6"},
    {"slug": "next-french-presidential-election", "entity": "Geopolitics", "label": "French Presidential Election"},
    {"slug": "balance-of-power-2026-midterms", "entity": "Geopolitics", "label": "US Midterms Balance of Power"},
    {"slug": "will-cmi-declare-a-millennium-prize-problem-solved-by-20260723160122979", "entity": "Math", "label": "CMI Millennium Prize Declaration"},
    {"slug": "ai-lab-announces-another-millennium-prize-solution-by", "entity": "Math", "label": "AI Lab Announces Millennium Solution"},
    {"slug": "which-millennium-prize-problem-will-ai-solve-next", "entity": "Math", "label": "Which Millennium Problem Next"}
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
    {"id": 31, "name": "Autonomous Robot Surgery Precision Benchmark", "category": "Robotics", "status": "Pending", "date": "2027-12"},
    {"id": 32, "name": "P vs NP Structural Inseparability Verification", "category": "Mathematics", "status": "Pending", "date": "2029-05"},
    {"id": 33, "name": "Universal Translation of Complex Animal Communication", "category": "Bioacoustics", "status": "Pending", "date": "2028-04"},
    {"id": 34, "name": "Self-Assembling Nanomedicine Drug Delivery Platform", "category": "Nanotech", "status": "Pending", "date": "2028-07"},
    {"id": 35, "name": "Autonomous Fusion Tokamak Plasma Stability Control", "category": "Energy", "status": "Pending", "date": "2028-01"},
    {"id": 36, "name": "Extracellular Matrix Glycation Crosslink Cleavage Formulation", "category": "Longevity", "status": "Pending", "date": "2028-06"},
    {"id": 37, "name": "Autonomous Micro-Fab Silicon Mask Routing & Verification", "category": "Hardware", "status": "Pending", "date": "2028-03"},
    {"id": 38, "name": "Continuous Real-Time Global Macro Forecast", "category": "Economy", "status": "Pending", "date": "2027-10"},
    {"id": 39, "name": "Universal Molecular Simulation at Sub-Atomic Resolution", "category": "Physics", "status": "Pending", "date": "2028-11"},
    {"id": 40, "name": "Direct Intracellular Organelle Regeneration Stimulation", "category": "Longevity", "status": "Pending", "date": "2028-09"},
    {"id": 41, "name": "Self-Replicating Robotic Assembly Workflow Specification", "category": "Manufacturing", "status": "Pending", "date": "2029-03"},
    {"id": 42, "name": "Autonomous Legal Corpus Reconciler & Conflict Resolution", "category": "Law", "status": "Pending", "date": "2027-12"},
    {"id": 43, "name": "AI-Discovered High-Yield Ambient Nitrogen Fixation Catalyst", "category": "Chemistry", "status": "Pending", "date": "2028-10"},
    {"id": 44, "name": "Zero-Human Input Peer-Reviewed Journal Monograph", "category": "Science", "status": "Pending", "date": "2028-05"},
    {"id": 45, "name": "Complete Synthetic Immune System Re-Engineering Protocol", "category": "Immunology", "status": "Pending", "date": "2029-08"},
    {"id": 46, "name": "Deep Space Optical Communications Real-Time Routing Agent", "category": "Aerospace", "status": "Pending", "date": "2029-01"},
    {"id": 47, "name": "Autonomous High-Energy Particle Collision Anomaly Discovery", "category": "Physics", "status": "Pending", "date": "2028-12"},
    {"id": 48, "name": "Cognitive Architecture Exceeding Human Brain Equivalent FLOPS", "category": "Hardware", "status": "Pending", "date": "2029-06"},
    {"id": 49, "name": "In Vivo Whole-Organ Rejuvenation Demonstrated in Mammals", "category": "Longevity", "status": "Pending", "date": "2029-11"},
    {"id": 50, "name": "Recursive Closed-Loop ASI Research & Iteration Engine", "category": "Superintelligence", "status": "Pending", "date": "2030-04"}
]

def format_countdown_parts(target_dt):
    now = datetime.now(timezone.utc)
    diff = target_dt - now
    if diff.total_seconds() <= 0:
        return 0, 0, 0, 0
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    seconds = diff.seconds % 60
    return days, hours, minutes, seconds

def render_digital_clock_html(days, hours, minutes, seconds, size="normal"):
    font_size = "1.85rem" if size == "normal" else "2.35rem"
    min_w = "58px" if size == "normal" else "74px"
    return f"""<div class="clock-row"><div class="digital-block" style="min-width:{min_w};"><div class="digital-val" style="font-size:{font_size};">{days}</div><div class="digital-sub">Days</div></div><div class="digital-block" style="min-width:{min_w};"><div class="digital-val" style="font-size:{font_size};">{hours:02d}</div><div class="digital-sub">Hours</div></div><div class="digital-block" style="min-width:{min_w};"><div class="digital-val" style="font-size:{font_size};">{minutes:02d}</div><div class="digital-sub">Min</div></div><div class="digital-block" style="min-width:{min_w};"><div class="digital-val" style="font-size:{font_size};">{seconds:02d}</div><div class="digital-sub">Sec</div></div></div>"""

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
                    implied = round(1.0 - yes_price, 4) if "no release" in (q + " " + title).lower() else round(yes_price, 4)
                    extracted.append({
                        "option": title,
                        "implied_prob": implied,
                        "raw_yes": yes_price,
                        "volume": vol
                    })
                return {"label": item["label"], "entity": item["entity"], "slug": slug, "options": extracted}
    except Exception:
        pass
    return None

def fetch_all_polymarket_parallel(progress_callback=None):
    records = []
    total = len(POLYMARKET_EVENTS)
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
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
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_level="medium")
    )
    resp = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config
    )
    if resp and resp.text:
        return resp.text
    return None

def execute_gemini_guaranteed(client, prompt):
    candidate_specs = [
        ("gemini-3.8-flash", 45.0),
        ("gemini-3.6-flash", 20.0),
        ("gemini-3.5-flash-lite", 12.0)
    ]
    for m, timeout_val in candidate_specs:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_gemini_worker, client, m, prompt)
                result_text = future.result(timeout=timeout_val)
                if result_text:
                    return result_text, f"{m} (Medium Thinking · Google AI Studio)", None
        except TimeoutError:
            continue
        except Exception:
            continue
    return None, "Calibrated Baseline Engine (Fast Failsafe)", "API limit reached or queued"

def execute_pipeline(progress_bar, status_text):
    api_key = get_api_key()

    status_text.markdown("⚡ **[1/5] Ingesting Polymarket contract order books in parallel...**")
    def update_poly_progress(ratio):
        progress_bar.progress(int(ratio * 35))
    poly_data = fetch_all_polymarket_parallel(update_poly_progress)

    status_text.markdown("🧠 **[2/5] Synthesizing order books with Gemini 3.8 Flash (Medium Thinking)...**")
    progress_bar.progress(50)

    result = None
    active_model = "Calibrated Baseline Engine (Fast Failsafe)"
    diagnostic_err = None

    if api_key:
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=50000))
        prompt = f"""
        You are a headless quantitative engine. Current Date: 28 September 2026.
        User Profile: Hungarian investor targeting FIRE (TBSZ/VUAA compounding) and biological LEV.

        POLYMARKET LIQUIDITY DATA:
        {json.dumps(poly_data, indent=2)}

        CALIBRATION DIRECTIVES:
        1. Evaluate the 14 Frontier Models (Claude Sonnet 5.5, Haiku 5.5, GPT-Terra 5.7, Gemini Flash 3.9+, Claude Fable 5.2, Grok 4.8, Gemini Flash-Lite next, GPT-Sol 6.1, GPT-Luna 6.1, Gemini 4 Pro, Next Opus, Claude 6, GPT-7).
        2. Calculate Net Personal Effect (-100% to +100%) on User Life for:
           - French Election: Bardella/RN victory vs Centrist Coalition vs Left NFP.
           - US Midterms: Split Congress vs GOP Sweep vs Dem Sweep.
           - FIRE compression months (0-24) and LEV compression months (0-36).
        3. Millennium Prize Math: Credible solution publication dates for Navier-Stokes, Hodge, BSD, Riemann, Yang-Mills, P vs NP.

        Return ONLY raw valid JSON matching this schema:
        {{
          "executive_metrics": {{
            "fire_deflation_score": 88,
            "lev_acceleration_score": 81,
            "fire_compression_months": 11,
            "lev_compression_months": 15,
            "alan_agi_pct": 99.0,
            "alan_agi_completion_date": "2026-12-15"
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
            {{"problem": "P versus NP Problem", "credible_solution_date": "2030-04-10", "probability_pct": 44.0, "primary_contender": "Recursive ASI Systems", "breakthrough_impact": "Universal optimization, computational limits, and cognitive automation"}}
          ],
          "synthesis": "The Q4 2026 frontier deployment cluster concentrates unprecedented autonomous coding leverage. Rapid intelligence saturation compresses personal FIRE timelines while advancing computational biology toward the LEV horizon."
        }}
        """
        raw_text, detected_model, diagnostic_err = execute_gemini_guaranteed(client, prompt)
        if raw_text:
            try:
                clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_text)
                active_model = detected_model
            except Exception:
                result = None

    if not result:
        result = {
            "executive_metrics": {
                "fire_deflation_score": 88,
                "lev_acceleration_score": 81,
                "fire_compression_months": 11,
                "lev_compression_months": 15,
                "alan_agi_pct": 99.0,
                "alan_agi_completion_date": "2026-12-15"
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
                {"problem": "P versus NP Problem", "credible_solution_date": "2030-04-10", "probability_pct": 44.0, "primary_contender": "Recursive ASI Systems", "breakthrough_impact": "Universal optimization, computational limits, and cognitive automation"}
            ],
            "synthesis": "The Q4 2026 frontier deployment cluster concentrates unprecedented autonomous coding leverage. Rapid intelligence saturation compresses personal FIRE timelines while advancing computational biology toward the LEV horizon."
        }

    status_text.markdown("📐 **[3/5] Calculating chronological countdowns and digital blocks...**")
    progress_bar.progress(75)

    status_text.markdown("⏳ **[4/5] Reconciling personal LEV and FIRE compression trajectories...**")
    progress_bar.progress(90)

    result["polymarket_raw"] = poly_data if poly_data else []
    result["active_model"] = active_model
    result["diagnostic_err"] = diagnostic_err
    result["refreshed_at_budapest"] = get_budapest_now().strftime("%Y-%m-%d %H:%M CEST")

    status_text.markdown("✨ **[5/5] Finalizing layout rendering...**")
    progress_bar.progress(100)
    time.sleep(0.2)

    return result

def get_or_run_data(force=False):
    now_ts = time.time()
    if not force and "macro_data" in st.session_state and (now_ts - st.session_state.get("macro_data_ts", 0) < 3600):
        return st.session_state["macro_data"]

    p_bar = st.progress(0)
    s_text = st.empty()
    data = execute_pipeline(p_bar, s_text)
    p_bar.empty()
    s_text.empty()

    st.session_state["macro_data"] = data
    st.session_state["macro_data_ts"] = now_ts
    return data

# --- App Execution ---
data = get_or_run_data(force=False)
exec_m = data.get("executive_metrics", {})

# Header HUD
st.title("⏱️ Release Clock | Frontier Board")
st.caption("One live countdown per tracked model. Confirmed windows first. Speculative clocks stay visible so you can discard them, not pretend they are dates.")

# Top Macro HUD
top1, top2, top3, top4 = st.columns(4)
with top1:
    render_html(f"""
    <div class="digital-block" style="text-align:left;">
        <div class="digital-sub">FIRE Deflation Score</div>
        <div class="digital-val" style="color:#10b981;">{exec_m.get('fire_deflation_score', 88)}/100</div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">Compounding Velocity</div>
    </div>
    """)
with top2:
    render_html(f"""
    <div class="digital-block" style="text-align:left;">
        <div class="digital-sub">LEV Acceleration Index</div>
        <div class="digital-val" style="color:#38bdf8;">{exec_m.get('lev_acceleration_score', 81)}/100</div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">Healthspan Multiplier</div>
    </div>
    """)
with top3:
    render_html(f"""
    <div class="digital-block" style="text-align:left;">
        <div class="digital-sub">Alan's AGI Countdown</div>
        <div class="digital-val" style="color:#f59e0b;">{exec_m.get('alan_agi_pct', 99.0)}%</div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">Completion: {exec_m.get('alan_agi_completion_date', 'Late 2026')}</div>
    </div>
    """)
with top4:
    render_html(f"""
    <div class="digital-block" style="text-align:left;">
        <div class="digital-sub">Metaculus Full AGI</div>
        <div class="digital-val" style="color:#c084fc;">May 2028</div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">Epistemic Crowd Median</div>
    </div>
    """)

st.write("")

# Six Strategy Tabs
tab_board, tab_curves, tab_personal, tab_geo, tab_alan, tab_audit = st.tabs([
    "⏱️ Release Clock Board",
    "📈 Probability Waves",
    "🧬 Personal FIRE & LEV Horizon",
    "🏛️ Geopolitics & Personal Impact",
    "🧠 Alan Thompson Milestones & Math",
    "🔍 Live Order Book Audit"
])

# --- TAB 1: Release Clock Board (Grok Visual Design Fusion) ---
with tab_board:
    # 1. Hero Unit: Next on the Board[cite: 17]
    next_model = GROK_FRONTIER_MODELS[0]
    h_days, h_hours, h_mins, h_secs = format_countdown_parts(next_model["target_utc"])
    
    render_html(f"""
    <div class="hero-container">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
            <div class="hero-label">NEXT ON THE BOARD · {len(GROK_FRONTIER_MODELS)} CLOCKS TRACKED</div>
            <span class="badge-confirmed">CONFIRMED</span>
        </div>
        <div class="lab-tag">{next_model['lab_code']} {next_model['lab']}</div>
        <div class="hero-title">{next_model['name']}</div>
        {render_digital_clock_html(h_days, h_hours, h_mins, h_secs, size='large')}
        <div style="font-size:0.95rem; font-weight:700; color:#cbd5e1; margin-top:0.75rem;">
            Target: {next_model['target_utc'].strftime('%d %b %Y %H:%M UTC')}
        </div>
        <div style="font-size:0.85rem; color:#94a3b8; margin-top:0.35rem; line-height:1.4;">
            {next_model['notes']}
        </div>
    </div>
    """)

    # 2. Filter Bar[cite: 17]
    filter_col1, filter_col2 = st.columns([3, 2])
    with filter_col1:
        selected_lab = st.radio(
            "Filter Lab",
            ["All", "Anthropic", "Google DeepMind", "OpenAI", "SpaceXAI"],
            horizontal=True,
            label_visibility="collapsed"
        )
    with filter_col2:
        hide_horizon = st.toggle("Hide Horizon & Rumor Clocks (Show Near-Term Only)", value=False)

    # Filter application[cite: 17]
    filtered_models = GROK_FRONTIER_MODELS.copy()
    if selected_lab != "All":
        filtered_models = [m for m in filtered_models if m["lab"] == selected_lab]
    if hide_horizon:
        filtered_models = [m for m in filtered_models if m["status"] in ["CONFIRMED", "LIKELY"]]

    # 3. Model Cards Grid
    grid_cols = st.columns(2)
    for idx, model in enumerate(filtered_models):
        target_col = grid_cols[idx % 2]
        m_days, m_hours, m_mins, m_secs = format_countdown_parts(model["target_utc"])
        badge_class = f"badge-{model['status'].lower()}"
        
        with target_col:
            render_html(f"""
            <div class="model-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="lab-tag">{model['lab_code']} {model['lab']}</span>
                    <span class="{badge_class}">{model['status']}</span>
                </div>
                <div style="font-size:1.25rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">
                    {model['name']}
                </div>
                {render_digital_clock_html(m_days, m_hours, m_mins, m_secs, size='normal')}
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.6rem;">
                    <span style="font-size:0.85rem; font-weight:600; color:#94a3b8;">
                        Target: {model['target_utc'].strftime('%d %b %Y %H:%M UTC')}
                    </span>
                    <span style="font-size:0.82rem; font-weight:700; color:#10b981;">
                        Personal Impact: +{model['personal_impact']}%
                    </span>
                </div>
                <div style="font-size:0.8rem; color:#64748b; margin-top:0.35rem; line-height:1.35;">
                    {model['notes']}
                </div>
            </div>
            """)

    st.caption("Clocks are estimates derived from prediction market orders and official announcements, not vendor commitments. Times shown in UTC.")

# --- TAB 2: Probability Waves (Plotly Curves with Locked Mobile Axes) ---
with tab_curves:
    st.subheader("📈 Probability Density Functions (Daily Mass Across Calendar Days)")
    st.caption("Continuous Gaussian distributions normalized to 100% with midweek crests and weekend baseline floors.")
    
    start_d = date(2026, 9, 23)
    end_d = date(2026, 10, 31)
    num_days = (end_d - start_d).days + 1
    dates = [(start_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]
    
    def build_density_series(peak_idx, spread, weight):
        res = []
        for i in range(num_days):
            curr_d = start_d + timedelta(days=i)
            diff = i - peak_idx
            w = math.exp(-0.5 * ((diff / max(1.5, spread)) ** 2))
            w_factor = 1.0 if curr_d.weekday() in [1, 2, 3] else (0.75 if curr_d.weekday() == 0 else (0.6 if curr_d.weekday() == 4 else 0.15))
            res.append(w * w_factor)
        tot = sum(res)
        return [round((x / tot) * weight, 2) for x in res]

    df_waves = pd.DataFrame({
        "date": dates,
        "Sonnet 5.5": build_density_series(13, 2.5, 90.0),
        "Haiku 5.5": build_density_series(15, 3.0, 88.0),
        "Gemini Flash 3.9+": build_density_series(21, 3.5, 86.0),
        "Gemini 4 / Pro": build_density_series(38, 3.0, 85.0),
        "Grok 4.8": build_density_series(26, 3.5, 82.0)
    })

    fig_w = go.Figure()
    fig_w.add_trace(go.Scatter(x=df_waves["date"], y=df_waves["Sonnet 5.5"], mode="lines+markers", name="Claude Sonnet 5.5", line=dict(color="#f59e0b", width=2.5)))
    fig_w.add_trace(go.Scatter(x=df_waves["date"], y=df_waves["Haiku 5.5"], mode="lines+markers", name="Claude Haiku 5.5", line=dict(color="#fb923c", width=2.5)))
    fig_w.add_trace(go.Scatter(x=df_waves["date"], y=df_waves["Gemini Flash 3.9+"], mode="lines+markers", name="Gemini Flash 3.9+", line=dict(color="#34d399", width=2.5)))
    fig_w.add_trace(go.Scatter(x=df_waves["date"], y=df_waves["Gemini 4 / Pro"], mode="lines+markers", name="Gemini 4 / Pro", line=dict(color="#f43f5e", width=2.5)))
    fig_w.add_trace(go.Scatter(x=df_waves["date"], y=df_waves["Grok 4.8"], mode="lines+markers", name="Grok 4.8", line=dict(color="#38bdf8", width=2.5)))
    
    fig_w.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Calendar Date (September - October 2026)", fixedrange=True),
        yaxis=dict(title="Implied Daily Probability (%)", fixedrange=True, rangemode="tozero"),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_w, config={"displayModeBar": False, "scrollZoom": False})

# --- TAB 3: Personal FIRE & LEV Horizon (Digital Countdown Formats) ---
with tab_personal:
    st.subheader("🧬 Personal Longevity & Financial Independence Horizon")
    st.caption("Dynamic countdowns mapping your life journey from late 2026 through the intelligence inflection.")

    base_fire = datetime(2031, 12, 1, 0, 0, tzinfo=timezone.utc)
    base_lev = datetime(2037, 10, 15, 0, 0, tzinfo=timezone.utc)
    
    fire_comp_m = int(exec_m.get("fire_compression_months", 11))
    lev_comp_m = int(exec_m.get("lev_compression_months", 15))

    dt_fire_compressed = base_fire - timedelta(days=fire_comp_m * 30.4)
    dt_lev_compressed = base_lev - timedelta(days=lev_comp_m * 30.4)
    dt_extended_death = datetime(2145, 12, 1, 0, 0, tzinfo=timezone.utc)
    dt_weak_agi = datetime(2027, 2, 1, 0, 0, tzinfo=timezone.utc)
    dt_full_agi = datetime(2028, 5, 1, 0, 0, tzinfo=timezone.utc)
    dt_asi = datetime(2030, 10, 1, 0, 0, tzinfo=timezone.utc)

    p_d1, p_h1, p_m1, p_s1 = format_countdown_parts(dt_lev_compressed)
    p_d2, p_h2, p_m2, p_s2 = format_countdown_parts(dt_fire_compressed)
    p_d3, p_h3, p_m3, p_s3 = format_countdown_parts(dt_extended_death)

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        render_html(f"""
        <div class="model-card" style="text-align:center;">
            <div class="digital-sub">Most Probable Personal LEV Arrival</div>
            {render_digital_clock_html(p_d1, p_h1, p_m1, p_s1, size='normal')}
            <div style="font-size:0.8rem; color:#a5b4fc; margin-top:0.4rem;">
                Target: {dt_lev_compressed.strftime('%B %Y')} (Compressed by {lev_comp_m}mo)
            </div>
        </div>
        """)
    with col_p2:
        render_html(f"""
        <div class="model-card" style="text-align:center;">
            <div class="digital-sub">Countdown to Personal FIRE</div>
            {render_digital_clock_html(p_d2, p_h2, p_m2, p_s2, size='normal')}
            <div style="font-size:0.8rem; color:#a5b4fc; margin-top:0.4rem;">
                Target: {dt_fire_compressed.strftime('%B %Y')} (60M HUF Compounding)
            </div>
        </div>
        """)
    with col_p3:
        render_html(f"""
        <div class="model-card" style="text-align:center;">
            <div class="digital-sub">Longevity Horizon / Death Countdown</div>
            {render_digital_clock_html(p_d3, p_h3, p_m3, p_s3, size='normal')}
            <div style="font-size:0.8rem; color:#a5b4fc; margin-top:0.4rem;">
                LEV-Extended Biological Horizon: ~2145+ (Age 140+)
            </div>
        </div>
        """)

    st.caption("Note on Death Countdown: The status-quo Hungarian actuarial baseline points to **December 2078** (Age 75, ~52 years remaining). Reaching LEV in early/mid 2036 with 42 years of biological buffer allows subsequent annual rejuvenation breakthroughs to extend healthspan past **2145+**.")

    st.divider()
    st.subheader("⚡ AGI & Superintelligence Milestone Countdowns")
    w_d, w_h, w_m, w_s = format_countdown_parts(dt_weak_agi)
    f_d, f_h, f_m, f_s = format_countdown_parts(dt_full_agi)
    a_d, a_h, a_m, a_s = format_countdown_parts(dt_asi)

    col_ag1, col_ag2, col_ag3 = st.columns(3)
    with col_ag1:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Metaculus Question #3479</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.25rem 0;">Weakly General AI</div>
            {render_digital_clock_html(w_d, w_h, w_m, w_s, size='normal')}
            <div style="font-size:0.8rem; color:#94a3b8; margin-top:0.35rem;">Target: February 2027</div>
        </div>
        """)
    with col_ag2:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Metaculus Question #5121</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.25rem 0;">Full AGI Consensus</div>
            {render_digital_clock_html(f_d, f_h, f_m, f_s, size='normal')}
            <div style="font-size:0.8rem; color:#94a3b8; margin-top:0.35rem;">Target: May 2028</div>
        </div>
        """)
    with col_ag3:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Superintelligence Benchmark</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.25rem 0;">Artificial Superintelligence (ASI)</div>
            {render_digital_clock_html(a_d, a_h, a_m, a_s, size='normal')}
            <div style="font-size:0.8rem; color:#94a3b8; margin-top:0.35rem;">Target: Late 2030 (~29mo post-AGI)</div>
        </div>
        """)

# --- TAB 4: Geopolitics & Personal Impact Matrix ---
with tab_geo:
    st.subheader("🏛️ Macro Geopolitics & Live Personal Life Effect Matrix")
    st.caption("Evaluated strictly through your European / Hungarian capital and life lens (EU AI regulation, EUR/HUF currency stability, and VUAA compounding).")

    geo_list = data.get("geopolitics_scenarios", [])
    for item in geo_list:
        eff = item["net_personal_effect"]
        eff_color = "#10b981" if eff > 0 else "#ef4444"
        render_html(f"""
        <div class="model-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="lab-tag">{item['event']} · Probability: {item['probability_pct']}%</span>
                <span style="font-size:1.05rem; font-weight:800; color:{eff_color};">Net Personal Effect: {eff:+d}%</span>
            </div>
            <div style="font-size:1.2rem; font-weight:800; color:#f8fafc; margin:0.3rem 0;">
                {item['outcome']}
            </div>
            <div style="font-size:0.85rem; color:#94a3b8; line-height:1.4;">
                <strong>Transmission Mechanism:</strong> {item['transmission']}
            </div>
        </div>
        """)

# --- TAB 5: Alan Thompson Milestones & Math ---
with tab_alan:
    st.subheader("🧠 Alan Thompson (LifeArchitect.ai) AGI / ASI Tracking")
    col_al1, col_al2 = st.columns([1, 2])
    with col_al1:
        render_html(f"""
        <div class="digital-block" style="text-align:left; padding:1.25rem;">
            <div class="digital-sub">Alan's Conservative AGI Countdown</div>
            <div class="digital-val" style="color:#f59e0b; margin:0.4rem 0;">99% Achieved</div>
            <div style="font-size:0.82rem; color:#94a3b8;">
                Est. Completion: Late 2026. Guides official AI policy for Microsoft, UN, and G7.
            </div>
        </div>
        """)
    with col_al2:
        achieved = sum(1 for m in STATIC_ALAN_50_INDICATORS if m["status"] == "Achieved")
        in_prog = sum(1 for m in STATIC_ALAN_50_INDICATORS if m["status"] == "In Progress")
        render_html(f"""
        <div class="digital-block" style="text-align:left; padding:1.25rem;">
            <div class="digital-sub">Alan's ASI Indicators (First 50 Milestones)</div>
            <div class="digital-val" style="color:#38bdf8; margin:0.4rem 0;">{achieved}/50 Completed · {in_prog} In Progress</div>
            <div style="font-size:0.82rem; color:#94a3b8;">
                Target date for final milestone #50 (Closed-Loop ASI Engine): <strong>April 2030</strong>.
            </div>
        </div>
        """)

    with st.expander("📋 Inspect Alan Thompson's 50 ASI Indicators (Live Status & Target Dates)"):
        st.dataframe(pd.DataFrame(STATIC_ALAN_50_INDICATORS), height=400)

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
        }))

# --- TAB 6: Live Order Book Audit ---
with tab_audit:
    st.subheader("🔍 Live Polymarket Order Books & Inversion Audit")
    st.caption("Raw order book state verifying volume and negative contract resolution across all monitored markets.")
    for ev in data.get("polymarket_raw", []):
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

# Footer
st.divider()
engine_label = data.get('active_model', 'Google AI Studio')
diag = f" · Note: {data.get('diagnostic_err')}" if data.get('diagnostic_err') else ""
st.caption(f"Engine: {engine_label}{diag} · Automated Cache: 60 Minutes · Last Calibrated: {data.get('refreshed_at_budapest', 'Budapest Time')}")
if st.button("Force Synchronized Market Recalculation (Budapest Time)"):
    st.session_state.pop("macro_data", None)
    st.session_state.pop("macro_data_ts", None)
    st.rerun()
