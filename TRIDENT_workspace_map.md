# TRIDENT — Mappa concettuale del workspace

## In due righe — cos'è TRIDENT

Un acceleratore di **AI red-teaming black-box, multi-agente**, costruito su GitHub Copilot SDK + (futura) PyRIT. Prende un **prompt in linguaggio naturale**, lo trasforma in un **piano di scan** su 3 layer (Prompt / Application / Model), dispatcha **agenti verticali** che eseguono solo skill autorizzate dalla `PolicyGate`, e produce un **report HTML + trace JSONL**.

I 4 invarianti che governano tutto il design (vedi [README.md](README.md)):

1. Le skill non chiamano mai PyRIT direttamente → solo via `PyritRunner`.
2. Ogni azione passa per `PolicyGate.check`.
3. Solo la `Trace` immutabile alimenta il report (no blackboard condivisa).
4. Core target-agnostic: solo `src/targets/*.py` conosce gli endpoint.

---

## Root del workspace

| File | Cosa contiene |
|---|---|
| [README.md](README.md) | Overview, smoke test, comandi `trident run`, diagramma del wiring NL→Ranker→ScanPlan→Coordinator→Verticali→Report, switch ad Azure OpenAI. |

---

## `catalog/` — il "cervello" tassonomico (target-agnostico)

Contenuto **YAML dichiarativo** (techniques + packages) + **5 documenti `.md` di riferimento** + **JSON Schema**.

### YAML — la sorgente macchina

| File | Cosa contiene |
|---|---|
| [catalog/prompt.yaml](catalog/prompt.yaml) | **5 tecniche** del layer Prompt: `TRD-PRM-001` (system prompt extraction), `-002` (direct injection), `-003` (multi-turn jailbreak), `-004` (obfuscated), `-R01` (guardrail probing/recon). |
| [catalog/application.yaml](catalog/application.yaml) | **9 tecniche** del layer Application: indirect/RAG (`APP-001`), sensitive info (`-002`), XSS (`-003`), tool abuse (`-004`), memory poisoning (`-005`), exfil-via-tool (`-006`), credential harvesting (`-007`), tool poisoning (`-008`), recon `-R01`. |
| [catalog/model.yaml](catalog/model.yaml) | **6 tecniche** del layer Model: fingerprinting (`MOD-001`), data extraction (`-002`), misinformation (`-003`), e 3 deferred-mvp (membership inference, distillation, inversion). |
| [catalog/packages.yaml](catalog/packages.yaml) | **12 package** = bundle curati di tecniche: 4 profili (`PKG-QUICK`, `OWASP`, `ATLAS`, `360`), 3 per-layer (`PROMPT/APP/MODEL`), 5 per-focus (`GUARDRAIL`, `EXFIL`, `RAG`, `AGENTIC`, `RECON`). |
| [catalog/schema/catalog.schema.json](catalog/schema/catalog.schema.json) | JSON Schema autoritativo. Vocabolari chiusi (converter, scorer, OWASP, capability, severity). Validato a load-time da `SkillRegistry.load_dir`. |

### MD — i contratti di riferimento

