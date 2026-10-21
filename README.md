# CLCS submissions -> SharePoint feed

A monthly GitHub job reads the public UN CLCS submissions page, works out
`Extended_continental_shelf_status` for every State, and publishes **one feed item per State whose value changed**
(`docs/feed.xml`). A Power Automate flow (standard RSS trigger) writes each item into `State_Legal_Institutional`.
No ISA data is stored here: only values derived from the public page and the State names/IDs in `names.json`.

## Format rules (in clcs_feed.py)
- Solo submissions are grouped by status with one year per submission: `Submissions with recommendations (2007, 2009, 2009)`.
- Each joint submission is its own clause. Revised submissions use the same pattern with "Revised" in front.
- Clauses are ordered by submission year, regardless of status.
- Status comes from the row colour on the page (red = active, none = pending, green = recommendations, blue = deposit).
- A State whose row colour and recommendation dates disagree is NOT published; it is listed in `needs_review.txt`.
- Set `GROUP_SOLO_BY_STATUS = False` for one clause per submission.

## One-time setup
1. Create a free GitHub account and a **public** repo; upload everything in this folder (keep the `.github` folder).
2. Repo > Settings > Pages > Deploy from branch > `main` / `/docs`. The feed is then at `https://luca-tjo.github.io/clcs-feed/feed.xml`.
3. Repo > Actions > "CLCS submissions check" > Run workflow > mode **init** (records today's page as the baseline, publishes nothing).
4. Review `docs/values.csv` (written by `python clcs_feed.py --dry-run`, or the workflow's **dry-run** mode). After that review: run it again with mode **publish-all** to push every State once.
5. From then on the monthly run publishes only genuine changes.

## Power Automate flow (all standard connectors)
1. New automated cloud flow, trigger **RSS - When a feed item is published**. Feed URL = the feed above; "Chosen property" = PublishDate.
2. **SharePoint - Get items**: site = Communication site, list = State_Legal_Institutional,
   Filter Query (plain text box) = `Title eq '` + the **Feed title** token + `'`.
   (Côte d'Ivoire contains an apostrophe and needs the title wrapped in `replace(...,'''','''''')`.)
3. **Condition**: `length(body('Get_items')?['value'])` is greater than `0`.
4. If yes, **SharePoint - Update item**: Id = `first(body('Get_items')?['value'])?['ID']`,
   Title = `first(body('Get_items')?['value'])?['Title']`, Extended_continental_shelf_status = the **Feed summary** token.
   Leave every other field untouched.
5. Test: run the GitHub job in publish-all mode, then use Test > Automatically in the flow.

## Handover
The flow runs under its owner's account. Add a colleague as co-owner (flow > Share) before the internship ends.
The repo owner receives GitHub's failure emails if the page layout changes and the script stops (it refuses to publish if it cannot find the tables).
