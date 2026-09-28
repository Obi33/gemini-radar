"""
Frontier Board | Model Release Clocks, Benchmark Stakes & FIRE/LEV Engine

Requirements: streamlit>=1.37, requests, pandas, plotly, tzdata (Windows only),
              google-genai (optional)
Secrets: GEMINI_API_KEY (optional, used for 4-sentence macroeconomic executive briefs)
"""
import html
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = types = None

st.set_page_config(
    page_title="Frontier Board | Intelligence, Capital & LEV",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------- Configuration

MARKET_TTL = 600     # seconds a Polymarket snapshot stays cached
SUMMARY_TTL = 3600   # seconds a Gemini brief stays cached
GAMMA_URL = "https://gamma-api.polymarket.com/events"

try:
    BUDAPEST = ZoneInfo("Europe/Budapest")
except Exception:  # tzdata missing. Fixed +2h is only right in summer, so install tzdata.
    BUDAPEST = timezone(timedelta(hours=2))

# Anthropic ships Haiku after Sonnet. If a market date puts Haiku first, push it this far behind.
HAIKU_LAG_DAYS = 9
# Order books too thin to trust: always use the calibrated cadence date.
ILLIQUID_IDS = {"gemini_flash_lite_next"}

# Personal / scenario assumptions. Move to st.secrets if this app or repo is ever public.
BIRTH_DATE = datetime(2003, 12, 1, tzinfo=timezone.utc)
LIFE_EXPECTANCY_YEARS = 75.0
LEV_ARRIVAL = datetime(2036, 7, 1, tzinfo=timezone.utc)
EXTENDED_HORIZON = datetime(2145, 12, 1, tzinfo=timezone.utc)
ALAN_AGI_GAUGE = ("99.0%", "Est. Completion: Q4 2026")

# Probability-wave chart
PLOT_HORIZON_DAYS = 38
PLOT_COLORS = ["#f59e0b", "#fb923c", "#34d399", "#c084fc", "#06b6d4", "#f472b6", "#a3e635"]
# Releases cluster Tue to Thu, taper Mon/Fri, and rarely land on weekends.
WEEKDAY_RELEASE_WEIGHT = {0: 0.75, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.6, 5: 0.15, 6: 0.15}


def render_html(s):
    """Render an HTML snippet. Lines are stripped so markdown never treats indentation as a code
    block, and blank lines are dropped because a blank line ends a markdown HTML block early."""
    cleaned = "\n".join(line.strip() for line in s.splitlines() if line.strip())
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

# ---------------------------------------------------------------- Time helpers


def now_utc():
    return datetime.now(timezone.utc)


def to_budapest(dt):
    return dt.astimezone(BUDAPEST)


def age_at(dt):
    return (dt - BIRTH_DATE).days / 365.25


def countdown_parts(target, now=None):
    now = now or now_utc()
    secs = int((target - now).total_seconds())
    if secs <= 0:
        return 0, 0, 0, 0
    return secs // 86400, (secs % 86400) // 3600, (secs % 3600) // 60, secs % 60


def eta_text(target, now):
    d, h, m, _ = countdown_parts(target, now)
    return f"in {d}d {h}h" if d else f"in {h}h {m}m"


# ---------------------------------------------------------------- HTML fragments


def clock_html(target, now=None, large=False):
    d, h, m, s = countdown_parts(target, now)
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


def model_card_html(m, now):
    target = m["target"]
    return f"""
    <div class="model-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="lab-tag">{m['code']} {html.escape(m['lab'])}</span>
            <span>{badges(m)}</span>
        </div>
        <div style="font-size:1.25rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">
            {html.escape(m['name'])}
        </div>
        {clock_html(target, now)}
        <div style="color:#94a3b8; font-size:0.85rem; font-weight:600;">
            Target: {target.strftime('%d %b %Y %H:%M UTC')} ({to_budapest(target).strftime('%H:%M')} Budapest)
        </div>
        <div style="color:#64748b; font-size:0.8rem; margin-top:0.35rem; line-height:1.35;">
            {html.escape(m['notes'])}
        </div>
    </div>
    """


# ---------------------------------------------------------------- Polymarket


def get_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY")


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_yes_price(raw):
    """outcomePrices is normally a JSON-encoded list like '["0.63","0.37"]' but may already be a list."""
    prices = json.loads(raw) if isinstance(raw, str) else raw
    return float(prices[0])


def fetch_event(item):
    """Fetch one Polymarket event. Returns None on failure so one bad slug never breaks the board."""
    slug, entity, label = item
    data = None
    for attempt in range(2):
        try:
            res = requests.get(GAMMA_URL, params={"slug": slug}, timeout=(3, 5))
            if res.status_code == 200:
                data = res.json()
                break
            if res.status_code < 500 and res.status_code != 429:
                return None  # 404 and friends: retrying will not help
        except (requests.RequestException, ValueError):
            pass
        if attempt == 0:
            time.sleep(0.3)
    if not data:
        return None

    event_obj = data[0] if isinstance(data, list) else data
    options = []
    for m in event_obj.get("markets", []):
        question = m.get("question") or ""
        title = m.get("groupItemTitle") or question
        try:
            yes = _parse_yes_price(m.get("outcomePrices"))
        except (TypeError, ValueError, IndexError):
            continue  # no usable price: skip it instead of inventing a 50% quote
        volume = _to_float(m.get("volumeNum") or m.get("volume"))
        inverted = "no release" in f"{question} {title}".lower()
        options.append({
            "option": title,
            "implied_prob": round(1.0 - yes, 4) if inverted else round(yes, 4),
            "raw_yes": yes,
            "volume": volume,
        })
    return {"label": label, "entity": entity, "slug": slug, "options": options}


@st.cache_data(ttl=MARKET_TTL, show_spinner=f"Syncing {len(POLYMARKET_EVENTS)} Polymarket contracts in parallel...")
def load_market():
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = [r for r in ex.map(fetch_event, POLYMARKET_EVENTS) if r]
    if not results:
        # Raising keeps a total outage out of the cache, so the next rerun retries immediately.
        raise RuntimeError("Polymarket returned no data")
    return results


# ---------------------------------------------------------------- Market-to-date logic

_YEAR_RE = re.compile(r"\b20\d{2}\b")
_PREFIX_RE = re.compile(r"^(?:before|by)\s+")
_DATE_FORMATS = ("%B %d %Y", "%b %d %Y", "%Y-%m-%d")
_GRACE = timedelta(days=1)             # keep dates that passed within the last day
_ROLLOVER = timedelta(days=120)        # a yearless date older than this means "next year"


def parse_option_date(text, now):
    """'By October 15' or 'September 28' -> datetime at 16:00 UTC, or None if it is not a date."""
    txt = _PREFIX_RE.sub("", text.lower().replace(",", "").strip())
    if not txt:
        return None
    has_year = bool(_YEAR_RE.search(txt))
    candidate = txt if has_year else f"{txt} {now.year}"
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        parsed = parsed.replace(hour=16, minute=0, second=0, tzinfo=timezone.utc)
        if not has_year and parsed < now - _ROLLOVER:
            try:
                parsed = parsed.replace(year=parsed.year + 1)
            except ValueError:  # Feb 29 landing in a non-leap year
                return None
        return parsed
    return None


def parse_discrete_date_market(options, now, min_volume=1000, min_peak=0.25):
    """Daily contracts ('September 28', 'September 29', ...). Returns the modal date when the
    book has enough volume and the peak carries at least `min_peak` probability."""
    if sum(o.get("volume", 0) for o in options) < min_volume:
        return None
    candidates = []
    for o in options:
        if "no release" in o["option"].lower():
            continue
        d = parse_option_date(o["option"], now)
        if d and d >= now - _GRACE:
            candidates.append((o["implied_prob"], d))
    if not candidates:
        return None
    prob, best = max(candidates, key=lambda c: c[0])
    return best if prob >= min_peak else None


def parse_cumulative_market(options, now, min_volume=1500):
    """'Released by <date>' strikes -> the date the curve crosses 50%, by linear interpolation.
    Needs enough volume to override the hand-calibrated date."""
    if sum(o.get("volume", 0) for o in options) < min_volume:
        return None
    pts = []
    for o in options:
        d = parse_option_date(o["option"], now)
        if d and d >= now - _GRACE:
            pts.append((d, o["implied_prob"]))
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])

    # First live strike already at or above 50%: only trust it when it is imminent.
    if pts[0][1] >= 0.50:
        return pts[0][0] if (pts[0][0] - now).days <= 4 else None

    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if p0 <= 0.50 <= p1 and p1 > p0:
            return d0 + (d1 - d0) * ((0.50 - p0) / (p1 - p0))
    return None


