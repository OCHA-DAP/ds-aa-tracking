"""Status collapse (2026-09-21), kept as a schema-pass step:

  1. framework_version.kb_status keeps only endorsed | development | pre-development —
     'superseded' is inferred (a newer endorsed version exists) and 'retired' moved to
     country_hazard.retired (manual, framework level);
  2. window_status gets one row per window (aa.window ∪ entered_window) that has none,
     triggered = true when an activation of that version names the window (or the version
     has a single window, or an activation is marked full) — a seed for hand curation.

The window-first migration of the same day (renaming the pre-window tables to zz_legacy_*
and seeding the window tables from them) ran once; its code and the zz_legacy_* tables are
gone (2026-10-30, D168).
"""

import sqlalchemy as sa

def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def collapse_statuses(conn):
    """Steps 1 + 2: run AFTER the CREATE TABLE pass (needs window_status, country_hazard.retired)."""
    done = []
    n = conn.execute(sa.text(
        "UPDATE aa.framework_version SET kb_status = 'endorsed' "
        "WHERE kb_status IN ('superseded', 'retired')")).rowcount
    if n:
        done.append(f"framework_version: {n} superseded/retired -> endorsed (inferred now)")
        # first collapse only: retire the pairs the tracking sheet last called dormant/retired
        m = conn.execute(sa.text("""
            UPDATE aa.country_hazard r SET retired = true,
                   retired_note = coalesce(retired_note, 'seeded from sheet status ' || s.status)
            FROM (SELECT DISTINCT ON (country_iso3, hazard) country_iso3, hazard, status
                  FROM aa.framework_status ORDER BY country_iso3, hazard, as_of DESC) s
            WHERE s.country_iso3 = r.country_iso3 AND s.hazard = r.hazard
              AND s.status IN ('dormant', 'retired') AND NOT r.retired""")).rowcount
        done.append(f"country_hazard: {m} pairs flagged retired (sheet said dormant/retired)")
    # windows without a status row: seed from the activations, then leave to curation
    wins = conn.execute(sa.text("""
        SELECT w.country_iso3, w.hazard, w.version, w.window_name
        FROM (SELECT country_iso3, hazard, version, window_name FROM aa.window
              UNION SELECT country_iso3, hazard, version, window_name FROM aa.entered_window) w
        LEFT JOIN aa.window_status s USING (country_iso3, hazard, version, window_name)
        WHERE s.window_name IS NULL""")).fetchall()
    if not wins:
        return done
    acts = conn.execute(sa.text("""
        SELECT country_iso3, hazard, version, window_name, event_date, full_activation
        FROM aa.window_activation""")).fetchall()
    by_ver = {}
    for a in acts:
        by_ver.setdefault((a[0], a[1], a[2]), []).append(a)
    n_win = {}
    for w in wins:
        n_win[(w[0], w[1], w[2])] = n_win.get((w[0], w[1], w[2]), 0) + 1
    seeded = 0
    for w in wins:
        key = (w[0], w[1], w[2])
        va = by_ver.get(key, [])
        wn = _norm(w[3])
        hit = [a for a in va if a[3] and (wn in _norm(a[3]) or _norm(a[3]) in wn)]
        if not hit:                            # 'wt1' / 'Window 1' vs 'Window 1 — livelihoods'
            import re
            m = re.fullmatch(r"(?:w[a-z]*\s*|window\s*)(\d)", wn)
            if m:
                hit = [a for a in va if a[3] and re.search(r"\bwindow\s*" + m.group(1) + r"\b",
                                                           _norm(a[3]))]
        if not hit and va and (n_win[key] == 1 or any(a[5] is True for a in va)):
            hit = va
        dates = sorted(a[4] for a in hit if a[4])
        first = dates[0] if dates else None
        if first and len(first) == 7:
            first += "-01"                     # month precision -> first of month
        elif first and len(first) != 10:
            first = None                       # year-only: no date
        conn.execute(sa.text("""
            INSERT INTO aa.window_status (country_iso3, hazard, version, window_name,
                                          triggered, triggered_on, note, updated_by)
            VALUES (:c, :h, :v, :w, :t, :d, :n, 'seed')
            ON CONFLICT DO NOTHING"""),
            {"c": w[0], "h": w[1], "v": w[2], "w": w[3], "t": bool(hit), "d": first,
             "n": ("seeded: " + "; ".join(f"{a[3]} {a[4]}" for a in hit)) if hit
                  else "seeded: no activation matched"})
        seeded += 1
    done.append(f"window_status: {seeded} windows seeded ({sum(1 for w in wins)} without a row)")
    return done
