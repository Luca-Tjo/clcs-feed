# ISA state feeds

A weekly GitHub job reads public UN pages, works out a value per State for one SharePoint column each,
and publishes **one RSS feed per column** with one item per State whose value changed. A Power Automate
flow per column (standard RSS trigger) writes each item into `State_Legal_Institutional`.
No ISA data is stored here: only values derived from public pages and the State names/IDs in `names.json`.

| Feed | Source page | SharePoint column | Feed URL |
|---|---|---|---|
| `clcs` | UN CLCS submissions | `Extended_continental_shelf_status` | https://luca-tjo.github.io/isa-state-feeds/clcs/feed.xml |
| `unclos` | UN Treaty Collection XXI-6 | `UNCLOS_membership` | https://luca-tjo.github.io/isa-state-feeds/unclos/feed.xml |
| `agreement-1994` | UN Treaty Collection XXI-6-a | `1994_agreement_status` | https://luca-tjo.github.io/isa-state-feeds/agreement-1994/feed.xml |

## Layout
- `feeds.py`: runs any feed (modes below). `FEEDS` at the top lists them.
- `sources/`: one module per source page. `clcs.py` (row colours), `treaty.py` (UN treaty status tables, one class per treaty).
- `common.py` + `names.json`: page names -> list Titles. Spelling differences go in `ALIASES`.
- `data/<feed>/`: baseline (`state.json`), `needs_review.txt`, `last_run.txt`.
- `docs/<feed>/`: the published `feed.xml`, and `values.csv` from a dry run.
- `tools/samples/`: saved copies of each page for offline testing (`--html`).

## Modes (Actions > "ISA state feeds" > Run workflow, pick feed + mode)
- **normal**: publish only States whose value changed (what the Monday schedule runs, for all feeds).
- **init**: record today's values as the baseline, publish nothing. Run once when a feed is added.
- **dry-run**: write `docs/<feed>/values.csv` to review; nothing is published.
- **publish-all**: publish every State once (first fill of a column).
- **test-one**: publish a single State (default France) to test a flow.

## Format rules
**CLCS**: solo submissions grouped by status, `pending consideration` for not yet considered; each joint submission is
its own clause; revised submissions prefixed "Revised"; clauses ordered by year. Status comes from the row colour.
A State whose row colour and recommendation dates disagree is not published; it is listed in `needs_review.txt`.

**UNCLOS**: `Signatory and Party: <signature> | <ratification>`, `Party: <date> <a/d/c>`, `Signatory: <date>`, `Non Party`.

**1994 Agreement**: `Signatory and Party: <signature> | <consent>`, `Party: <date>`, `Signatory but not Party: <date>`,
`Non Party (Provisional Application:<date>)`, `Non Party`. The "notification of non-provisional application" column is ignored.

States not on a treaty page get `Non Party`. Treaty participants that are not rows in the list are listed in
`NOT_IN_LIST` (sources/treaty.py); any other unmatched name is flagged in `needs_review.txt`.

Every source aborts without publishing if the page layout changes (missing tables, changed column headers, too few rows),
and GitHub emails the repo owner that the run failed. One broken feed does not stop the others.

## Adding a feed
1. A module or class in `sources/` with `COLUMN`, `URL`, `FEED_TITLE` and `build(html, names) -> (values, review, unmatched)`.
   Another UN treaty is just a new class in `treaty.py` with its header list and a `fmt` function.
2. Add it to `FEEDS` in `feeds.py` and to the `feed` options in `.github/workflows/feeds.yml`.
3. Save a sample page into `tools/samples/`, dry-run against it, compare with the current SharePoint export.
4. Run **init** on GitHub, copy a Power Automate flow (below), then **publish-all**.

## Power Automate flow (one per feed, all standard connectors)
1. Trigger **RSS - When a feed item is published**. Feed URL = the feed above; chosen property = PublishDate.
2. **SharePoint - Get items**: list `State_Legal_Institutional`, Top Count 1,
   Filter Query (plain text box) = `Title eq '` + expression `replace(triggerOutputs()?['body/title'],'''','''''')` + `'`.
3. **Condition**: `length(outputs('Get_items')?['body/value'])` is greater than `0`.
4. True: **SharePoint - Update item**: Id = `first(outputs('Get_items')?['body/value'])?['ID']`,
   Title = `first(outputs('Get_items')?['body/value'])?['Title']`, the feed's column = **Feed summary**. Leave every other field empty.
5. False: **Send an email (V2)** to the owner with Feed title and Feed summary.

For a new column: open an existing flow > **Save As**, change the feed URL and the column in Update item, turn it on.
The trigger only picks up items published after the flow is on, so turn the flow on before running publish-all.

## Handover
The flows run under their owner's account: add a colleague as co-owner (flow > Share) before the internship ends.
The repo owner receives GitHub's failure emails: add a collaborator or transfer the repo to an ISA account.
