<p align="center">
  <img src="assets/trident_logo_gray.png" alt="TRIDENT logo" width="450">
</p>

<p align="center">
  <img src="assets/microsoft_logo.png" alt="Microsoft logo" width="100">
</p>

# TRIDENT

> Project submission for the Microsoft Global Intern Hackathon 2026.

**Black-box, multi-agent AI red-teaming accelerator for generative-AI systems.**

TRIDENT turns a natural language goal — *"jailbreak the chatbot"*, *"prove it leaks data"*,
*"just map the attack surface"* — into a **governed, auditable, standards-mapped red-team
campaign**. It selects techniques from a curated catalog (20 techniques + 12 packages)(**OWASP LLM Top 10 (2025)** ×
**MITRE ATLAS** v6), dispatches them across three attack layers through fenced agents,
scores every result with deterministic oracles and LLM judges, and emits a self-contained
HTML report — **enriched with real-time web research so even non-expert users can understand
and act on it** — backed by an immutable trace.

It is built end-to-end on the Microsoft stack: the **GitHub Copilot SDK** for
agentic orchestration, **Microsoft Foundry** as the single model plane, **PyRIT** as the
attack-execution surface, **Azure AI Evaluation** naming for attack strategies, and the
**MSRC AI bug bar** for severity — closing the loop with remediation mapped to Microsoft
defenses (Content Safety, Foundry guardrails, Azure AI Gateway, Defender for AI).

<p align="center">
  <img src="assets/trident_pc.png" alt="TRIDENT logo" width="450">
</p>

---

## Table of contents

