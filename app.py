"""
Frontier Board | Release Clocks, Market Odds, FIRE Calculator

Requirements: streamlit>=1.37, requests, pandas, plotly, google-genai (optional)
Secrets: GEMINI_API_KEY (optional, only used for the short market summary)

Design rules:
- Live data (Polymarket) drives what it can. Manual constants are labelled "manual".
- Nothing is invented by an LLM. Gemini only summarises the fetched order books.
"""
import html
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

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

st.set_page_config(page_title="Frontier Board", page_icon="⏱️", layout="wide",
                   initial_sidebar_state="collapsed")


def render_html(s):
    st.markdown("\n".join(line.strip() for line in s.strip().splitlines()), unsafe_allow_html=True)


render_html("""
<style>
.hero-container{background:radial-gradient(circle at top right,#1e1b4b 0%,#0f172a 60%,#020617 100%);
border:1px solid #3b82f6;border-radius:1rem;padding:1.5rem;margin-bottom:1.5rem}
.hero-label{font-size:.72rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#60a5fa}
.hero-title{font-size:1.85rem;font-weight:800;color:#f8fafc;margin:.25rem 0 .5rem}
.clock-row{display:flex;gap:.65rem;flex-wrap:wrap;margin:.85rem 0}
.digital-block{background:#070b12;border:1px solid #1e293b;border-radius:.5rem;padding:.65rem .9rem;text-align:center}
.digital-val{font-family:'JetBrains Mono','Courier New',monospace;font-weight:800;color:#f8fafc;line-height:1}
.digital-sub{font-size:.62rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8;margin-top:.35rem}
.model-card{background:#0b1120;border:1px solid #1e293b;border-radius:.75rem;padding:1.15rem;margin-bottom:.85rem}
.badge{font-size:.65rem;font-weight:800;letter-spacing:.08em;padding:2px 7px;border-radius:4px;text-transform:uppercase}
.badge-confirmed{background:#064e3b;color:#34d399;border:1px solid #059669}
.badge-likely{background:#0c4a6e;color:#38bdf8;border:1px solid #0284c7}
.badge-speculative{background:#451a03;color:#fbbf24;border:1px solid #d97706}
.badge-horizon{background:#3b0764;color:#c084fc;border:1px solid #9333ea}
.badge-market{background:#134e4a;color:#5eead4;border:1px solid #0d9488}
.badge-manual{background:#1e293b;color:#94a3b8;border:1px solid #475569}
.lab-tag{font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#94a3b8;text-transform:uppercase}
</style>
""")

# ---------------------------------------------------------------- data

CANDIDATES = [("gemini-3.8-flash", 45.0), ("gemini-3.6-flash", 20.0), ("gemini-3.5-flash-lite", 12.0)]


def M(name, lab, code, dt, status, notes, poly=None):
    return {"name": name, "lab": lab, "code": code, "poly": poly, "status": status,
            "notes": notes, "source": "manual",
            "target": datetime(*dt, 16, 0, tzinfo=timezone.utc)}


