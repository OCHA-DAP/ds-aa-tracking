"""Canonical vocabularies + normalization helpers.

Framework identity across all tracking tables is (country_iso3, hazard) using the
canonical hazard vocabulary below — the same identity rule as the KB (D62), extended
to hazards the KB doesn't cover yet. Raw source spellings are always preserved in
*_raw columns.
"""

import re

# ---------------------------------------------------------------- countries

COUNTRY_TO_ISO3 = {
    "afghanistan": "AFG",
    "albania": "ALB",
    "algeria": "DZA",
    "angola": "AGO",
    "bangladesh": "BGD",
    "benin": "BEN",
    "bolivia": "BOL",
    "burkina faso": "BFA",
    "burundi": "BDI",
    "cameroon": "CMR",
    "car": "CAF",
    "central african republic": "CAF",
    "chad": "TCD",
    "colombia": "COL",
    "congo dr": "COD",
    "congo, the democratic republic of the": "COD",
    "democratic republic of the congo": "COD",
    "drc": "COD",
    "cuba": "CUB",
    "djibouti": "DJI",
    "dominican republic": "DOM",
    "ecuador": "ECU",
    "egypt": "EGY",
    "el salvador": "SLV",
    "eritrea": "ERI",
    "ethiopia": "ETH",
    "fiji": "FJI",
    "guatemala": "GTM",
    "haiti": "HTI",
    "honduras": "HND",
    "india": "IND",
    "indonesia": "IDN",
    "iraq": "IRQ",
    "kenya": "KEN",
    "korea dpr": "PRK",
    "korea republic of": "KOR",
    "lao pdr": "LAO",
    "micronesia": "FSM",
    "moldova republic of": "MDA",
    "occupied palestinian territory": "PSE",
    "palestinian territory, occupied": "PSE",
    "opt": "PSE",
    "lac dry corridor": "LAC-DC",
    "dry corridor": "LAC-DC",
    "lebanon": "LBN",
    "libya": "LBY",
    "madagascar": "MDG",
    "malawi": "MWI",
    "mali": "MLI",
    "mauritania": "MRT",
    "mauretania": "MRT",  # common misspelling in the sheets
    "mozambique": "MOZ",
    "myanmar": "MMR",
    "nepal": "NPL",
    "nicaragua": "NIC",
    "niger": "NER",
    "nigeria": "NGA",
    "pakistan": "PAK",
    "palestine": "PSE",
    "peru": "PER",
    "philippines": "PHL",
    "somalia": "SOM",
    "south sudan": "SSD",
    "sri lanka": "LKA",
    "sudan": "SDN",
    "syria": "SYR",
    "syrian arab republic": "SYR",
    "timor-leste": "TLS",
    "uganda": "UGA",
    "ukraine": "UKR",
    "vanuatu": "VUT",
    "venezuela": "VEN",
    "viet nam": "VNM",
    "vietnam": "VNM",
    "yemen": "YEM",
    "zambia": "ZMB",
    "zimbabwe": "ZWE",
}


def norm_country(name):
    """Return (iso3, cleaned_name). iso3 is None when unmapped (caller decides)."""
    if name is None:
        return None, None
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    # strip sub-framework parentheticals: "Bangladesh(Jamuna)", "DRC-1"
    base = re.sub(r"\s*\(.*\)$", "", cleaned)
    base = re.sub(r"-\d+$", "", base)
    base = base.rstrip("*").strip()
    return COUNTRY_TO_ISO3.get(base.lower()), cleaned


def subunit_of(name):
    """Extract sub-framework label: 'Bangladesh(Jamuna)' -> 'Jamuna', 'DRC-2' -> '2'."""
    if name is None:
        return None
    m = re.search(r"\(([^)]+)\)\s*$", str(name).strip())
    if m:
        return m.group(1).strip()
    m = re.search(r"-(\d+)$", str(name).strip())
    if m:
        return m.group(1)
    return None


# ISO3 embedded in CERF codes: "24-RR-BDI-65155", "CERF-AGO-25-RR-1468",
# "CERF-COD-25-RR-CEF-34883". Old *project* codes ("20-RR-WFP-040") embed the
# agency, not the country — never parse those for geography.
_APP_OLD = re.compile(r"^\d{2}-(?:RR|UF)-([A-Z]{3})-\d+")
_APP_NEW = re.compile(r"^CERF-([A-Z]{3})-\d{2}-(?:RR|UF)")


def iso3_from_application_code(code):
    if not code:
        return None
    code = str(code).strip()
    for pat in (_APP_OLD, _APP_NEW):
        m = pat.match(code)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------- hazards

HAZARD_MAP = {
    "drought": "drought",
    "droughts": "drought",
    # KB identity rule: Malawi's dry-spells pilot is the mwi-drought framework
    "dry spells": "drought",
    "dry spell": "drought",
    "flood": "flood",
    "floods": "flood",
    "flooding": "flood",
    "storm": "storm",
    "storms": "storm",
    "cyclone": "storm",
    "cyclones": "storm",
    "tropical cyclone": "storm",
    "tropical cyclones": "storm",
    "tropical-cyclone": "storm",  # KB frontmatter vocabulary
    "hurricane": "storm",
    "hurricanes": "storm",
    "cholera": "cholera",
    "plague": "plague",
    "locusts": "locusts",
    "locust": "locusts",
    "food insecurity": "food_insecurity",
    "drought/food insecurity": "food_insecurity",
    "earthquake": "earthquake",
}


def norm_hazard(value):
    """Return (canonical, raw). Unmapped values pass through slugified."""
    if value is None:
        return None, None
    raw = re.sub(r"\s+", " ", str(value)).strip()
    canon = HAZARD_MAP.get(raw.lower())
    if canon is None:
        canon = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return canon, raw


# ---------------------------------------------------------------- statuses

# Canonical operational-stage vocabulary. Legend from Julia's 2026 planning sheet;
# other sheets' spellings mapped onto it. This is the *operational* lifecycle,
# deliberately distinct from the KB page-status vocabulary
# (pre-development|development|endorsed|superseded|retired).
STATUS_MAP = {
    "activated & implementing": "activated_implementing",
    "monitoring": "monitoring",
    "live": "active",
    "live (but not new)": "active",
    "continued live": "active",
    "active": "active",
    "acitive": "active",
    "active*": "active",
    "active (regional fund only)": "active",
    "newly endorsed": "active",
    "revised": "active",
    "project finalization": "project_finalization",
    "under development": "under_development",
    "development": "under_development",
    "under revision": "under_revision",
    "revision": "under_revision",
    "under revision or renewal": "under_revision",
    "early conversations": "early_conversations",
    "advanced conversations": "advanced_conversations",
    "dormant": "dormant",
    "expired": "expired",
    "planned": "planned",
    "tbc": "tbc",
    "under development ": "under_development",
}


def norm_status(value):
    if value is None:
        return None, None
    raw = re.sub(r"\s+", " ", str(value)).strip()
    return STATUS_MAP.get(raw.lower(), "other"), raw


MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"],
        start=1,
    )
}


def norm_month(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    return MONTHS.get(v)


FUND_MAP = {
    "cerf": "cerf",
    "country fund": "country_fund",
    "regional fund": "regional_fund",
    "cbpf": "country_fund",
}


def norm_fund(value):
    if value is None:
        return None
    return FUND_MAP.get(str(value).strip().lower(), str(value).strip().lower())
