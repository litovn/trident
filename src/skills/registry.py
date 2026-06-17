import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..core.models import Layer, Package, TechniqueConfig


class CatalogValidationError(Exception):
    """Raised when the catalog violates schema/catalog.schema.json."""

def _read_frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter block of a SKILL.md into a technique dict.

    A SKILL.md is the single source of truth for one technique: the frontmatter
    carries the full TechniqueConfig, the Markdown body is the agent-facing
    procedure (ignored here).
    """
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise CatalogValidationError(f"{path}: missing or malformed YAML frontmatter")
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        raise CatalogValidationError(f"{path}: frontmatter is not a mapping")
    # SKILL.md convention: `name` is the SDK skill slug (lowercase, == folder name);
    # the human-readable technique label lives in `title`. TRIDENT's model uses
    # `name` for the human label (ranker corpus, reports), so map title → name.
    if "title" in fm:
        fm["name"] = fm.pop("title")
    return fm

# ──────────────────────────────────────────────────────────────────────────
# Pure-Python subset validator for the JSON Schema we use (type / required /
# enum / items / pattern). Zero external dependency — runs in any environment.
# ──────────────────────────────────────────────────────────────────────────
def _mini_validate(obj: Any, schema: dict, path: str) -> list[str]:
    errs: list[str] = []
    if "enum" in schema:
        if obj not in schema["enum"]:
            errs.append(f"{path}: {obj!r} not allowed (enum {schema['enum']})")
        return errs
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            return [f"{path}: expected object"]
        for r in schema.get("required", []):
            if r not in obj:
                errs.append(f"{path}.{r}: required field missing")
        for k, v in obj.items():
            if k in schema.get("properties", {}):
                errs += _mini_validate(v, schema["properties"][k], f"{path}.{k}")
    elif t == "array":
        if not isinstance(obj, list):
            return [f"{path}: expected array"]
        item_schema = schema.get("items")
        if item_schema:
            for i, el in enumerate(obj):
                errs += _mini_validate(el, item_schema, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(obj, str):
            errs.append(f"{path}: expected string")
        elif "pattern" in schema and not re.search(schema["pattern"], obj):
            errs.append(f"{path}: {obj!r} fails pattern {schema['pattern']}")
    elif t == "integer":
        if isinstance(obj, bool) or not isinstance(obj, int):
            errs.append(f"{path}: expected integer")
    return errs


def validate_catalog(raw_techniques: list[dict], raw_packages: list[dict],
                     schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tdef, pdef = schema["$defs"]["technique"], schema["$defs"]["package"]
    errs: list[str] = []
    ids: set[str] = set()
    for t in raw_techniques:
        errs += _mini_validate(t, tdef, f"technique[{t.get('id', '?')}]")
        if "id" in t:
            ids.add(t["id"])
    for p in raw_packages:
        errs += _mini_validate(p, pdef, f"package[{p.get('id', '?')}]")
    for p in raw_packages:                              # cross-object: refs must exist
        for tid in p.get("techniques", []):
            if tid not in ids:
                errs.append(f"package[{p.get('id', '?')}]: technique ref {tid!r} not found")
    if errs:
        raise CatalogValidationError(
            "Catalog validation failed:\n  - " + "\n  - ".join(errs))


# ──────────────────────────────────────────────────────────────────────────
# Registry (= Catalog index, Pydantic-typed throughout)
# ──────────────────────────────────────────────────────────────────────────
class SkillRegistry:
    """Index over the catalog. `techniques` and `packages` are public dicts so the
    ranker and the gate can iterate directly without coupling to private state."""

    def __init__(self) -> None:
        self.techniques: dict[str, TechniqueConfig] = {}
        self.packages: dict[str, Package] = {}

    # ---- loading -------------------------------------------------------

    def load_dir(self, catalog_dir: Path | str, *, validate: bool = True) -> "SkillRegistry":
        """Load the catalog.

        Techniques are sourced from ``skills_catalog/<ID>/SKILL.md`` frontmatter
        (the single source of truth — a technique IS its skill). Packages are
        curated bundles in ``packages.yaml``. Schema validation is on by default.
        """
        d = Path(catalog_dir)

        # Techniques: one SKILL.md per technique; the YAML frontmatter carries the
        # full TechniqueConfig (the Markdown body is the agent-facing procedure).
        raw_t: list[dict] = [
            _read_frontmatter(skill_md)
            for skill_md in sorted((d / "skills_catalog").glob("*/SKILL.md"))
        ]

        # Packages: curated bundles (any *.yaml in the catalog root exposing `packages:`).
        raw_p: list[dict] = []
        for yml in sorted(d.glob("*.yaml")):
            data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
            raw_p += data.get("packages", [])

        schema_path = d / "schema" / "catalog.schema.json"
        if validate and schema_path.exists():
            validate_catalog(raw_t, raw_p, schema_path)
        for entry in raw_t:
            tech = TechniqueConfig.model_validate(entry)
            self.techniques[tech.id] = tech
        for entry in raw_p:
            pkg = Package.model_validate(entry)
            self.packages[pkg.id] = pkg
        return self

    # ---- queries -------------------------------------------------------

    def has(self, technique_id: str) -> bool:
        return technique_id in self.techniques

    def get(self, technique_id: str) -> TechniqueConfig:
        if technique_id not in self.techniques:
            raise KeyError(f"unknown technique: {technique_id}")
        return self.techniques[technique_id]

    def for_layer(self, layer: Layer, technique_ids: list[str]) -> list[TechniqueConfig]:
        return [self.techniques[t] for t in technique_ids
                if t in self.techniques and self.techniques[t].layer == layer]

    def all(self) -> list[TechniqueConfig]:
        return list(self.techniques.values())

    def all_packages(self) -> list[Package]:
        return list(self.packages.values())

    def package(self, pid: str) -> Package:
        return self.packages[pid]
