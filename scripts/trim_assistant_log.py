"""Remove the texts of the AA assistant's questions once they are older than the keeping period
(D248): the question, the answer, the reader's comment and the error message. The counts stay.

The proxy does the same as records come in (proxy/server.js, assistantTrim) and when the admin
page reads them; this nightly step (databricks/nightly.py) is the one that does not depend on
anyone asking a question or opening a page. Nothing to do on a database without the table.

Usage: uv run python scripts/trim_assistant_log.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
os.environ.setdefault("PGSSLMODE", "require")

import ocha_stratus as stratus  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from ds_aa_tracking.schema import ASSISTANT_KEEP_DAYS  # noqa: E402


def trim(engine, days=ASSISTANT_KEEP_DAYS):
    with engine.begin() as conn:
        if not conn.execute(sa.text("SELECT to_regclass('aa.assistant_question') IS NOT NULL")).scalar():
            return None
        return conn.execute(sa.text(
            """UPDATE aa.assistant_question SET question = NULL, answer = NULL, comment = NULL, error = NULL
               WHERE asked_at < now() - make_interval(days => :d)
                 AND (question IS NOT NULL OR answer IS NOT NULL OR comment IS NOT NULL OR error IS NOT NULL)"""),
            {"d": days}).rowcount


if __name__ == "__main__":
    n = trim(stratus.get_engine(stage="dev", write=True))
    print("assistant questions: no table yet" if n is None
          else f"assistant questions: the texts of {n} question(s) older than {ASSISTANT_KEEP_DAYS} days removed")
