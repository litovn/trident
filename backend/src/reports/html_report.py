import html
import json
from pathlib import Path

_SEV_COLOR = {"critical": "#b00020", "high": "#d9534f", "medium": "#e08e0b",
              "low": "#3a87ad", "info": "#777"}


def _esc(x: object) -> str:
    return html.escape(str(x if x is not None else ""))


def _sev_badge(sev: str) -> str:
    color = _SEV_COLOR.get((sev or "info").lower(), "#777")
    return (f'<span style="background:{color};color:#fff;border-radius:4px;'
            f'padding:1px 7px;font-size:.8rem">{_esc(sev)}</span>')


def _chains_section(chains: list[dict]) -> str:
    if not chains:
        return ('<h2>Cross-layer attack chains</h2>'
                '<p class="muted">No cross-layer chain — successes did not span ≥2 layers.</p>')
    blocks = []
    for ch in chains:
        steps = " &nbsp;→&nbsp; ".join(
            f'<strong>{_esc(s["layer"])}</strong>·{_esc(s["technique_id"])} '
            f'<span class="muted">({_esc(s["atlas_tactic"]) or "—"})</span>'
            for s in ch.get("steps", [])
        )
        blocks.append(
            f'<div class="chain"><div class="chain-head">'
            f'Blast radius: {_sev_badge(ch.get("blast_radius","info"))} &nbsp;·&nbsp; '
            f'layers: {_esc(", ".join(ch.get("layers", [])))} '
            f'<span class="muted">— {_esc(ch.get("label",""))}</span></div>'
            f'<div class="chain-steps">{steps}</div></div>'
        )
    return "<h2>Cross-layer attack chains</h2>" + "".join(blocks)


def _findings_table(findings: list[dict]) -> str:
    if not findings:
        return '<h2>Findings</h2><p class="muted">No successful findings.</p>'
    rows = "".join(
        f"<tr><td>{_esc(f['layer'])}</td><td>{_esc(f['technique_id'])}</td>"
        f"<td>{_esc(f['name'])}</td><td>{_esc(f['owasp_id'])}</td>"
        f"<td>{_esc(f['atlas_tactic'])}</td><td>{_sev_badge(f['severity'])}</td></tr>"
        for f in findings
    )
    return (
        "<h2>Findings (successful)</h2>"
        '<table><thead><tr><th>Layer</th><th>Technique</th><th>Name</th>'
        "<th>OWASP</th><th>ATLAS tactic</th><th>Severity</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _coverage_section(cov: dict) -> str:
    planned, tested = cov.get("planned", []), cov.get("tested", [])
    not_tested = cov.get("not_tested_in_scope", [])
    excluded = cov.get("excluded_pre_scan", [])
    excl_rows = "".join(
        f"<li><code>{_esc(e.get('id'))}</code> "
        f"<span class='muted'>({_esc(e.get('reason'))}"
        f"{(': ' + _esc(', '.join(e.get('missing', [])))) if e.get('missing') else ''})</span></li>"
        for e in excluded
    ) or "<li class='muted'>none</li>"
    return (
        "<h2>Coverage (honest)</h2>"
        f"<p>Tested <strong>{len(tested)}</strong> of <strong>{len(planned)}</strong> "
        f"planned techniques ({round(cov.get('coverage_pct', 0) * 100)}%).</p>"
        f"<p class='muted'>In scope but not tested: "
        f"{_esc(', '.join(not_tested)) or 'none'}</p>"
        f"<p><strong>Excluded before the scan</strong> (and why):</p><ul>{excl_rows}</ul>"
    )


def _remediation_sources(sources: list[dict]) -> str:
    """Render the web-search citations for a remediation item, if any."""
    links = [
        f'<a href="{_esc(s.get("url"))}" target="_blank" rel="noopener noreferrer">'
        f'{_esc(s.get("title") or s.get("url"))}</a>'
        for s in (sources or []) if s.get("url")
    ]
    if not links:
        return ""
    return ("<div class='muted' style='font-size:.85rem;margin-top:.2rem'>Sources: "
            + " · ".join(links) + "</div>")


def _remediation_section(rem: list[dict]) -> str:
    if not rem:
        return ""
    items = "".join(
        f"<li>{_esc(r['control'])} "
        f"<span class='muted'>— addresses {r['addresses_findings']} finding(s)</span></li>"
        + (f"<div style='margin-top:.25rem'>{_esc(r['description'])}</div>"
           if r.get("description") else "")
        + _remediation_sources(r.get("sources", []))
        + "</li>"
        for r in rem
    )
    return f"<h2>Recommended controls</h2><ul>{items}</ul>"


def render(correlation: dict, out_path: Path) -> Path:
    c = correlation
    summary = c.get("coordinator_summary") or ""
    summary_html = f'<p class="summary">{_esc(summary)}</p>' if summary else ""
    raw = html.escape(json.dumps(c, indent=2, default=str))
    body = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>TRIDENT Report — {_esc(c.get('campaign_id', ''))}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color:#1b1b1b; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .25rem; }}
  h2 {{ margin-top: 2rem; }}
  .kpis {{ display:flex; gap:1rem; flex-wrap:wrap; margin:1rem 0; }}
  .kpi {{ background:#f4f4f4; border-radius:8px; padding:.6rem 1rem; min-width:120px; }}
  .kpi b {{ display:block; font-size:1.5rem; }}
  .muted {{ color:#666; }}
  .summary {{ background:#eef4ff; border-left:4px solid #3a6; padding:.6rem 1rem; border-radius:4px; }}
  table {{ border-collapse:collapse; width:100%; margin-top:.5rem; }}
  th,td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid #eee; font-size:.92rem; }}
  th {{ background:#fafafa; }}
  .chain {{ background:#fff8f0; border:1px solid #f0d8b8; border-radius:8px; padding:.8rem 1rem; margin:.6rem 0; }}
  .chain-steps {{ margin-top:.4rem; }}
  details > summary {{ cursor:pointer; color:#666; margin-top:2rem; }}
  pre {{ background:#f4f4f4; padding:1rem; overflow:auto; border-radius:6px; }}
</style></head>
<body>
<h1>TRIDENT Report — {_esc(c.get('campaign_id', ''))}</h1>
{summary_html}
<div class="kpis">
  <div class="kpi"><b>{c.get('total_techniques_fired', 0)}</b>techniques fired</div>
  <div class="kpi"><b>{c.get('total_successes', 0)}</b>successes</div>
  <div class="kpi"><b>{c.get('total_blocked', 0)}</b>blocked</div>
  <div class="kpi"><b>{c.get('total_failed', 0)}</b>failed</div>
  <div class="kpi"><b>{len(c.get('potential_chains', []))}</b>chains</div>
</div>
<p class="muted">Layers executed: {_esc(", ".join(c.get("layers_executed", [])))}</p>
{_chains_section(c.get("potential_chains", []))}
{_findings_table(c.get("findings", []))}
{_coverage_section(c.get("coverage", {}))}
{_remediation_section(c.get("remediation", []))}
<details><summary>Raw correlation JSON</summary><pre>{raw}</pre></details>
</body></html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    return out_path