# Manual fallback dates. Where "poly" matches a cumulative market, the market median replaces them.
MODELS = [
    M("Claude Sonnet 5.5", "Anthropic", "ANTH", (2026, 9, 29), "CONFIRMED",
      "51% by Sep 28, 84% by Sep 29 ($51K vol). Announced as coming within weeks.", "Next Claude Sonnet"),
    M("Claude Haiku 5.5", "Anthropic", "ANTH", (2026, 10, 8), "CONFIRMED",
      "78% by Oct 15, 95% by Oct 31. No earlier price point, so the median is extrapolated.", "Next Claude Haiku"),
    M("Gemini Flash 3.9+", "Google DeepMind", "GOOG", (2026, 10, 20), "LIKELY",
      "51% by Oct 15 and 54% by Oct 31 on thin volume, 94% by Nov 30.", "Gemini Flash 3.9+"),
    M("Gemini 4 / Pro Flagship", "Google DeepMind", "GOOG", (2026, 10, 28), "CONFIRMED",
      "Weekly market ($86K), normalised: ~35% by Oct 18, ~46% by Oct 25, ~59% by Nov 1. Google says Gemini 4 is in post-training."),
    M("Gemini Flash-Lite next", "Google DeepMind", "GOOG", (2026, 10, 30), "LIKELY",
      "50% by Oct 31 on $56 of volume, 80% by Nov 30. Very thin.", "Gemini Flash-Lite 3.6+"),
    M("Claude Fable 5.2", "Anthropic", "ANTH", (2026, 10, 28), "LIKELY",
      "55% by Oct 31, 92% by Dec 31 ($31K).", "Next Fable 5.2+"),
    M("Grok 4.8", "SpaceXAI", "SXAI", (2026, 11, 4), "LIKELY",
      "45% by Oct 31, 82% by Nov 30 on $1K. Pretraining reportedly finished mid-Sep.", "Grok 4.8+"),
    M("GPT-Astra 6.1", "OpenAI", "OAI", (2026, 10, 27), "LIKELY",
      "17% by Oct 9, 61% by Oct 31 ($8K), 94% by Dec 31.", "GPT-Astra 6.1"),
    M("Next Claude Opus", "Anthropic", "ANTH", (2026, 11, 20), "LIKELY",
      "69% by Nov 30, 88% by Dec 31 on $2.6K. Opus 5 to 5.5 took about 60 days, which points to late Nov.", "Next Claude Opus"),
    M("GPT-Luna 6.1", "OpenAI", "OAI", (2026, 12, 2), "SPECULATIVE",
      "48% by Nov 30, 80% by Dec 31 on $1K.", "GPT-Luna 6.1"),
    M("GPT-Sol 6.1", "OpenAI", "OAI", (2026, 12, 5), "SPECULATIVE",
      "Only $80 traded, so this follows Luna. Sol 6 shipped Sep 22."),
    M("GPT-Terra 5.7", "OpenAI", "OAI", (2026, 12, 10), "SPECULATIVE",
      "About 43% by Nov 30 (Sep 24 quote). A GPT-6 Terra would also qualify."),
    M("Claude 6", "Anthropic", "ANTH", (2027, 6, 2), "HORIZON",
      "35% by Mar 31, 56% by Jun 30, 87% by Dec 31, 2027 (Sep 7 snapshot).", "Claude 6"),
    M("GPT-7", "OpenAI", "OAI", (2027, 8, 28), "HORIZON",
      "34% by Jun 30, 2027 and 84% by Dec 31, 2027.", "GPT-7"),
]

POLYMARKET_EVENTS = [
    ("when-will-the-next-google-gemini-pro-model-be-released-20260817144359068", "Google", "Gemini Pro"),
    ("next-google-gemini-pro-model-released-byptptpt", "Google", "Gemini Pro Cumulative"),
    ("gemini-4pt0-released-by-june-30-2026", "Google", "Gemini 4.0 Flash"),
    ("next-gemini-flash-model-3pt9-released-byptptpt", "Google", "Gemini Flash 3.9+"),
    ("next-openai-gpt-terra-5pt7-released-byptptpt", "OpenAI", "GPT-Terra 5.7"),
    ("gpt-astra-6pt1-released-byptptpt", "OpenAI", "GPT-Astra 6.1"),
    ("next-gpt-sol-6pt1-released-byptptpt", "OpenAI", "GPT-Sol 6.1"),
    ("gpt-7-released-byptptpt", "OpenAI", "GPT-7"),
    ("next-claude-sonnet-released-byptptpt-20260701203831153", "Anthropic", "Next Claude Sonnet"),
    ("next-claude-haiku-released-byptptpt-20260701205353326", "Anthropic", "Next Claude Haiku"),
    ("next-claude-opus-released-byptptpt-20260923144500000", "Anthropic", "Next Claude Opus"),
    ("claude-6-released-byptptpt", "Anthropic", "Claude 6"),
    ("next-fable-model-5pt2-released-byptptpt", "Anthropic", "Next Fable 5.2+"),
    ("next-google-gemini-flash-lite-model-3pt6-released-byptptpt", "Google", "Gemini Flash-Lite 3.6+"),
    ("next-gpt-luna-6pt1-released-byptptpt", "OpenAI", "GPT-Luna 6.1"),
    ("next-grok-model-4pt8-released-by", "SpaceXAI", "Grok 4.8+"),
    ("next-french-presidential-election", "Geopolitics", "French Presidential Election"),
    ("balance-of-power-2026-midterms", "Geopolitics", "US Midterms Balance of Power"),
    ("will-cmi-declare-a-millennium-prize-problem-solved-by-20260723160122979", "Math", "CMI Millennium Prize Declaration"),
    ("ai-lab-announces-another-millennium-prize-solution-by", "Math", "AI Lab Announces Millennium Solution"),
    ("which-millennium-prize-problem-will-ai-solve-next", "Math", "Which Millennium Problem Next"),
]

