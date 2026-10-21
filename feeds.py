#!/usr/bin/env python3
"""Scrape public pages and publish one RSS feed per SharePoint column, with one item per State
whose value changed. A Power Automate flow (standard RSS trigger) writes each item into the list.

Usage
  python feeds.py <feed> [<feed> ...]          normal weekly run: publish only States whose value changed
  python feeds.py all                          every feed in turn
  python feeds.py <feed> --init                record current values as the baseline, publish nothing
  python feeds.py <feed> --publish-all         publish every State
  python feeds.py <feed> --dry-run             write docs/<feed>/values.csv for review, change nothing else
  python feeds.py <feed> --only "[S59] France" publish just that State (to test a flow)
  add  --html saved_page.html                  read a saved copy of the page instead of fetching it

Feeds are listed in FEEDS below. Adding one = a module in sources/ with COLUMN, URL, FEED_TITLE, build().
"""
import argparse, csv, hashlib, json, sys, time, datetime as dt
from email.utils import format_datetime
from xml.sax.saxutils import escape
from common import ROOT, load_names
from sources import clcs
from sources.treaty import UNCLOS, Agreement1994

FEEDS = {"clcs": clcs, "unclos": UNCLOS, "agreement-1994": Agreement1994}
PAGES_URL = "https://luca-tjo.github.io/isa-state-feeds/{feed}/feed.xml"
KEEP_DAYS = 45                       # feed items older than this are dropped
USER_AGENT = "Mozilla/5.0 (isa-state-feeds weekly check; +https://github.com/Luca-Tjo/isa-state-feeds)"

def fetch(url):
    import requests
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120); r.raise_for_status()
    return r.text

def write_feed(path, src, items, now):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           "<title>" + escape(src.FEED_TITLE) + "</title>", "<link>" + escape(src.URL) + "</link>",
           "<description>One item per State whose " + escape(src.COLUMN) + " value changed</description>",
           "<lastBuildDate>" + format_datetime(now) + "</lastBuildDate>"]
    for it in sorted(items, key=lambda i: i["pub"], reverse=True):
        out += ["<item>", "<title>" + escape(it["title"]) + "</title>",
                '<guid isPermaLink="false">' + escape(it["guid"]) + "</guid>",
                "<pubDate>" + format_datetime(dt.datetime.fromisoformat(it["pub"])) + "</pubDate>",
                "<description>" + escape(it["value"]) + "</description>", "</item>"]
    out.append("</channel></rss>")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(out), encoding="utf-8")

def run(name, a, names):
    src = FEEDS[name]
    data, docs = ROOT / "data" / name, ROOT / "docs" / name
    data.mkdir(parents=True, exist_ok=True); docs.mkdir(parents=True, exist_ok=True)
    state_path = data / "state.json"
    html = open(a.html, encoding="utf-8", errors="replace").read() if a.html else fetch(src.URL)
    values, review, unmatched = src.build(html, names)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"values": {}, "items": []}
    prev = state["values"]

    if a.dry_run:
        with (docs / "values.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["Title", src.COLUMN, "Changed since baseline"])
            for t in sorted(values): w.writerow([t, values[t] or "", "" if not prev else ("yes" if prev.get(t) != values[t] else "no")])
            for line in review: w.writerow([line.split(":")[0], "", "HELD: " + line.split(": ", 1)[1]])
            for u in unmatched: w.writerow([u, "", "page name not matched to a list row"])
        print(f"[{name}] DRY RUN: {len(values)} States written to docs/{name}/values.csv | {len(review)} need review | unmatched: {unmatched}")
        return

    now = dt.datetime.now(dt.timezone.utc)
    if a.only and a.only not in values: raise SystemExit(f"--only: {a.only!r} is not a Title on the {name} page")
    changed = [a.only] if a.only else [t for t, v in values.items() if v and (a.publish_all or (t in prev and prev[t] != v) or (t not in prev and not a.init and prev))]
    if not a.init:
        for t in changed:
            state["items"].append(dict(title=t, value=values[t], pub=now.isoformat(),
                                       guid=f"{t}|{now:%Y%m%d%H%M}|{hashlib.md5(values[t].encode()).hexdigest()[:8]}"))
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["items"] = [i for i in state["items"] if i["pub"] >= cutoff]
    state["values"] = {**prev, **{t: v for t, v in values.items() if v}}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    write_feed(docs / "feed.xml", src, state["items"], now)
    (data / "needs_review.txt").write_text("\n".join(review + [f"Page name not matched to a list row: {u}" for u in unmatched]) or "Nothing to review.", encoding="utf-8")
    (data / "last_run.txt").write_text(now.strftime("%Y-%m-%d") + "\n")
    print(f"[{name}] {len(values)} States | {len(changed) if not a.init else 0} published | {len(review)} need review | unmatched: {unmatched}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feeds", nargs="+", help="feed names, or 'all': " + ", ".join(FEEDS))
    ap.add_argument("--html"); ap.add_argument("--init", action="store_true"); ap.add_argument("--publish-all", action="store_true")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--only")
    a = ap.parse_args()
    feeds = list(FEEDS) if a.feeds == ["all"] else a.feeds
    bad = [f for f in feeds if f not in FEEDS]
    if bad: ap.error(f"unknown feed(s) {bad}; choose from {list(FEEDS)} or 'all'")
    if a.html and len(feeds) > 1: ap.error("--html works with a single feed")
    names, failed = load_names(), []
    for i, name in enumerate(feeds):
        if i: time.sleep(3)              # treaties.un.org asks for a 2 s crawl delay
        try: run(name, a, names)
        except SystemExit as e:          # one broken page must not stop the other feeds
            print(f"[{name}] FAILED: {e}", file=sys.stderr); failed.append(name)
        except Exception as e:
            print(f"[{name}] FAILED: {type(e).__name__}: {e}", file=sys.stderr); failed.append(name)
    if failed: sys.exit(f"Failed feeds: {failed}")

if __name__ == "__main__": main()
