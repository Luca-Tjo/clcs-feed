#!/usr/bin/env python3
"""Read the UN CLCS submissions page and publish an RSS feed of changed
Extended_continental_shelf_status values (one feed item per State).

Modes
  python clcs_feed.py --init           record current values as the baseline, publish nothing
  python clcs_feed.py --publish-all    publish every State that appears on the page
  python clcs_feed.py                  normal monthly run: publish only States whose value changed
  python clcs_feed.py --only "[S59] France"   publish just that State (to test the flow)
  python clcs_feed.py --dry-run        write docs/values.csv for review, change nothing else
  add  --html saved_page.html          read a saved copy of the page instead of fetching it
"""
import argparse, csv, hashlib, json, re, sys, datetime as dt
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape
from bs4 import BeautifulSoup

URL = "https://www.un.org/depts/los/clcs_new/commission_submissions.htm"
ROOT = Path(__file__).parent
FEED, STATE, REVIEW, LASTRUN = ROOT/"docs/feed.xml", ROOT/"state.json", ROOT/"needs_review.txt", ROOT/"last_run.txt"
VALUES_CSV = ROOT/"docs/values.csv"
FEED_URL_HINT = "https://luca-tjo.github.io/clcs-feed/feed.xml"
KEEP_DAYS = 45                       # feed items older than this are dropped
GROUP_SOLO_BY_STATUS = True          # False = one clause per submission
SOLO_WITH_AND = {"Trinidad and Tobago", "United Kingdom of Great Britain and Northern Ireland"}
ALIASES = {"republic of korea": "korea republic of", "viet nam": "vietnam", "russian federation": "russia",
           "tanzania": "united republic of tanzania", "federated states of micronesia": "micronesia federated states of"}
COLOURS = {"rgba(245,122,122,0.3)": "active", "rgba(102,255,153,0.4)": "recs", "rgba(102,255,255,0.4)": "deposit"}
WORD = {"recs": "with recommendations", "deposit": "with recommendations followed by deposit",
        "active": "under active consideration", "awaiting": "pending consideration"}
SOLO_ORDER = ["deposit", "recs", "active", "awaiting"]

def norm(s):
    s = re.sub(r"\bthe\b", "", (s or "").lower())
    s = s.replace("united kingdom of great britain and northern ireland", "united kingdom")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def status_of(td, tr):
    # colour is normally on each cell, but some rows (e.g. Nigeria) carry it on the <tr> instead
    m = re.search(r"background-color:\s*([^;]+)", td.get("style") or "") or re.search(r"background-color:\s*([^;]+)", tr.get("style") or "")
    return COLOURS.get(re.sub(r"\s+", "", m.group(1)) if m else "", "awaiting")

def split_states(title):
    for a, b in (("United Kingdom of Great Britain and Northern Ireland", "United Kingdom"), ("(Tokelau)", ""),
                 ("Togolese Republic", "Togo"), ("Republic of Benin", "Benin"),
                 ("Republic of Mauritius", "Mauritius"), ("Republic of Seychelles", "Seychelles")):
        title = title.replace(a, b)
    t = re.sub(r"^\s*joint submission( of| by)?( the)?\s*", "", title, flags=re.I).strip()
    t = re.sub(r"\s+(concerning|in respect of|-).*$", "", t)
    return [re.sub(r"^the\s+", "", p.strip(), flags=re.I) for p in re.split(r",\s*|\s+and\s+", t) if p.strip()]

def parse(html):
    tabs = BeautifulSoup(html, "lxml").find_all("table")
    if len(tabs) < 4: raise SystemExit("PARSE ERROR: expected 4 tables, found %d" % len(tabs))
    rows = []
    for ti, revised in ((2, False), (3, True)):
        for r in tabs[ti].find_all("tr")[1:]:
            c = r.find_all("td")
            if len(c) < 8: continue
            a = c[1].find("a")
            link = re.sub(r"\s+", " ", (a or c[1]).get_text(" ", strip=True))
            joint = bool(re.match(r"joint", link, re.I)) or ((("," in link) or (" and " in link))
                    and link not in SOLO_WITH_AND and "revised" not in link.lower())
            base = re.sub(r" - .*$", "", link)
            states = split_states(base) if joint else [re.sub(r"^The ", "", base)]
            if joint and not re.match(r"joint", link, re.I): link = "Joint submission by " + link
            link = link.replace("United Kingdom of Great Britain and Northern Ireland", "United Kingdom") if joint else link
            ym = re.search(r"(\d{4})\s*$", c[2].get_text(strip=True))
            status = status_of(c[-1], r)
            has_recs = bool(c[5].get_text(strip=True))
            rows.append(dict(no=c[0].get_text(strip=True).rstrip("."), revised=revised, joint=joint, title=link,
                             states=states, year=int(ym.group(1)) if ym else None, status=status,
                             conflict=has_recs != (status in ("recs", "deposit"))))
    n_orig, n_rev = sum(not r["revised"] for r in rows), sum(r["revised"] for r in rows)
    if n_orig < 90 or n_rev < 8: raise SystemExit(f"PARSE ERROR: only {n_orig} original / {n_rev} revised rows found")
    return rows

