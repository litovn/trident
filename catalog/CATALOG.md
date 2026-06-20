# TRIDENT — Attack Catalog (textual view)

Catalog version **v0.3** · target-agnostic · 3 layers (Prompt / Application / Model).
Taxonomies: **OWASP GenAI/LLM Top 10 (2025)** × **MITRE ATLAS** (matrix v6 / 2026.05).
Machine source: `catalog/skills_catalog/<ID>/SKILL.md` (YAML frontmatter, one per technique). Packages: `catalog/packages.yaml`.
Principle: agents **select** from the catalog, they never invent. Recon vs Attack = a filter on the `phase` field.

---

## 1. Coverage map — OWASP

| OWASP 2025 | Covered | Layer | Entries | Notes |
|---|---|---|---|---|
| **LLM01** Prompt Injection | ✅ | Prompt, App | PRM-002/003/004, APP-001/005 | direct, multi-turn jailbreak, obfuscated, indirect, memory poisoning |
| **LLM02** Sensitive Information Disclosure | ✅ | App, Model | APP-002/007, MOD-002/006 | app exfil, credential harvesting, model extraction + inversion |
| **LLM03** Supply Chain | ⛔ | — | — | **not targetable** in black-box (about dependencies/artifacts, not I/O) |
| **LLM04** Data & Model Poisoning | 🟡 | App | APP-001 | data poisoning via normal input (RAG) **yes**; weight poisoning **no** |
| **LLM05** Improper Output Handling | ✅ | App | APP-003 | XSS / unsanitized markup |
| **LLM06** Excessive Agency | ✅ | App | APP-004/006/008 | tool abuse, exfil-via-tool, tool poisoning (needs `has_tools`) |
| **LLM07** System Prompt Leakage | ✅ | Prompt | PRM-001, PRM-R01 | extraction + recon probing |
| **LLM08** Vector & Embedding Weaknesses | ✅ | App | APP-001 | via RAG poisoning / retrieval manipulation (`owasp_secondary`) |
| **LLM09** Misinformation | ✅ | Model | MOD-003 | false / ungrounded output (judged scorer) |
| **LLM10** Unbounded Consumption | ⛔ | — | — | **not targetable**: DoS outside the Rules of Engagement |

Legend: ✅ covered · 🟡 partial · ⛔ not targetable (declared, not hidden).
**Coverage metric** for the report = ✅ cells / targetable cells; LLM03 and LLM10 excluded with a stated reason.

## 2. Coverage map — ATLAS (techniques exercised)

| ATLAS tactic | Technique / ID | Entry |
|---|---|---|
| Discovery | AML.T0069 Discover LLM System Information | PRM-R01 |
| Discovery | AML.T0084 Discover AI Agent Configuration | APP-R01 |
| Discovery | AML.T0014 Discover AI Model Family | MOD-001 |
| Execution | AML.T0051.000 LLM Prompt Injection: Direct | PRM-002 |
| Execution | AML.T0053 AI Agent Tool Invocation | APP-004 |
| Privilege Escalation | AML.T0054 LLM Jailbreak | PRM-003 |
| Defense Evasion | AML.T0068 LLM Prompt Obfuscation | PRM-004 |
| Defense Evasion | AML.T0067 LLM Trusted Output Manipulation | APP-003 |
| Persistence | AML.T0070 RAG Poisoning (+ T0051.001 Indirect) | APP-001 |
| Persistence | AML.T0080 AI Agent Context Poisoning (Memory) | APP-005 |
| Persistence | AML.T0110 AI Agent Tool Poisoning | APP-008 |
| Credential Access | AML.T0082 RAG Credential Harvesting (+ T0083) | APP-007 |
| Exfiltration | AML.T0056 Extract LLM System Prompt | PRM-001 |
| Exfiltration | AML.T0057 LLM Data Leakage | APP-002, MOD-002 |
| Exfiltration | AML.T0086 Exfiltration via AI Agent Tool Invocation | APP-006 |
| Exfiltration | AML.T0024.002 Extract AI Model | MOD-005 *(post-MVP)* |
| Exfiltration | AML.T0024.001 Invert AI Model | MOD-006 *(post-MVP)* |
| Exfiltration | AML.T0024.000 Infer Training Data Membership | MOD-004 *(post-MVP)* |
| Impact | External Harms (no exact ATLAS technique for misinformation) | MOD-003 |