# Manual milestones. Update by hand and keep the as-of date honest.
MANUAL_AS_OF = "2026-09-28"
MILESTONES = [
    ("Weakly General AI (Metaculus #3479)", datetime(2027, 2, 1, tzinfo=timezone.utc)),
    ("Full AGI (Metaculus #5121)", datetime(2028, 5, 1, tzinfo=timezone.utc)),
    ("ASI benchmark (manual estimate)", datetime(2030, 10, 1, tzinfo=timezone.utc)),
]

# (name, category, status, date). Manual list, not live.
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

# ---------------------------------------------------------------- helpers


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
    return secs // 86400, secs % 86400 // 3600, secs % 3600 // 60, secs % 60


def clock_html(target, large=False):
    d, h, m, s = countdown_parts(target)
    fs, mw = ("2.35rem", "74px") if large else ("1.85rem", "58px")
    blocks = "".join(
        f'<div class="digital-block" style="min-width:{mw}"><div class="digital-val" '
        f'style="font-size:{fs}">{v}</div><div class="digital-sub">{u}</div></div>'
        for v, u in ((d, "Days"), (f"{h:02d}", "Hours"), (f"{m:02d}", "Min"), (f"{s:02d}", "Sec")))
    return f'<div class="clock-row">{blocks}</div>'


def badges(model):
    return (f'<span class="badge badge-{model["status"].lower()}">{model["status"]}</span> '
            f'<span class="badge badge-{model["source"]}">{model["source"]}</span>')


def get_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY")


def fetch_event(item):
    slug, entity, label = item
    try:
        res = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=4)
        data = res.json() if res.status_code == 200 else None
        if not data:
            return None
        options = []
        for m in data[0].get("markets", []):
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


@st.cache_data(ttl=600, show_spinner="Syncing order books...")
def load_market():
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch_event, POLYMARKET_EVENTS))
    return [r for r in results if r]


def implied_median(options):
    """First date where a cumulative 'released by X' market crosses 50%. None if it cannot be trusted."""
    now, pts = now_utc(), []
    for o in options:
        txt = o["option"].lower().replace("by ", "").replace(",", "").strip()
        for fmt in ("%B %d %Y", "%b %d %Y", "%B %d", "%b %d"):
            try:
                d = datetime.strptime(txt, fmt)
            except ValueError:
                continue
            if "%Y" not in fmt:
                d = d.replace(year=now.year)
                if d.replace(tzinfo=timezone.utc) < now - timedelta(days=180):
                    d = d.replace(year=now.year + 1)
            pts.append((d.replace(hour=16, tzinfo=timezone.utc), o["implied_prob"]))
            break
    if len(pts) < 3:
        return None
    pts.sort()
    probs = [p for _, p in pts]
    if any(b < a - 0.03 for a, b in zip(probs, probs[1:])):
        return None  # not monotonic, so not a cumulative market
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if p0 < 0.5 <= p1:
            return d0 + (d1 - d0) * ((0.5 - p0) / (p1 - p0))  # interpolate the 50% crossing
    return None  # no bracketing points, keep the manual estimate


def resolve_models(market):
    by_label = {e["label"]: e for e in market}
    out = []
    for m in MODELS:
        m = dict(m)
        ev = by_label.get(m["poly"]) if m["poly"] else None
        d = implied_median(ev["options"]) if ev else None
        if d and d > now_utc():
            m["target"], m["source"] = d, "market"
        out.append(m)
    return out


def options_df(options, top=None):
    df = pd.DataFrame(options).rename(columns={"option": "Option", "implied_prob": "Implied %",
                                               "volume": "Volume (USD)"})[["Option", "Implied %", "Volume (USD)"]]
    df["Implied %"] = (df["Implied %"] * 100).round(1)
    df = df.sort_values("Implied %", ascending=False)
    return df.head(top) if top else df


@st.cache_data(ttl=3600, show_spinner=False)
def load_summary(payload):
    key = get_api_key()
    if not key or genai is None:
        return None, "Gemini not configured"
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=50000))
    prompt = ("Today is 28 September 2026. Below are live prediction-market order books. "
              "Write at most 5 plain sentences on what they imply for the next 90 days of AI model releases. "
              "Use only the numbers given, flag thin volume, invent nothing, no hype.\n" + payload)
    cfg = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="medium"))
    for name, timeout in CANDIDATES:
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            resp = ex.submit(lambda n=name: client.models.generate_content(
                model=n, contents=prompt, config=cfg)).result(timeout=timeout)
            if resp and resp.text:
                return resp.text.strip(), name
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)
    return None, "All Gemini models failed or timed out"


