# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary:** Chartered Accountants (CAs), tax practitioners, and articled assistants/staff in India.
- **Situation:** Monthly and annual accounting cycles, GST return filing periods (GSTR-1, GSTR-3B, GSTR-2B reconciliation), tax audits.
- **Job:** Unpack messy client file dumps (PDF bank statements, Excel sheets, invoices, scans), extract structured transaction data, reconcile records, and produce GST- and Tally/Zoho-ready outputs without manual entry.

## Product Purpose

CA Unpacker transforms client monthly financial file dumps into clean, GST-ready Excel packs and accounting software imports directly on the CA's local PC. It eliminates manual data entry, format conversion, and reconciliation while guaranteeing complete data confidentiality.

## Positioning

100% local, privacy-guaranteed desktop processing ("Nothing is uploaded"). All parsing, OCR, and reconciliation execute entirely on the CA's local machine under `%LOCALAPPDATA%\CAUnpacker\`. Unlike cloud-based aggregators, it requires no cloud storage, no third-party data transmission, and zero client privacy risk.

## Operating Context

- **Environment:** Windows desktop PCs running Windows 10/11; local PyWebView interface (`apps/ui/`) and marketing/download landing pages (`designs/ca-unpacker-landing/`).
- **Inputs:** Client folders containing PDF bank statements (scanned or digital across Indian banks), Excel spreadsheets, sales/purchase registers, GSTR JSON files.
- **Outputs:** Standardized Excel packs, Tally XML / Zoho Books import formats, reconciliation master sheets.
- **Workflow:** Fast drag-and-drop dump of client files -> automatic classification & parsing -> inline validation/preview -> one-click export.

## Capabilities and Constraints

- **Technical Constraints:**
  - Frontend is HTML5, CSS3, and Vanilla JavaScript (`apps/ui/index.html`, `apps/ui/styles.css`, `apps/ui/app.js`) communicating with the Python backend via PyWebView API bindings (`window.pywebview.api`).
  - Must remain smooth and responsive within PyWebView's Windows WebView2 runtime.
  - Zero external cloud API calls for processing client financial documents.
- **Surface Targets:**
  - Desktop Application UI (`apps/ui/`): High utility, dense data presentation, live parsing feedback, file preview pane.
  - Landing Page (`designs/ca-unpacker-landing/`): Product showcase, trust signals, direct Windows installer download.
  - Surface focus is flexible and depends on the user's explicit task request.

## Brand Commitments

- **Tone & Identity:** Modern professional utility. Sleek typography, subtle borders, polished dark and light modes. Clean, authoritative, and dependable.
- **Voice:** Direct, precise, professional financial software terminology (GST, ITC, Reconciliation, Bank Statement Parsing, Tally XML). No marketing fluff or patronizing copy.
- **Standing visual preference (2026-09-15):** Contemporary, keyboard-first, high-density desktop tool. Rejected as too literal, retro, and low-utility: physical-world costume metaphors (printout spools, film benches, record almirahs). Craft bar sits alongside Linear / Arc / Raycast, Tally Prime / Busy, and Stripe / Vercel dashboards. No KPI-card SaaS dashboard, no retro skeuomorphism.

## Evidence on Hand

- Core Python parsing engine (`apps/engine/`) supporting bank layout patterns and PDF extractors.
- Working PyWebView desktop shell (`apps/desktop/app.py`).
- Desktop UI (`apps/ui/index.html`, `apps/ui/styles.css`, `apps/ui/app.js`) with preview panes and stage navigation.
- Product roadmaps and vision documents (`README.md`, `STAGES.md`, `BUILD-PLAN.md`, `PRODUCT-VISION-CHAT-SUMMARY-2026-08-17.md`).

## Product Principles

1. **Local-First & Confidential:** Client financial data never leaves the local machine; interface emphasizes security, isolation, and local certainty.
2. **High-Efficiency Ergonomics:** Designed for high volume during tax deadlines—clear visual hierarchy, rapid scanning, keyboard-friendly navigation.
3. **Deterministic & Verifiable:** Every parsed value links back to original source documents; transparent parsing status and clear error indicators.
4. **Modern Professional Finish:** Polished aesthetics with crisp borders, intentional typography, and unified light/dark themes without sacrificing information density.

## Accessibility & Inclusion

- High contrast text readability for complex data tables and financial numbers.
- Legible tabular numerals and aligned financial figures.
- Clear visible focus states for keyboard-driven workflows.
