# Bugs to Fix

Owner: Benny

1. ~~Fix the bank statement-to-Excel parsing.~~ Done — wrapped/page-break rows and running-balance repair are locked in (`c517216`).
2. ~~Make Restart clear only the data, without restarting the app.~~ Done — **Delete everything** now wipes the library and rebuilds it empty in the same window (`wipe_and_reset`); the app returns to the first-run setup instead of spawning a new process. Jobs still running during the wipe are stopped from recreating data.
3. Persist the firm name, folder name, and client name after they are entered, so reopening the app does not require entering them again.
4. Improve processing for scanned PDFs and PDFs with different layouts and formats.
5. Modernize the UI: it currently feels dated and overwhelming, especially because all post-processing results are dumped on the user at once. Present results progressively in a clearer workflow.
6. ~~Ask for and save a separate profile for each client of the firm; the app is currently not collecting this information.~~ Done — profession catalog plus per-client rule packs; see `docs/CLIENT-PROFILES.md`. Treatment checks are prompts only, not postings.
7. Make citations more polished and easier to review, similar to NotebookLM.
8. ~~Add an in-app file preview pane, similar to the Codex app, so users can inspect files without leaving the app.~~ Done — click a file name in the period list, or **Open full page** from a crop. PDF pages, images, JSON, CSV/XLSX tables, TXT/XML and ZIP listings render in a right-hand pane; other types offer **Open in app**. See `docs/PREVIEW.md`.