def _market_target(model, by_label, now):
    """Discrete daily market first, then the cumulative curve. None means fall back to the registry date."""
    ev = by_label.get(model.get("poly_discrete") or "")
    if ev:
        t = parse_discrete_date_market(ev["options"], now)
        if t and t > now:
            return t
    ev = by_label.get(model.get("poly_cumulative") or "")
    if ev:
        t = parse_cumulative_market(ev["options"], now)
        if t and t > now:
            return t
    return None


def resolve_all_models(market, now):
    by_label = {e["label"]: e for e in market}
    out = []
    for base in MODELS:
        m = dict(base)
        out.append(m)
        if m["id"] in ILLIQUID_IDS:
            m["source"] = "cadence"
            continue
        target = _market_target(m, by_label, now)
        if target:
            m["target"], m["source"] = target, "market"

    # Pipeline order: Haiku 5.5 follows Sonnet 5.5.
    sonnet_t = next((m["target"] for m in out if m["id"] == "claude_sonnet_55"), None)
    if sonnet_t:
        for m in out:
            if m["id"] == "claude_haiku_55" and m["target"] <= sonnet_t:
                m["target"] = sonnet_t + timedelta(days=HAIKU_LAG_DAYS)
                m["source"] = "manual"
    return out


def options_df(options, top=None):
    cols = ["Option", "Implied %", "Volume (USD)"]
    if not options:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(options).rename(columns={
        "option": "Option", "implied_prob": "Implied %", "volume": "Volume (USD)",
    })[cols]
    df["Implied %"] = (df["Implied %"] * 100).round(1)
    df = df.sort_values("Implied %", ascending=False)
    return df.head(top) if top else df


