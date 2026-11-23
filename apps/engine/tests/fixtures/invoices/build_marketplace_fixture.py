"""Rebuild the marketplace invoice fixture with fictional identities.

The original ``flpk.pdf`` was a real Flipkart tax invoice carrying a customer's
name, address, GSTIN, PAN, CIN, order id and a device serial. It was committed
to a public repo, so every personally identifying string is replaced here.

Text is replaced in place with PDF redactions, which keeps the ruling lines,
column positions, fonts and amounts exactly as the parser expects them.

Run it only when the fixture needs regenerating::

    python -m apps.engine.tests.fixtures.invoices.build_marketplace_fixture \
        --source /path/to/real.pdf --out apps/engine/tests/fixtures/invoices/flpk.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Every replacement is fictional. Amounts are untouched: they are not personal.
REPLACEMENTS = (
    ("Health &amp; Happiness Private Limited", "Example Trading Private Limited"),
    ("Health & Happiness Private Limited", "Example Trading Private Limited"),
    ("Health &amp; Happiness", "Example Trading"),
    ("29AADCH8449J1Z0", "29AAACX1234C1Z5"),
    ("aadch8449j", "aaacx1234c"),
    ("U52100HR2016PTC073827", "U72900KA2019PTC123456"),
    ("Darshan V", "Test Buyer"),
    ("No 6, main road.", "12 Sample Street."),
    ("No 6, main road,", "12 Sample Street,"),
    ("Bangalore Division 560090", "Bengaluru Division 560001"),
    ("OD433324739056338100", "OD000000000000000001"),
    ("FAIH9X2500133941", "EXM9X2500001111"),
    ("BFF9725004803384", "EXM9X2500002222"),
    ("S5N0CV13T536217", "SN0000000000001"),
    ("COMGNRNUKRMMXNZQ", "FSN0000000000000"),
    (
        "Sy no 18/2,18/3,18/4 19/1,19/2,19/3,20/1,20/2,20/3,21/2,22/2,23/2,23/3,23/4 "
        "Taverekere venkatapura, hosakote taluk,",
        "Plot 44, Industrial Estate, Phase 2,",
    ),
    (
        "nadagudi hobli,bangalore 562122, Bangalore , KARNATAKA, India - 562122, IN-KA",
        "Whitefield, Bengaluru 560066, Karnataka, India - 560066, IN-KA",
    ),
    (
        " , Unit No.1001, 10th Floor, Park Centra Sector-30, GURUGRAM, HARYANA - 122001",
        " , Unit No.1, 1st Floor, Sample Tower, BENGALURU, KARNATAKA - 560001",
    ),
)

# Fragments that must not survive anywhere in the rebuilt file. Checked after
# the redactions, because a silently missed string is the whole risk here.
SECRETS = (
    "Darshan",
    "aadch8449j",
    "29AADCH8449J1Z0",
    "U52100HR2016PTC073827",
    "OD433324739056338100",
    "FAIH9X2500133941",
    "BFF9725004803384",
    "S5N0CV13T536217",
    "COMGNRNUKRMMNZQ",
    "COMGNRNUKRMMXNZQ",
    "Taverekere",
    "nadagudi",
    "562122",
    "Park Centra",
    "main road",
)


def _redact(document, page, needle: str, replacement: str) -> int:
    """Remove the original glyphs, then draw the replacement ourselves.

    ``apply_redactions(text=...)`` inserts text that some extractors cannot
    read back, which would make the fixture behave differently from the real
    invoice. Drawing with an explicit standard font keeps every engine seeing
    the same page.
    """
    hits = page.search_for(needle)
    for rect in hits:
        page.add_redact_annot(rect)
    if hits:
        page.apply_redactions(images=0, graphics=0)
    for rect in hits:
        placed = False
        for size in (9, 8.5, 8, 7.5, 7, 6.5, 6):
            box = rect + (-1, -1, 1, 1)
            if page.insert_textbox(
                box,
                replacement,
                fontsize=size,
                fontname="helv",
                align=0,
                color=(0, 0, 0),
            ) >= 0:
                placed = True
                break
        if not placed:
            page.insert_text((rect.x0, rect.y1), replacement, fontsize=6, fontname="helv")
    return len(hits)


def rebuild(source: Path, out: Path) -> None:
    import pymupdf

    document = pymupdf.open(source)
    missed: list[str] = []
    for page in document:
        for original, replacement in REPLACEMENTS:
            if _redact(document, page, original, replacement) == 0:
                missed.append(original[:40])
    document.save(str(out), garbage=4, deflate=True)

    text = "".join(page.get_text() for page in pymupdf.open(out))
    leaked = [secret for secret in SECRETS if secret.lower() in text.lower()]
    document.close()
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    if missed:
        print("could not find these strings to replace (check them by hand):")
        for item in missed:
            print("  -", item)
    if leaked:
        raise SystemExit(f"refusing to finish: personal strings survived: {leaked}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    rebuild(args.source, args.out)


if __name__ == "__main__":
    main()
