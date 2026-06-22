# TRIDENT — Attack strategy reference (converter names)

Every `converters` / `converters_alt` value in the catalog is a name from the
**`azure-ai-evaluation` `AttackStrategy` enum** (verified against the official
"Run AI Red Teaming Agent locally" docs, 2026-04). Source of truth for execution is
**PyRIT-direct** (ADR-004), so each single-turn strategy maps 1:1 to a PyRIT
converter class `<Name>Converter`. The RTA enum is used as the canonical naming.

`Baseline` = no converter (send the objective unchanged). RTA runs Baseline first by default.

## Single-turn strategies used in the catalog
| Catalog value | AttackStrategy | PyRIT converter class | Complexity |
|---|---|---|---|
| Baseline | (default, no strategy) | — (direct send) | baseline |
| Base64 | Base64 | Base64Converter | easy |
| Flip | Flip | FlipConverter | easy |
| Leetspeak | Leetspeak | LeetspeakConverter | easy |
| Morse | Morse | MorseConverter | easy |
| ROT13 | ROT13 | ROT13Converter | easy |
| UnicodeConfusable | UnicodeConfusable | UnicodeConfusableConverter | easy |
| Url | Url | UrlConverter | easy |
| Diacritic | Diacritic | DiacriticConverter | easy |
| StringJoin | StringJoin | StringJoinConverter | easy |
| SuffixAppend | SuffixAppend | SuffixAppendConverter | easy |
| Tense | Tense | TenseConverter (LLM-assisted) | moderate |
| IndirectAttack | IndirectAttack | XPIA — indirect prompt injection into context/tool output | easy |
| Jailbreak | Jailbreak | UPIA — user-injected jailbreak prompt | easy |

## Multi-turn strategies
| Catalog value | AttackStrategy | Notes | Complexity |
|---|---|---|---|
| Crescendo | Crescendo | gradual multi-turn escalation | difficult |
| Multiturn | Multiturn | generic multi-turn | difficult |

**Beyond the Azure enum (PyRIT-direct only):** TAP (Tree of Attacks with Pruning),
PAIR, and Skeleton Key are **not** in the `AttackStrategy` enum. They are available as
PyRIT orchestrators/attacks when running PyRIT directly. Use them only on the
PyRIT-direct path; do not pass them as RTA `AttackStrategy` values.

## Important limits (from the official docs)
- The RTA scan path supports **single-turn, text-only** interactions. True multi-turn
  (Crescendo/TAP/etc.) therefore runs via **PyRIT-direct orchestrators**, not via the
  RTA `scan()` strategy list.
- `AttackStrategy.Compose([a, b])` chains exactly **two** strategies (e.g. Base64 + ROT13).
- The full enum also includes: AnsiAttack, AsciiArt, AsciiSmuggler, Atbash, Binary,
  Caesar, CharacterSpace, CharSwap, UnicodeSubstitution — not used in the current
  catalog but available if we extend it.
- Grouped shortcuts: `AttackStrategy.EASY` / `.MODERATE` / `.DIFFICULT`.

## How the SDK team consumes this
1. Read a technique's `converters` (+ `converters_alt`).
2. For single-turn values → instantiate the matching PyRIT `<Name>Converter` and chain them.
3. For `Crescendo` / `Multiturn` → use the PyRIT multi-turn orchestrator.
4. `Baseline` → send the objective with no converter.