# ---------------------------------------------------------------- app

market = load_market()
models = resolve_models(market)

st.title("⏱️ Frontier Board")
st.caption("Release clocks driven by prediction markets where possible. Tags: market = live median, "
           "manual = my hand-interpolated estimate from the order books read on 2026-09-28. Estimates, not vendor commitments.")

upcoming = sorted((m for m in models if m["target"] > now_utc()), key=lambda m: m["target"])
h1, h2, h3, h4 = st.columns(4)
h1.metric("Next release", upcoming[0]["name"] if upcoming else "None", f"{countdown_parts(upcoming[0]['target'])[0]} days" if upcoming else None, delta_color="off")
h2.metric("Clocks tracked", len(models))
h3.metric("Market feeds live", f"{len(market)}/{len(POLYMARKET_EVENTS)}")
h4.metric("Market-driven clocks", sum(m["source"] == "market" for m in models))

tab_board, tab_curves, tab_personal, tab_geo, tab_alan, tab_audit = st.tabs([
    "⏱️ Release Clocks", "📈 Market Curves", "💰 FIRE Calculator",
    "🏛️ Geopolitics", "🧠 Milestones & Math", "🔍 Order Book Audit"])

# ---- Tab 1: clocks (ticks every second, filters live outside the fragment)
with tab_board:
    f1, f2 = st.columns([3, 2])
    f1.radio("Lab", ["All", "Anthropic", "Google DeepMind", "OpenAI", "SpaceXAI"],
             horizontal=True, label_visibility="collapsed", key="lab_filter")
    f2.toggle("Near-term only (confirmed and likely)", key="near_only")


    @st.fragment(run_every="1s")
    def render_board():
        pool = sorted((m for m in models if m["target"] > now_utc()), key=lambda m: m["target"])
        released = [m["name"] for m in models if m["target"] <= now_utc()]
        if not pool:
            st.info("All tracked clocks have passed their target dates.")
            return
        nxt = pool[0]
        render_html(f"""
        <div class="hero-container">
        <div class="hero-label">NEXT ON THE BOARD · {len(pool)} CLOCKS RUNNING</div>
        <div class="lab-tag">{nxt['code']} {html.escape(nxt['lab'])} &nbsp; {badges(nxt)}</div>
        <div class="hero-title">{html.escape(nxt['name'])}</div>
        {clock_html(nxt['target'], large=True)}
        <div style="color:#cbd5e1;font-weight:700">Target: {nxt['target'].strftime('%d %b %Y %H:%M UTC')}</div>
        <div style="color:#94a3b8;font-size:.85rem;margin-top:.35rem">{html.escape(nxt['notes'])}</div>
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
                <div style="display:flex;justify-content:space-between;align-items:center">
                <span class="lab-tag">{m['code']} {html.escape(m['lab'])}</span><span>{badges(m)}</span></div>
                <div style="font-size:1.25rem;font-weight:800;color:#f8fafc;margin:.35rem 0">{html.escape(m['name'])}</div>
                {clock_html(m['target'])}
                <div style="color:#94a3b8;font-size:.85rem;font-weight:600">Target: {m['target'].strftime('%d %b %Y %H:%M UTC')}</div>
                <div style="color:#64748b;font-size:.8rem;margin-top:.35rem">{html.escape(m['notes'])}</div>
                </div>
                """)
        if released:
            st.caption("Past target date, check for release: " + ", ".join(released))


    render_board()

# ---- Tab 2: real market curves
with tab_curves:
    st.subheader("Live market distributions")
    st.caption("Straight from the order books. Bars are implied probabilities per option, in market order.")
    labeled = [e for e in market if e["entity"] in ("Google", "OpenAI", "Anthropic", "SpaceXAI") and e["options"]]
    if labeled:
        pick = st.selectbox("Market", [f"{e['entity']} · {e['label']}" for e in labeled])
        ev = labeled[[f"{e['entity']} · {e['label']}" for e in labeled].index(pick)]
        fig = go.Figure(go.Bar(x=[o["option"] for o in ev["options"]],
                               y=[round(o["implied_prob"] * 100, 1) for o in ev["options"]],
                               marker_color="#3b82f6"))
        fig.update_layout(template="plotly_dark", yaxis_title="Implied probability (%)",
                          xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True, rangemode="tozero"),
                          margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, config={"displayModeBar": False})
        st.caption(f"Total volume in this market: ${sum(o['volume'] for o in ev['options']):,.0f}")
    else:
        st.warning("No market feeds loaded. Try again in a minute.")

    payload = json.dumps([{"market": e["label"], "top": options_df(e["options"], 6).to_dict("records")}
                          for e in labeled], default=str)
    summary, engine = load_summary(payload)
    st.markdown("**Market summary**" + (f" · {engine}" if summary else ""))
    st.write(summary or f"Unavailable ({engine}).")