---

## 3. Technique cards

### Layer PROMPT
**TRD-PRM-001 · System prompt extraction** — *exploit* · lead exploit. Forces the bot to reveal hidden system instructions. OWASP LLM07 · ATLAS Exfiltration (T0056). Scorer: `leak_detector` (deterministic). Severity **High**.
**TRD-PRM-002 · Direct prompt injection** — *exploit*. Overrides intended behavior. OWASP LLM01 · ATLAS Execution (T0051.000). Scorer: `refusal_judge`. Severity **High**.
**TRD-PRM-003 · Multi-turn jailbreak** — *exploit* · `multi_turn`. Crescendo/TAP/Skeleton Key. OWASP LLM01 · ATLAS Privilege Escalation (T0054). Scorer: `refusal_judge`. Severity **High**.
**TRD-PRM-004 · Obfuscated injection** — *exploit*. Evades keyword filters. OWASP LLM01 · ATLAS Defense Evasion (T0068). Scorer: `refusal_judge`. Severity **Medium**.
**TRD-PRM-R01 · Guardrail probing** — *recon* · lead recon. Probes defenses, hints at system prompt. ATLAS Discovery (T0069). Scorer: `judged_objective`. Severity **Info**.

### Layer APPLICATION
**TRD-APP-001 · Indirect injection (RAG poisoning)** — *exploit* · lead exploit. Plants an instruction in an ingested doc. OWASP LLM01/LLM08 · ATLAS Persistence (T0070 + T0051.001). Scorer: `exfil_canary`. Severity **Critical**.
**TRD-APP-002 · Sensitive information disclosure** — *exploit*. Extracts PII/secrets/other records. OWASP LLM02 · ATLAS Exfiltration (T0057). Scorer: `exfil_canary`. Severity **High**.
**TRD-APP-003 · Improper output handling (XSS)** — *exploit*. Unsanitized executable markup. OWASP LLM05 · ATLAS Defense Evasion (T0067). Scorer: `output_markup` (deterministic). Severity **High**.
**TRD-APP-004 · Excessive agency / tool abuse** — *exploit* · `has_tools`. Invokes tools beyond mandate. OWASP LLM06 · ATLAS Execution (T0053). Scorer: `judged_objective`. Severity **High**.
**TRD-APP-005 · Agent memory/context poisoning** — *exploit* · `multi_turn`, `is_agentic`. Persists an instruction in agent memory. OWASP LLM01 · ATLAS Persistence (T0080). Scorer: `exfil_canary`. Severity **High**.
**TRD-APP-006 · Exfiltration via tool** — *exploit* · `has_tools`. Exfiltrates through a tool call. OWASP LLM06 · ATLAS Exfiltration (T0086). Scorer: `exfil_canary`. Severity **Critical**.
**TRD-APP-007 · Credential harvesting (RAG/config)** — *exploit*. Extracts secrets from RAG/config. OWASP LLM02 · ATLAS Credential Access (T0082/T0083). Scorer: `exfil_canary`. Severity **Critical**.
**TRD-APP-008 · Tool poisoning** — *exploit* · `has_tools`, `is_agentic`. Corrupts a tool definition. OWASP LLM06 · ATLAS Persistence (T0110). Scorer: `judged_objective`. Severity **High**.
**TRD-APP-R01 · RAG/tool surface enumeration** — *recon* · lead recon. Maps sources/tools. ATLAS Discovery (T0084). Scorer: `judged_objective`. Severity **Info**.

