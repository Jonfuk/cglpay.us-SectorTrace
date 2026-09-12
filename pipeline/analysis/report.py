"""Admin-only report bundle serializers; never used by public exports."""
from __future__ import annotations

import csv
import io
import json
from html import escape


def bundle(payload: dict, fmt: str = "json") -> tuple[str, str]:
    if fmt == "json":
        return json.dumps(payload, indent=2, sort_keys=True, default=str), "application/json"
    if fmt == "csv":
        rows = payload.get("signals", [])
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=(sorted(rows[0]) if rows else ["signal_id"]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue(), "text/csv"
    if fmt == "html":
        body = "".join(f"<tr><td>{escape(str(row.get('signal_id', '')))}</td><td>{escape(str(row.get('signal_type', '')))}</td><td>{escape(str(row.get('direction', '')))}</td></tr>" for row in payload.get("signals", []))
        return "<!doctype html><title>SectorTrace analysis report</title><table><tr><th>Signal</th><th>Type</th><th>Direction</th></tr>" + body + "</table>", "text/html; charset=utf-8"
    raise ValueError("report format must be json, csv or html")