def show_market_table(by_label, label, title, top=8):
    st.markdown(f"**{title}**")
    ev = by_label.get(label)
    if ev and ev["options"]:
        st.dataframe(options_df(ev["options"], top), hide_index=True)
    else:
        st.caption("Feed unavailable.")


# ---------------------------------------------------------------- Gemini brief


def build_summary_payload(events):
    return json.dumps(
        [{"market": e["label"], "top": options_df(e["options"], 6).to_dict("records")} for e in events],
        default=str,
    )


def _generation_config(model_name):
    cfg = types.GenerateContentConfig()
    if "flash" in model_name and "lite" not in model_name:
        try:
            cfg.thinking_config = types.ThinkingConfig(thinking_level="medium")
        except Exception:  # older SDKs do not know thinking_level
            pass
    return cfg


@st.cache_data(ttl=SUMMARY_TTL, show_spinner=False)
def generate_summary(_payload, today_label):
    """Try each candidate model in turn. `_payload` is underscore-prefixed so it is NOT part of the
    cache key: order books wiggle every refresh, and keying on them would re-bill Gemini every 10
    minutes instead of hourly. Raises on failure, so failures are never cached."""
    key = get_api_key()
    prompt = (
        f"Current Date: {today_label}. User is a Hungarian index investor aiming for FIRE via VUAA compounding and LEV. "
        "Review these live prediction-market order books. "
        "Provide 4 concise sentences analyzing model release density, potential slippage, and capital compounding velocity. "
        "Use hard numbers only, note thin volume, no conversational preamble.\n" + _payload
    )
    errors = []
    for name, timeout_s in CANDIDATES:
        try:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
            resp = client.models.generate_content(model=name, contents=prompt, config=_generation_config(name))
            if resp and resp.text:
                return resp.text.strip(), name
            errors.append(f"{name}: empty response")
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}")
    raise RuntimeError("all candidates failed (" + "; ".join(errors) + ")")


