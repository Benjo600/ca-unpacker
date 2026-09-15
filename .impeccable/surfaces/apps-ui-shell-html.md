---
version: 1
slug: "apps-ui-shell-html"
primary_target: "apps/ui/shell.html"
related_targets: []
---

# Surface brief — CA Unpacker app shell

- **Scope:** Desktop application shell (`apps/ui/shell.html`); the frame that carries Clients, Intake, Recon, and Preview.
- **Mode:** Operate.

## Audience and job

CA partners and articled assistants running 20–50 client files a period on a Windows PC during GST filing week. They must see, at a glance, what is parsed, held, or failed, and verify any figure against its source without leaving the keyboard.

## Direction contract

**THESIS:** A contemporary, keyboard-first workbench where the client file is the primary object and every parsed figure is one keystroke from its source. It refuses two things: the KPI-card SaaS dashboard, and the physical-world costume (no printout spools, film rails, or record almirahs).

**OWN-WORLD:** Dark-first graphite #0B0D0F, panels #111417 and #171B1F, hairlines at 8% white; text #ECEEF1 on #98A2AD secondary. One signal cobalt #4C7DFF for action and selection; amber #E0A33E only for attention/ITC mismatch; green #3FB950 and red #F85149 for state. Archivo for UI, Spline Sans Mono tabular for every figure and identifier, both self-hosted woff2 (no CDN). One neutral document ground #E9EBED carries source previews and the output sheet so a document never reads as chrome. Squares, hairlines, 6px radius ceiling, no glass, no gradients, 26–28px rows.

**STORY:** The assistant drops a client folder, watches files classify and parse, spot-checks any figure against its source in one keystroke, reconciles GSTR-2B against books, then exports a Tally-ready pack — all offline. They trust that nothing left the machine.

**FIRST VIEWPORT:** A 40px top bar (identity, client/period context, command field, local-only pill, theme, account) and a 28px status bar (counts, engine, quota, keyboard hints). Between them: a 264px client rail of dense rows with state marks, the main work surface carrying the file table in monospace figures with stage progress, and a 380px inspector showing the selected file's source with a tie-out marker. Run/Export sits top-right of the work surface.

**FORM:** Standing exit — the category standard (contemporary professional desktop tool) chosen by the user after two re-rolls. Ordered-list position: canon, the permanent alternative, not a rolled world. Seed key `ee42843a`.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
