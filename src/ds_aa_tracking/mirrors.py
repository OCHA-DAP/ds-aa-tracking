"""The mirrors (D154): tables and views in schema `aa` that another repo copies in from an
outside source every day (ds-cerf-supplement: OneGMS, the CBPF OData API, its storm and
drought matchers). They are never written here: the admin page's proxy refuses them,
scripts/apply_entries.py refuses an entries file that touches one, and the publish run warns
about any `aa` table that is neither this repo's (schema.py) nor a listed mirror.

The one list is proxy/mirror_tables.json, so that it ships in the proxy's deploy zip; this
module reads the same file.
"""

import json
from pathlib import Path

import sqlalchemy as sa

from ds_aa_tracking import schema

_LIST = Path(__file__).parents[2] / "proxy" / "mirror_tables.json"
if not _LIST.is_file():   # e.g. a copy of src/ + scripts/ without it (databricks/nightly.py copies it)
    raise SystemExit(f"the mirror list {_LIST} is missing: copy proxy/mirror_tables.json beside src/")
MIRRORS = json.loads(_LIST.read_text())


def mirror_of(name):
    """What the mirror table or view `name` holds and where it comes from, or None."""
    return (MIRRORS["tables"].get(name) or MIRRORS["views"].get(name)
            or next((d for p, d in MIRRORS["prefixes"].items() if name.startswith(p)), None))


def refusal(name):
    """Why `name` is never written here, in one line; None when it is not a mirror."""
    d = mirror_of(name)
    return d and (f"aa.{name} is a mirror and is never written here: {d}, refreshed "
                  f"{MIRRORS['refresh']} by {MIRRORS['repo']}. {MIRRORS['fix']}")


def undescribed(engine):
    """Base tables in `aa` that neither schema.py defines nor the mirror list describes (the
    retired zz_legacy_ tables aside): another writer's new table, editable in the admin page
    until it is listed in proxy/mirror_tables.json."""
    with engine.connect() as conn:
        names = conn.execute(sa.text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'aa' AND table_type = 'BASE TABLE'")).scalars().all()
    ours = set(schema.TABLES) | set(schema.DURABLE_TABLES)
    return sorted(n for n in names
                  if n not in ours and not n.startswith("zz_legacy_") and not mirror_of(n))
