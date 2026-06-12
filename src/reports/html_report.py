import html
import json
from pathlib import Path


def render(correlation: dict, out_path: Path) -> Path:
    payload = html.escape(json.dumps(correlation, indent=2, default=str))
    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>TRIDENT Report</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .25rem; }}
  pre {{ background: #f4f4f4; padding: 1rem; overflow: auto; border-radius: 6px; }}
  .meta {{ color: #666; font-size: .9rem; }}
</style></head>
<body>
<h1>TRIDENT Report</h1>
<p class="meta">Layers executed: {", ".join(correlation.get("layers_executed", []))} ·
Techniques fired: {correlation.get("total_techniques_fired", 0)} ·
Successes: {correlation.get("total_successes", 0)} ·
Blocked: {correlation.get("total_blocked", 0)}</p>
<pre>{payload}</pre>
</body></html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path
