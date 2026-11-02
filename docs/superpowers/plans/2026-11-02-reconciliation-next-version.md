# Reconciliation — what we add next (plan you can read)

Written 2 Nov 2026. No technical words on purpose. If something here is unclear, that is my fault, tell me.

---

## 1. Where the feature stands today

The app already does the hard mechanical part:

- It compares the purchases in the client's books against the tax portal download (the 2B file).
- It writes one Excel with all the rows and a short list of the leftovers.
- It shows a tray inside the app with five labels: **Matched**, **Only in books**, **Only in 2B**, **Amount mismatch**, **Likely (confirm)**.
- Bank statement lines are used only as a side hint, and are clearly labelled as a hint, not a match.

What it cannot do is just as important:

- It decides and then stops. The accountant cannot agree, disagree, or make a note.
- Every time the month is re-run, all of it is thrown away and rebuilt.
- A row says *what* it is, never *why* it is.
- It counts rows, not rupees.
- The "Reconciliation Desk" entry in the left menu is greyed out and marked SOON, so the feature has no home of its own.

So today it is a good report. It is not yet a workspace.

---

## 2. What an accountant actually does with a reconciliation

1. Look at the money at stake first, to decide whether it is worth an hour.
2. Work only the problem rows, biggest first.
3. Decide each one: agree it, fix it in the books, chase the supplier, or note that a credit note is coming.
4. Hand over proof of what was decided, by whom, and when.
5. Come back next month without redoing the decisions already taken.

The plan below is built in that order, because that is the order of the work.

---

## 3. The plan — five parts

### Part 1 — Show the money, not the count
- At the top of the tray: total on the portal, total in the books, the gap, **credit at risk** (portal entries with nothing in the books) and **credit claimed without support** (books entries missing on the portal).
- Every figure is clickable and filters the list below it.
- The Excel cover page carries the same rupee figures, not just row counts.
- If there is no portal file that month, show what is missing instead of hiding the whole section.

*Why first:* the rupee gap is the only number that decides whether the rest of the work happens.

### Part 2 — Tell me why each row is flagged
- Each row carries one plain sentence, for example: "Same supplier and invoice, amount differs by 40.00", "Same supplier and amount, date is 3 days apart", "No such invoice on the portal".
- Exceptions sort by money, largest first, by default.
- A row can be searched by supplier name or GSTIN.

*Why:* it removes the double-checking that currently happens by hand.

### Part 3 — Let me decide, and remember it
- Buttons on each row: **Accept**, **Reject**, **Add note**, with short ready-made reasons (rate difference, credit note pending, supplier has not filed, wrong GSTIN, and one free-text box).
- The decision is saved with date and time and lives with that month.
- Re-running the month keeps the decisions and only flags genuinely new rows.
- A decision never hides a difference: the rupee gap stays visible underneath.

*Why:* this is the part that turns the tray into a working tool. Without memory, an accountant re-does the same thirty decisions every time.

### Part 4 — Handle the messy real cases
- One invoice split across two portal lines, and the reverse (two invoices merged into one on the portal).
- The same invoice appearing twice on one side.
- Credit notes: today they are quietly dropped, so they vanish from view. They should appear as their own group, so nothing is silently lost.
- A per-client tolerance for dates (default same day, optional 7 days) and for amounts (default 1 rupee), because some clients are always a day off.
- Compare tax by tax (taxable value, central, state, integrated), not only the invoice total, because a notice is almost always about tax.

*Why:* these are the cases that eat an afternoon.

### Part 5 — Give it a home, and make the file audit-proof
- Turn the greyed-out **Reconciliation Desk** into the real workspace, one month at a time, so nobody has to open a pack to find it.
- Export only the exceptions, as a small file that can be sent to the client.
- A one-page summary for the working papers: counts, rupees, each decision, who and when.

*Why:* the file has to survive an audit and a partner's review.

---

## 4. What we deliberately do not add

- No portal login, no filing, no automatic edits to the books.
- Nothing leaves the computer.
- A machine guess never becomes a fact on its own; only a person can accept a row.

---

## 5. Order of work and rough size

| Step | What the accountant gets | Effort |
|---|---|---|
| 1 | Rupee summary, clickable filters | about half a day |
| 2 | "Why" sentence per row, sorted by money, search | about half a day |
| 3 | Accept / reject / note, remembered across re-runs | 2–3 days |
| 4 | Credit notes, split and duplicate invoices, tolerances, tax-by-tax | 3–4 days |
| 5 | Desk as a real place, exceptions export, one-page audit summary | about 2 days |

Steps 1–3 deliver roughly most of the day-to-day value and can be finished first and shown to a CA. Total for everything: about two weeks of focused work.

---

## 6. How we will know it works

- Take one real month of a client: books plus portal file, with a few deliberate problems planted.
- Every problem must land in the right group, with the right rupee figure, before the next step begins.
- After re-running the same month, every decision taken must still be there, unchanged.
- Everything that works today must keep working; this is an addition, not a rewrite.
- Nothing is called finished until an accountant can go from "month loaded" to "decisions done" without opening Excel.

---

## 7. Choices I need from you

1. **Order:** money summary first, or decision buttons first? My recommendation is the order above (money, then why, then decide).
2. **Demo timing:** is there anyone you want to show this to soon? If yes, we stop after step 2 and show that.
3. **Tolerance:** per client (saved once, remembered) or per month (asked each time)?
4. **Audit trail:** is a saved decision with date enough for now, or do you want a printable record from day one? My recommendation is a saved trail now, printing in step 5.
5. **Credit notes:** should they be grouped separately, or shown inside the normal list with a label?