- [The problem](#the-problem)
- [The value of TRIDENT](#what-trident-is--the-value-proposition)
- [The innovation](#whats-new--the-innovation)
- [The Microsoft stack](#the-microsoft-stack-integrated)
- [How it works](#how-it-works--the-four-phase-pipeline)
- [The catalog: 3 layers, 20 techniques](#the-catalog-3-layers-20-techniques)
- [Attack packages](#attack-packages)
- [Scoring: confirmed vs assessed](#scoring-confirmed-vs-assessed)
- [The report](#the-report)
- [Design invariants](#design-invariants)
- [Install](#install)
- [Configure Microsoft Foundry](#configure-microsoft-foundry)
- [Run](#run)
- [Onboarding a target](#onboarding-a-target)
- [Project structure](#project-structure)
- [Roadmap](#roadmap)
- [License & responsible use](#license--responsible-use)

---

## The problem

Generative-AI applications ship with a new, poorly-understood attack surface — prompt
injection, jailbreaks, RAG poisoning, tool/agent abuse, data exfiltration, model
extraction. Yet red-teaming them today is **inconsistent by construction**:

- **Findings depend on tester creativity.** Two engineers probing the same app produce
  different results; coverage is uneven and nobody can say what was *not* tested.
- **Results aren't reproducible.** Ad-hoc prompts in a chat window leave no audit trail,
  so a "we tested it" claim can't be verified or re-run.
- **It's easy to stray outside the rules.** Without an enforced scope, an offensive test
  can hit the wrong host, exceed a budget, or run a technique that was meant to be off-limits.
- **Findings don't map to standards.** Raw transcripts don't translate into OWASP/ATLAS
  coverage, MSRC severities, or a remediation plan a defender can act on.
- **"Success" is fuzzy.** A model that *sounds* jailbroken may just be role-playing; a
  claimed leak may be a hallucination. Teams routinely over- or under-count.

The result: security teams either under-test (miss real risk) or over-test (burn time on
noisy, unrepeatable probes) — and either way struggle to *prove* what they did.

---

## What TRIDENT is — the value proposition

TRIDENT makes a GenAI red-team campaign **declarative, governed, and auditable**. You give
it a target profile, a one-line Rules-of-Engagement manifest, and a natural language goal; it
gives you a reproducible campaign and a report you can hand to an MSRC reviewer.

| Property | What it means | Why it matters |
|---|---|---|
| **Black-box** | Needs only an endpoint + a small YAML profile — no weights, no source. | Test any vendored or third-party GenAI app, exactly as an attacker would. |
| **Declarative** | A natural language prompt → a curated attack **package**; a manifest declares the constraints. | Anyone can launch a rigorous campaign; the *plan* is data, not tribal knowledge. |
| **Governed by code** | Every action passes a **policy gate** (mode, host allowlist, technique denylist, per-vertical budget, HITL) before touching the target. | The Rules of Engagement are *enforced*, not just documented. |
| **Standards-mapped** | Every technique is tagged to **OWASP LLM Top 10** and **MITRE ATLAS**; severity follows the **MSRC AI bug bar**. | Findings translate straight into compliance coverage and triage. |
| **Confirmed vs assessed** | Deterministic ground-truth (a planted honeytoken) is distinguished from LLM judgement. | You know exactly how much to trust each finding. |
| **Auditable** | One **immutable trace** records every prompt, response, verdict, and evidence. | Reproducible, defensible, re-runnable — the whole campaign, on the record. |

In one line: **TRIDENT is the difference between "we poked at it for a bit" and "here is a
signed, standards-mapped, reproducible red-team report with confirmed evidence and a
remediation plan."**

---

## What's new — the innovation

TRIDENT is not a prompt collection and not a single autonomous "hacker agent". Its design
contributions are specific and defensible:

**1. Natural language → a *governed* campaign.**
A conversational advisor turns a vague goal into a concrete, reviewed **attack package**,
asking clarifying questions only when the request is genuinely ambiguous. The chosen
package is then projected through a deterministic scope-and-gate seam — so the human intent
becomes an executable plan *without* letting a model invent techniques or exceed the rules.

**2. Agents *select*, they never invent.**
The catalog is the single source of truth. Every vertical agent may only fire techniques
that already exist in the reviewed catalog, by ID; the weaponized prompt text is resolved
*inside* the policy-gated tool, never authored by the agent. This bounds the blast radius
and keeps runs reproducible and reviewable.

**3. "Agentic surface over a deterministic floor."**
The Coordinator is a real LLM agent that reasons about which layers to attack and writes
the cross-layer narrative — but underneath it, a deterministic *floor* guarantees that
scoping happened and every in-scope layer actually ran, even if the model skipped a step.
You get agentic flexibility **and** demo-grade reproducibility from the same run.

**4. Confirmed ground truth via a canary honeytoken.**
Rather than trusting an LLM to say "yes, it leaked", TRIDENT plants a unique honeytoken per
campaign, injects it into objectives via a `{planted_secret}` placeholder, and only marks a
disclosure **confirmed** when that exact token reappears in the output — with the token's
data classification driving MSRC severity. LLM judgements are still available, but labeled
**assessed** so they're never confused with proof.

**5. Rules of Engagement as Code.**
The manifest declares *constraints* (mode, host allowlist, technique denylist, query
budgets, HITL gates) — not the plan. A single policy gate enforces all of them on every
action, so safety is a property of the engine, not of operator discipline.

**6. The catalog technique *is* an SDK skill.**
Each technique is one `SKILL.md` whose **YAML frontmatter is the machine config** and whose
**Markdown body is the agent-facing procedure** — the very same file the GitHub Copilot SDK
loads as a skill into the vertical agent. One artifact, validated against a JSON Schema at
load time, drives both the engine and the agent.

**7. Correlation, honestly scoped.**
TRIDENT *correlates* successful findings post-hoc into cross-layer ATLAS kill-chains and
computes honest coverage (planned vs tested vs excluded, with reasons) — while explicitly
**not** claiming to autonomously execute emergent exploits. Coverage gaps (e.g. OWASP LLM03
Supply Chain, LLM10 Unbounded Consumption) are declared as not black-box-targetable, never
hidden.

**8. Reports the whole team can read — enhanced by the web.**
A raw finding like *"TRD-APP-001 confirmed · LLM01 · ATLAS Persistence · Critical"* is
meaningful to a red-teamer and opaque to everyone else. TRIDENT **expands its own report
with real-time web research** (via the Foundry Agent Service `web_search` tool): every
surfaced Microsoft control and finding is turned into a plain-language, **source-cited**
explanation of what it is, why it matters, and how to fix it. The same report serves a
security engineer *and* a product owner, manager, or developer who has never heard of
ATLAS — without diluting the technical core underneath.

---

## The Microsoft stack, integrated

TRIDENT is a working demonstration of how Microsoft's AI-security building blocks compose
into a single, coherent tool. Each product owns exactly one concern:

```mermaid
flowchart TB
    subgraph ORCH["GitHub Copilot SDK — agentic orchestration"]
        CO["Coordinator session<br/>(agents-as-tools)"]
        PV["Prompt vertical<br/>(fenced session + skills)"]
        AV["Application vertical<br/>(fenced session + skills)"]
        MV["Model vertical<br/>(fenced session + skills)"]
        CO --> PV & AV & MV
    end

    subgraph EXEC["PyRIT — attack execution surface"]
        CONV["Converters<br/>(single-turn strategies)"]
        JUDGE["SelfAsk* scorers<br/>(judged)"]
        ORCHE["CrescendoAttack<br/>(multi-turn)"]
    end

    subgraph FOUNDRY["Microsoft Foundry — the single model plane"]
        MODEL["Chat deployment<br/>(Coordinator + advisor + judge reasoning)"]
        WEBS["Agent Service web_search<br/>(grounded remediation)"]
    end

    PV & AV & MV --> CONV & JUDGE & ORCHE
    CO -. reasoning .-> MODEL
    PV & AV & MV -. reasoning .-> MODEL
    JUDGE -. judge LLM .-> MODEL
    ORCHE -. adversarial LLM .-> MODEL
    CO -. grounding .-> WEBS

    STD["Standards & severity<br/>OWASP LLM Top 10 · MITRE ATLAS · MSRC AI bug bar<br/>Azure AI Evaluation AttackStrategy naming"]
    DEF["Remediation → Microsoft defenses<br/>Content Safety · Foundry guardrails · Azure AI Gateway · Defender for AI"]

    ORCH --> STD
    EXEC --> STD
    STD --> DEF
```

### GitHub Copilot SDK — agentic orchestration
The Copilot SDK provides the multi-agent runtime. `TridentClient` (`src/core/client.py`)
wraps `CopilotClient` and creates sessions bound to a Foundry deployment. The **Coordinator**
is a top-level session that exposes the three vertical dispatchers **as tools**
(`dispatch_prompt_agent` / `dispatch_app_agent` / `dispatch_model_agent`) plus `select_scope`
and `web_search` — the "agents-as-tools" pattern. Each in-scope layer spins up a **fenced
vertical session** that sees only that layer's skills. Crucially, the SDK's own **skills**
mechanism loads the catalog `SKILL.md` files directly (`skill_directories` + `enable_skills`),
so the reviewed technique cards *are* the agent's knowledge.

### Microsoft Foundry — the single model plane
**Every model call in TRIDENT routes through Microsoft Foundry** and bills to Foundry credit
— TRIDENT never consumes GitHub Copilot tokens. That includes the Coordinator's reasoning
and the vertical agents (Copilot SDK `provider: { type: "azure" }`), the conversational
advisor (`openai.AzureOpenAI` against the same account), the PyRIT judge target
(`OpenAIChatTarget`), and the adversarial LLM driving multi-turn Crescendo. Authentication
prefers `DefaultAzureCredential` (Managed Identity in production, `az login` locally) with a
Foundry API-key fallback for BYOK. Grounded remediation uses the **Foundry Agent Service
`web_search` tool** via the Responses API.

### PyRIT — the attack execution surface
[PyRIT](https://github.com/Azure/PyRIT) (Microsoft, MIT) is the execution engine. Skills
never call PyRIT directly — they funnel through `PyritRunner` (`src/skills/pyrit_runner.py`)
and three technique-agnostic SDK tools:

- `pyrit_send_prompt` — single-turn send with catalog-declared **converters** applied.
- `pyrit_run_scorer` — evaluate a response (deterministic **or** PyRIT `SelfAsk*` judged).
- `pyrit_run_orchestrator` — real multi-turn attacks via PyRIT `CrescendoAttack`.

### Azure AI Evaluation — canonical strategy naming
Every `converters` value in the catalog is a name from the **`azure-ai-evaluation`
`AttackStrategy` enum** (Base64, Flip, Leetspeak, ROT13, UnicodeConfusable, Tense,
IndirectAttack, Jailbreak, Crescendo, …), verified against the official *AI Red Teaming
Agent* docs and mapped 1:1 to the executing PyRIT converter class. TRIDENT speaks the same
attack-strategy vocabulary as Azure's own red-teaming agent.

### MSRC AI bug bar — severity you can triage
Severity follows the **Microsoft Vulnerability Severity Classification for AI/ML Systems**.
A finding's severity is computed from impact actually achieved × ease of exploitation × the
targeted data's classification — not from the technique alone — so the report speaks the
language an MSRC reviewer already uses. Content-track issues (e.g. misinformation) are
reported as In/Out-of-scope flags, never as inflated security severities.

### Closing the loop — remediation to Microsoft defenses
Each technique card declares the Microsoft controls that mitigate it (**Content Safety**,
**Foundry guardrails**, **Azure AI Gateway**, **Defender for AI**). The report's remediation
section aggregates the controls addressing the successful findings and — using the Foundry
Agent Service `web_search` tool — expands each into a plain-language, **source-cited**
description that a non-expert can follow. The output is not just "you're vulnerable" but
"here, in words anyone can act on, is the Microsoft control that fixes it — and here are the
sources." See [The report](#the-report) for the full enhancement layer.

---

## How it works — the four-phase pipeline

```
NL prompt ("prove it leaks the planted secret")
   │
   ▼  Phase 1 — Package advisor (conversational, Foundry-backed; or --package)
Chosen package (e.g. PKG-EXFIL)
   │
   ▼  Phase 2 — scope_to_scan (gating: capabilities, allow/denylist, mode, status)
ScanPlan(verticals = [1 or 3], skipped = [...])
   │
   ▼  Phase 3 — Coordinator (Copilot SDK, agents-as-tools)
    ├── dispatch_prompt_agent ─► fenced Prompt session ─►┐
    ├── dispatch_app_agent    ─► fenced App session    ─►├─► Scorecards
    └── dispatch_model_agent  ─► fenced Model session  ─►┘
                                       │  each skill handler:
                                       │  1. PolicyGate.check(action)
                                       │  2. PyritRunner.execute(technique, params, target)
                                       │  3. SuccessOracle / LLM judge → verdict
                                       │  4. Trace.append_*
   │
   ▼  Phase 4 — reports.correlator + reports.html_report
output/<campaign>.html  +  output/<campaign>.trace.jsonl
```

Four collaborating roles:

1. **NL→scope advisor** (`src/nl/`) — a conversational package selector grounded in the
   catalog; it proposes the top matching packages, or asks to clarify when the prompt is
   vague. Falls back to a deterministic default package when Foundry is absent.
2. **Coordinator** (`src/orchestrator/`) — the top-level Copilot SDK agent. It calls
   `select_scope` first, dispatches each in-scope vertical, optionally grounds findings with
   `web_search`, and writes one cross-layer summary. A deterministic floor guarantees the
   plan and every in-scope vertical actually ran.
3. **Vertical agents** (`src/agents/`) — Prompt / Application / Model specialists, each a
   fenced session that fires only its layer's techniques by ID.
4. **Runner + oracle + trace** (`src/skills/`, `src/targets/`, `src/core/`) — the
   deterministic spine: policy-gate → execute via PyRIT → score → record.

A campaign targets **one layer or all three — never exactly two** (ADR-021): a single focused
surface, or a full-stack sweep, but not an arbitrary pair.

---

## The catalog: 3 layers, 20 techniques

The catalog is the single source of truth. Each technique is one file —
`catalog/skills_catalog/<ID>/SKILL.md` — whose **YAML frontmatter is the machine config**
and whose **Markdown body is the agent-facing procedure**. The registry loads techniques
from these files and validates each against `catalog/schema/catalog.schema.json` at load
time (fail-fast: bad enums, missing fields, malformed IDs, and dangling package references
are all rejected before anything runs).

| Layer | Attacks | Techniques |
|---|---|---|
| **Prompt** (`TRD-PRM-*`) | the input / prompt surface | 5 — system-prompt extraction, direct injection, multi-turn jailbreak, obfuscated injection, guardrail recon |
| **Application** (`TRD-APP-*`) | RAG, tools, orchestration | 9 — indirect/RAG injection, info disclosure, output-handling (XSS), tool abuse, memory poisoning, exfil-via-tool, credential harvesting, tool poisoning, surface enumeration |
| **Model** (`TRD-MOD-*`) | the model via its API | 6 — fingerprinting, data extraction, misinformation, + membership inference / extraction / inversion (post-MVP) |

Coverage is honest: **LLM03** (Supply Chain) and **LLM10** (Unbounded Consumption) are
marked ⛔ not black-box targetable, with a stated reason. Full OWASP × ATLAS matrices and
per-technique cards live in [catalog/CATALOG.md](backend/catalog/CATALOG.md).

---

## Attack packages

A **package** bundles technique IDs with safe limits (`max_intensity`, `query_budget`) and
the modes it runs in. The advisor resolves a prompt to a package. 12 packages
([catalog/packages.yaml](backend/catalog/packages.yaml)):

- **Profiles (one-click):** `PKG-QUICK` · `PKG-OWASP` · `PKG-ATLAS` · `PKG-360`.
- **Per-layer:** `PKG-PROMPT` · `PKG-APP` · `PKG-MODEL`.
- **Per-focus:** `PKG-GUARDRAIL` (jailbreak) · `PKG-EXFIL` (exfiltration) · `PKG-RAG`
  (retrieval) · `PKG-AGENTIC` (tool abuse) · `PKG-RECON` (non-intrusive).

---

## Scoring: confirmed vs assessed

Every result carries a verdict *kind* so you know how much to trust it:

| Verdict | Meaning | Produced by |
|---|---|---|
| **`confirmed`** | deterministic ground truth, with evidence in the trace | `exfil_canary` / `leak_detector` (honeytoken), `output_markup` (regex), `categorical_match` (fingerprint) |
| **`assessed`** | an LLM judgement, not ground truth | `refusal_judge` / `judged_objective` (PyRIT `SelfAsk*`, offline heuristic fallback) |

Deterministic detectors are powered by a per-target **SuccessOracle**
(`src/targets/oracle.py`). The key mechanism is a **canary honeytoken**: generated per
campaign, planted via the adapter's `plant_surface`, and injected into objectives through
`{planted_secret}`. When the model emits that exact token, disclosure is *confirmed*, and
the canary's `data_classification` drives **MSRC AI bug-bar** severity. Judged scorers
evaluate a **benign `success_criterion`** (never the raw attack objective, which would trip
the judge model's own content filter) via the PyRIT `SelfAsk*` subsystem. See
[catalog/severity.md](backend/catalog/severity.md), [catalog/oracle.md](backend/catalog/oracle.md),
[catalog/scorers.md](backend/catalog/scorers.md), and [catalog/strategies.md](backend/catalog/strategies.md).

---

## The report

A TRIDENT report has **two layers**: a deterministic *core* built from the immutable trace,
and a **web-grounded enhancement layer** that expands that core into language anyone can act
on. This is what turns TRIDENT's output from an expert-only scorecard into a document a whole
team can read.

### 1. The deterministic core

Phase 4 joins the per-vertical scorecards from the trace into a single payload and renders a
self-contained HTML report (`src/reports/`):

- **Findings** — every successful technique, with layer, OWASP ID, ATLAS tactic, and MSRC
  severity badge.
- **Cross-layer attack chains** — successes spanning ≥2 layers, sequenced along the ATLAS
  kill-chain, with a blast-radius severity. Correlated **post-hoc** — TRIDENT identifies
  chains, it does not autonomously execute emergent exploits.
- **Coverage** — planned vs tested vs excluded-pre-scan (with reasons), and a coverage
  percentage.
- **Remediation** — the Microsoft controls that address each successful finding.

The core is fully offline and deterministic: the catalog is the source of truth for *which*
findings and controls appear, so nothing can be invented.

### 2. Enhanced by the web — reports non-experts can actually use

A raw finding like *"TRD-APP-001 confirmed · LLM01 · ATLAS Persistence · Critical"* tells a
red-teamer a lot and everyone else almost nothing. TRIDENT closes that gap by **expanding its
own report with real-time web research**, powered by the Foundry Agent Service `web_search`
tool:

- **Grounded remediation.** For every Microsoft control the campaign surfaces
  (`src/reports/remediation_enrich.py`), TRIDENT runs one focused, finding-aware web search
  and turns the grounded answer into a concise, plain-language description of *what the
  control is, why this finding needs it, and how to apply it* — each with **source-URL
  citations** so the guidance is verifiable, never hand-waved.
- **Grounded narrative.** While synthesizing the cross-layer summary, the Coordinator can
  call `web_search` to expand or contextualize specific findings with current public-web
  information (what a technique means, up-to-date guidance), again citing its sources.

The enhancement is **additive and safe by design**: Python owns the loop and the schema (the
catalog still decides *which* controls appear), the model only authors the human-readable
`description` text and returns its citations, and every existing field is preserved. When web
grounding is not configured the report gracefully falls back to the deterministic core — the
exact same shape, just without the expanded prose.

The result: **the same report serves a security engineer *and* a product owner, a manager, or
a developer who has never heard of MITRE ATLAS** — a terse, expert-only scorecard becomes an
explainable, cited, actionable document, without sacrificing the rigor of the core beneath it.

Every report is backed by `output/<campaign>.trace.jsonl` — the immutable, line-per-event
record of every gate decision, execution, and dispatch.

---

## Design invariants

Four rules keep the system auditable and target-agnostic:

1. **Skills never call PyRIT directly** — they go through `skills.pyrit_runner.PyritRunner`.
2. **Every action passes `core.policy_gate.PolicyGate.check`** inside the skill handler.
3. **Only the immutable `core.trace.Trace`** feeds the report — no shared blackboard.
4. **Target-agnostic core** — only `src/targets/*.py` may know endpoint specifics.

| Concept | Type | Notes |
|---|---|---|
| `mode` | `recon` / `attack` | Campaign-level (manifest). Gate-enforced (ADR-018). |
| `phase` | `recon` / `exploit` / `both` | Technique-level; recon mode keeps `phase ∈ {recon, both}`. |
| `severity_base` | `critical`…`info` | MSRC AI bug bar. |
| `scorer` | enum | Deterministic → SuccessOracle (`confirmed`); judged → PyRIT `SelfAsk*` (`assessed`). |
| Layer cardinality | `1` OR `3`, never `2` | ADR-021: one layer or all three. |

The policy gate enforces five rules on every action: **denylist** → **mode/phase + status**
→ **per-vertical budget** → **host allowlist** (hostname comparison, not substring) →
**HITL**.

---

## Install

> **Python 3.11+** required. All commands run from inside `backend/`.

```powershell
cd backend
pip install -e ".[sdk,ranker,real,dev]"   # full install; extras compose as needed
```

| Extra | Pulls in | Needed for |
|---|---|---|
| `sdk` | `github-copilot-sdk`, `azure-identity` | agentic Coordinator + vertical sessions |
| `ranker` | `openai`, `azure-identity` | the Phase-1 NL→scope advisor |
| `real` | `pyrit` | PyRIT execution surface (converters, judged scorers, orchestrators) |
| `bridge` | `fastapi`, `uvicorn` | the optional `server.py` frontend bridge |
| `dev` | `pytest`, `build` | tests + packaging |

The **base install** (no extras) runs the deterministic core and the offline web engine.
`requirements.txt` is a pinned lockfile of a known-good environment.

---

## Configure Microsoft Foundry

Both the Coordinator and the advisor route **every model call through Microsoft Foundry**
(billed to Foundry credit, never Copilot tokens). `FOUNDRY_ENDPOINT` enables the full
agentic path; without it the advisor falls back to a deterministic package and the judge to
an offline heuristic — a run still works.

```powershell
$env:FOUNDRY_ENDPOINT         = "https://<account>.cognitiveservices.azure.com/"
$env:FOUNDRY_MODEL_DEPLOYMENT = "gpt-4o-mini"

az login   # DefaultAzureCredential (preferred); or set $env:FOUNDRY_API_KEY for BYOK
```

Copy `.env.example` to `.env` for the complete variable list. `TridentClient`
(`src/core/client.py`) and the advisor read `FoundrySettings` (`src/core/config.py`) from
the environment — no code change needed. Grounded remediation additionally uses
`FOUNDRY_PROJECT_ENDPOINT` (the Foundry Agent Service Responses API); it degrades to a no-op
when unset.

---

## Run

> All commands run from inside `backend/`.

### Web UI

`frontend/frontend.html` is a single-file console (planner, live terminal, report viewer)
served by a stdlib web bridge (`src/web/`) — zero extra deps beyond the base install. It
runs the in-process **Echo** target out of the box, so you can exercise the full
plan → dispatch → score → report flow with no external target and no Foundry.

```powershell
run_web.cmd                 # http://localhost:8765
run_web.cmd --port 9000     # for custom port
```

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | capability probe (catalog counts, foundry/pyrit/sdk flags) |
| `GET  /api/packages`, `/api/techniques` | catalog data for the UI |
| `POST /api/plan` | one advisor turn — propose packages or clarify |
| `POST /api/campaign` | run a recon/attack campaign; returns trace + report |
| `GET  /api/logstream` | Server-Sent Events: live engine logs |

### CLI

Point it at a manifest (Rules of Engagement) and a prompt; the advisor (or `--package`)
selects the scope.

```powershell
python -m src.cli `
  --manifest manifests/aigoat.yaml `
  --catalog  catalog --targets-dir targets --out output `
  --prompt   "direct prompt injection: override the bot and exfiltrate the secret"

# Skip the advisor and pin a package:
python -m src.cli --manifest manifests/aigoat.yaml --package PKG-GUARDRAIL `
  --prompt "bypass the guardrails"
```

Useful flags (`python -m src.cli --help`): `--package <ID>`, `--confirm-chain`
(human-in-the-loop per layer), `--targets-dir`, `--catalog`, `--out`. A run writes
`output/<campaign>.html` and `output/<campaign>.trace.jsonl`.

A manifest is small and declarative — `manifests/aigoat.yaml`:

```yaml
campaign_id: aigoat
mode: attack                 # recon | attack — gate-enforced (ADR-018)
target_profile_id: aigoat    # resolves targets/aigoat.yaml by its `id`
technique_denylist: []
host_allowlist: [127.0.0.1]  # attack traffic stays here
query_budget_per_vertical: 5
hitl_techniques: []
```

> **Echo** is in-process and needs nothing — the fastest end-to-end smoke. **AIGoat**
> needs the target running locally and `AIGOAT_PASSWORD` (see `.env.example`).

---

## Onboarding a target

The core is **target-agnostic** — only `src/targets/*.py` may know endpoint specifics. A
target plugs in via a YAML **profile** plus a `success_oracle` block; **targetability is
computed** (a technique runs only if the target's `capabilities` satisfy its
`needs_capabilities`).

```yaml
id: my-target
name: "My GenAI app"
base_url: "https://my-target.invalid"
capabilities: [has_chat]            # drives targetability
surfaces:
  chat: { method: POST, path: /api/chat }
auth: { type: none }                # none | bearer | apikey | cookie
success_oracle:
  canary:                           # → exfil_canary / leak_detector
    prefix: TRIDENT
    plant_surface: chat             # chat | retrieval_ingest | search | tool
    data_classification: Confidential
  expected_model_set: [GPT, Llama, Mistral, Phi]   # → categorical_match
```

| Detector | Verdict | Needs in profile |
|---|---|---|
| `exfil_canary` / `leak_detector` | `confirmed` | `success_oracle.canary` + adapter that plants it |
| `output_markup` | `confirmed` | nothing — generic regex |
| `categorical_match` | `confirmed` | `success_oracle.expected_model_set` |
| `refusal_judge` / `judged_objective` | `assessed` | nothing — LLM judge, offline fallback |

Two adapters ship today: **`echo`** (in-process) and **`aigoat`** (HTTP, the reference
vulnerable target). Because AIGoat lacks `has_tools`/`is_agentic`, the tool/agentic
techniques (APP-004/005/006/008) are automatically skipped against it — targetability in
action. A new `id` needs a small adapter implementing `send()` (and `plant()` for a canary).
See [targets/target_profile.example.yaml](backend/targets/target_profile.example.yaml) and
[targets/aigoat.yaml](backend/targets/aigoat.yaml).

---

## Project structure

```
backend/                  # all Python: engine, API, catalog, profiles
├── src/
│   ├── core/             # client (Foundry), models, policy_gate, trace, config
│   ├── nl/               # advisor + scope_to_scan
│   ├── skills/           # base, registry, pyrit_runner, judge, pyrit_tools, web_search
│   ├── agents/           # vertical-session factory + briefs/personas
│   ├── orchestrator/     # coordinator, dispatch (agents-as-tools), scope_tool
│   ├── targets/          # adapter Protocol, oracle, echo, aigoat
│   ├── reports/          # correlator, html_report, json_report, remediation_enrich
│   ├── web/              # stdlib HTTP server + engine + SSE logbus
│   └── cli.py            # python -m src.cli
├── catalog/              # 20 techniques + 12 packages + JSON Schema + design docs
├── targets/              # declarative target profiles
├── manifests/            # Rules of Engagement as Code
├── run_web.cmd · requirements.txt · pyproject.toml · .env.example

frontend/frontend.html    # single-file TRIDENT console
server.py                 # optional FastAPI bridge (frontend/index.html ↔ campaign)
output/                   # generated reports (.html) + traces (.trace.jsonl)
```

---

## Roadmap

- Automatic technique synthesis — tooling that drafts new `SKILL.md` techniques.
- Re-wire the `pytest` suite (policy gate, advisor, end-to-end dispatch).
- Real PyRIT `SelfAsk*` as the default judge everywhere (replacing the offline heuristic).
- Cumulative-scope model techniques (`TRD-MOD-004/005/006`) with a campaign-level scorer.
- Foundry hosted deployment (`azd up` with Key Vault + Managed Identity).
- Richer HTML report — attack-chain visualization and an ATLAS heatmap.

---

## License & responsible use

MIT © Nikita Litovchenko, Luca Medea, Lorenzo Albani, Riccardo Ponte, Changchen Yu, Alp Bayrak. See [pyproject.toml](backend/pyproject.toml).

> **Use responsibly.** TRIDENT is an offensive-security tool. Only run it against systems
> you own or are explicitly authorized to test, and keep every campaign inside the
> `host_allowlist` and Rules of Engagement declared in its manifest.
