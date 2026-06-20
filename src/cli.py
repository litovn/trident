import argparse
import asyncio
import logging
import sys
import yaml
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=getattr(logging, os.environ.get("TRIDENT_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from .core.client import TridentClient
from .core.models import Manifest, Package, TargetProfile
from .core.trace import Trace
from .nl.scope_to_scan import default_package
from .orchestrator.coordinator import Coordinator
from .reports.correlator import correlate, scorecards_from_trace
from .reports.html_report import render
from .skills.registry import SkillRegistry
from .targets.adapter import TargetAdapter
from .targets.aigoat import AIGoatTargetAdapter
from .targets.echo import EchoTargetAdapter
from .targets.oracle import NullOracle, SuccessOracle


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _build_target(profile: TargetProfile, canary: str | None) -> TargetAdapter:
    if profile.id == "echo":
        return EchoTargetAdapter(canary=canary)
    if profile.id == "aigoat":
        password = os.environ.get("AIGOAT_PASSWORD")
        if not password:
            raise RuntimeError(
                "AIGOAT_PASSWORD env var is required to attack the AIGoat target "
                "(e.g. $env:AIGOAT_PASSWORD='password123')."
            )
        return AIGoatTargetAdapter(profile=profile, password=password, canary=canary)
    raise ValueError(f"Unknown target profile id: {profile.id!r}")


async def _plant_canary(target: TargetAdapter, oracle: SuccessOracle) -> None:
    """Pre-flight: if the campaign uses a planted canary, write it into the target
    via the configured ``plant_surface`` so ``exfil_canary`` can fire for real.

    Best-effort and target-agnostic: targets without a ``plant`` capability (or
    without a ``plant_surface`` in the oracle config) are silently skipped.
    """
    if not oracle.canary:
        return
    surface = oracle.cfg.get("canary", {}).get("plant_surface")
    if not surface:
        return
    plant = getattr(target, "plant", None)
    if plant is None:
        return
    ok = await plant(surface, oracle.canary)
    print(f"[pre-flight] canary plant via {surface!r}: {'ok' if ok else 'skipped/failed'}")


def _load_target_profile(targets_dir: Path, profile_id: str) -> TargetProfile:
    """Resolve the TargetProfile named by the manifest's ``target_profile_id``.

    The manifest is the campaign spec: it names its target by id, and TRIDENT
    resolves the matching profile from ``targets_dir`` (matched on the YAML ``id``
    field, not the filename).
    """
    candidates = sorted(targets_dir.glob("*.yaml"))
    for path in candidates:
        if _load_yaml(path).get("id") == profile_id:
            return TargetProfile.model_validate(_load_yaml(path))
    available = ", ".join(sorted(filter(None, (_load_yaml(p).get("id") for p in candidates)))) or "(none)"
    raise SystemExit(
        f"target profile id {profile_id!r} (from manifest) not found under {targets_dir}/ "
        f"— available ids: {available}"
    )


def _advisor_repl(prompt: str, registry: SkillRegistry, manifest: Manifest) -> Package:
    """Interactive package selection. The advisor asks questions only when the
    prompt is vague, otherwise proposes the top packages immediately; the operator
    picks one. UI-agnostic core (``src/nl/advisor.py``); this is just the terminal
    front-end (a web UI would drive the same ``PackageAdvisor.step``)."""
    from .nl.advisor import PackageAdvisor

    advisor = PackageAdvisor(registry, manifest.mode)
    history: list[dict] = [{"role": "user", "content": prompt}]
    while True:
        turn = advisor.step(history)
        if turn.kind == "clarify":
            print("\n[advisor] I need a bit more detail to choose well:")
            for q in turn.questions:
                print(f"  • {q}")
            answer = input("\nYour answer (blank = just choose for me): ").strip()
            history.append({"role": "user",
                            "content": answer or "Please just propose the best packages now."})
            continue
        print("\n[advisor] Recommended attack packages:\n")
        for i, c in enumerate(turn.candidates, 1):
            print(f"  {i}. {c.id} — {c.name}")
            print(f"     layers: {', '.join(c.layers) or '-'} | budget: {c.query_budget} "
                  f"| intensity: {c.max_intensity}")
            print(f"     {c.rationale}")
        pick = input(f"\nPick a package [1-{len(turn.candidates)}] (default 1): ").strip()
        idx = int(pick) - 1 if pick.isdigit() and 1 <= int(pick) <= len(turn.candidates) else 0
        return registry.packages[turn.candidates[idx].id]


def _resolve_package(args: argparse.Namespace, registry: SkillRegistry,
                     manifest: Manifest) -> Package:
    """Pick the campaign's attack package: explicit ``--package`` → interactive
    advisor (needs Foundry + a TTY) → deterministic default per mode."""
    if args.package:
        pkg = registry.packages.get(args.package)
        if pkg is None:
            raise SystemExit(
                f"--package {args.package!r} not found; available: "
                f"{', '.join(sorted(registry.packages))}")
        return pkg
    foundry = bool(os.environ.get("FOUNDRY_ENDPOINT") or os.environ.get("AZURE_OPENAI_ENDPOINT"))
    if foundry and sys.stdin.isatty():
        try:
            return _advisor_repl(args.prompt, registry, manifest)
        except Exception as exc:                       # advisor is best-effort
            logging.getLogger("trident").warning(
                "package advisor unavailable (%s) — using default package", exc)
    return default_package(manifest.mode, registry)


async def _run(args: argparse.Namespace) -> None:
    manifest = Manifest.model_validate(_load_yaml(Path(args.manifest)))
    target_profile = _load_target_profile(Path(args.targets_dir), manifest.target_profile_id)
    registry = SkillRegistry().load_dir(Path(args.catalog))

    chosen_package = _resolve_package(args, registry, manifest)

    # HITL per-layer confirmation is interactive — enable only on a real TTY so
    # non-interactive runs never hang waiting for input.
    confirm_chain = bool(args.confirm_chain) and sys.stdin.isatty()
    if args.confirm_chain and not confirm_chain:
        logging.getLogger("trident").warning(
            "--confirm-chain ignored: stdin is not an interactive terminal")

    out_dir = Path(args.out)
    trace_path = out_dir / f"{manifest.campaign_id}.trace.jsonl"
    trace = Trace(jsonl_path=trace_path)

    oracle = (SuccessOracle(target_profile.success_oracle)
              if target_profile.success_oracle else NullOracle())
    target = _build_target(target_profile, canary=oracle.canary)

    client = TridentClient()
    await client.start()
    try:
        await _plant_canary(target, oracle)
        coord = Coordinator(client, manifest, target, target_profile, registry, trace,
                            oracle=oracle, chosen_package=chosen_package,
                            confirm_chain=confirm_chain)

        summary = await coord.run_agentic(args.prompt)

        corr = correlate(
            scorecards_from_trace(trace),
            coord.last_plan,
            registry,
            summary=summary,
        )
    finally:
        await client.stop()
        aclose = getattr(target, "aclose", None)
        if aclose is not None:
            await aclose()

    html_out = out_dir / f"{manifest.campaign_id}.html"
    render(corr, html_out)

    print(json.dumps(corr, indent=2, default=str))
    print(f"\nReport: {html_out}")
    print(f"Trace : {trace_path}")


def main() -> None:
    p = argparse.ArgumentParser(prog="trident", description="TRIDENT — red-teaming accelerator")
    p.add_argument("--manifest", required=True, help="Path to manifest YAML")
    p.add_argument("--targets-dir", default="targets",
                   help="Directory of TargetProfile YAMLs (default: targets); the manifest's "
                        "target_profile_id selects which profile to use")
    p.add_argument("--catalog", default="catalog", help="Catalog directory (default: catalog)")
    p.add_argument("--prompt", required=True, help="NL prompt describing what to test")
    p.add_argument("--package", default="",
                   help="Skip the advisor and use this attack package id (e.g. PKG-EXFIL)")
    p.add_argument("--confirm-chain", action="store_true",
                   help="HITL: ask before dispatching each layer (attack-chain step); interactive TTY only")
    p.add_argument("--out", default="output", help="Output directory (default: output)")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