| File | Cosa contiene |
|---|---|
| [catalog/CATALOG.md](catalog/CATALOG.md) | Vista testuale del catalogo: coverage map OWASP × ATLAS, schede tecniche, note di onestà (LLM03/LLM10 non targetable, MSRC bug bar). |
| [catalog/scorers.md](catalog/scorers.md) | Mapping catalog-scorer → PyRIT-scorer ufficiale. Cosa fa `SuccessOracle` (deterministico) vs cosa fa PyRIT self-ask (judged). |
| [catalog/oracle.md](catalog/oracle.md) | Contratto del **canary/honeytoken**: generate → plant (l'adapter) → resolve `{planted_secret}` → detect via `SuccessOracle`. |
| [catalog/severity.md](catalog/severity.md) | Metodologia severity = **MSRC AI bug bar** (Critical/Important/Moderate/Low + Track A security / Track B content). Mappa tecnica→categoria→driver. |
| [catalog/strategies.md](catalog/strategies.md) | Mapping converter del catalogo → enum `AttackStrategy` di `azure-ai-evaluation` → classi PyRIT `<Name>Converter`. |

---

## `src/` — il codice runtime

### `src/core/` — modelli, gate, trace, client SDK

| File | Cosa fa |
|---|---|
| [src/core/models.py](src/core/models.py) | Tutti i tipi Pydantic + i vocabolari `Literal`/`frozenset`. Modelli chiave: `TechniqueConfig`, `Package`, `TargetProfile`, `Manifest`, `Scope`, `VerticalConfig`, `ScanPlan`, `Action`, `Decision`, `Verdict`, `ExecutionResult`, `TraceStep`, `Scorecard`. Include il dizionario `_PHASE_TO_MODES` per il gating recon/attack. |
| [src/core/policy_gate.py](src/core/policy_gate.py) | `PolicyGate.check(action)` — **7 regole** in ordine: denylist → allowlist → layer scope → mode/phase + status `deferred-mvp` → budget per vertical → host_allowlist → HITL. Restituisce `Decision(allow, reason, rule)`. |
| [src/core/trace.py](src/core/trace.py) | `Trace` immutabile con sink JSONL. 3 metodi append: `append_gate`, `append_exec`, `append_dispatch`. Unica fonte verità per il report. |
| [src/core/client.py](src/core/client.py) | `TridentClient` — wrapper sottile attorno a `copilot.CopilotClient`. Crea `Session` con tools, `custom_agents`, `PermissionHandler.approve_all`. |
| [src/core/__init__.py](src/core/__init__.py) | Vuoto (marker). |

### `src/nl/` — Phase 1 (Ranker) + Phase 2 (scope_to_scan)

| File | Cosa fa |
|---|---|
| [src/nl/ranker.py](src/nl/ranker.py) | **Ranker ibrido**: lexicon (alias + OWASP id) + embedding cosine + LLM confirmer. Strategia "package-first": se il top package supera la threshold lo restituisce, altrimenti tecniche specifiche. Backend pluggable: `AzureOpenAIEmbedder/Confirmer` (prod) oppure `KeywordEmbedder/PassthroughConfirmer` (offline). Factory `make_ranker(registry, offline=None)`. |
| [src/nl/scope_to_scan.py](src/nl/scope_to_scan.py) | Trasforma uno `Scope` in `ScanPlan`. Applica gating filtri: deny/allow, mode/phase, `target.supports(needs_capabilities)`, status `deferred-mvp`. Produce un `VerticalConfig` per layer con superfici, converters, objectives, scorers, atlas chain. |
| [src/nl/__init__.py](src/nl/__init__.py) | Vuoto. |

### `src/skills/` — registry + runner + handler factory

| File | Cosa fa |
|---|---|
| [src/skills/registry.py](src/skills/registry.py) | `SkillRegistry.load_dir()` legge tutti gli YAML di `catalog/`, applica `validate_catalog` (validator subset puro-Python del JSON Schema), e indicizza `techniques` + `packages`. |
| [src/skills/base.py](src/skills/base.py) | `make_skill_handler(tech, ctx)` → handler async che (1) costruisce `Action`, (2) **chiama `gate.check`**, (3) se ok chiama `runner.execute`, (4) appende a `trace`. Espone `handler.technique` per metadati. |
| [src/skills/pyrit_runner.py](src/skills/pyrit_runner.py) | `PyritRunner.execute(tech, params, target)` — risolve `{planted_secret}` negli objectives via oracle, manda al target, score via oracle (deterministic) o stub assessed (judged). Bumpa severity in base a `data_classification`. |
| [src/skills/__init__.py](src/skills/__init__.py) | Vuoto. |

### `src/agents/` — SDK tool wrapping + brief verticali

| File | Cosa fa |
|---|---|
| [src/agents/factory.py](src/agents/factory.py) | `wrap_as_sdk_tools(handlers)` → registra ogni skill come `@define_tool` Copilot. `build_vertical_session()` crea una Session fenced per il layer, esponendo SOLO le tecniche autorizzate. |
| [src/agents/briefs.py](src/agents/briefs.py) | `VERTICAL_PERSONAS` (3 system prompts per Prompt/App/Model agent) + `build_brief(vcfg)` che genera il testo del brief con target, capabilities, surfaces, converters, scorers, objectives, OWASP×ATLAS chain. |
| [src/agents/__init__.py](src/agents/__init__.py) | Vuoto. |

### `src/orchestrator/` — Phase 3 (Coordinator + dispatch tools)

| File | Cosa fa |
|---|---|
| [src/orchestrator/coordinator.py](src/orchestrator/coordinator.py) | `Coordinator` — top-level. `intake(prompt)` esegue Phase 1+2. `run_agentic(prompt)` crea la Coordinator Session con i 3 dispatch tool come tools e lascia che l'LLM li chiami con i JSON dei `VerticalConfig`. |
| [src/orchestrator/dispatch.py](src/orchestrator/dispatch.py) | `make_dispatch_tools()` produce i 3 `@define_tool`: `dispatch_prompt_agent`, `dispatch_app_agent`, `dispatch_model_agent`. Ognuno: build vertical session → invia brief → aggrega `Scorecard` dal `Trace`. |
| [src/orchestrator/__init__.py](src/orchestrator/__init__.py) | Vuoto. |

### `src/targets/` — adapter, oracle, target di riferimento

| File | Cosa fa |
|---|---|
| [src/targets/adapter.py](src/targets/adapter.py) | `TargetResponse` dataclass + `TargetAdapter` Protocol (`id`, `endpoint`, `capabilities`, `async send`). |
| [src/targets/echo.py](src/targets/echo.py) | `EchoTargetAdapter` in-process. Simula leak quando il prompt contiene `leak/exfil/planted/canary` (esponendo il canary), markup quando contiene `xss/<script/markup`, fingerprint quando contiene `which model`. Permette ai dry-run di mostrare verdetti `confirmed`. |
| [src/targets/oracle.py](src/targets/oracle.py) | `make_canary()`, `resolve_placeholders()`, `SuccessOracle` (detect deterministico per `exfil_canary` / `leak_detector` / `output_markup` / `categorical_match`), `NullOracle` (fallback negativo). Costruito dal blocco `success_oracle` del target profile. |
| [src/targets/__init__.py](src/targets/__init__.py) | Vuoto. |

### `src/reports/` — correlator + HTML

| File | Cosa fa |
|---|---|
| [src/reports/correlator.py](src/reports/correlator.py) | `correlate(scorecards)` → dict con ASR per layer, oracle hits, total successes/blocked/failed, coverage. (v1: chain construction reale e coverage). |
| [src/reports/html_report.py](src/reports/html_report.py) | `render(correlation, out_path)` → HTML semplice con metadata + JSON pretty-printed. |
| [src/reports/__init__.py](src/reports/__init__.py) | Vuoto. |

### Entry point

| File | Cosa fa |
|---|---|
| [src/cli.py](src/cli.py) | Comando `trident`. Carica manifest + target profile + catalog, costruisce oracle + adapter Echo + client SDK + Coordinator, chiama `run_agentic(prompt)`, raccoglie scorecards dal trace, chiama correlate + render. |
| [src/__init__.py](src/__init__.py) | Vuoto. |

---

## `manifests/` — Rules of Engagement as Code

| File | Cosa fa |
|---|---|
| [manifests/sample.yaml](manifests/sample.yaml) | `smoke-001-recon`, mode `recon`, target `echo`, tutti e 3 i layer, budget 20. Solo phase ∈ {recon, both} sopravvive al gate. |
| [manifests/sample_attack.yaml](manifests/sample_attack.yaml) | `smoke-002-attack`, mode `attack`, stessi parametri. Tecniche exploit attive end-to-end. |

---

## `targets/` — target profile dichiarativi

| File | Cosa fa |
|---|---|
| [targets/echo.yaml](targets/echo.yaml) | Profilo del target Echo in-process. Caps `has_chat, has_retrieval, exposes_system_prompt`. APP-004/005/006/008 auto-skipped (no `has_tools`/`is_agentic`). Oracle con canary `TRIDENT` + `expected_model_set: [Echo]`. |
| [targets/aigoat.yaml](targets/aigoat.yaml) | Profilo AIGoat (chatbot "Cracky" + storefront RAG). Endpoint REST reali, auth bearer, defense_levels L0/L1/L2, flag CTF `AIGOAT\{...\}`, `expected_model_set: [Mistral-7B-Instruct, Mistral, Llama, GPT]`. |
| [targets/target_profile.example.yaml](targets/target_profile.example.yaml) | Schema di riferimento per documentare il formato del TargetProfile. |

---

## Flusso dati end-to-end (la spina dorsale concettuale)

```
NL prompt
   │
   ▼ Phase 1 (nl/ranker.py)
      → Scope (selection_mode = package | techniques)
   │
   ▼ Phase 2 (nl/scope_to_scan.py)
      → ScanPlan(verticals[VerticalConfig×N], skipped[…])
   │
   ▼ Phase 3 (orchestrator/coordinator.py)
      Coordinator Session con 3 dispatch tools
        ├─ dispatch_prompt_agent  → fenced PromptVertical Session
        ├─ dispatch_app_agent     → fenced AppVertical Session
        └─ dispatch_model_agent   → fenced ModelVertical Session
                                       │
                                       ▼ per ogni skill handler:
                                       1. PolicyGate.check → Trace.append_gate
                                       2. PyritRunner.execute:
                                            - resolve {planted_secret} via oracle
                                            - target.send(prompt)
                                            - oracle.detect (deterministic)
                                                  OR judged stub (v0) / PyRIT (v1)
                                          → Trace.append_exec
                                       3. Scorecard aggregato dal Trace
   │
   ▼ Phase 4 (reports/correlator.py + html_report.py)
      output/<campaign>.html  +  output/<campaign>.trace.jsonl
```

---

## Note operative

- Nel workspace **non esistono** né `tests/` né `pyproject.toml` (il README li menziona ma non sono presenti).
- Il `src/` non ha un `pyproject` che lo trasformi in package installabile — il comando `trident` del README presuppone un setup che oggi manca.
- Tutti i moduli `__init__.py` sono attualmente vuoti (fungono solo da marker di package).