def load_summary(payload, today_label):
    if genai is None:
        return None, "google-genai not installed"
    if not get_api_key():
        return None, "Gemini offline (API key omitted)"
    try:
        return generate_summary(payload, today_label)
    except RuntimeError as exc:
        return None, str(exc)


# ---------------------------------------------------------------- Model helpers


def months_to_target(pv, pmt, annual_rate_pct, fv, max_months=1200):
    """Months until pv, compounding monthly with contribution pmt, reaches fv.
    Returns None when the target is unreachable or more than `max_months` away."""
    if pv >= fv:
        return 0
    if annual_rate_pct <= 0:
        if pmt <= 0:
            return None
        n = math.ceil((fv - pv) / pmt)
    else:
        r = (1 + annual_rate_pct / 100.0) ** (1.0 / 12.0) - 1.0
        numerator, denominator = fv * r + pmt, pv * r + pmt
        if numerator <= 0 or denominator <= 0:
            return None
        n = math.ceil(math.log(numerator / denominator) / math.log1p(r))
    return n if n <= max_months else None


def fmt_months(n):
    return "not reachable" if n is None else f"{n // 12}y {n % 12}m"


def build_density_series(peak, start_d, num_days, spread=2.8, weight=90.0):
    peak_idx = (peak.date() - start_d).days
    raw = []
    for i in range(num_days):
        day = start_d + timedelta(days=i)
        bell = math.exp(-0.5 * ((i - peak_idx) / max(1.5, spread)) ** 2)
        raw.append(bell * WEEKDAY_RELEASE_WEIGHT[day.weekday()])
    total = sum(raw) or 1.0
    return [round(x / total * weight, 2) for x in raw]


# ---------------------------------------------------------------- App Execution

NOW = now_utc()  # one clock reading per run, so every countdown on the page agrees

try:
    market = load_market()
    market_down = False
except RuntimeError:
    market, market_down = [], True
by_label = {e["label"]: e for e in market}
models = resolve_all_models(market, NOW)
upcoming = sorted((m for m in models if m["target"] > NOW), key=lambda m: m["target"])
labeled = [e for e in market if e["entity"] in ("Google", "OpenAI", "Anthropic", "SpaceXAI", "Crown") and e["options"]]

st.title("⏱️ Frontier Board")
st.caption("Precision intelligence dashboard tracking frontier model releases, FIRE velocity, and Longevity Escape Velocity. Times shown in UTC and Budapest time.")
if market_down:
    st.warning("Polymarket is unreachable right now. Showing calibrated pipeline dates only.")

h1, h2, h3, h4 = st.columns(4)
h1.metric("Next on Board", upcoming[0]["name"] if upcoming else "None",
          eta_text(upcoming[0]["target"], NOW) if upcoming else None, delta_color="off")
h2.metric("Clocks Tracked", len(models), f"{len(upcoming)} Active")
h3.metric("Live Market Feeds", f"{len(market)}/{len(POLYMARKET_EVENTS)}", "Polymarket Gamma")
n_market = sum(m["source"] == "market" for m in models)
h4.metric("Market-Calibrated", n_market, f"{len(models) - n_market} Pipeline Backstops")

tab_board, tab_crown, tab_curves, tab_personal, tab_geo, tab_alan, tab_audit = st.tabs([
    "⏱️ Release Clocks",
    "👑 AI Frontier Crown & Benchmarks",
    "📈 Probability Waves",
    "🧬 FIRE & LEV Horizon",
    "🏛️ Geopolitics",
    "🧠 Milestones & Math",
    "🔍 Order Book Audit",
])

