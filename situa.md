cli.py

main()  → argparse (--manifest --target --catalog --prompt --out)

  └─ _run()

# 1. _load_yaml → Manifest + TargetProfile          [core/models.py]

## TargetProfile: CHE COSA ATTACCO
        nikita: 
        "TargetProfile ok adesso è utile e lo possiamo compilare solo perché conosciamo AIGoat e abbiamo informazioni su di lui. Ma ti ricordo l'idae di TRIDENT è che questo vanga applicato a qualsiasi modello si desideri, come ci si aspetta di avere informazioni a riguardo, dubito ci siano."
        
        AI:
        "Ho letto oracle.py. Il SuccessOracle parte da cfg = cfg or {}: se non gli dai niente, degrada senza rompersi. Quei campi spaventosi di aigoat.yaml non sono requisiti — sono scorciatoie. Il problema è che aigoat.yaml li mette tutti insieme senza etichettarli, e così sembra che servano tutti."

| Bucket	| Campi	| Li hai per un target qualsiasi?|
|----|----|----|
|A — Minimo per partire	|base_url, surface chat, auth	|Sì: se sei autorizzato a testarlo, conosci indirizzo e credenziali. Non è onniscienza, è il presupposto del red-teaming legale.|
|B — Scopribile in RECON	|capabilities, surfaces, identità del modello	|No a priori, ma li SCOPRI: è esattamente il compito della modalità recon.|
|C — Scorciatoie white-box / CTF	|flag.pattern (AIGOAT{}), leak.reference (system prompt noto), expected_model_set preciso, defense_levels L0/L1/L2, ctf_challenge_mapping |No, e NON ti servono. Sono comodità che AIGoat offre perché è un CTF. Il commento stesso dice "white-box, validation-only".|

C è interamente opzionale

### 2. Come fa TRIDENT a sapere se un attacco è riuscito SENZA conoscere il target

1. Canary piantato (make_canary in oracle.py): TRIDENT genera lui stesso un honeytoken (TRIDENT-CANARY-a1b2c3...), lo pianta tramite una surface, e poi controlla se "ricompare" nell'output. Non è informazione che hai sul target — è una trappola che porti tu. Funziona su qualunque bersaglio.

2. output_markup: una regex fissa che rileva XSS/markup eseguibile. Zero conoscenza del target.

3. Scorer giudicati da LLM (refusal_judge, judged_objective): un giudice LLM valuta la risposta. Zero conoscenza del target — guarda solo se il modello ha rifiutato o se l'obiettivo è stato raggiunto.
    
Quindi per un target sconosciuto usi: canary + markup + giudice LLM. I detector white-box (flag noto, system-prompt noto) sono solo un bonus quando li hai.


    Profilo MINIMO (base_url + chat + auth)
        → RECON: fingerprint del modello, enumerazione surface, probe delle guardrail
        → produce un TargetProfile arricchito + ipotesi di debolezza
        → un umano autorizza (HITL)
        → ATTACK valida

### Recon
Recon è la macchina che costruisce il profilo che oggi sei costretto a scrivere a mano. Per un target ignoto non riempi expected_model_set (lo scopre il fingerprinting), non hai leak.reference (usi le euristiche generiche), non hai flag (è roba da CTF).

### PROBLEMA
- G1 — Il loop recon→profilo NON è implementato. Le tecniche di recon (TRD-PRM-R01, TRD-APP-R01, TRD-MOD-001) girano e scrivono nella trace, ma niente riassembla il loro output in un TargetProfile. La promessa dell'ADR-018 è sulla carta, non nel codice. Per questo oggi sei obbligato a scrivere tutto a mano — ed è ciò che ti ha fatto pensare "ma queste info non le avrò mai".

- G2 — aigoat.yaml non etichetta i bucket. Mescola "minimo", "scopribile" e "scorciatoia CTF" come se fossero tutti necessari.

- G3 — leak.reference è white-box e stride con la tesi black-box (ADR-014). Va bene come scorciatoia di validazione per il PoC, ma deve essere chiaramente marcato come opzionale.

## Manifest: COSA MI E' PERMESSO FARE
Il manifest è ciò che il PolicyGate legge per autorizzare o bloccare ogni azione

