from __future__ import annotations

import html
import json
from pathlib import Path

from apps.engine.parsers.bank.parser import parse_bank_pdf
from apps.engine.validators.balance import check_balance

PDF = Path(r"d:\All downloads\07-Documents-PDFs\09-Needs-Review\Opaque-Scans\testy stss.pdf")
OUT_DIR = Path.home() / "AppData" / "Local" / "Temp" / "ca-unpacker-compare"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed = parse_bank_pdf(PDF)
    check = check_balance(parsed["rows"], parsed["opening_balance"], parsed["stated_closing"])
    summary = {
        "engine": parsed.get("engine"),
        "strategy": parsed.get("parse_strategy"),
        "profile": parsed.get("profile"),
        "pdf_type": parsed.get("pdf_type"),
        "pages": parsed.get("page_count"),
        "opening": parsed.get("opening_balance"),
        "closing": parsed.get("stated_closing"),
        "rows": len(parsed.get("rows") or []),
        "status": check.get("status"),
        "computed_closing": check.get("computed_closing"),
        "broken_at_row": check.get("broken_at_row"),
        "flags": check.get("flags"),
    }
    (OUT_DIR / "parse.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rows_html = []
    for index, row in enumerate(parsed.get("rows") or [], start=1):
        flags = ",".join(row.get("flags") or [])
        mark = " mismatch" if "balance_mismatch" in (row.get("flags") or []) or "running_balance_break" in (row.get("flags") or []) else ""
        rows_html.append(
            "<tr class='{mark}'><td>{i}</td><td>{date}</td><td>{desc}</td><td class='num'>{debit}</td><td class='num'>{credit}</td><td class='num'>{bal}</td><td>{flags}</td></tr>".format(
                mark=mark.strip(),
                i=index,
                date=html.escape(str(row.get("date") or "")),
                desc=html.escape((row.get("description") or "")[:120]),
                debit="" if row.get("debit") is None else f"{row['debit']:,.2f}",
                credit="" if row.get("credit") is None else f"{row['credit']:,.2f}",
                bal="" if row.get("balance") is None else f"{row['balance']:,.2f}",
                flags=html.escape(flags),
            )
        )
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Parser vs statement</title>
<style>
body {{ margin:0; font-family: Segoe UI, sans-serif; height:100vh; display:flex; }}
.left {{ width:46%; overflow:auto; background:#111; }}
.left img {{ width:100%; display:block; }}
.panel {{ width:54%; overflow:auto; padding:16px 20px; background:#fff; color:#111; }}
h1 {{ font-size:18px; margin:0 0 8px; }}
.meta {{ font-size:13px; color:#333; margin-bottom:12px; }}
table {{ border-collapse:collapse; width:100%; font-size:12px; }}
th, td {{ border-bottom:1px solid #ddd; padding:4px 6px; text-align:left; vertical-align:top; }}
.num {{ text-align:right; font-variant-numeric: tabular-nums; }}
tr.mismatch {{ background:#ffe8e8; }}
</style></head>
<body>
<div class="left">
<img src="/page-1.png" alt="page 1">
<img src="/page-2.png" alt="page 2">
<img src="/page-3.png" alt="page 3">
<img src="/page-4.png" alt="page 4">
<img src="/page-5.png" alt="page 5">
<img src="/page-6.png" alt="page 6">
</div>
<div class="panel">
<h1>What the parser extracted</h1>
<div class="meta">
strategy <b>{html.escape(str(summary['strategy']))}</b> ·
engine <b>{html.escape(str(summary['engine']))}</b> ·
profile <b>{html.escape(str(summary['profile']))}</b> ·
{summary['rows']} rows ·
opening {summary['opening']} ·
printed close {summary['closing']} ·
computed {summary['computed_closing']} ·
<b>{html.escape(str(summary['status']))}</b>
{'' if not summary['broken_at_row'] else ' · break at row '+str(summary['broken_at_row'])}
</div>
<table>
<thead><tr><th>#</th><th>Date</th><th>Narration</th><th>Debit</th><th>Credit</th><th>Balance</th><th>Flags</th></tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</div>
</body></html>
"""
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    print(json.dumps(summary))
    print("wrote", OUT_DIR / "index.html")


if __name__ == "__main__":
    main()