# ---- Tab 1: Release Board
with tab_board:
    f1, f2 = st.columns([3, 2])
    lab_choice = f1.radio("Lab", ["All", *sorted({m["lab"] for m in MODELS})],
                          horizontal=True, label_visibility="collapsed")
    near_only = f2.toggle("Near-term only (Confirmed & Likely)")

    released = [m["name"] for m in models if m["target"] <= NOW]

    if not upcoming:
        st.info("All tracked clocks have resolved past their target dates.")
    else:
        nxt = upcoming[0]
        render_html(f"""
        <div class="hero-container">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="hero-label">NEXT ON THE BOARD · {len(upcoming)} CLOCKS RUNNING</div>
                <div>{badges(nxt)}</div>
            </div>
            <div class="lab-tag" style="margin-top:0.4rem;">{nxt['code']} {html.escape(nxt['lab'])}</div>
            <div class="hero-title">{html.escape(nxt['name'])}</div>
            {clock_html(nxt['target'], NOW, large=True)}
            <div style="color:#cbd5e1; font-weight:700; font-size:0.95rem;">
                Target: {nxt['target'].strftime('%d %b %Y %H:%M UTC')} ({to_budapest(nxt['target']).strftime('%H:%M')} Budapest)
            </div>
            <div style="color:#94a3b8; font-size:0.85rem; margin-top:0.35rem; line-height:1.4;">
                {html.escape(nxt['notes'])}
            </div>
        </div>
        """)

        shown = [m for m in upcoming
                 if (lab_choice == "All" or m["lab"] == lab_choice)
                 and (not near_only or m["status"] in ("CONFIRMED", "LIKELY"))]
        if not shown:
            st.info("No clocks match these filters.")
        cols = st.columns(2)
        for i, m in enumerate(shown):
            with cols[i % 2]:
                render_html(model_card_html(m, NOW))

        if released:
            st.caption("Passed target window: " + ", ".join(released))


# ---- Tab 2: AI Frontier Crown & Benchmarks
with tab_crown:
    st.subheader("👑 Frontier AI Crown & Superiority Stakes")
    st.caption("Live prediction market odds on model superiority, Chatbot Arena milestones, and Humanity's Last Exam (HLE).")

    crown_tables = [
        ("Best AI Model End of October", "Best Model: End of October"),
        ("Best AI Model End of November", "Best Model: End of November"),
        ("Best AI Model End of 2026", "Best Model: End of 2026"),
    ]
    for col, (label, title) in zip(st.columns(3), crown_tables):
        with col:
            show_market_table(by_label, label, title, top=4)

    st.divider()

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.subheader("🥊 Chatbot Arena Races")
        show_market_table(by_label, "First to Hit 1550 on Arena", "First AI to Hit 1550 on Arena in 2026", top=5)
        show_market_table(by_label, "Sonnet Text Arena Debut", "Next Sonnet Model: Text Arena Debut Score", top=4)
        show_market_table(by_label, "Gemini Pro Arena Debut Score", "Next Gemini Pro: Arena Debut Score", top=4)

    with b_col2:
        st.subheader("🎓 Humanity's Last Exam (HLE) Stakes")
        show_market_table(by_label, "Highest Gemini HLE Score 2026", "Highest Google Gemini Score on HLE in 2026", top=4)
        show_market_table(by_label, "Highest Claude HLE Score 2026", "Highest Claude Score on HLE in 2026", top=4)
        show_market_table(by_label, "Highest OpenAI HLE Score 2026", "Highest OpenAI Score on HLE in 2026", top=4)