### Layer MODEL
**TRD-MOD-001 · Model fingerprinting** — *recon* · lead recon. Identifies model family/version. ATLAS Discovery (T0014). Scorer: `categorical_match`. Severity **Info**.
**TRD-MOD-002 · Model data extraction** — *exploit* · lead exploit. Elicits memorized/training data. OWASP LLM02 · ATLAS Exfiltration (T0057). Scorer: `leak_detector`. Severity **High**.
**TRD-MOD-003 · Misinformation** — *exploit*. False/ungrounded claims. OWASP LLM09 · ATLAS Impact (External Harms). Scorer: `judged_objective`. Severity **Medium**.
**TRD-MOD-004 · Membership inference** — *exploit* · `cumulative` · **post-MVP**. ATLAS Exfiltration (T0024.000). Scorer: `cumulative_metric`. Severity **Medium**.
**TRD-MOD-005 · Model extraction / distillation** — *exploit* · `cumulative` · **post-MVP** · Model-layer pillar. Behavioral cloning. ATLAS Exfiltration (T0024.002). Scorer: `cumulative_metric`. Severity **High**.
**TRD-MOD-006 · Model inversion** — *exploit* · `cumulative` · **post-MVP**. Reconstructs training-input attributes. OWASP LLM02 · ATLAS Exfiltration (T0024.001). Scorer: `cumulative_metric`. Severity **High**.

---

## 4. Packages (`packages.yaml`)

**Profiles (one-click):** Quick scan · OWASP LLM sweep · ATLAS kill-chain · Full 360.
**Per-layer (single-layer option; rule {1 or all 3}):** Prompt only · Application only · Model only.
**Per-focus (intent-themed):** Guardrail bypass · Data exfiltration · RAG security · Agentic/tool abuse · Recon only.

Each package carries safe `limits` (max_intensity, query_budget) and the `modes` it runs in (recon / attack).

## 5. Targets (`targets/`)

The catalog is target-agnostic. Each target plugs in via a **target profile** (`targets/target_profile.example.yaml`) declaring its `capabilities` + surface→endpoint map + a `success_oracle` block. **Targetability is computed**: a technique runs only if the target's capabilities satisfy its `needs_capabilities`. AIGoat (`targets/aigoat.yaml`) is the PoC demo target only — because it lacks `has_tools`/`is_agentic`, the tool/agentic techniques (APP-004/005/006/008) are automatically skipped against it.

**Success determination** (`oracle.py`, contract in `oracle.md`): deterministic scorers (canary/leak/markup/fingerprint) are evaluated by the per-target **SuccessOracle** using the planted **canary** (honeytoken) — generated per campaign, planted by the adapter, resolved into objectives via `{planted_secret}`. The canary's `data_classification` feeds the MSRC severity. Judged scorers use PyRIT self-ask; cumulative are deferred.

## 6. Honesty notes (for the commission)
- ⛔ cells (LLM03, LLM10) stay on the map **declared as not targetable**, not hidden.
- `judged_*` scorers produce **assessed** verdicts (not ground-truth); `*_detector` / `*_canary` / `output_markup` / `categorical_match` produce **confirmed** verdicts (deterministic, with evidence in the trace). Scoring uses the **official PyRIT Scorer subsystem** — see `scorers.md` for the catalog-scorer → PyRIT-scorer mapping.
- ATLAS IDs **verified** against the official matrix (v6 / 2026.05). Misinformation (LLM09) has **no exact ATLAS technique** → mapped to Impact · External Harms.
- Cumulative techniques (MOD-004/005/006) are defined but their campaign-level scorer is **post-MVP**.
- Converter/strategy names are **verified** against the `azure-ai-evaluation` `AttackStrategy` enum (see `strategies.md` for the strategy → PyRIT converter-class mapping). `Baseline` = direct send. TAP/PAIR/Skeleton Key are PyRIT-direct orchestrators, not in the Azure enum.
- **Severity** follows the official **Microsoft MSRC AI bug bar** — see `severity.md`. Two tracks: security vulns (Critical/Important/Moderate/Low, driven by impact × ease × data classification) and content issues (In/Out of Scope, no rating). Note: per MSRC, **system-prompt extraction is not a standalone vuln** (enabler; severity flows to the leak/chain), and **misinformation is a content-track issue** (no security severity).
- **Validation is enforced**: every entry is checked against `schema/catalog.schema.json` at load time (`SkillRegistry.load_dir` → fail fast). Bad enums (converter/scorer/owasp/capability/severity), missing required fields, malformed IDs, and dangling package→technique refs are rejected before anything runs.