... nel design originale (vedi il commento in cima a Manifest in models.py) il manifest dovrebbe dichiarare solo vincoli, lasciando che sia il ranker a scegliere layer e tecniche dal prompt in linguaggio naturale. Ma i manifest reali (aigoat_l0_*) fissano layers e technique_allowlist — cioè bypassano il ranker.



# 2. SkillRegistry().load_dir(catalog)               [skills/registry.py]
        Skillgen non è mai stata una visione di Trident, è stato creato una volta smeplicemente come scipt per riformulare i contenuti degli *.yaml ed è stato dimentic lì. Rimuoviamo skillgen.py completamente, facendo diventare SKILL.md come sorgente unica.

skillgen.py rimosso e SKILL.md è ora la sorgente unica di verità. Ecco cosa è cambiato.

1. Migrato i 20 SKILL.md — il frontmatter ora contiene l'intero TechniqueConfig (layer, phase, converters, scorer, objectives, severità, owasp/atlas, capabilities…), con name = nome leggibile, id = TRD-…, e description = il blend per lo skill-matcher dell'SDK. Il corpo Markdown (la procedura per l'agente) è preservato intatto.
2. Riscritto registry.py — load_dir ora legge le tecniche dai frontmatter di skills_catalog/*/SKILL.md (nuovo helper _read_frontmatter); i package restano da packages.yaml.
3. Eliminati: src/skills/skillgen.py, catalog/prompt.yaml, catalog/application.yaml, catalog/model.yaml.
4. Aggiornati i riferimenti: CATALOG.md, README.md (albero + bullet + roadmap), docstring di factory.py e pyrit_tools.py, commento in smoke_aigoat.py.



# OK - 3. Trace(jsonl_path)                               [core/trace.py]


# 4. oracle = SuccessOracle | NullOracle             [targets/oracle.py]
        cli.py: SuccessOracle(profile.success_oracle)  →  oracle.canary
        → _build_target(profile, canary)  →  l'adapter PIANTA il canary
        PyritRunner._score
        → scorer_factory.score_deterministic(scorer, resp, oracle)
                → PREFERISCE PyRIT (SubStringScorer / MarkdownInjectionScorer)
                → FALLBACK a oracle.detect() quando il substring non è configurato

Funzionano su qualunque target (zero conoscenza): canary, output_markup, scorer giudicati.
Bonus white-box/CTF (tutti opzionali): flag.pattern, leak.reference, expected_model_set.
Questo è il punto di forza che rende reale l'idea "applicabile a qualsiasi bersaglio".   
        
- Easy: Unificare _MARKUP/_HTML_MARKUP in una costante condivisa.
- Easy: Codice morto. Il classmethod from_target_profile non è chiamato da nessuno (il cli costruisce l'oracle direttamente).
- Refactoring: Doppio percorso di scoring. La logica output_markup (e idem il canary) esiste due volte: in scorer_factory (percorso vivo, via PyRIT) e in oracle.detect() (fallback). Due implementazioni della "stessa verifica" → rischio di deriva. Si lega alla consolidazione route_score già annotata. → oracle.py unica fonte, scorer_factory eliminato (Il suo wrapping PyRIT (SubStringScorer/MarkdownInjectionScorer) non aggiungeva accuratezza rispetto a un match substring/regex, ed era duplicato con l'oracle.)

        Due cose da segnalare (trasparenza)
        1. Divergenza dichiarata dall'ADR-001: gli scorer deterministici non passano più dal sottosistema Scorer di PyRIT — usano l'oracle pure-Python. PyRIT resta per converter, scorer giudicati e orchestratori. La logica: substring/regex via PyRIT era cerimonia + duplicazione, e l'oracle è il core target-agnostico e Foundry-free su cui si regge la tesi "qualsiasi target". Se preferisci tenere fede all'ADR-001 alla lettera, è reversibile.
        2. Unificazioni di comportamento (intenzionali, probabilmente più corrette): exfil_canary e leak_detector ora controllano entrambi canary|flag|leak.reference (unione dei segnali di disclosure); categorical_match ora è case-insensitive.

 
# 5. _build_target(profile, canary)                  [targets/echo.py | aigoat.py]
        Il design (oracle.md, aigoat.yaml) dice chiaramente:

        "l'adapter scrive il token nel target via plant_surface (retrieval_ingest → /api/knowledge-base)"

In pratica, plant_surface nei profili è configurazione aspirazionale — descrive un comportamento che il codice non esegue. 
Conseguenza pratica: la demo "canary exfil" funziona su echo (che simula), ma non su AIGoat reale. È un'asimmetria da sapere — soprattutto perché "canary exfil" è uno degli headline del progetto.

Contratto pulito; AIGoat è genuinamente guidato dal profilo (lo swap-test dell'ADR-013 passerebbe per target HTTP); ciclo di vita async corretto; zero leakage di AIGoat nel core. Su questo, l'architettura è fedele all'idea.

- Il canary ora viene davvero piantato
        adapter.py — il Protocol ora documenta plant(surface, content) e aclose() come metodi opzionali (send resta l'unico obbligatorio; i chiamanti usano getattr, coerente col pattern esistente).

        echo.py — ora è stateful e coerente: plant() ingerisce il token in una KB in-memory; send() lo fa riemergere sui prompt di retrieval/exfil. È una simulazione RAG-exfil credibile, non più il vecchio "echo su parola chiave".

        aigoat.py — nuovo plant(surface, content): risolve l'endpoint dal profilo (retrieval_ingest → /api/knowledge-base), fa il POST col bearer, best-effort (cattura gli errori HTTP → False). Il campo del body è content di default, sovrascrivibile via surfaces.<surface>.body_field.

        cli.py — nuovo passo di pre-flight _plant_canary(target, oracle), chiamato dopo client.start() e prima del Coordinator. Legge plant_surface dall'oracle, usa la guardia getattr, stampa l'esito. Target-agnostico: target senza plant o senza plant_surface → saltato in silenzio.

        oracle.md — documentato che il planting è ora cablato.

Il planting è pre-flight, fuori dal policy gate e fuori dalla trace — è setup dell'harness (come la generazione del canary), non un'azione d'attacco. Scelta difendibile; se preferisci tracciarlo per audit, è un'aggiunta futura.

su AIGoat reale il planting è best-effort: di default manda {"content": <token>}
 
# 6. client.start()                                  [core/client.py → Foundry/SDK]
il token Azure AD che costruiamo con tanta cura quasi certamente non arriva mai al runtime → l'autenticazione del Coordinator probabilmente fallisce su una run Foundry reale è possibile che il percorso del Coordinator non abbia mai funzionato davvero. (non "certo", perché il backend del Copilot CLI potrebbe acquisire le credenziali Azure per conto suo quando vede type: azure)
        Fix (D-CL-1): al momento di new_session(), risolvere il token (await sul provider / credential.get_token) e passare bearer_token=<stringa> (oppure api_key). Cautela: i bearer scadono (~1h), ma dato che le sessioni si creano fresche va bene; sessioni singole molto lunghe potrebbero servire un refresh.

README e .env.example dicono "FOUNDRY_ENDPOINT + az login, oppure FOUNDRY_API_KEY". Ma _build_provider_config non include mai api_key. Quindi il BYOK via FOUNDRY_API_KEY non funziona per il Coordinator — solo il ranker legge quella variabile d'ambiente direttamente. Stesso tema "auth cablata a metà".
        Fix (D-CL-2): includere api_key nel dict provider quando è impostata (l'SDK lo supporta).

Campi morti in config.py




# 7. Coordinator(...).run_agentic(prompt)            [orchestrator/coordinator.py]
Ma oracle.detect ritorna kind="confirmed" anche per i negativi confermati (es. "nessun canary trovato" → success=False, kind=confirmed). Quindi un check deterministico fallito gonfia oracle_hits.



# 8. estrai scorecard dalla trace → correlate        [reports/correlator.py]


# 9. render(corr, html)                              [reports/html_report.py]


Semnatic ranking?
Copilot SDK funziona?
Coordinator lancia in parallaleo se stesso usando tool specializzati?