# ---- Tab 3: Probability Waves & Live Distributions
with tab_curves:
    st.subheader("Comparative Release Density")
    st.caption(
        f"Stylized view, not raw market data: a bell curve around each model's target date over the next "
        f"{PLOT_HORIZON_DAYS} days, weighted toward Tue to Thu release days."
    )

    start_d = NOW.date()
    num_days = PLOT_HORIZON_DAYS + 1
    end_d = start_d + timedelta(days=PLOT_HORIZON_DAYS)
    dates = [(start_d + timedelta(days=i)).isoformat() for i in range(num_days)]

    in_window = [m for m in upcoming if m["target"].date() <= end_d]
    chosen = st.multiselect(
        "Models to plot",
        [m["name"] for m in in_window],
        default=[m["name"] for m in in_window[:5]],
    )

    fig_w = go.Figure()
    for i, m in enumerate(m for m in in_window if m["name"] in chosen):
        fig_w.add_trace(go.Scatter(
            x=dates, y=build_density_series(m["target"], start_d, num_days),
            mode="lines+markers", name=m["name"],
            line=dict(color=PLOT_COLORS[i % len(PLOT_COLORS)], width=2.5),
        ))
    fig_w.update_layout(
        template="plotly_dark",
        xaxis=dict(title="Calendar Date", fixedrange=True),
        yaxis=dict(title="Relative Daily Density (%)", fixedrange=True, rangemode="tozero"),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_w, config={"displayModeBar": False, "scrollZoom": False})

    st.divider()
    st.subheader("Live Polymarket Order Book Distributions")
    if labeled:
        choices = {f"{e['entity']} · {e['label']}": e for e in labeled}
        ev = choices[st.selectbox("Market Event", list(choices))]
        fig_bar = go.Figure(go.Bar(
            x=[o["option"] for o in ev["options"]],
            y=[round(o["implied_prob"] * 100, 1) for o in ev["options"]],
            marker_color="#3b82f6",
        ))
        fig_bar.update_layout(
            template="plotly_dark",
            yaxis_title="Implied Probability (%)",
            xaxis=dict(fixedrange=True),
            yaxis=dict(fixedrange=True, rangemode="tozero"),
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_bar, config={"displayModeBar": False, "scrollZoom": False})
        st.caption(f"Total Traded Volume: ${sum(o['volume'] for o in ev['options']):,.0f}")
    else:
        st.warning("No market feeds loaded.")

    # Filled at the very end of the script, so a slow Gemini call never blocks the other tabs.
    brief_slot = st.container()


