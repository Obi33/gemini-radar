"""
Frontier Board | Model Release Clocks, Benchmark Stakes & FIRE/LEV Engine

Requirements: streamlit>=1.37, requests, pandas, plotly, google-genai (optional)
Secrets: GEMINI_API_KEY (optional, used for 4-sentence macroeconomic executive briefs)
"""
import html
import json
import os
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, date, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

st.set_page_config(
    page_title="Frontier Board | Intelligence, Capital & LEV", 
    page_icon="⏱️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)


def render_html(s):
    cleaned = "\n".join(line.strip() for line in s.strip().splitlines())
    st.markdown(cleaned, unsafe_allow_html=True)


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
}
.hero-title {
    font-size: 1.85rem;
    font-weight: 800;
    color: #f8fafc;
    margin: 0.25rem 0 0.5rem;
}
.clock-row {
    display: flex;
    gap: 0.65rem;
    flex-wrap: wrap;
    margin: 0.85rem 0;
}
.digital-block {
    background: #070b12;
    border: 1px solid #1e293b;
    border-radius: 0.5rem;
    padding: 0.65rem 0.9rem;
    text-align: center;
}
.digital-val {
    font-family: 'JetBrains Mono', 'Courier New', monospace;
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
    background: #0b1120;
    border: 1px solid #1e293b;
    border-radius: 0.75rem;
    padding: 1.15rem;
    margin-bottom: 0.85rem;
}
.badge {
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    padding: 2px 7px;
    border-radius: 4px;
    text-transform: uppercase;
}
.badge-confirmed { background: #064e3b; color: #34d399; border: 1px solid #059669; }
.badge-likely { background: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7; }
.badge-speculative { background: #451a03; color: #fbbf24; border: 1px solid #d97706; }
.badge-horizon { background: #3b0764; color: #c084fc; border: 1px solid #9333ea; }
.badge-market { background: #134e4a; color: #5eead4; border: 1px solid #0d9488; }
.badge-cadence { background: #1e1b4b; color: #a5b4fc; border: 1px solid #4338ca; }
.badge-manual { background: #1e293b; color: #94a3b8; border: 1px solid #475569; }
.lab-tag {
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #94a3b8;
    text-transform: uppercase;
}
.stTabs [data-baseweb="tab-list"] { gap: 1.1rem; }
.stTabs [data-baseweb="tab"] {
    font-size: 0.92rem;
    font-weight: 600;
    padding-top: 0.35rem;
    padding-bottom: 0.35rem;
}
</style>
""")

# ---------------------------------------------------------------- Data Registry

CANDIDATES = [("gemini-3.8-flash", 45.0), ("gemini-3.6-flash", 20.0), ("gemini-3.5-flash-lite", 12.0)]


def M(id_str, name, lab, code, dt, status, notes, poly_cumulative=None, poly_discrete=None, personal_impact=20):
    return {
        "id": id_str,
        "name": name,
        "lab": lab,
        "code": code,
        "poly_cumulative": poly_cumulative,
        "poly_discrete": poly_discrete,
        "status": status,
        "notes": notes,
        "source": "manual",
        "personal_impact": personal_impact,
        "target": datetime(*dt, 16, 0, tzinfo=timezone.utc)
    }


# Comprehensive Model Registry calibrated across all monitored Polymarket events
MODELS = [
    M("claude_sonnet_55", "Claude Sonnet 5.5", "Anthropic", "ANTH", (2026, 9, 29), "CONFIRMED",
      "Market prices Sep 28 (63%) and Sep 29 (31%) on $11K+ volume, with 84% cumulative probability by Sep 29. Imminent drop.",
      poly_cumulative="Next Claude Sonnet Cumulative", poly_discrete="Next Claude Sonnet Daily Date", personal_impact=62),

    M("claude_haiku_55", "Claude Haiku 5.5", "Anthropic", "ANTH", (2026, 10, 8), "CONFIRMED",
      "78% by Oct 15, 95% by Oct 31 ($11.7K vol). Anthropic confirmed Haiku directly follows Sonnet 5.5 in coming weeks.",
      poly_cumulative="Next Claude Haiku", personal_impact=18),

    M("gemini_flash_39", "Gemini Flash 3.9+", "Google DeepMind", "GOOG", (2026, 10, 13), "LIKELY",
      "51% by Oct 15, 94% by Nov 30. High-efficiency test run directly leading into the Gemini 4 flagship.",
      poly_cumulative="Gemini Flash 3.9+", personal_impact=24),

    M("claude_fable_52", "Claude Fable 5.2", "Anthropic", "ANTH", (2026, 10, 17), "SPECULATIVE",
      "55% by Oct 31, 92% by Dec 31 ($31K vol). Specialized structural reasoning checkpoint.",
      poly_cumulative="Next Fable 5.2+", personal_impact=26),

    M("gpt_astra_61", "GPT-Astra 6.1", "OpenAI", "OAI", (2026, 10, 18), "SPECULATIVE",
      "17% by Oct 9, 61% by Oct 31 ($8K vol). Continuous planning and test-time reasoning upgrade.",
      poly_cumulative="GPT-Astra 6.1", personal_impact=32),

    M("grok_48", "Grok 4.8", "SpaceXAI", "SXAI", (2026, 10, 19), "LIKELY",
      "45% by Oct 31, 82% by Nov 30 on $1K vol. Interim Colossus run checkpoint.",
      poly_cumulative="Grok 4.8+", personal_impact=35),

    M("gemini_4", "Gemini 4 / Pro Flagship", "Google DeepMind", "GOOG", (2026, 10, 21), "CONFIRMED",
      "True market median sits at Oct 20-22 ($1.4M vol; 77% by Oct 31). Oct 31 is the contract expiration date, not the mode.",
      poly_cumulative="Gemini Pro Cumulative", poly_discrete="Next Gemini Pro Daily Date", personal_impact=58),

    M("gemini_flash_lite_next", "Gemini Flash-Lite next", "Google DeepMind", "GOOG", (2026, 10, 21), "LIKELY",
      "Distilled lightweight engine calibrated to launch alongside the Gemini 4 family. Polymarket $56 book is illiquid.",
      poly_cumulative="Gemini Flash-Lite 3.6+", personal_impact=20),

    M("gpt_sol_61", "GPT-Sol 6.1", "OpenAI", "OAI", (2026, 10, 24), "SPECULATIVE",
      "Sol 6.0 deployed Sep 22. Speed-reasoning derivative trailing Astra.",
      poly_cumulative="GPT-Sol 6.1", personal_impact=24),

    M("gpt_luna_61", "GPT-Luna 6.1", "OpenAI", "OAI", (2026, 10, 28), "SPECULATIVE",
      "48% by Nov 30, 80% by Dec 31 on $1K vol. Compact sub-agent execution model.",
      poly_cumulative="GPT-Luna 6.1", personal_impact=20),

    M("claude_opus_next", "Next Claude Opus", "Anthropic", "ANTH", (2026, 11, 24), "LIKELY",
      "69% by Nov 30, 88% by Dec 31 on $2.6K vol. Cadence interval following Opus 5.5.",
      poly_cumulative="Next Claude Opus", personal_impact=44),

    M("gpt_terra_57", "GPT-Terra 5.7", "OpenAI", "OAI", (2027, 1, 20), "SPECULATIVE",
      "Polymarket/Release Oracle median sits in Q1 2027 (Jan 20 to Mar 15). Not an early Oct sprint.",
      poly_cumulative="GPT-Terra 5.7", personal_impact=16),

    M("claude_6", "Claude 6", "Anthropic", "ANTH", (2027, 4, 30), "HORIZON",
      "35% by Mar 31, 56% by Jun 30, 87% by Dec 31, 2027. Implied median is late April 2027.",
      poly_cumulative="Claude 6", personal_impact=78),

    M("gpt_7", "GPT-7", "OpenAI", "OAI", (2027, 8, 25), "HORIZON",
      "34% by Jun 30, 2027 and 84% by Dec 31, 2027. True median lands around late August 2027.",
      poly_cumulative="GPT-7", personal_impact=85),
]

# Full 34-Event Polymarket Tracking Registry (incorporating all requested links)
POLYMARKET_EVENTS = [
    # Google Gemini Models & Intervals
    ("gemini-4pt0-released-by-june-30-2026", "Google", "Gemini 4.0 Flash"),
    ("next-gemini-flash-model-3pt9-released-byptptpt", "Google", "Gemini Flash 3.9+"),
    ("next-google-gemini-flash-lite-model-3pt6-released-byptptpt", "Google", "Gemini Flash-Lite 3.6+"),
    ("next-gemini-pro-model-released-onptptpt-20260922131618444", "Google", "Next Gemini Pro Daily Date"),
    ("when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "Google", "Gemini Pro Interval Window"),
    ("next-google-gemini-pro-model-released-byptptpt", "Google", "Gemini Pro Cumulative"),

    # Google Gemini Benchmarks & Arena
    ("next-google-gemini-pro-model-humanitys-last-exam-debut-20260729192434644", "Benchmarks", "Gemini Pro HLE Debut"),
    ("highest-google-gemini-score-on-humanitys-last-exam-in-2026-20260723192605545", "Benchmarks", "Highest Gemini HLE Score 2026"),
    ("next-google-gemini-pro-model-arena-debut", "Benchmarks", "Gemini Pro Arena Debut Score"),

    # Anthropic Claude Models
    ("next-claude-sonnet-released-onptptpt-20260921225443", "Anthropic", "Next Claude Sonnet Daily Date"),
    ("next-claude-sonnet-released-byptptpt-20260701203831153", "Anthropic", "Next Claude Sonnet Cumulative"),
    ("next-claude-haiku-released-byptptpt-20260701205353326", "Anthropic", "Next Claude Haiku"),
    ("next-fable-model-5pt2-released-byptptpt", "Anthropic", "Next Fable 5.2+"),
    ("next-claude-opus-released-byptptpt-20260923144500000", "Anthropic", "Next Claude Opus"),
    ("claude-6-released-byptptpt", "Anthropic", "Claude 6"),

    # Anthropic Claude Benchmarks & Arena
    ("next-sonnet-model-text-arena-debut-20260827110151621", "Benchmarks", "Sonnet Text Arena Debut"),
    ("next-claude-opus-model-humanitys-last-exam-debut-20261231", "Benchmarks", "Claude Opus HLE Debut"),
    ("highest-claude-score-on-humanitys-last-exam-in-2026-20260723190836285", "Benchmarks", "Highest Claude HLE Score 2026"),

    # OpenAI Models
    ("next-openai-gpt-terra-5pt7-released-byptptpt", "OpenAI", "GPT-Terra 5.7"),
    ("gpt-astra-6pt1-released-byptptpt", "OpenAI", "GPT-Astra 6.1"),
    ("next-gpt-sol-6pt1-released-byptptpt", "OpenAI", "GPT-Sol 6.1"),
    ("next-gpt-luna-6pt1-released-byptptpt", "OpenAI", "GPT-Luna 6.1"),
    ("gpt-7-released-byptptpt", "OpenAI", "GPT-7"),
    ("highest-openai-score-on-humanitys-last-exam-in-2026-20260723225144062", "Benchmarks", "Highest OpenAI HLE Score 2026"),

    # SpaceXAI / xAI
    ("next-grok-model-4pt8-released-by", "SpaceXAI", "Grok 4.8+"),

    # Frontier AI Crown & Arena Race Markets
    ("which-companys-ai-will-first-hit-1550-on-chatbot-arena-in-2026", "Crown", "First to Hit 1550 on Arena"),
    ("which-company-has-the-best-ai-model-end-of-october", "Crown", "Best AI Model End of October"),
    ("which-company-has-the-best-ai-model-end-of-november", "Crown", "Best AI Model End of November"),
    ("which-company-has-best-ai-model-end-of-2026", "Crown", "Best AI Model End of 2026"),

    # Macro Geopolitics
    ("next-french-presidential-election", "Geopolitics", "French Presidential Election"),
    ("balance-of-power-2026-midterms", "Geopolitics", "US Midterms Balance of Power"),

    # Millennium Mathematics Markets
    ("will-cmi-declare-a-millennium-prize-problem-solved-by-20260723160122979", "Math", "CMI Millennium Prize Declaration"),
    ("ai-lab-announces-another-millennium-prize-solution-by", "Math", "AI Lab Announces Millennium Solution"),
    ("which-millennium-prize-problem-will-ai-solve-next", "Math", "Which Millennium Problem Next"),
]

MANUAL_AS_OF = "2026-09-28"
MILESTONES = [
    ("Weakly General AI (Metaculus #3479)", datetime(2027, 2, 1, tzinfo=timezone.utc)),
    ("Full AGI (Metaculus #5121)", datetime(2028, 5, 1, tzinfo=timezone.utc)),
    ("ASI Benchmark (Consensus Median)", datetime(2030, 10, 1, tzinfo=timezone.utc)),
]

GEOPOLITICS_TRANSMISSION = [
    {
        "event": "French Presidential Election",
        "outcome": "National Rally / Bardella Victory",
        "prob": 46.0,
        "effect": -24,
        "transmission": "EU institutional friction, EUR weakness vs USD, trade friction impacting Hungarian exports and currency stability."
    },
    {
        "event": "French Presidential Election",
        "outcome": "Centrist / Pro-European Coalition",
        "prob": 38.0,
        "effect": 18,
        "transmission": "Single market integrity preserved, defense procurement compounding, stable EU tech framework."
    },
    {
        "event": "French Presidential Election",
        "outcome": "New Popular Front (Left Coalition)",
        "prob": 16.0,
        "effect": -12,
        "transmission": "Increased corporate wealth taxes on CAC 40 multinationals, regulatory caution on compute infrastructure."
    },
    {
        "event": "US 2026 Midterms",
        "outcome": "Split Congress (Gridlock: GOP Senate / Dem House)",
        "prob": 52.0,
        "effect": 22,
        "transmission": "Peak regulatory stability. No disruptive tax hikes or antitrust breakups, optimal for continuous VUAA ETF compounding."
    },
    {
        "event": "US 2026 Midterms",
        "outcome": "Republican Unified Sweep",
        "prob": 32.0,
        "effect": 12,
        "transmission": "Corporate tax reductions and deregulated compute buildouts offset by aggressive tariff pressure on European trade."
    },
    {
        "event": "US 2026 Midterms",
        "outcome": "Democratic Unified Sweep",
        "prob": 14.0,
        "effect": -8,
        "transmission": "Aggressive frontier model liability frameworks and antitrust scrutiny on hyperscalers."
    }
]

MILLENNIUM_CONSENSUS = [
    {"problem": "Navier-Stokes Singularity Formation", "solution_date": "2026-11-15", "prob": 92.0, "contender": "OpenAI / Independent Hybrid Proof", "impact": "Fluid dynamics and simulation acceleration"},
    {"problem": "Hodge Conjecture", "solution_date": "2027-02-28", "prob": 74.0, "contender": "OpenAI Next-Gen Reasoner", "impact": "Algebraic geometry and complex manifold analysis"},
    {"problem": "Birch and Swinnerton-Dyer Conjecture", "solution_date": "2027-07-20", "prob": 68.0, "contender": "DeepMind / Anthropic Math Agents", "impact": "Elliptic curve arithmetic and cryptographic hardening"},
    {"problem": "Riemann Hypothesis", "solution_date": "2028-05-15", "prob": 58.0, "contender": "Ensemble Autonomous Reasoners", "impact": "Prime distribution structure and foundational mathematics"},
    {"problem": "Yang-Mills Existence & Mass Gap", "solution_date": "2028-11-30", "prob": 52.0, "contender": "Quantum Field Theory AI Engines", "impact": "Mathematical foundation of particle physics"},
    {"problem": "P versus NP Problem", "solution_date": "2030-04-10", "prob": 44.0, "contender": "Recursive ASI Systems", "impact": "Universal optimization and computational complexity limits"},
    {"problem": "General Frontier Math (Erdos / Collatz)", "solution_date": "2026-12-10", "prob": 95.0, "contender": "Lean 4 Autoformalization Clusters", "impact": "Continuous automated peer-reviewed proof synthesis"}
]

A, P, N = "Achieved", "In Progress", "Pending"
ALAN = [
    ("Formal Proof of Navier-Stokes Singularity Formation", "Mathematics", A, "2026-09"),
    ("Self-Supervised De Novo Protein Rejuvenation Sequence", "Biomedicine", A, "2026-07"),
    ("Autonomous End-to-End Compiler Optimization (C/Rust)", "Software", A, "2026-08"),
    ("Direct In Silico Small Molecule Drug Target Hit (>99% Affinity)", "Biomedicine", A, "2026-05"),
    ("Superhuman Competitive Programming (IOI Gold Level)", "Software", A, "2025-12"),
    ("Autonomous Erdos Conjecture Settlement", "Mathematics", A, "2026-06"),
    ("Universal Robot World Model Zero-Shot Transfer", "Robotics", A, "2026-08"),
    ("Automated Bug Bounding & Kernel Exploit Zero-Day Synthesis", "Software", A, "2026-07"),
    ("Continuous Test-Time Compute Self-Correction Loop", "Reasoning", A, "2026-09"),
    ("Autonomous Material Lattice Superconductor Screening", "Physics", A, "2026-08"),
    ("Hodge Conjecture Sub-Case Formalization in Lean 4", "Mathematics", P, "2026-11"),
    ("Whole-Cell Epigenetic Aging Clock Reversal Simulation", "Longevity", P, "2026-12"),
    ("Full Codebase Autonomous Architecture Refactoring (10M+ LOC)", "Software", P, "2026-10"),
    ("Birch & Swinnerton-Dyer Rank Parity Verification", "Mathematics", P, "2027-02"),
    ("Self-Directed Wet-Lab Chemistry Synthesis API Loop", "Biochemistry", P, "2026-12"),
    ("Superhuman Cross-Disciplinary Grant Hypothesis Synthesis", "Science", P, "2027-01"),
    ("Mitochondrial DNA Mutation Repair Modeling", "Longevity", P, "2027-03"),
    ("Continuous Recursive Model Alignment & Oversight Agents", "Alignment", P, "2026-11"),
    ("Zero-Human Input Hardware Architecture Schematic Design", "Hardware", P, "2027-04"),
    ("Autonomous Microeconomic Arbitrage & Supply Chain Optimization", "Economy", P, "2026-12"),
    ("Complete In Vitro Neural Connectome Dynamic Simulation", "Neuroscience", P, "2027-06"),
    ("Universal Mathematical Translation & Lean Autoformalization", "Mathematics", P, "2027-01"),
    ("Automated Clinical Trial Synthetic Cohort Modeling", "Medicine", P, "2027-04"),
    ("Self-Synthesizing Autonomous Machine Learning Engineer", "Software", P, "2026-11"),
    ("Quantum Chromodynamics Lattice Mass Gap Simulation", "Physics", P, "2027-08"),
    ("Senolytic Molecule Target Discovery & Toxicity Filter", "Longevity", P, "2027-03"),
    ("Autonomous Space Mission Orbit & Trajectory Optimizer", "Astrophysics", N, "2027-09"),
    ("Riemann Hypothesis Zero-Density Critical Strip Proof", "Mathematics", N, "2028-02"),
    ("Telomere Lengthening Transcriptional Factor Cocktail Design", "Longevity", N, "2027-11"),
    ("Fully Unsupervised Scientific Paper Review & Flaw Finder", "Science", N, "2027-05"),
    ("Autonomous Robot Surgery Precision Benchmark", "Robotics", N, "2027-12"),
    ("P vs NP Structural Inseparability Verification", "Mathematics", N, "2029-05"),
    ("Universal Translation of Complex Animal Communication", "Bioacoustics", N, "2028-04"),
    ("Self-Assembling Nanomedicine Drug Delivery Platform", "Nanotech", N, "2028-07"),
    ("Autonomous Fusion Tokamak Plasma Stability Control", "Energy", N, "2028-01"),
    ("Extracellular Matrix Glycation Crosslink Cleavage Formulation", "Longevity", N, "2028-06"),
    ("Autonomous Micro-Fab Silicon Mask Routing & Verification", "Hardware", N, "2028-03"),
    ("Continuous Real-Time Global Macro Forecast", "Economy", N, "2027-10"),
    ("Universal Molecular Simulation at Sub-Atomic Resolution", "Physics", N, "2028-11"),
    ("Direct Intracellular Organelle Regeneration Stimulation", "Longevity", N, "2028-09"),
    ("Self-Replicating Robotic Assembly Workflow Specification", "Manufacturing", N, "2029-03"),
    ("Autonomous Legal Corpus Reconciler & Conflict Resolution", "Law", N, "2027-12"),
    ("AI-Discovered High-Yield Ambient Nitrogen Fixation Catalyst", "Chemistry", N, "2028-10"),
    ("Zero-Human Input Peer-Reviewed Journal Monograph", "Science", N, "2028-05"),
    ("Complete Synthetic Immune System Re-Engineering Protocol", "Immunology", N, "2029-08"),
    ("Deep Space Optical Communications Real-Time Routing Agent", "Aerospace", N, "2029-01"),
    ("Autonomous High-Energy Particle Collision Anomaly Discovery", "Physics", N, "2028-12"),
    ("Cognitive Architecture Exceeding Human Brain Equivalent FLOPS", "Hardware", N, "2029-06"),
    ("In Vivo Whole-Organ Rejuvenation Demonstrated in Mammals", "Longevity", N, "2029-11"),
    ("Recursive Closed-Loop ASI Research & Iteration Engine", "Superintelligence", N, "2030-04"),
]

# ---------------------------------------------------------------- Helpers


def now_utc():
    return datetime.now(timezone.utc)


def budapest_now():
    try:
        return datetime.now(zoneinfo.ZoneInfo("Europe/Budapest"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=2)))


def countdown_parts(target):
    secs = int((target - now_utc()).total_seconds())
    if secs <= 0:
        return 0, 0, 0, 0
    return secs // 86400, (secs % 86400) // 3600, (secs % 3600) // 60, secs % 60


def clock_html(target, large=False):
    d, h, m, s = countdown_parts(target)
    fs, mw = ("2.35rem", "74px") if large else ("1.85rem", "58px")
    blocks = "".join(
        f'<div class="digital-block" style="min-width:{mw}"><div class="digital-val" '
        f'style="font-size:{fs}">{v}</div><div class="digital-sub">{u}</div></div>'
        for v, u in ((d, "Days"), (f"{h:02d}", "Hours"), (f"{m:02d}", "Min"), (f"{s:02d}", "Sec"))
    )
    return f'<div class="clock-row">{blocks}</div>'


def badges(model):
    status_b = f'<span class="badge badge-{model["status"].lower()}">{model["status"]}</span>'
    source_b = f'<span class="badge badge-{model["source"]}">{model["source"]}</span>'
    impact_b = f'<span style="font-size:0.75rem; font-weight:700; color:#10b981;">+{model["personal_impact"]}%</span>'
    return f'{status_b} {source_b} &nbsp; {impact_b}'


def get_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY")


def fetch_event(item):
    slug, entity, label = item
    try:
        res = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=4)
        if res.status_code != 200:
            return None
        data = res.json()
        if not data:
            return None
        
        event_obj = data[0] if isinstance(data, list) else data
        options = []
        for m in event_obj.get("markets", []):
            q = m.get("question", "")
            title = m.get("groupItemTitle", "") or q
            try:
                yes = float(json.loads(m.get("outcomePrices", '["0.5","0.5"]'))[0])
            except Exception:
                yes = 0.5
            vol = float(m.get("volumeNum", 0) or m.get("volume", 0) or 0)
            implied = round(1.0 - yes, 4) if "no release" in (q + " " + title).lower() else round(yes, 4)
            options.append({"option": title, "implied_prob": implied, "raw_yes": yes, "volume": vol})
        return {"label": label, "entity": entity, "slug": slug, "options": options}
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner="Syncing 34 Polymarket contracts in parallel...")
def load_market():
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(fetch_event, POLYMARKET_EVENTS))
    return [r for r in results if r]


def parse_discrete_date_market(options, min_volume=1000):
    """
    Parses discrete daily date contracts (e.g. 'September 28', 'September 29', 'October 16').
    Returns the peak probability date if volume >= min_volume and peak >= 25%.
    """
    now = now_utc()
    total_vol = sum(o.get("volume", 0) for o in options)
    if total_vol < min_volume:
        return None

    date_candidates = []
    for o in options:
        txt = o["option"].lower().replace(",", "").strip()
        if "no release" in txt:
            continue
        has_year = any(str(y) in txt for y in (2026, 2027, 2028))
        if not has_year:
            txt = f"{txt} {now.year}"

        for fmt in ("%B %d %Y", "%b %d %Y", "%Y-%m-%d"):
            try:
                d = datetime.strptime(txt, fmt)
            except ValueError:
                continue
            if not has_year and d.replace(tzinfo=timezone.utc) < now - timedelta(days=120):
                d = d.replace(year=now.year + 1)
            target_d = d.replace(hour=16, minute=0, second=0, tzinfo=timezone.utc)
            if target_d >= now - timedelta(days=1):
                date_candidates.append((target_d, o["implied_prob"], o["volume"]))
            break

    if not date_candidates:
        return None

    # Pick the mode (highest probability date)
    date_candidates.sort(key=lambda x: x[1], reverse=True)
    best_date, best_prob, _ = date_candidates[0]
    if best_prob >= 0.25:
        return best_date
    return None


def parse_cumulative_market(options, min_volume=1500):
    """
    Calculates the 50% crossing date from cumulative strikes.
    Requires at least $1,500 volume to override hand-calibrated dates.
    """
    now = now_utc()
    total_vol = sum(o.get("volume", 0) for o in options)
    if total_vol < min_volume:
        return None

    pts = []
    for o in options:
        txt = o["option"].lower().replace("before ", "").replace("by ", "").replace(",", "").strip()
        has_year = any(str(y) in txt for y in (2026, 2027, 2028))
        if not has_year:
            txt = f"{txt} {now.year}"

        for fmt in ("%B %d %Y", "%b %d %Y", "%Y-%m-%d"):
            try:
                d = datetime.strptime(txt, fmt)
            except ValueError:
                continue
            if not has_year and d.replace(tzinfo=timezone.utc) < now - timedelta(days=120):
                d = d.replace(year=now.year + 1)
            target_d = d.replace(hour=16, minute=0, second=0, tzinfo=timezone.utc)
            if target_d >= now - timedelta(days=1):
                pts.append((target_d, o["implied_prob"]))
            break

    if len(pts) < 2:
        return None
    pts.sort()

    # Case 1: First strike is already >= 50%
    if pts[0][1] >= 0.50:
        if (pts[0][0] - now).days <= 4:
            return pts[0][0]
        return None

    # Case 2: Linear interpolation between brackets
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if p0 <= 0.50 <= p1 and p1 > p0:
            frac = (0.50 - p0) / (p1 - p0)
            return d0 + (d1 - d0) * frac
    return None


def resolve_all_models(market):
    """
    Estimates the release of every single model by testing discrete daily markets,
    cumulative strike curves, and liquidity rules.
    """
    by_label = {e["label"]: e for e in market}
    out = []

    for m in MODELS:
        m = dict(m)

        # 1. Enforce cadence lock for Flash-Lite (rejects illiquid $56 order book)
        if m.get("id") == "gemini_flash_lite_next":
            m["source"] = "cadence"
            out.append(m)
            continue

        # 2. Check Discrete Daily Market First (e.g. Sonnet Sep 28/29, Gemini Pro Oct 16)
        discrete_target = None
        if m.get("poly_discrete"):
            ev_d = by_label.get(m["poly_discrete"])
            if ev_d:
                discrete_target = parse_discrete_date_market(ev_d["options"], min_volume=1000)

        if discrete_target and discrete_target > now_utc():
            m["target"] = discrete_target
            m["source"] = "market"
            out.append(m)
            continue

        # 3. Check Cumulative 'Released By' Market
        cumulative_target = None
        if m.get("poly_cumulative"):
            ev_c = by_label.get(m["poly_cumulative"])
            if ev_c:
                cumulative_target = parse_cumulative_market(ev_c["options"], min_volume=1500)

        if cumulative_target and cumulative_target > now_utc():
            m["target"] = cumulative_target
            m["source"] = "market"
            out.append(m)
            continue

        # 4. Fallback to Calibrated Pipeline Date
        out.append(m)

    # 5. Enforce Anthropic Pipeline Order: Haiku 5.5 follows Sonnet 5.5
    sonnet_t = next((m["target"] for m in out if m.get("id") == "claude_sonnet_55"), None)
    for m in out:
        if m.get("id") == "claude_haiku_55" and sonnet_t:
            if m["target"] <= sonnet_t:
                m["target"] = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)
                m["source"] = "manual"

    return out


def options_df(options, top=None):
    df = pd.DataFrame(options).rename(columns={
        "option": "Option", 
        "implied_prob": "Implied %",
        "volume": "Volume (USD)"
    })[["Option", "Implied %", "Volume (USD)"]]
    df["Implied %"] = (df["Implied %"] * 100).round(1)
    df = df.sort_values("Implied %", ascending=False)
    return df.head(top) if top else df


@st.cache_data(ttl=3600, show_spinner=False)
def load_summary(payload):
    key = get_api_key()
    if not key or genai is None:
        return None, "Gemini offline (API key omitted)"
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=45000))
    prompt = (
        "Current Date: 28 September 2026. User is a Hungarian index investor aiming for FIRE via VUAA compounding and LEV. "
        "Review these live prediction-market order books. "
        "Provide 4 concise sentences analyzing model release density, potential slippage, and capital compounding velocity. "
        "Use hard numbers only, note thin volume, no conversational preamble.\n" + payload
    )
    for name, timeout in CANDIDATES:
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            cfg = types.GenerateContentConfig()
            if "flash" in name and "lite" not in name:
                try:
                    cfg.thinking_config = types.ThinkingConfig(thinking_level="medium")
                except Exception:
                    pass
            resp = ex.submit(lambda n=name: client.models.generate_content(
                model=n, contents=prompt, config=cfg
            )).result(timeout=timeout)
            if resp and resp.text:
                return resp.text.strip(), name
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)
    return None, "All candidate models timed out"


# ---------------------------------------------------------------- App Execution

market = load_market()
models = resolve_all_models(market)

st.title("⏱️ Frontier Board")
st.caption("Precision intelligence dashboard tracking frontier model releases, FIRE velocity, and Longevity Escape Velocity. Times shown in UTC and Budapest time.")

# Executive Top HUD
upcoming = sorted((m for m in models if m["target"] > now_utc()), key=lambda m: m["target"])
h1, h2, h3, h4 = st.columns(4)
next_model_text = upcoming[0]["name"] if upcoming else "None"
next_days_text = f"{countdown_parts(upcoming[0]['target'])[0]} days" if upcoming else None

h1.metric("Next on Board", next_model_text, next_days_text, delta_color="off")
h2.metric("Clocks Tracked", len(models), "14 Models Active")
h3.metric("Live Market Feeds", f"{len(market)}/{len(POLYMARKET_EVENTS)}", "Polymarket Gamma")
h4.metric("Market-Calibrated", sum(m["source"] == "market" for m in models), f"{sum(m['source'] != 'market' for m in models)} Pipeline Backstops")

tab_board, tab_crown, tab_curves, tab_personal, tab_geo, tab_alan, tab_audit = st.tabs([
    "⏱️ Release Clocks", 
    "👑 AI Frontier Crown & Benchmarks",
    "📈 Probability Waves", 
    "🧬 FIRE & LEV Horizon",
    "🏛️ Geopolitics", 
    "🧠 Milestones & Math", 
    "🔍 Order Book Audit"
])

# ---- Tab 1: Grok-Style Release Board
with tab_board:
    f1, f2 = st.columns([3, 2])
    f1.radio(
        "Lab", 
        ["All", "Anthropic", "Google DeepMind", "OpenAI", "SpaceXAI"],
        horizontal=True, 
        label_visibility="collapsed", 
        key="lab_filter"
    )
    f2.toggle("Near-term only (Confirmed & Likely)", key="near_only")

    pool = sorted((m for m in models if m["target"] > now_utc()), key=lambda m: m["target"])
    released = [m["name"] for m in models if m["target"] <= now_utc()]

    if not pool:
        st.info("All tracked clocks have resolved past their target dates.")
    else:
        nxt = pool[0]
        render_html(f"""
        <div class="hero-container">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="hero-label">NEXT ON THE BOARD · {len(pool)} CLOCKS RUNNING</div>
                <div>{badges(nxt)}</div>
            </div>
            <div class="lab-tag" style="margin-top:0.4rem;">{nxt['code']} {html.escape(nxt['lab'])}</div>
            <div class="hero-title">{html.escape(nxt['name'])}</div>
            {clock_html(nxt['target'], large=True)}
            <div style="color:#cbd5e1; font-weight:700; font-size:0.95rem;">
                Target: {nxt['target'].strftime('%d %b %Y %H:%M UTC')} ({nxt['target'].astimezone(zoneinfo.ZoneInfo('Europe/Budapest')).strftime('%H:%M')} Budapest)
            </div>
            <div style="color:#94a3b8; font-size:0.85rem; margin-top:0.35rem; line-height:1.4;">
                {html.escape(nxt['notes'])}
            </div>
        </div>
        """)

        shown = pool
        if st.session_state.get("lab_filter", "All") != "All":
            shown = [m for m in shown if m["lab"] == st.session_state["lab_filter"]]
        if st.session_state.get("near_only"):
            shown = [m for m in shown if m["status"] in ("CONFIRMED", "LIKELY")]

        cols = st.columns(2)
        for i, m in enumerate(shown):
            with cols[i % 2]:
                render_html(f"""
                <div class="model-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="lab-tag">{m['code']} {html.escape(m['lab'])}</span>
                        <span>{badges(m)}</span>
                    </div>
                    <div style="font-size:1.25rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">
                        {html.escape(m['name'])}
                    </div>
                    {clock_html(m['target'])}
                    <div style="color:#94a3b8; font-size:0.85rem; font-weight:600;">
                        Target: {m['target'].strftime('%d %b %Y %H:%M UTC')}
                    </div>
                    <div style="color:#64748b; font-size:0.8rem; margin-top:0.35rem; line-height:1.35;">
                        {html.escape(m['notes'])}
                    </div>
                </div>
                """)

        if released:
            st.caption("Passed target window: " + ", ".join(released))


# ---- Tab 2: AI Frontier Crown & Benchmarks
with tab_crown:
    st.subheader("👑 Frontier AI Crown & Superiority Stakes")
    st.caption("Live prediction market odds on model superiority, Chatbot Arena milestones, and Humanity's Last Exam (HLE).")

    by_lbl = {e["label"]: e for e in market}

    # Section 1: Crown Races
    cr_col1, cr_col2, cr_col3 = st.columns(3)
    with cr_col1:
        ev = by_lbl.get("Best AI Model End of October")
        st.markdown("**Best Model: End of October**")
        if ev and ev["options"]:
            st.dataframe(options_df(ev["options"], 4), hide_index=True)
    with cr_col2:
        ev = by_lbl.get("Best AI Model End of November")
        st.markdown("**Best Model: End of November**")
        if ev and ev["options"]:
            st.dataframe(options_df(ev["options"], 4), hide_index=True)
    with cr_col3:
        ev = by_lbl.get("Best AI Model End of 2026")
        st.markdown("**Best Model: End of 2026**")
        if ev and ev["options"]:
            st.dataframe(options_df(ev["options"], 4), hide_index=True)

    st.divider()

    # Section 2: Chatbot Arena & HLE Benchmarks
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.subheader("🥊 Chatbot Arena Races")
        ev_1550 = by_lbl.get("First to Hit 1550 on Arena")
        if ev_1550 and ev_1550["options"]:
            st.markdown("**First AI to Hit 1550 on Arena in 2026**")
            st.dataframe(options_df(ev_1550["options"], 5), hide_index=True)

        ev_sonnet_arena = by_lbl.get("Sonnet Text Arena Debut")
        if ev_sonnet_arena and ev_sonnet_arena["options"]:
            st.markdown("**Next Sonnet Model: Text Arena Debut Score**")
            st.dataframe(options_df(ev_sonnet_arena["options"], 4), hide_index=True)

        ev_gemini_arena = by_lbl.get("Gemini Pro Arena Debut Score")
        if ev_gemini_arena and ev_gemini_arena["options"]:
            st.markdown("**Next Gemini Pro: Arena Debut Score**")
            st.dataframe(options_df(ev_gemini_arena["options"], 4), hide_index=True)

    with b_col2:
        st.subheader("🎓 Humanity's Last Exam (HLE) Stakes")
        ev_gemini_hle = by_lbl.get("Highest Gemini HLE Score 2026")
        if ev_gemini_hle and ev_gemini_hle["options"]:
            st.markdown("**Highest Google Gemini Score on HLE in 2026**")
            st.dataframe(options_df(ev_gemini_hle["options"], 4), hide_index=True)

        ev_claude_hle = by_lbl.get("Highest Claude HLE Score 2026")
        if ev_claude_hle and ev_claude_hle["options"]:
            st.markdown("**Highest Claude Score on HLE in 2026**")
            st.dataframe(options_df(ev_claude_hle["options"], 4), hide_index=True)

        ev_openai_hle = by_lbl.get("Highest OpenAI HLE Score 2026")
        if ev_openai_hle and ev_openai_hle["options"]:
            st.markdown("**Highest OpenAI Score on HLE in 2026**")
            st.dataframe(options_df(ev_openai_hle["options"], 4), hide_index=True)


# ---- Tab 3: Probability Waves & Live Distributions
with tab_curves:
    st.subheader("Comparative Probability Density Functions")
    st.caption("Normalized daily mass distribution across the Q4 2026 intelligence compression window.")

    start_d = date(2026, 9, 23)
    end_d = date(2026, 11, 5)
    num_days = (end_d - start_d).days + 1
    dates = [(start_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]

    def build_density_series(peak_date_obj, spread, weight):
        res = []
        peak_idx = (peak_date_obj.date() - start_d).days
        for i in range(num_days):
            curr_d = start_d + timedelta(days=i)
            diff = i - peak_idx
            w = math.exp(-0.5 * ((diff / max(1.5, spread)) ** 2))
            w_factor = 1.0 if curr_d.weekday() in [1, 2, 3] else (0.75 if curr_d.weekday() == 0 else (0.6 if curr_d.weekday() == 4 else 0.15))
            res.append(w * w_factor)
        tot = sum(res)
        return [round((x / tot) * weight, 2) for x in res]

    df_waves = pd.DataFrame({"date": dates})
    key_models = [m for m in models if m["target"].date() <= end_d][:5]
    colors = ["#f59e0b", "#fb923c", "#34d399", "#c084fc", "#06b6d4"]

    fig_w = go.Figure()
    for m, c in zip(key_models, colors):
        series = build_density_series(m["target"], 2.8, 90.0)
        fig_w.add_trace(go.Scatter(
            x=df_waves["date"], y=series, mode="lines+markers", 
            name=m["name"], line=dict(color=c, width=2.5)
        ))

    fig_w.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Calendar Date", fixedrange=True),
        yaxis=dict(title="Implied Daily Density (%)", fixedrange=True, rangemode="tozero"),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_w, config={"displayModeBar": False, "scrollZoom": False})

    st.divider()
    st.subheader("Live Polymarket Order Book Distributions")
    labeled = [e for e in market if e["entity"] in ("Google", "OpenAI", "Anthropic", "SpaceXAI", "Crown") and e["options"]]
    if labeled:
        pick = st.selectbox("Market Event", [f"{e['entity']} · {e['label']}" for e in labeled])
        ev = labeled[[f"{e['entity']} · {e['label']}" for e in labeled].index(pick)]
        fig_bar = go.Figure(go.Bar(
            x=[o["option"] for o in ev["options"]],
            y=[round(o["implied_prob"] * 100, 1) for o in ev["options"]],
            marker_color="#3b82f6"
        ))
        fig_bar.update_layout(
            template="plotly_dark",
            yaxis_title="Implied Probability (%)",
            xaxis=dict(fixedrange=True),
            yaxis=dict(fixedrange=True, rangemode="tozero"),
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(fig_bar, config={"displayModeBar": False, "scrollZoom": False})
        st.caption(f"Total Market Liquidity: ${sum(o['volume'] for o in ev['options']):,.0f}")
    else:
        st.warning("No market feeds loaded.")

    payload = json.dumps([
        {"market": e["label"], "top": options_df(e["options"], 6).to_dict("records")}
        for e in labeled
    ], default=str)
    summary, engine = load_summary(payload)
    st.markdown("**Executive Market Intelligence**" + (f" · {engine}" if summary else ""))
    st.write(summary or f"Unavailable ({engine}).")


# ---- Tab 4: Personal FIRE & Longevity Escape Velocity
with tab_personal:
    st.subheader("Personal FIRE Engine & Compounding Velocity")
    st.caption("Calculated in constant today's HUF for asset compounding via VUAA inside a tax-sheltered TBSZ account.")

    c1, c2, c3, c4 = st.columns(4)
    start = c1.number_input("Invested Assets (HUF)", 0, value=15_000_000, step=1_000_000)
    monthly = c2.number_input("Monthly Contribution (HUF)", 0, value=350_000, step=25_000)
    ret = c3.slider("Real Return (% per year)", 0.0, 12.0, 6.5, 0.5)
    target = c4.number_input("FIRE Target Milestone (HUF)", 1_000_000, value=60_000_000, step=5_000_000)

    def months_to_fire(pv, pmt, rate_annual, fv):
        if pv >= fv:
            return 0
        if rate_annual <= 0:
            return math.ceil((fv - pv) / pmt) if pmt > 0 else 999
        r = (1 + rate_annual / 100.0) ** (1.0 / 12.0) - 1.0
        numerator = fv * r + pmt
        denominator = pv * r + pmt
        if denominator <= 0 or numerator <= 0:
            return 999
        return math.ceil(math.log(numerator / denominator) / math.log(1.0 + r))

    m_base = months_to_fire(start, monthly, ret, target)
    fire_date = now_utc() + timedelta(days=int(m_base * 30.4375))

    render_html(f"""
    <div class="hero-container" style="border-color:#10b981;">
        <div class="hero-label" style="color:#34d399;">PERPETUAL FINANCIAL INDEPENDENCE (FIRE) COUNTDOWN</div>
        <div class="hero-title">{target:,.0f} HUF Target Milestone</div>
        {clock_html(fire_date, large=True)}
        <div style="color:#cbd5e1; font-weight:700;">
            Projected Arrival: {fire_date.strftime('%B %Y')} ({m_base // 12} years, {m_base % 12} months)
        </div>
    </div>
    """)

    sens_cols = st.columns(3)
    for col, rate in zip(sens_cols, (max(ret - 2.0, 0.0), ret, ret + 2.0)):
        n = months_to_fire(start, monthly, rate, target)
        col.metric(f"At {rate:.1f}% Real Return", f"{n // 12}y {n % 12}m", f"Target: {n} months")

    st.divider()
    st.subheader("Longevity Escape Velocity (LEV) & Biological Horizon")
    st.caption("Personalized timeline mapping status-quo biological senescence against AI-accelerated LEV crossover.")

    birth_date = datetime(2003, 12, 1, tzinfo=timezone.utc)
    status_quo_death = birth_date + timedelta(days=int(75.0 * 365.25))
    lev_compressed = datetime(2036, 7, 1, tzinfo=timezone.utc)
    extended_lifespan = datetime(2145, 12, 1, tzinfo=timezone.utc)

    l1, l2, l3 = st.columns(3)
    with l1:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Crossover Point</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Personal LEV Arrival</div>
            {clock_html(lev_compressed)}
            <div style="color:#38bdf8; font-size:0.8rem; font-weight:700;">Target: July 2036 (Age 32.6)</div>
            <div style="color:#64748b; font-size:0.75rem; margin-top:0.25rem;">Compressed by 15 months via lab capex wave.</div>
        </div>
        """)
    with l2:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Actuarial Senescence</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Status-Quo Mortality</div>
            {clock_html(status_quo_death)}
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:700;">Target: Dec 2078 (Age 75.0)</div>
            <div style="color:#64748b; font-size:0.75rem; margin-top:0.25rem;">Hungarian actuarial baseline without rejuvenation.</div>
        </div>
        """)
    with l3:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Post-LEV Trajectory</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Extended Healthspan</div>
            {clock_html(extended_lifespan)}
            <div style="color:#a855f7; font-size:0.8rem; font-weight:700;">Horizon: ~2145+ (Age 140+)</div>
            <div style="color:#64748b; font-size:0.75rem; margin-top:0.25rem;">Rejuvenation pace exceeding 1.0 biological year per chronological year.</div>
        </div>
        """)


# ---- Tab 5: Geopolitics & Personal Transmission Matrix
with tab_geo:
    st.subheader("Geopolitical Transmission & Personal Life Impact Matrix")
    st.caption("Quantified transmission channels to Hungarian cost of living, EUR/HUF currency stability, and VUAA ETF compounding.")

    for g in GEOPOLITICS_TRANSMISSION:
        eff = g["effect"]
        eff_color = "#10b981" if eff > 0 else "#ef4444"
        render_html(f"""
        <div class="model-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="lab-tag">{g['event']} · Probability: {g['prob']:.1f}%</span>
                <span style="font-size:1.05rem; font-weight:800; color:{eff_color};">Net Personal Effect: {eff:+d}%</span>
            </div>
            <div style="font-size:1.2rem; font-weight:800; color:#f8fafc; margin:0.3rem 0;">
                {g['outcome']}
            </div>
            <div style="font-size:0.85rem; color:#94a3b8; line-height:1.4;">
                <strong>Transmission Mechanism:</strong> {g['transmission']}
            </div>
        </div>
        """)

    st.divider()
    st.subheader("Live Prediction Market Feeds")
    geo = [e for e in market if e["entity"] == "Geopolitics" and e["options"]]
    for ev in geo:
        st.markdown(f"**{ev['label']}**")
        st.dataframe(options_df(ev["options"], 8), hide_index=True)


# ---- Tab 6: Alan Thompson Milestones & Millennium Math
with tab_alan:
    st.subheader("Alan Thompson (LifeArchitect.ai) ASI Milestones")
    st.caption("Tracks the conservative 50-indicator trajectory toward artificial superintelligence.")

    df_alan = pd.DataFrame(ALAN, columns=["Milestone", "Category", "Status", "Date"])
    counts = df_alan["Status"].value_counts()
    
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Alan's AGI Gauge", "99.0%", "Est. Completion: Q4 2026")
    a2.metric("Achieved", int(counts.get(A, 0)), "Green Badges")
    a3.metric("In Progress", int(counts.get(P, 0)), "Active Research")
    a4.metric("Pending", int(counts.get(N, 0)), "Frontier Indicators")

    with st.expander("Inspect All 50 ASI Indicators"):
        st.dataframe(df_alan, hide_index=True, height=400)

    st.divider()
    st.subheader("Millennium Prize Mathematics Credible Solution Dates")
    st.caption("Estimated single most likely calendar date that a verified proof is publicly published by any lab or researcher.")

    df_math = pd.DataFrame(MILLENNIUM_CONSENSUS).rename(columns={
        "problem": "Millennium Prize Problem",
        "solution_date": "Credible Solution Date",
        "prob": "Confidence (%)",
        "contender": "Leading Mechanism",
        "impact": "Disciplinary Impact"
    })
    st.dataframe(df_math, hide_index=True)

    st.divider()
    st.subheader("Live Millennium Prize Market Feeds")
    for ev in (e for e in market if e["entity"] == "Math" and e["options"]):
        st.markdown(f"**{ev['label']}**")
        st.dataframe(options_df(ev["options"], 8), hide_index=True)


# ---- Tab 7: Live Epistemic & Order Book Audit
with tab_audit:
    st.subheader("Raw Prediction Market Order Books")
    missing = [lbl for _, _, lbl in POLYMARKET_EVENTS if lbl not in {e["label"] for e in market}]
    if missing:
        st.warning("Failed to harvest: " + ", ".join(missing))
    for ev in market:
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

st.divider()
st.caption(f"Market cache: 10 min · Summary cache: 60 min · Budapest Calibration Time: {budapest_now().strftime('%Y-%m-%d %H:%M %Z')}")
if st.button("Force Synchronized Market Recalculation"):
    st.cache_data.clear()
    st.rerun()
