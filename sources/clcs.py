"""UN CLCS submissions page -> Extended_continental_shelf_status.

Status comes from the row colour; joint submissions are their own clause; clauses are ordered by year.
"""
import re
from bs4 import BeautifulSoup
from common import norm, title_for

COLUMN = "Extended_continental_shelf_status"
URL = "https://www.un.org/depts/los/clcs_new/commission_submissions.htm"
FEED_TITLE = "CLCS submissions - Extended continental shelf status updates"

GROUP_SOLO_BY_STATUS = True          # False = one clause per submission
SOLO_WITH_AND = {"Trinidad and Tobago", "United Kingdom of Great Britain and Northern Ireland"}
COLOURS = {"rgba(245,122,122,0.3)": "active", "rgba(102,255,153,0.4)": "recs", "rgba(102,255,255,0.4)": "deposit"}
WORD = {"recs": "with recommendations", "deposit": "with recommendations followed by deposit",
        "active": "under active consideration", "awaiting": "pending consideration"}
SOLO_ORDER = ["deposit", "recs", "active", "awaiting"]

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
    parts = []                                         # (earliest year, text)
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

def build(html, names):
    """Returns (values {Title: value}, review [lines], unmatched [page names])."""
    rows = parse(html)
    values, review, unmatched = {}, [], set()
    for s in sorted({s for r in rows for s in r["states"]}):
        title = title_for(s, names)
        if not title: unmatched.add(s); continue
        if any(r["conflict"] for r in rows if norm(s) in {norm(x) for x in r["states"]}):
            review.append(f"{title}: page colour and recommendation dates disagree - not published"); continue
        values[title] = value_for(s, rows)
    return values, review, sorted(unmatched)
