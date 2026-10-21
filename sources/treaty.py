"""UN Treaty Collection status pages (treaties.un.org) -> one status column per treaty.

Every State in names.json gets a value; a State absent from the participant table is "Non Party".
The column layout is checked against the expected headers so a redesigned page aborts instead of
publishing wrong values.
"""
import re
from bs4 import BeautifulSoup
from common import title_for

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def date_only(v):
    """'23 Jun 2003 a' -> '23 Jun 2003' (drops the accession/succession/etc. marker)."""
    m = re.match(r"^(\d{1,2} \w{3} \d{4})", v)
    return m.group(1) if m else v

def grid(html, expect_headers, min_rows):
    """Participant table as {page name: [cell, ...]} (participant column excluded)."""
    t = BeautifulSoup(html, "lxml").find("table", id=re.compile(r"tblgrid$"))
    if t is None: raise SystemExit("PARSE ERROR: participant table not found")
    trs = t.find_all("tr")
    head = [clean(c.get_text(" ", strip=True)) for c in trs[0].find_all(["td", "th"], recursive=False)][1:]
    if len(head) != len(expect_headers) or not all(h.startswith(e) for h, e in zip(head, expect_headers)):
        raise SystemExit(f"PARSE ERROR: table columns changed: {head}")
    out = {}
    for r in trs[1:]:
        c = [clean(x.get_text(" ", strip=True)) for x in r.find_all("td", recursive=False)]
        if len(c) != len(expect_headers) + 1 or not c[0]: continue
        out[re.sub(r"[\s\d,]+$", "", c[0])] = c[1:]     # strip footnote numbers: "European Union 6 , 8"
    if len(out) < min_rows: raise SystemExit(f"PARSE ERROR: only {len(out)} participants found")
    return out

# participants that are not rows in the SharePoint list; anything else unmatched is flagged for review
NOT_IN_LIST = {"Afghanistan", "Andorra", "Burundi", "Central African Republic", "Democratic People's Republic of Korea",
               "El Salvador", "Eritrea", "Ethiopia", "Libya", "Liechtenstein", "United Arab Emirates"}

def build_from(html, names, expect_headers, min_rows, fmt):
    values, unmatched = {}, []
    for name, cells in grid(html, expect_headers, min_rows).items():
        title = title_for(name, names)
        if title: values[title] = fmt(cells)
        elif name not in NOT_IN_LIST: unmatched.append(name)
    for title in names.values():
        values.setdefault(title, "Non Party")
    return values, [], sorted(unmatched)


class UNCLOS:
    COLUMN = "UNCLOS_membership"
    URL = "https://treaties.un.org/pages/ViewDetailsIII.aspx?src=TREATY&mtdsg_no=XXI-6&chapter=21&Temp=mtdsg3&clang=_en"
    FEED_TITLE = "UNCLOS membership updates"
    HEADERS = ["Signature", "Formal confirmation"]

    @staticmethod
    def fmt(c):
        sig, rat = c                       # both keep their marker, e.g. "28 May 1993 d", "23 Jun 2003 a"
        if sig and rat: return f"Signatory and Party: {sig} | {rat}"
        if rat: return f"Party: {rat}"
        if sig: return f"Signatory: {sig}"
        return "Non Party"

    @classmethod
    def build(cls, html, names):
        return build_from(html, names, cls.HEADERS, 150, cls.fmt)


class Agreement1994:
    COLUMN = "1994_agreement_status"
    URL = "https://treaties.un.org/Pages/ViewDetails.aspx?src=IND&mtdsg_no=XXI-6-a&chapter=21&clang=_en"
    FEED_TITLE = "1994 Agreement (Part XI) status updates"
    HEADERS = ["Signature", "Provisional application", "Notification of non-provisional", "Simplified procedure"]

    @staticmethod
    def fmt(c):
        # the 3rd column records States that declined provisional application, so it is ignored
        sig, prov, _declined, rat = c
        if sig and rat: return f"Signatory and Party: {date_only(sig)} | {date_only(rat)}"
        if rat: return f"Party: {date_only(rat)}"
        if sig: return f"Signatory but not Party: {date_only(sig)}"
        if prov: return f"Non Party (Provisional Application:{date_only(prov)})"
        return "Non Party"

    @classmethod
    def build(cls, html, names):
        return build_from(html, names, cls.HEADERS, 140, cls.fmt)
