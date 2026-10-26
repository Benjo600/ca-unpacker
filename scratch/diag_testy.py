import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.engine.pdf_extract import extract_pdf
from apps.engine.parsers.bank.profiles import detect_profile
from apps.engine.parsers.bank.parser import _rows_from_lines, _rows_from_extracted_words
from apps.engine.parsers.bank.money import DATE_RE, amounts_in
from apps.engine.parsers.bank.patterns import clean_text, is_boilerplate, looks_like_txn

import pickle

path = Path('testy stss.pdf')
cache = Path('scratch/testy_ext.pkl')
if cache.exists():
    with open(cache, 'rb') as f:
        ext = pickle.load(f)
else:
    ext = extract_pdf(path)
    with open(cache, 'wb') as f:
        pickle.dump(ext, f)

header = "\n".join(page.text for page in ext.pages[:2])
profile = detect_profile(header, path.name)
print(f"Profile: {profile.key} ({profile.label})")

print("\n--- FIRST 30 EXTRACTED LINES ---")
for i, line in enumerate(ext.lines[:30]):
    text = clean_text(line.text)
    has_date = bool(DATE_RE.search(text))
    amounts = amounts_in(text)
    print(f"[{i:02d}] (page {line.page}) date={has_date} amounts={amounts} :: {text}")

line_rows, line_cand = _rows_from_lines(ext.lines, profile, path.name)
word_rows, word_cand = _rows_from_extracted_words(ext, profile, path.name)
print(f"\nLine rows: {len(line_rows)} (candidates: {line_cand})")
print(f"Word rows: {len(word_rows)} (candidates: {word_cand})")

if line_rows:
    print("\nSample line row 0:", line_rows[0])
    print("Sample line row 1:", line_rows[1] if len(line_rows) > 1 else "none")

from apps.engine.parsers.bank.parser import _finish_rows, _choose_rows, _balance_near, OPENING_RE, CLOSING_RE
opening = _balance_near(ext, OPENING_RE)
closing = _balance_near(ext, CLOSING_RE)
print(f"Opening balance: {opening}, Closing balance: {closing}")

fin_lines = _finish_rows(line_rows, opening, None, None, profile)
fin_words = _finish_rows(word_rows, opening, None, None, profile)
print(f"Finished lines count: {len(fin_lines)}, Finished words count: {len(fin_words)}")

chosen, cand, strat = _choose_rows(
    opening, closing,
    ("columns", fin_words, word_cand),
    ("lines", fin_lines, line_cand),
)
print(f"Chosen: strategy={strat}, rows={len(chosen)}, candidates={cand}")