# ---- Tab 3: FIRE calculator
with tab_personal:
    st.subheader("FIRE calculator")
    st.caption("Your inputs, real (after-inflation) returns, so the target is in today's HUF. "
               "The defaults are placeholders, change them.")
    c1, c2, c3, c4 = st.columns(4)
    start = c1.number_input("Invested now (HUF)", 0, value=0, step=100_000)
    monthly = c2.number_input("Per month (HUF)", 0, value=50_000, step=5_000)
    ret = c3.slider("Real return, % per year", 0.0, 10.0, 5.0, 0.5)
    target = c4.number_input("Target (HUF)", 1_000_000, value=60_000_000, step=1_000_000)


    def months_to(rate):
        r, bal, n = (1 + rate / 100) ** (1 / 12) - 1, float(start), 0
        while bal < target and n < 960:
            bal, n = bal * (1 + r) + monthly, n + 1
        return n if bal >= target else None


    cols = st.columns(3)
    for col, rate in zip(cols, (max(ret - 2, 0), ret, ret + 2)):
        n = months_to(rate)
        col.metric(f"At {rate:.1f}% real", f"{n // 12}y {n % 12}m" if n is not None else "80y+")
    st.caption("The spread across return assumptions is the honest answer. Contribution rate moves the date "
               "far more than any forecast about markets.")

    st.divider()
    st.subheader("AGI milestones (manual estimates)")
    ms = st.columns(3)
    for col, (label, dt) in zip(ms, MILESTONES):
        col.metric(label, dt.strftime("%b %Y"), f"{max((dt - now_utc()).days // 30, 0)} months away", delta_color="off")
    st.caption(f"Hand-set values, as of {MANUAL_AS_OF}. Not live.")

# ---- Tab 4: geopolitics from market odds
with tab_geo:
    st.subheader("Election and midterm odds")
    st.caption("Live market probabilities only. No modelled personal-impact scores.")
    geo = [e for e in market if e["entity"] == "Geopolitics" and e["options"]]
    if not geo:
        st.info("No geopolitics feeds loaded.")
    for ev in geo:
        st.markdown(f"**{ev['label']}**")
        st.dataframe(options_df(ev["options"], 8), hide_index=True)

# ---- Tab 5: Alan list and Millennium markets
with tab_alan:
    st.subheader("Alan Thompson ASI indicators (manual list)")
    df_alan = pd.DataFrame(ALAN, columns=["Milestone", "Category", "Status", "Date"])
    counts = df_alan["Status"].value_counts()
    a1, a2, a3 = st.columns(3)
    a1.metric("Achieved", int(counts.get(A, 0)))
    a2.metric("In progress", int(counts.get(P, 0)))
    a3.metric("Pending", int(counts.get(N, 0)))
    with st.expander("Full list"):
        st.dataframe(df_alan, hide_index=True, height=400)
    st.caption(f"Hand-maintained, as of {MANUAL_AS_OF}. Verify against the source before relying on it.")

    st.divider()
    st.subheader("Millennium Prize markets")
    for ev in (e for e in market if e["entity"] == "Math" and e["options"]):
        st.markdown(f"**{ev['label']}**")
        st.dataframe(options_df(ev["options"], 8), hide_index=True)

# ---- Tab 6: audit
with tab_audit:
    st.subheader("Raw order books")
    missing = [lbl for _, _, lbl in POLYMARKET_EVENTS if lbl not in {e["label"] for e in market}]
    if missing:
        st.warning("Failed to load: " + ", ".join(missing))
    for ev in market:
        with st.expander(f"{ev['entity']} · {ev['label']} ({len(ev['options'])} options)"):
            st.caption(f"Slug: `{ev['slug']}`")
            if ev["options"]:
                st.table(pd.DataFrame(ev["options"]))

st.divider()
st.caption(f"Market cache 10 min · Summary cache 60 min · Last render {budapest_now().strftime('%Y-%m-%d %H:%M %Z')}")
if st.button("Force refresh"):
    st.cache_data.clear()
    st.rerun()
