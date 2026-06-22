"""JSON report artifact — the machine-readable data contract for downstream
consumers (e.g. the frontend dashboard).

``html_report.render`` produces a human-facing page; this module persists the
exact correlation payload as a stable, versioned ``<campaign>.report.json`` so a
separate frontend can render it without scraping HTML or parsing stdout.

The shape is documented in ``report.schema.json`` (JSON Schema draft-07). Bump
``SCHEMA_VERSION`` whenever the contract changes in a backward-incompatible way
(e.g. removing/renaming a field); additive changes keep the same major version.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

# Semantic version of the report.json contract (see report.schema.json).
# Frontend consumers should check the major version to detect breaking changes.
SCHEMA_VERSION = "1.0.0"

# Ships next to this module; the canonical spec for the report.json contract.
SCHEMA_PATH = Path(__file__).with_name("report.schema.json")


def build_report(correlation: dict) -> dict:
    """Wrap the correlation payload with contract metadata (version + timestamp).

    Every correlation key is preserved at the top level; only ``schema_version``
    and ``generated_at`` are added, so the contract stays flat and additive.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **correlation,
    }


def write_report(correlation: dict, out_path: Path) -> Path:
    """Persist the report payload as pretty-printed UTF-8 JSON and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_report(correlation)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return out_path
