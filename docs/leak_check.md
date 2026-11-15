# leak check: what can the agent see?

checked the round-2 messy monday boxes (morning2-k2, with and without the handbook) by building the
Docker image and listing every file outside system folders, then searching their contents.

**what's in the box**
- `/app/inbox/`: the 15 new supplier invoice emails
- `/app/company/finance/invoice_tracker_2026Q4.csv` (the file to edit) and `finance/archive/` (Q2, Q3)
- `/app/company/gmail|slack|jira/`: 1,241 emails, 833 slack threads, 729 tickets (Redwood corpus + our
  finance history)
- `/app/company/drive/AP_Policy_2026.md`: only in the handbook version, states the OLD rules by design
- nothing else of ours: home dotfiles and system files only

**what's not in the box**
- no `tests/`, no `expected.json`, no `solution/`. Valkyrie copies the grader in only after the agent stops
- each new invoice number appears only in its own inbox email: not in the tracker, not in any other doc
- the current habits are never written as text: no "REVIEW:" outside the tracker files, no "$10,000",
  no mention of Tomasz outside the tracker. The only way to learn them is the tracker rows
- file names that contain words like "check" or "test" are Redwood's own docs (e.g. onboarding
  checklists), unrelated to grading

**verdict:** no leak. The agent can't read the answer. The only way to score is to work it out.