# ---- Tab 4: Personal FIRE & Longevity Escape Velocity
with tab_personal:
    st.subheader("Personal FIRE Engine & Compounding Velocity")
    st.caption("Calculated in constant today's HUF for asset compounding via VUAA inside a tax-sheltered TBSZ account.")

    c1, c2, c3, c4 = st.columns(4)
    start = c1.number_input("Invested Assets (HUF)", 0, value=15_000_000, step=1_000_000)
    monthly = c2.number_input("Monthly Contribution (HUF)", 0, value=350_000, step=25_000)
    ret = c3.slider("Real Return (% per year)", 0.0, 12.0, 6.5, 0.5)
    target = c4.number_input("FIRE Target Milestone (HUF)", 1_000_000, value=60_000_000, step=5_000_000)

    m_base = months_to_target(start, monthly, ret, target)
    if m_base is None:
        st.warning("The target is not reachable within 100 years at these inputs.")
    else:
        fire_date = NOW + timedelta(days=int(m_base * 30.4375))
        render_html(f"""
        <div class="hero-container" style="border-color:#10b981;">
            <div class="hero-label" style="color:#34d399;">PERPETUAL FINANCIAL INDEPENDENCE (FIRE) COUNTDOWN</div>
            <div class="hero-title">{target:,.0f} HUF Target Milestone</div>
            {clock_html(fire_date, NOW, large=True)}
            <div style="color:#cbd5e1; font-weight:700;">
                Projected Arrival: {fire_date.strftime('%B %Y')} ({m_base // 12} years, {m_base % 12} months)
            </div>
        </div>
        """)

    for col, rate in zip(st.columns(3), (max(ret - 2.0, 0.0), ret, ret + 2.0)):
        n = months_to_target(start, monthly, rate, target)
        col.metric(f"At {rate:.1f}% Real Return", fmt_months(n), f"Target: {n} months" if n is not None else None)

    st.divider()
    st.subheader("Longevity Escape Velocity (LEV) & Biological Horizon")
    st.caption("Personalized timeline mapping status-quo biological senescence against AI-accelerated LEV crossover. Scenario assumptions, not forecasts.")

    status_quo_death = BIRTH_DATE + timedelta(days=int(LIFE_EXPECTANCY_YEARS * 365.25))

    l1, l2, l3 = st.columns(3)
    with l1:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Crossover Point</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Personal LEV Arrival</div>
            {clock_html(LEV_ARRIVAL, NOW)}
            <div style="color:#38bdf8; font-size:0.8rem; font-weight:700;">Target: {LEV_ARRIVAL:%B %Y} (Age {age_at(LEV_ARRIVAL):.1f})</div>
            <div style="color:#64748b; font-size:0.75rem; margin-top:0.25rem;">Compressed by 15 months via lab capex wave.</div>
        </div>
        """)
    with l2:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Actuarial Senescence</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Status-Quo Mortality</div>
            {clock_html(status_quo_death, NOW)}
            <div style="color:#94a3b8; font-size:0.8rem; font-weight:700;">Target: {status_quo_death:%b %Y} (Age {age_at(status_quo_death):.1f})</div>
            <div style="color:#64748b; font-size:0.75rem; margin-top:0.25rem;">Hungarian actuarial baseline without rejuvenation.</div>
        </div>
        """)
    with l3:
        render_html(f"""
        <div class="model-card">
            <div class="lab-tag">Post-LEV Trajectory</div>
            <div style="font-size:1.15rem; font-weight:800; color:#f8fafc; margin:0.35rem 0;">Extended Healthspan</div>
            {clock_html(EXTENDED_HORIZON, NOW)}
            <div style="color:#a855f7; font-size:0.8rem; font-weight:700;">Horizon: ~{EXTENDED_HORIZON.year}+ (Age 140+)</div>
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
    for ev in (e for e in market if e["entity"] == "Geopolitics" and e["options"]):
        st.markdown(f"**{ev['label']}**")
        st.dataframe(options_df(ev["options"], 8), hide_index=True)


# ---- Tab 6: Alan Thompson Milestones & Millennium Math
with tab_alan:
    st.subheader("Alan Thompson (LifeArchitect.ai) ASI Milestones")
    st.caption("Tracks the conservative 50-indicator trajectory toward artificial superintelligence.")

    df_alan = pd.DataFrame(ALAN, columns=["Milestone", "Category", "Status", "Date"])
    counts = df_alan["Status"].value_counts()

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Alan's AGI Gauge", *ALAN_AGI_GAUGE)
    a2.metric("Achieved", int(counts.get(A, 0)), "Green Badges")
    a3.metric("In Progress", int(counts.get(P, 0)), "Active Research")
    a4.metric("Pending", int(counts.get(N, 0)), "Frontier Indicators")

    with st.expander(f"Inspect All {len(df_alan)} ASI Indicators"):
        st.dataframe(df_alan, hide_index=True, height=400)

    st.divider()
    st.subheader("Millennium Prize Mathematics Credible Solution Dates")
    st.caption("Estimated single most likely calendar date that a verified proof is publicly published by any lab or researcher.")

    df_math = pd.DataFrame(MILLENNIUM_CONSENSUS).rename(columns={
        "problem": "Millennium Prize Problem",
        "solution_date": "Credible Solution Date",
        "prob": "Confidence (%)",
        "contender": "Leading Mechanism",
        "impact": "Disciplinary Impact",
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
    missing = [lbl for _, _, lbl in POLYMARKET_EVENTS if lbl not in by_label]
    if missing:
        st.warning("Failed to harvest: " + ", ".join(missing))
    for ev in market:
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

st.divider()
st.caption(
    f"Market cache: {MARKET_TTL // 60} min · Summary cache: {SUMMARY_TTL // 60} min · "
    f"Manual calibrations as of {MANUAL_AS_OF} · "
    f"Budapest time: {to_budapest(NOW).strftime('%Y-%m-%d %H:%M %Z')}"
)
if st.button("Force Synchronized Market Recalculation"):
    st.cache_data.clear()
    st.rerun()

# ---- Executive brief (rendered last, into the slot reserved in the Probability Waves tab)
if labeled:
    with brief_slot:
        with st.spinner("Generating executive brief..."):
            summary, engine = load_summary(build_summary_payload(labeled), NOW.strftime("%d %B %Y"))
        st.markdown("**Executive Market Intelligence**" + (f" · {engine}" if summary else ""))
        st.write(summary or f"Unavailable ({engine}).")
