"""Name matching shared by every source: page names -> SharePoint list Titles via names.json."""
import json, re
from pathlib import Path

ROOT = Path(__file__).parent

# page spelling (normalised) -> names.json key (normalised)
ALIASES = {"republic of korea": "korea republic of", "viet nam": "vietnam", "russian federation": "russia",
           "tanzania": "united republic of tanzania", "federated states of micronesia": "micronesia federated states of",
           "czech republic": "czechia", "iran islamic republic of": "iran", "naoero": "nauru",
           "netherlands kingdom of": "netherlands", "st kitts and nevis": "saint kitts and nevis",
           "st lucia": "saint lucia", "st vincent and grenadines": "saint vincent and grenadines"}

def norm(s):
    s = re.sub(r"\bthe\b", "", (s or "").lower())
    s = s.replace("united kingdom of great britain and northern ireland", "united kingdom")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def load_names():
    return json.loads((ROOT / "names.json").read_text(encoding="utf-8"))

def title_for(page_name, names):
    k = norm(page_name)
    return names.get(k) or names.get(ALIASES.get(k, ""))
