from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DUMP = ROOT / "test-dump"

BANKS = DUMP / "01-banks-digital"
BANKS_MESSY = DUMP / "02-banks-messy"
INVOICES = DUMP / "03-invoices"
GST = DUMP / "04-gst-json"
BOOKS = DUMP / "05-books-tally-zoho"
JUNK = DUMP / "06-unknown-junk"
MIXED = DUMP / "07-mixed-client-month"

HDFC = BANKS / "HDFC_Statement_Jul2026.pdf"
ICICI = BANKS / "ICICI_Statement_Jul2026.pdf"
SBI = BANKS / "SBI_Statement_Jul2026.pdf"

ACME = INVOICES / "Tax_Invoice_Acme.pdf"

GSTR_2B = GST / "GSTR-2B_July.json"
GSTR_1 = GST / "GSTR1_July.json"
GSTR_3B = GST / "GSTR3B_July.json"

TALLY_XML = BOOKS / "Tally_Daybook.xml"
TALLY_ZIP = BOOKS / "Tally_Backup.zip"
ZOHO_CSV = BOOKS / "Zoho_Books_Invoices.csv"

RANDOM_JPG = JUNK / "random_scan.jpg"
INVOICE_PHOTO = JUNK / "invoice_photo.png"
MEETING_NOTES = JUNK / "meeting_notes.docx"
