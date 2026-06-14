import argparse
import asyncio
import json
import os
from pathlib import Path

import yaml

# Load .env (FOUNDRY_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT, ...) BEFORE the
# Coordinator client reads its settings. python-dotenv is optional: when
# absent the user must export the vars manually.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .core.client import TridentClient
from .core.models import Manifest, Scorecard, TargetProfile
from .core.trace import Trace
from .orchestrator.coordinator import Coordinator
from .reports.correlator import correlate
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


async def _run(args: argparse.Namespace) -> None:
    manifest = Manifest.model_validate(_load_yaml(Path(args.manifest)))
    target_profile = TargetProfile.model_validate(_load_yaml(Path(args.target)))
    registry = SkillRegistry().load_dir(Path(args.catalog))

    out_dir = Path(args.out)
    trace_path = out_dir / f"{manifest.campaign_id}.trace.jsonl"
    trace = Trace(jsonl_path=trace_path)

    oracle = (SuccessOracle(target_profile.success_oracle)
              if target_profile.success_oracle else NullOracle())
    target = _build_target(target_profile, canary=oracle.canary)

    client = TridentClient()
    await client.start()
    try:
        coord = Coordinator(client, manifest, target, target_profile, registry, trace,
                            oracle=oracle)

        summary = await coord.run_agentic(args.prompt)
        scorecards: list[Scorecard] = []
        for step in trace.steps():
            if step.kind == "dispatch" and "scorecard" in step.payload:
                scorecards.append(Scorecard.model_validate(step.payload["scorecard"]))
        corr = correlate(scorecards)
        corr["coordinator_summary"] = summary
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
    p.add_argument("--target", required=True, help="Path to TargetProfile YAML")
    p.add_argument("--catalog", default="catalog", help="Catalog directory (default: catalog)")
    p.add_argument("--prompt", required=True, help="NL prompt describing what to test")
    p.add_argument("--out", default="output", help="Output directory (default: output)")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