def value_for(state, rows):
    me = norm(state)
    mine = [r for r in rows if me in {norm(x) for x in r["states"]}]
    parts = []                                         # (earliest year, order, text)
    for revised in (False, True):
        solo = [r for r in mine if not r["joint"] and r["revised"] == revised]
        pre = "Revised s" if revised else "S"
        if GROUP_SOLO_BY_STATUS:
            for st in SOLO_ORDER:
                ys = sorted(r["year"] for r in solo if r["status"] == st and r["year"])
                if ys: parts.append((ys[0], f"{pre}ubmissions {WORD[st]} ({', '.join(map(str, ys))})"))
        else:
            for r in solo: parts.append((r["year"] or 0, f"{pre}ubmission {WORD[r['status']]} ({r['year']})"))
    for r in [r for r in mine if r["joint"]]:
        w = "pending consideration" if r["status"] in ("active", "awaiting") else WORD[r["status"]]
        parts.append((r["year"] or 0, f"{r['title']} {w} ({r['year']})"))
    parts.sort(key=lambda p: p[0])                     # by submission date, regardless of status
    return "; ".join(t for _, t in parts) or None

def build(rows, names):
    values, review, unmatched = {}, [], set()
    page_states = sorted({s for r in rows for s in r["states"]})
    for s in page_states:
        key = norm(s); title = names.get(key) or names.get(ALIASES.get(key, ""))
        if not title: unmatched.add(s); continue
        if any(r["conflict"] for r in rows if norm(s) in {norm(x) for x in r["states"]}):
            review.append(f"{title}: page colour and recommendation dates disagree - not published"); continue
        values[title] = value_for(s, rows)
    return values, review, sorted(unmatched)

def write_feed(items, now):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           "<title>CLCS submissions - Extended continental shelf status updates</title>",
           "<link>" + URL + "</link>", "<description>One item per State whose status changed on the UN CLCS submissions page</description>",
           "<lastBuildDate>" + format_datetime(now) + "</lastBuildDate>"]
    for it in sorted(items, key=lambda i: i["pub"], reverse=True):
        pub = dt.datetime.fromisoformat(it["pub"])
        out += ["<item>", "<title>" + escape(it["title"]) + "</title>",
                '<guid isPermaLink="false">' + escape(it["guid"]) + "</guid>",
                "<pubDate>" + format_datetime(pub) + "</pubDate>",
                "<description>" + escape(it["value"]) + "</description>", "</item>"]
    out.append("</channel></rss>")
    FEED.parent.mkdir(exist_ok=True); FEED.write_text("\n".join(out), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--html"); ap.add_argument("--init", action="store_true")
    ap.add_argument("--publish-all", action="store_true"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--only")
    a = ap.parse_args()
    if a.html: html = Path(a.html).read_text(encoding="utf-8", errors="replace")
    else:
        import requests
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (clcs-feed monthly check)"}, timeout=60); r.raise_for_status(); html = r.text
    names = json.loads((ROOT/"names.json").read_text(encoding="utf-8"))
    values, review, unmatched = build(parse(html), names)
    if a.dry_run:
        prev = json.loads(STATE.read_text()).get("values", {}) if STATE.exists() else {}
        VALUES_CSV.parent.mkdir(exist_ok=True)
        with VALUES_CSV.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["Title", "Extended_continental_shelf_status", "Changed since baseline"])
            for t in sorted(values): w.writerow([t, values[t] or "", "" if not prev else ("yes" if prev.get(t) != values[t] else "no")])
            for line in review: w.writerow([line.split(":")[0], "", "HELD: " + line.split(": ", 1)[1]])
            for u in unmatched: w.writerow([u, "", "HELD: page name not matched to a list row"])
        print(f"DRY RUN: {len(values)} States written to {VALUES_CSV.name} | {len(review)} need review | unmatched: {unmatched}")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {"values": {}, "items": []}
    now = dt.datetime.now(dt.timezone.utc)
    prev = state["values"]
    if a.only and a.only not in values: raise SystemExit(f"--only: {a.only!r} is not a Title on the page")
    changed = [a.only] if a.only else [t for t, v in values.items() if v and (a.publish_all or (t in prev and prev[t] != v) or (t not in prev and not a.init and prev))]
    if not a.init:
        for t in changed:
            state["items"].append(dict(title=t, value=values[t], pub=now.isoformat(), guid=f"{t}|{now:%Y%m%d%H%M}|{hashlib.md5(values[t].encode()).hexdigest()[:8]}"))
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["items"] = [i for i in state["items"] if i["pub"] >= cutoff]
    state["values"] = {**prev, **{t: v for t, v in values.items() if v}}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    write_feed(state["items"], now)
    REVIEW.write_text("\n".join(review + [f"Page name not matched to a list row: {u}" for u in unmatched]) or "Nothing to review.", encoding="utf-8")
    LASTRUN.write_text(now.strftime("%Y-%m-%d") + "\n")
    print(f"{len(values)} States on page | {len(changed)} published | {len(review)} need review | unmatched: {unmatched}")

if __name__ == "__main__": main()
