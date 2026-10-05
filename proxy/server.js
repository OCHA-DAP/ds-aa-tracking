/* Extraction + entry proxy for the ds-aa-tracking entry page.
 *
 * The GH Pages site is static and credential-free; this app is the ONE place
 * credentials live (App Service app settings): the Anthropic key and the dev-DB
 * write login. Three fixed-purpose endpoints:
 *
 *   POST /extract    base64 framework PDF -> Claude (hard-coded prompt + forced
 *                    structured-output tool) -> registry fields + windows
 *   GET  /framework  ?iso3=&hazard= -> live version rows + windows + funding
 *                    (what the page diffs extracted values against)
 *   POST /entry      upsert aa.entered_version / entered_window / aa.window_funding
 *                    (entered rows; version totals attributed to the window) for one
 *                    (country, hazard, version); every field change is written
 *                    to aa.entry_audit (old, new, who, when). Replace-set
 *                    semantics per version: the posted windows/funding ARE the
 *                    version's rows. The nightly/manual ingest merges entered_*
 *                    into aa.framework_version (entered values win).
 *
 *   GET  /schema     every aa table + column (types, keys, owner, writable) — the
 *                    admin page is populated from this, Django-admin style
 *   GET  /rows       ?table=&limit=&offset=&order=&dir=&q=&f.<col>= -> paged rows
 *   GET  /distinct   ?table=&col= -> distinct values for filter sidebars
 *   POST /save       {table, key|null, row, by} -> UPDATE (key given) or INSERT,
 *                    field-level audit to aa.entry_audit
 *   POST /delete     {table, key, by} -> DELETE one row, audited
 *   GET  /versions   ?iso3=[&hazard=] -> every version of the pair(s): status, role (the
 *                    latest endorsed / superseded / a revision in development), document, seal, and
 *                    the backtest recorded now — how a writer finds the RIGHT version
 *   POST /entries    {entered_by, rows: [entries-file items], dry_run?, confirm_endorsed?,
 *                    seal?} -> applied NOW in one transaction (dry_run: every check, then
 *                    rolled back). Backtest writes name their target: the reply carries the
 *                    version cards, an unregistered version is refused, an endorsed one
 *                    needs confirm_endorsed naming it, a sealed one is refused
 *   GET  /whoami     -> {role}
 *
 * Two roles, two shared secrets in header x-site-token: SITE_TOKEN (viewer —
 * embedded in the staticrypt-encrypted pages, so "has the site password" =
 * viewer) and EDITOR_TOKEN (editor — never embedded; the pages prompt for it
 * once and keep it in localStorage). Reads need viewer; /extract, /entry, /save
 * and /delete need editor. Generic writes are refused on tables other writers
 * own (OneGMS mirrors), on the frozen KB-era record, on the backtest errata (the
 * errata job writes those) and on the append-only audit table. Backtests (window,
 * simulated_activation, version_performance_reported) are editable here while their
 * version is unsealed; the database's guard_sealed trigger refuses changes to a sealed
 * one, and its message comes back to the page as is.
 *
 * Other guards: origin allowlist, model allowlist, size cap, per-IP rate limits.
 * The Anthropic key can never be used for arbitrary requests.
 */
const http = require("http");
const { Pool } = require("pg");

const API_KEY = process.env.ANTHROPIC_API_KEY;
const SITE_TOKEN = process.env.SITE_TOKEN || "";
const EDITOR_TOKEN = process.env.EDITOR_TOKEN || "";   // unset -> SITE_TOKEN also edits (bootstrap only)
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ||
  "https://ocha-dap.github.io").split(",");
const MODELS = new Set(["claude-opus-5"]);
const MAX_BODY = 45 * 1024 * 1024;
const RATE = { extract: 20, entry: 60, read: 1200, write: 600, windowMs: 60 * 60 * 1000 };
// tables the generic /save and /delete refuse: other repos' loaders own them, or append-only
const READONLY_TABLES = new Set([
  "entry_audit",
  // document registry: content-addressed, written only by scripts/register_documents.py
  "framework_document", "version_document",
  // corrections to sealed backtests: written only by scripts/apply_backtests.py
  "backtest_erratum",
  // the KB-era record, frozen since the KB loaders stopped (2026-10-05)
  "funding_breakdown", "actual_activation", "activation_allocation",
  // ds-cerf-supplement OneGMS mirrors
  "cerf_allocation", "cerf_project", "cerf_project_sector", "cerf_project_country",
  "cerf_allocation_storm", "cerf_supplement", "cerf_contribution",
]);
const READONLY_PREFIXES = ["cbpf_", "zz_legacy_"];
const TABLE_OWNER = (t) =>
  t.startsWith("zz_legacy_") ? "retired" :
  READONLY_PREFIXES.some((p) => t.startsWith(p)) || t.startsWith("cerf_allocation_storm") ||
  ["cerf_allocation", "cerf_project", "cerf_project_sector", "cerf_project_country", "cerf_supplement", "cerf_contribution"].includes(t)
    ? "ds-cerf-supplement"
    : ["funding_breakdown", "actual_activation", "activation_allocation"].includes(t)
      ? "nobody — the frozen KB-era record"
      : t === "backtest_erratum" ? "the errata job (backtests/errata/)"
      : "ds-aa-tracking";
const isReadonly = (t) => READONLY_TABLES.has(t) || READONLY_PREFIXES.some((p) => t.startsWith(p));
const hits = new Map();

const pool = process.env.DSCI_AZ_DB_DEV_HOST
  ? new Pool({
      host: process.env.DSCI_AZ_DB_DEV_HOST,
      user: process.env.DSCI_AZ_DB_DEV_UID_WRITE,
      password: process.env.DSCI_AZ_DB_DEV_PW_WRITE,
      database: "postgres",
      ssl: process.env.DB_SSL === "disable" ? false : { rejectUnauthorized: false },  // disable: a local test DB
      max: 3,
    })
  : null;

const HAZARDS = new Set(["drought", "flood", "storm", "cholera", "plague", "locusts", "other"]);
const VERSION_RE = /^\d{4}(-\d{2}(-\d{2})?)?$/;
const ISO_RE = /^[A-Z]{3}$/;

const VERSION_FIELDS = ["doc_title", "doc_url", "endorsed_by", "valid_until",
  "valid_until_source", "window_rollup", "supersedes", "note"];
const WINDOW_FIELDS = ["basis", "trigger_statement", "monitoring_period", "note"];

const TOOL = {
  name: "record_framework",
  description:
    "Record the structured fields of an OCHA anticipatory action framework document.",
  input_schema: {
    type: "object",
    properties: {
      country_iso3: { type: "string", description: "ISO 3166-1 alpha-3 of the framework country" },
      country_name: { type: "string" },
      hazard: {
        type: "string",
        enum: ["drought", "flood", "storm", "cholera", "plague", "locusts", "other"],
        description: "Canonical hazard. Tropical cyclone/typhoon/hurricane = storm; dry spells = drought.",
      },
      version_date: { type: "string", description: "Endorsement / version date, YYYY-MM-DD. The date the document was endorsed or finalised, NOT the publication of annexes." },
      doc_title: { type: "string", description: "Full document title as printed" },
      endorsed_by: {
        type: "string", enum: ["erc", "cerf_secretariat", "unknown"],
        description: "erc = endorsed by the Emergency Relief Coordinator (major version / new validity); cerf_secretariat = minor revision approved by the CERF secretariat",
      },
      valid_until: { type: "string", description: "End of validity YYYY-MM-DD if the document states one, else empty" },
      valid_until_source: { type: "string", enum: ["doc-stated", "convention", "inherited", "unknown"] },
      window_rollup: {
        type: "string", enum: ["additive", "exclusive", "capped", "unknown"],
        description: "How window funding relates to the total: additive = every window separately funded and all can activate (total = sum); exclusive = either/or, whichever window triggers draws the shared pot (each window's amount ~ the total); capped = windows could together draw more than the envelope, first to fire draws down.",
      },
      supersedes: { type: "string", description: "Date label (YYYY[-MM[-DD]]) of the previous framework version this document supersedes, if stated" },
      version_funding: {
        type: "array",
        description: "The TOTAL pre-arranged amount per fund as stated in the document (CERF allocation, CBPF contribution, co-financing...).",
        items: {
          type: "object",
          properties: {
            fund: { type: "string", enum: ["cerf", "cbpf", "rhpf", "cofinancing", "other"] },
            financier: { type: "string", description: "Named source when fund is cofinancing/other" },
            total_usd: { type: "number" },
          },
          required: ["fund", "total_usd"],
        },
      },
      windows: {
        type: "array",
        description: "Every activation window / trigger stage defined in the document (readiness and action stages of the same window are ONE window; separate geographic or seasonal windows are separate entries).",
        items: {
          type: "object",
          properties: {
            window_name: { type: "string", description: "e.g. 'Window 1', 'Readiness/Activation', 'Jamuna', 'Gu season'" },
            basis: { type: "string", enum: ["observational", "forecast", "mixed"] },
            trigger_statement: { type: "string", description: "The trigger condition verbatim or near-verbatim from the document, <=600 characters" },
            monitoring_period: { type: "string", description: "e.g. 'April-June', 'dekads 21-26'" },
            funding: {
              type: "array",
              description: "What this window can draw, per fund, if the document splits amounts by window",
              items: {
                type: "object",
                properties: {
                  fund: { type: "string", enum: ["cerf", "cbpf", "rhpf", "cofinancing", "other"] },
                  financier: { type: "string" },
                  amount_usd: { type: "number" },
                },
                required: ["fund", "amount_usd"],
              },
            },
          },
          required: ["window_name", "trigger_statement"],
        },
      },
      note: { type: "string", description: "One-sentence caveat if anything above is uncertain or ambiguous in the document" },
    },
    required: ["country_iso3", "hazard", "version_date", "doc_title", "windows"],
  },
};

const PROMPT =
  "This PDF is (probably) an OCHA/CERF anticipatory action framework document. " +
  "Extract its registry fields with the record_framework tool. Dates as printed in " +
  "the document win over inferred dates; if the endorsement date is absent use the " +
  "document date. Capture EVERY activation window with its trigger statement " +
  "(condensed to the operative condition), the total pre-arranged amount PER FUND, " +
  "per-window amounts where the document splits them, and how window amounts roll " +
  "up to the total (additive / exclusive / capped). Amounts in USD. If the document " +
  "is not a framework document, still fill what you can and say so in `note`.";

function cors(req, res) {
  const origin = req.headers.origin || "";
  if (ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Headers", "content-type,x-site-token,x-editor-token");
    res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
    return true;
  }
  return false;
}

function role(req) {
  // viewer: x-site-token == SITE_TOKEN (embedded in the encrypted pages);
  // editor: x-editor-token == EDITOR_TOKEN (prompted for, kept in localStorage)
  const st = req.headers["x-site-token"] || "", et = req.headers["x-editor-token"] || "";
  if (EDITOR_TOKEN) {
    if (et === EDITOR_TOKEN || st === EDITOR_TOKEN) return "editor";
    if (!SITE_TOKEN || st === SITE_TOKEN) return "viewer";
    return null;
  }
  if (!SITE_TOKEN) return "editor";                       // nothing configured (local dev)
  return st === SITE_TOKEN ? "editor" : null;             // bootstrap: one token does both
}

function send(res, code, obj) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(obj));
}

function limited(req, res, kind) {
  const ip = (req.headers["x-forwarded-for"] || req.socket.remoteAddress || "?") + ":" + kind;
  const now = Date.now();
  const rec = (hits.get(ip) || []).filter((t) => now - t < RATE.windowMs);
  if (rec.length >= RATE[kind]) { send(res, 429, { error: "rate limit: try later" }); return true; }
  rec.push(now); hits.set(ip, rec);
  return false;
}

function readBody(req, res) {
  return new Promise((resolve) => {
    let size = 0; const chunks = [];
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BODY) { send(res, 413, { error: "body too large" }); req.destroy(); resolve(null); }
      else chunks.push(c);
    });
    req.on("end", () => {
      if (res.writableEnded) return resolve(null);
      try { resolve(JSON.parse(Buffer.concat(chunks).toString())); }
      catch { send(res, 400, { error: "bad JSON" }); resolve(null); }
    });
  });
}

// ------------------------------------------------------------------ /extract
async function extract(req, res) {
  if (!API_KEY) return send(res, 500, { error: "ANTHROPIC_API_KEY not configured" });
  if (limited(req, res, "extract")) return;
  const payload = await readBody(req, res);
  if (!payload) return;
  const model = MODELS.has(payload.model) ? payload.model : "claude-opus-5";
  if (!payload.pdf_base64) return send(res, 400, { error: "pdf_base64 required" });
  const oauth = API_KEY.startsWith("sk-ant-oat");
  const auth = oauth
    ? { authorization: `Bearer ${API_KEY}`, "anthropic-beta": "oauth-2025-04-20" }
    : { "x-api-key": API_KEY };
  try {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { ...auth, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model,
        max_tokens: 8192,
        ...(oauth ? { system: "You are Claude Code, Anthropic's official CLI for Claude." } : {}),
        tools: [TOOL],
        tool_choice: { type: "tool", name: "record_framework" },
        messages: [{
          role: "user",
          content: [
            { type: "document", source: { type: "base64", media_type: "application/pdf", data: payload.pdf_base64 } },
            { type: "text", text: PROMPT },
          ],
        }],
      }),
    });
    const out = await r.json();
    if (!r.ok) return send(res, 502, { error: out.error?.message || `upstream ${r.status}` });
    const tool = (out.content || []).find((b) => b.type === "tool_use");
    if (!tool) return send(res, 502, { error: "no structured output returned" });
    send(res, 200, { ok: true, data: tool.input, model, usage: out.usage });
  } catch (e) {
    send(res, 502, { error: String(e.message || e) });
  }
}

// ---------------------------------------------------------------- /framework
async function framework(req, res, q) {
  if (!pool) return send(res, 500, { error: "DB not configured" });
  if (limited(req, res, "read")) return;
  const iso3 = (q.get("iso3") || "").toUpperCase(), hazard = q.get("hazard") || "";
  if (!ISO_RE.test(iso3) || !HAZARDS.has(hazard))
    return send(res, 400, { error: "iso3 and hazard required" });
  const key = [iso3, hazard];
  try {
    const [versions, windows, wfunding, vfunding, entered] = await Promise.all([
      pool.query(
        `SELECT version, kb_framework, kb_status, valid_from::text, valid_until::text,
                valid_until_source, endorsed_by, supersedes, window_rollup,
                prearranged_usd_doc, doc_title, doc_url, source, note
         FROM aa.framework_version WHERE country_iso3=$1 AND hazard=$2
         ORDER BY valid_from NULLS LAST`, key),
      pool.query(
        `SELECT version, window_name, basis, trigger_statement, monitoring_period, note,
                entered_by, entered_at::text
         FROM aa.entered_window WHERE country_iso3=$1 AND hazard=$2
         ORDER BY version, window_name`, key),
      pool.query(
        `SELECT version, window_name, coalesce(fund_code, 'cofinancing') AS fund_code, financier,
                amount_usd, provenance
         FROM aa.window_funding
         WHERE country_iso3=$1 AND hazard=$2 AND agency IS NULL AND sector IS NULL
           AND window_name NOT IN ('single','unattributed')`, key),
      pool.query(
        `SELECT version, coalesce(fund_code, 'cofinancing') AS fund_code, financier,
                total_usd
         FROM aa.v_version_funding WHERE country_iso3=$1 AND hazard=$2`, key),
      pool.query(
        `SELECT version, doc_title, doc_url, endorsed_by, valid_until::text,
                valid_until_source, window_rollup, supersedes, note, entered_by,
                entered_at::text
         FROM aa.entered_version WHERE country_iso3=$1 AND hazard=$2`, key),
    ]);
    // KB trigger-performance windows (re-keyed post-cutover); absent pre-cutover
    let kbWindows = [];
    try {
      kbWindows = (await pool.query(
        `SELECT version, window_name, basis, allocation_usd, all_in
         FROM aa.window WHERE country_iso3=$1 AND hazard=$2`, key)).rows;
    } catch (e) { /* pre-cutover shape; ignore */ }
    send(res, 200, {
      ok: true,
      versions: versions.rows, entered_versions: entered.rows,
      windows: windows.rows, kb_windows: kbWindows,
      window_funding: wfunding.rows, version_funding: vfunding.rows,
    });
  } catch (e) {
    send(res, 502, { error: String(e.message || e) });
  }
}

// -------------------------------------------------------------------- /entry
function cleanFunding(rows, withWindow) {
  return (rows || [])
    .map((f) => ({
      window_name: withWindow ? String(f.window_name || "").trim() : undefined,
      fund_code: String(f.fund_code || "").trim().toLowerCase(),
      financier: f.financier ? String(f.financier).trim() : null,
      amount: f.amount_usd ?? f.total_usd,
    }))
    .filter((f) => f.fund_code && f.amount != null && isFinite(f.amount)
      && (!withWindow || f.window_name));
}

async function entry(req, res) {
  if (!pool) return send(res, 500, { error: "DB not configured" });
  if (limited(req, res, "entry")) return;
  const p = await readBody(req, res);
  if (!p) return;
  const iso3 = String(p.country_iso3 || "").toUpperCase();
  const hazard = String(p.hazard || "");
  const version = String(p.version || "").trim();
  const by = String(p.entered_by || "").trim();
  if (!ISO_RE.test(iso3)) return send(res, 400, { error: "bad country_iso3" });
  if (!HAZARDS.has(hazard)) return send(res, 400, { error: "bad hazard" });
  if (!VERSION_RE.test(version)) return send(res, 400, { error: "bad version (YYYY[-MM[-DD]])" });
  if (!by) return send(res, 400, { error: "entered_by required" });
  const key = [iso3, hazard, version];
  const rowKey = key.join("/");
  const audits = [];
  const audit = (table, rk, field, oldV, newV) => {
    const o = oldV == null ? null : String(oldV), n = newV == null ? null : String(newV);
    if (o !== n) audits.push([by, table, rk, field, o, n]);
  };

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // --- entered_version upsert with field-level audit
    const vf = {};
    for (const f of VERSION_FIELDS) {
      let v = p.version_fields ? p.version_fields[f] : undefined;
      if (v === "" || v === undefined) v = null;
      vf[f] = v;
    }
    const old = await client.query(
      `SELECT * FROM aa.entered_version
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key);
    const oldRow = old.rows[0] || {};
    for (const f of VERSION_FIELDS)
      audit("entered_version", rowKey, f,
        f === "valid_until" && oldRow[f] ? String(oldRow[f]).slice(0, 10) : oldRow[f],
        vf[f]);
    await client.query(
      `INSERT INTO aa.entered_version (country_iso3, hazard, version,
          doc_title, doc_url, endorsed_by, valid_until, valid_until_source,
          window_rollup, supersedes, note, entered_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
       ON CONFLICT (country_iso3, hazard, version) DO UPDATE SET
          doc_title=$4, doc_url=$5, endorsed_by=$6, valid_until=$7,
          valid_until_source=$8, window_rollup=$9, supersedes=$10, note=$11,
          entered_by=$12, entered_at=now()`,
      [...key, vf.doc_title, vf.doc_url, vf.endorsed_by, vf.valid_until,
       vf.valid_until_source, vf.window_rollup, vf.supersedes, vf.note, by]);

    // --- merge into the registry, same transaction (DB-first: visible immediately).
    //     source='entered' only on a brand-new row — it records the first sighting;
    //     valid_from on insert = the version label padded to a date.
    const vfrom = version.length === 4 ? `${version}-01-01` : version.length === 7 ? `${version}-01` : version;
    await client.query(
      `INSERT INTO aa.framework_version (country_iso3, hazard, version, valid_from,
          doc_title, doc_url, endorsed_by, valid_until, valid_until_source,
          window_rollup, supersedes, note, source)
       VALUES ($1,$2,$3,$4::date,$5,$6,$7,$8::date,$9,$10,$11,$12,'entered')
       ON CONFLICT (country_iso3, hazard, version) DO UPDATE SET
          doc_title = COALESCE(EXCLUDED.doc_title, aa.framework_version.doc_title),
          doc_url = COALESCE(EXCLUDED.doc_url, aa.framework_version.doc_url),
          endorsed_by = COALESCE(EXCLUDED.endorsed_by, aa.framework_version.endorsed_by),
          valid_until = COALESCE(EXCLUDED.valid_until, aa.framework_version.valid_until),
          valid_until_source = COALESCE(EXCLUDED.valid_until_source, aa.framework_version.valid_until_source),
          window_rollup = COALESCE(EXCLUDED.window_rollup, aa.framework_version.window_rollup),
          supersedes = COALESCE(EXCLUDED.supersedes, aa.framework_version.supersedes),
          note = COALESCE(EXCLUDED.note, aa.framework_version.note),
          updated_at = now()`,
      [...key, vfrom, vf.doc_title, vf.doc_url, vf.endorsed_by, vf.valid_until,
       vf.valid_until_source, vf.window_rollup, vf.supersedes, vf.note]);

    // --- windows: replace-set with per-field audit
    const oldWin = (await client.query(
      `SELECT * FROM aa.entered_window
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key)).rows;
    const newWin = (p.windows || [])
      .map((w) => ({ ...w, window_name: String(w.window_name || "").trim() }))
      .filter((w) => w.window_name);
    const oldByName = Object.fromEntries(oldWin.map((w) => [w.window_name, w]));
    const newNames = new Set(newWin.map((w) => w.window_name));
    for (const w of oldWin)
      if (!newNames.has(w.window_name))
        audit("entered_window", `${rowKey}/${w.window_name}`, "window", w.window_name, null);
    for (const w of newWin) {
      const o = oldByName[w.window_name] || {};
      if (!oldByName[w.window_name])
        audit("entered_window", `${rowKey}/${w.window_name}`, "window", null, w.window_name);
      for (const f of WINDOW_FIELDS)
        audit("entered_window", `${rowKey}/${w.window_name}`, f, o[f], w[f] || null);
    }
    await client.query(
      `DELETE FROM aa.entered_window
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key);
    for (const w of newWin)
      await client.query(
        `INSERT INTO aa.entered_window (country_iso3, hazard, version, window_name,
            basis, trigger_statement, monitoring_period, note, entered_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
        [...key, w.window_name, w.basis || null, w.trigger_statement || null,
         w.monitoring_period || null, w.note || null, by]);

    // --- funding: ALL of it hangs off the window (aa.window_funding). The page's rows
    //     for this version with provenance 'entered' are a replace-set. Per-fund version
    //     totals are attributed to the single window when there is one, else parked on
    //     the 'unattributed' sentinel (a curation queue) — never stored as version rows.
    const fundKind = (fc) => (fc === "cofinancing" || fc === "other") ? "cofinancing" : "prearranged";
    const oldWF = (await client.query(
      `SELECT * FROM aa.window_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3 AND provenance='entered'
         AND agency IS NULL AND sector IS NULL`, key)).rows;
    const newWF = cleanFunding(p.window_funding, true).filter((f) => newNames.has(f.window_name));
    const single = newWin.length === 1 ? newWin[0].window_name : (newWin.length === 0 ? "single" : "unattributed");
    const newVF = cleanFunding(p.version_funding, false)
      .filter((f) => !newWF.some((w) => w.fund_code === f.fund_code))   // window rows win
      .map((f) => ({ ...f, window_name: single }));
    const all = [...newWF, ...newVF];
    const wfKey = (f) => `${f.window_name}|${f.fund_code}|${f.financier || ""}`;
    const oldBy = Object.fromEntries(oldWF.map((f) => [wfKey({window_name: f.window_name, fund_code: f.fund_code || "cofinancing", financier: f.financier}), f]));
    const newKeys = new Set(all.map(wfKey));
    for (const f of oldWF) {
      const k = wfKey({window_name: f.window_name, fund_code: f.fund_code || "cofinancing", financier: f.financier});
      if (!newKeys.has(k)) audit("window_funding", `${rowKey}/${f.window_name}/${f.fund_code || "cofinancing"}`, "amount_usd", f.amount_usd, null);
    }
    for (const f of all)
      audit("window_funding", `${rowKey}/${f.window_name}/${f.fund_code}`, "amount_usd",
        (oldBy[wfKey(f)] || {}).amount_usd, f.amount);
    await client.query(
      `DELETE FROM aa.window_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3 AND provenance='entered'
         AND agency IS NULL AND sector IS NULL`, key);
    for (const f of all) {
      const kind = fundKind(f.fund_code);
      await client.query(
        `INSERT INTO aa.window_funding (country_iso3, hazard, version, window_name, kind,
            fund_code, financier, amount_usd, provenance, source)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'entered',$9)
         ON CONFLICT DO NOTHING`,
        [...key, f.window_name, kind, kind === "cofinancing" ? null : f.fund_code,
         f.financier, f.amount, `entered:${by}`]);
    }

    for (const a of audits)
      await client.query(
        `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
         VALUES ($1,$2,$3,$4,$5,$6)`, a);
    await client.query("COMMIT");
    send(res, 200, { ok: true, changes: audits.length,
      saved: { windows: newWin.length, window_funding: newWF.length, version_funding: newVF.length, unattributed: newVF.filter((f) => f.window_name === 'unattributed').length } });
  } catch (e) {
    await client.query("ROLLBACK").catch(() => {});
    send(res, 502, { error: String(e.message || e) });
  } finally {
    client.release();
  }
}

// ------------------------------------------------------ generic admin (CRUD)
// Schema cache: every base table / view in aa with columns and key columns. The
// admin page is populated from this, so new tables and columns show up on their
// own. Identifiers are only ever taken from this cache (never from the request).
let SCHEMA = null, schemaAt = 0;
const IDENT = /^[a-z_][a-z0-9_]*$/;
const q = (id) => '"' + id.replace(/"/g, '""') + '"';
async function schema(force) {
  if (SCHEMA && !force && Date.now() - schemaAt < 60_000) return SCHEMA;
  const cols = (await pool.query(
    `SELECT c.table_name, c.column_name, c.data_type, c.udt_name, c.is_nullable = 'YES' AS nullable,
            c.column_default, c.ordinal_position, t.table_type
     FROM information_schema.columns c
     JOIN information_schema.tables t USING (table_schema, table_name)
     WHERE c.table_schema = 'aa' ORDER BY c.table_name, c.ordinal_position`)).rows;
  const keys = (await pool.query(
    `SELECT c.conrelid::regclass::text AS tbl, c.contype,
            array_agg(a.attname::text ORDER BY k.ord)::text[] AS cols
     FROM pg_constraint c
     JOIN pg_namespace n ON n.oid = c.connamespace
     JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
     JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
     WHERE n.nspname = 'aa' AND c.contype IN ('p','u')
     GROUP BY 1, 2, c.oid ORDER BY (c.contype = 'p') DESC`)).rows;
  const counts = (await pool.query(
    `SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'aa'`)).rows;
  const nrows = Object.fromEntries(counts.map((r) => [r.relname, Number(r.n_live_tup)]));
  const tables = {};
  for (const c of cols) {
    const t = (tables[c.table_name] ??= {
      name: c.table_name, kind: c.table_type === "VIEW" ? "view" : "table", columns: [],
      key: null, key_type: null, owner: TABLE_OWNER(c.table_name),
      writable: false, n_rows: nrows[c.table_name] ?? null,
    });
    t.columns.push({
      name: c.column_name, type: c.data_type, udt: c.udt_name, nullable: c.nullable,
      has_default: c.column_default != null,
      generated: /identity|nextval/i.test(c.column_default || "") || c.column_name === "updated_at",
    });
  }
  for (const k of keys) {
    const name = k.tbl.replace(/^aa\./, "").replace(/^"|"$/g, "");
    const t = tables[name];
    if (t && !t.key) { t.key = k.cols; t.key_type = k.contype === "p" ? "primary" : "unique"; }
  }
  for (const t of Object.values(tables))
    t.writable = t.kind === "table" && !!t.key && !isReadonly(t.name);
  SCHEMA = tables; schemaAt = Date.now();
  return SCHEMA;
}
function tableOf(sch, name, res) {
  const t = name && IDENT.test(name) ? sch[name] : null;
  if (!t) { send(res, 404, { error: "unknown table" }); return null; }
  return t;
}
const colOf = (t, name) => t.columns.find((c) => c.name === name) || null;
const rowKey = (t, row) => (t.key || []).map((k) => row[k] == null ? "" : String(row[k])).join("/");

async function adminSchema(req, res, qs) {
  if (limited(req, res, "read")) return;
  try { send(res, 200, { ok: true, role: role(req), tables: Object.values(await schema(qs.get("refresh") === "1")) }); }
  catch (e) { send(res, 502, { error: String(e.message || e) }); }
}

async function adminRows(req, res, qs) {
  if (limited(req, res, "read")) return;
  try {
    const sch = await schema(); const t = tableOf(sch, qs.get("table"), res); if (!t) return;
    const limit = Math.min(Math.max(parseInt(qs.get("limit") || "100", 10) || 100, 1), 500);
    const offset = Math.max(parseInt(qs.get("offset") || "0", 10) || 0, 0);
    const where = [], params = [];
    const search = (qs.get("q") || "").trim();
    if (search) {
      const textCols = t.columns.filter((c) => c.type === "text").map((c) => q(c.name));
      if (textCols.length) { params.push("%" + search + "%"); where.push("(" + textCols.map((c) => `${c} ILIKE $${params.length}`).join(" OR ") + ")"); }
    }
    for (const [k, v] of qs.entries()) {
      if (!k.startsWith("f.")) continue;
      const c = colOf(t, k.slice(2)); if (!c) continue;
      if (v === "∅") where.push(`${q(c.name)} IS NULL`);
      else { params.push(v); where.push(`${q(c.name)}::text = $${params.length}`); }
    }
    const W = where.length ? " WHERE " + where.join(" AND ") : "";
    const oc = colOf(t, qs.get("order") || "") || (t.key ? colOf(t, t.key[0]) : t.columns[0]);
    const dir = qs.get("dir") === "desc" ? "DESC" : "ASC";
    const order = oc ? ` ORDER BY ${q(oc.name)} ${dir} NULLS LAST` : "";
    const sel = t.columns.map((c) =>
      c.type === "date" ? `${q(c.name)}::text AS ${q(c.name)}`
      : c.type.startsWith("timestamp") ? `to_char(${q(c.name)} AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') AS ${q(c.name)}`
      : q(c.name)).join(", ");
    const [rows, total] = await Promise.all([
      pool.query(`SELECT ${sel} FROM aa.${q(t.name)}${W}${order} LIMIT ${limit} OFFSET ${offset}`, params),
      pool.query(`SELECT count(*)::int AS n FROM aa.${q(t.name)}${W}`, params),
    ]);
    send(res, 200, { ok: true, rows: rows.rows, total: total.rows[0].n, limit, offset });
  } catch (e) { send(res, 502, { error: String(e.message || e) }); }
}

async function adminDistinct(req, res, qs) {
  if (limited(req, res, "read")) return;
  try {
    const sch = await schema(); const t = tableOf(sch, qs.get("table"), res); if (!t) return;
    const c = colOf(t, qs.get("col") || ""); if (!c) return send(res, 404, { error: "unknown column" });
    const r = await pool.query(
      `SELECT ${q(c.name)}::text AS v, count(*)::int AS n FROM aa.${q(t.name)}
       GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 41`);
    send(res, 200, { ok: true, values: r.rows, truncated: r.rows.length > 40 });
  } catch (e) { send(res, 502, { error: String(e.message || e) }); }
}

// coerce form values: '' -> NULL; booleans; everything else is cast by Postgres
function coerce(c, v) {
  if (v === undefined) return undefined;
  if (v === null || v === "") return null;
  if (c.type === "boolean") return v === true || v === "true" || v === "t" || v === "1";
  return String(v);
}

async function adminSave(req, res) {
  if (limited(req, res, "write")) return;
  const p = await readBody(req, res); if (!p) return;
  const by = String(p.by || "").trim();
  if (!by) return send(res, 400, { error: "'by' (your name) is required" });
  const client = await pool.connect();
  try {
    const sch = await schema(); const t = tableOf(sch, p.table, res); if (!t) return;
    if (!t.writable) return send(res, 403, { error: `${t.name} is read-only here (owned by ${t.owner})` });
    const row = p.row && typeof p.row === "object" ? p.row : {};
    const editable = t.columns.filter((c) => !c.generated);
    await client.query("BEGIN");
    let key = p.key && typeof p.key === "object" ? p.key : null, oldRow = null;
    if (key) {
      const kc = t.key.map((k, i) => `${q(k)}::text = $${i + 1}`).join(" AND ");
      const cur = await client.query(`SELECT * FROM aa.${q(t.name)} WHERE ${kc}`, t.key.map((k) => String(key[k] ?? "")));
      if (!cur.rows.length) { await client.query("ROLLBACK"); return send(res, 404, { error: "row not found" }); }
      oldRow = cur.rows[0];
    }
    const audits = [], sets = [], params = [];
    const norm = (v) => v == null ? null : v instanceof Date ? v.toISOString().slice(0, 10) : String(v);
    for (const c of editable) {
      if (!(c.name in row)) continue;
      const v = coerce(c, row[c.name]);
      if (oldRow ? norm(oldRow[c.name]) === norm(v) : v === null) continue;   // no-op: skip
      params.push(v); sets.push(`${q(c.name)} = $${params.length}`);
      audits.push([by, t.name, "", c.name, oldRow ? norm(oldRow[c.name]) : null, norm(v)]);
    }
    let saved;
    if (oldRow) {
      if (!sets.length) { await client.query("ROLLBACK"); return send(res, 200, { ok: true, changes: 0, key }); }
      if (colOf(t, "updated_at")) sets.push("updated_at = now()");
      const kc = t.key.map((k) => { params.push(String(key[k] ?? "")); return `${q(k)}::text = $${params.length}`; }).join(" AND ");
      saved = (await client.query(`UPDATE aa.${q(t.name)} SET ${sets.join(", ")} WHERE ${kc} RETURNING *`, params)).rows[0];
    } else {
      const cols = editable.filter((c) => c.name in row && coerce(c, row[c.name]) !== null);
      if (!cols.length) { await client.query("ROLLBACK"); return send(res, 400, { error: "empty row" }); }
      const vals = cols.map((c) => coerce(c, row[c.name]));
      saved = (await client.query(
        `INSERT INTO aa.${q(t.name)} (${cols.map((c) => q(c.name)).join(", ")})
         VALUES (${cols.map((_, i) => `$${i + 1}`).join(", ")}) RETURNING *`, vals)).rows[0];
    }
    const rk = rowKey(t, saved);
    for (const a of audits) {
      a[2] = rk;
      await client.query(
        `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
         VALUES ($1,$2,$3,$4,$5,$6)`, a);
    }
    if (!oldRow)
      await client.query(
        `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
         VALUES ($1,$2,$3,'(row)',NULL,'created')`, [by, t.name, rk]);
    await client.query("COMMIT");
    send(res, 200, { ok: true, changes: audits.length, key: Object.fromEntries(t.key.map((k) => [k, saved[k]])), row: saved });
  } catch (e) {
    await client.query("ROLLBACK").catch(() => {});
    send(res, 400, { error: String(e.message || e) });
  } finally { client.release(); }
}

async function adminDelete(req, res) {
  if (limited(req, res, "write")) return;
  const p = await readBody(req, res); if (!p) return;
  const by = String(p.by || "").trim();
  if (!by) return send(res, 400, { error: "'by' (your name) is required" });
  const client = await pool.connect();
  try {
    const sch = await schema(); const t = tableOf(sch, p.table, res); if (!t) return;
    if (!t.writable) return send(res, 403, { error: `${t.name} is read-only here (owned by ${t.owner})` });
    const key = p.key && typeof p.key === "object" ? p.key : null;
    if (!key) return send(res, 400, { error: "key required" });
    const kc = t.key.map((k, i) => `${q(k)}::text = $${i + 1}`).join(" AND ");
    const params = t.key.map((k) => String(key[k] ?? ""));
    await client.query("BEGIN");
    const gone = (await client.query(`DELETE FROM aa.${q(t.name)} WHERE ${kc} RETURNING *`, params)).rows;
    if (gone.length !== 1) { await client.query("ROLLBACK"); return send(res, gone.length ? 409 : 404, { error: gone.length ? "key matches several rows" : "row not found" }); }
    await client.query(
      `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
       VALUES ($1,$2,$3,'(row)',$4,'deleted')`, [by, t.name, rowKey(t, gone[0]), JSON.stringify(gone[0]).slice(0, 4000)]);
    await client.query("COMMIT");
    send(res, 200, { ok: true });
  } catch (e) {
    await client.query("ROLLBACK").catch(() => {});
    send(res, 400, { error: String(e.message || e) });
  } finally { client.release(); }
}

// ----------------------------------------------------------------- /versions
// What a writer must know before touching a backtest: every version of a (country, hazard)
// pair with its status, role (which endorsed one is the latest, what a development one
// revises), validity, document, seal, and the backtest recorded now. /entries puts the same
// cards in every reply, so a dry run always says WHICH version it is about to change.
const BACKTEST_TABLES = ["window", "simulated_activation", "version_performance_reported"];
const DEV_STATUSES = new Set(["development", "pre-development"]);
const VERSION_COLS = ["country_iso3", "hazard", "version"];
const vkey = (o) => VERSION_COLS.map((c) => o[c]).join("/");

async function versionCards(db, pairs) {
  if (!pairs.length) return [];
  const args = [pairs.map((x) => x.country_iso3), pairs.map((x) => x.hazard)];
  const P = `(SELECT DISTINCT * FROM unnest($1::text[], $2::text[]) AS p(country_iso3, hazard))`;
  const vs = (await db.query(
    `SELECT f.country_iso3, f.hazard, f.version, f.kb_status AS status,
            f.valid_from::text AS valid_from, f.valid_until::text AS valid_until,
            (f.valid_until IS NOT NULL AND f.valid_until < CURRENT_DATE) AS lapsed,
            f.endorsed_by,
            coalesce(f.doc_title, d.title) AS doc_title, coalesce(d.official_url, f.doc_url) AS doc_url,
            f.backtest_sealed_at::text AS sealed_at,
            f.backtest_sealed_by AS sealed_by, f.backtest_sealed_against AS sealed_against
     FROM aa.framework_version f JOIN ${P} p USING (country_iso3, hazard)
     LEFT JOIN LATERAL (                      -- the version's current document, if registered
       SELECT fd.title, vd.official_url FROM aa.version_document vd
       JOIN aa.framework_document fd USING (sha256)
       WHERE (vd.country_iso3, vd.hazard, vd.version) = (f.country_iso3, f.hazard, f.version)
         AND vd.superseded_by IS NULL AND vd.role IN ('endorsed', 'published')
       ORDER BY (vd.role = 'endorsed') DESC LIMIT 1) d ON true
     ORDER BY f.country_iso3, f.hazard, coalesce(f.valid_from::text, f.version), f.version`, args)).rows;
  const ws = (await db.query(
    `SELECT w.country_iso3, w.hazard, w.version, w.window_name, w.analysis_start, w.analysis_end,
            w.source,
            (SELECT array_agg(s.event_year ORDER BY s.event_year) FROM aa.simulated_activation s
             WHERE (s.country_iso3, s.hazard, s.version, s.window_name)
                 = (w.country_iso3, w.hazard, w.version, w.window_name)) AS years
     FROM aa."window" w JOIN ${P} p USING (country_iso3, hazard)
     ORDER BY w.window_name`, args)).rows;
  const byPair = new Map();
  for (const v of vs) {
    const k = `${v.country_iso3}/${v.hazard}`;
    if (!byPair.has(k)) byPair.set(k, { country_iso3: v.country_iso3, hazard: v.hazard, versions: [] });
    byPair.get(k).versions.push({
      ...v, key: vkey(v), sealed: v.sealed_at != null,
      windows: ws.filter((w) => vkey(w) === vkey(v)).map((w) => ({
        window_name: w.window_name, analysis_start: w.analysis_start,
        analysis_end: w.analysis_end, source: w.source, years: w.years || [] })),
    });
  }
  for (const pair of byPair.values()) {      // versions arrive oldest first
    const endorsed = pair.versions.filter((v) => v.status === "endorsed");
    const current = endorsed[endorsed.length - 1];
    endorsed.forEach((v, i) => {
      v.role = v !== current ? `endorsed — superseded by ${endorsed[i + 1].version}`
        : "endorsed — the latest endorsed version" + (v.lapsed ? ` (validity ended ${v.valid_until})` : "");
    });
    for (const v of pair.versions) {
      if (DEV_STATUSES.has(v.status))
        v.role = current ? `${v.status} — a revision of ${current.version}, not endorsed`
                         : `${v.status} — no endorsed version of this framework yet`;
      else if (!v.role) v.role = `status not set (${v.status}) — set it on the tracking site`;
    }
  }
  return [...byPair.values()];
}

async function versions(req, res, qs) {
  if (limited(req, res, "read")) return;
  const iso3 = (qs.get("iso3") || "").toUpperCase(), hazard = qs.get("hazard") || "";
  if (!ISO_RE.test(iso3) || (hazard && !IDENT.test(hazard)))
    return send(res, 400, { error: "iso3 (and optionally hazard) required" });
  try {
    const pairs = (await pool.query(
      `SELECT country_iso3, hazard FROM aa.country_hazard WHERE country_iso3 = $1
       UNION SELECT country_iso3, hazard FROM aa.framework_version WHERE country_iso3 = $1`, [iso3])).rows;
    const want = hazard ? pairs.filter((x) => x.hazard === hazard) : pairs;
    const cards = await versionCards(pool, want);
    if (hazard && !cards.length)
      return send(res, 404, {
        error: `no framework version registered for ${iso3}/${hazard}`,
        hint: pairs.length ? `hazards registered for ${iso3}: ${pairs.map((x) => x.hazard).sort().join(", ")}`
                           : `nothing is registered for ${iso3}`,
        versions: await versionCards(pool, pairs) });
    send(res, 200, { ok: true, versions: cards });
  } catch (e) { send(res, 502, { error: String(e.message || e) }); }
}

// ------------------------------------------------------------------ /entries
// An entries file (the format of scripts/apply_entries.py: a row to upsert, a "delete" by
// full key, an "op": "replace" of a version's rows) applied NOW, in one transaction — the
// immediate path for the KB skill record-simulated-activations, from any repo. dry_run
// applies it, runs every check (seal, span, foreign keys, CHECKs) and rolls back.
//
// Backtests get four things on top, because a write can come from anywhere:
//   * the reply always carries the version cards of every pair the file touches, the
//     touched versions marked — the caller shows them before anyone says yes;
//   * a version that is not in aa.framework_version is refused, with the pair's real ones;
//   * an ENDORSED version's backtest is written only when confirm_endorsed names it (and
//     only it): development work can't land on the endorsed record by accident — and
//     confirm_endorsed naming a version that is not endorsed is refused as well;
//   * a sealed one is refused here as anywhere (the database's guard): errata only.
// "seal": {"version": "ISO3/hazard/version", "against": "the document + page"} seals an
// endorsed version in the same transaction, after the changes and the checks.
// The reply's `performance` is the recomputed backtest (aa.v_window_performance) as it
// stands inside the transaction. Every change is audited as 'entries-api: <entered_by>'.
const param = (v) => (v !== null && typeof v === "object" ? JSON.stringify(v) : v);
class Refusal extends Error {
  constructor(message, extra) { super(message); this.extra = extra || {}; }
}

async function applyEntries(req, res) {
  if (limited(req, res, "write")) return;
  const p = await readBody(req, res); if (!p) return;
  const by = String(p.entered_by || "").trim();
  if (!by) return send(res, 400, { error: "'entered_by' (who, from what) is required" });
  const items = Array.isArray(p.rows) ? p.rows : [];
  const seal = p.seal && typeof p.seal === "object" ? p.seal : null;
  if (!items.length && !seal) return send(res, 400, { error: "'rows' is empty" });
  const dry = p.dry_run === true;
  const confirmed = new Set(Array.isArray(p.confirm_endorsed) ? p.confirm_endorsed.map(String) : []);
  const sch = await schema();
  const client = await pool.connect();
  const plan = [];
  let cards = [];
  try {
    // ---- which backtest versions does this touch?
    const touched = new Map();
    const touch = (i, obj) => {
      if (VERSION_COLS.some((c) => typeof obj[c] !== "string" || !obj[c]))
        throw new Refusal(`item ${i}: a backtest row needs ${VERSION_COLS.join(", ")}`);
      touched.set(vkey(obj), Object.fromEntries(VERSION_COLS.map((c) => [c, obj[c]])));
    };
    items.forEach((item, i) => {
      if (!item || typeof item !== "object") throw new Refusal(`item ${i}: not an object`);
      if (!BACKTEST_TABLES.includes(item.table)) return;
      if (item.delete) touch(i, item.delete);
      else if (item.op === "replace") { touch(i, item.scope || {}); (item.rows || []).forEach((r) => touch(i, r)); }
      else touch(i, item.row || {});
    });
    let sealKey = null;
    if (seal) {
      const m = /^([A-Z]{3})\/([a-z_]+)\/(.+)$/.exec(String(seal.version || ""));
      if (!m) throw new Refusal("seal.version must be 'ISO3/hazard/version'");
      if (!String(seal.against || "").trim())
        throw new Refusal("seal.against is required: the endorsed document (link) + page / table the record was checked against");
      sealKey = m[0];
      touched.set(sealKey, { country_iso3: m[1], hazard: m[2], version: m[3] });
    }

    await client.query("BEGIN");
    const pairs = [...new Map([...touched.values()].map((t) => [`${t.country_iso3}/${t.hazard}`, t])).values()];
    cards = await versionCards(client, pairs);
    const cardOf = new Map();
    for (const pair of cards) for (const v of pair.versions) {
      v.target = touched.has(v.key);
      cardOf.set(v.key, v);
    }
    // ---- the target must be a registered version, unsealed; endorsed only when named
    const needsConfirm = [];
    for (const k of touched.keys()) {
      const v = cardOf.get(k);
      const t0 = touched.get(k);
      if (!v && !cards.some((pr) => pr.country_iso3 === t0.country_iso3 && pr.hazard === t0.hazard)) {
        const others = (await client.query(           // wrong hazard word? show the country's pairs
          `SELECT country_iso3, hazard FROM aa.country_hazard WHERE country_iso3 = $1
           UNION SELECT country_iso3, hazard FROM aa.framework_version WHERE country_iso3 = $1`,
          [t0.country_iso3])).rows;
        cards = await versionCards(client, others);
        throw new Refusal(`${k}: no framework is registered for ${t0.country_iso3}/${t0.hazard} — nothing written`, {
          hint: others.length ? `hazards registered for ${t0.country_iso3}: ${others.map((x) => x.hazard).sort().join(", ")}`
                              : `nothing is registered for ${t0.country_iso3}` });
      }
      if (!v) throw new Refusal(`${k} is not a registered framework version — nothing written`, {
        hint: "Pick one of the registered versions below (the label must match exactly), or register the version on the tracking site (entry page) first. Never write a backtest under a label that is no version." });
      if (v.sealed) throw new Refusal(`the backtest of ${k} is SEALED (checked against: ${v.sealed_against}) — nothing written`, {
        hint: "A sealed backtest changes only through an erratum: backtests/errata/ in ds-aa-tracking (backtests/README.md). A changed analysis is a new version." });
      const isDev = DEV_STATUSES.has(v.status);
      if (!isDev) needsConfirm.push(k);
      if (isDev && confirmed.has(k)) throw new Refusal(`${k} was confirmed as the endorsed version to write, but it is in ${v.status} — check which version you mean. Nothing written`);
    }
    for (const k of confirmed)
      if (!touched.has(k)) throw new Refusal(`${k} was confirmed as the endorsed version to write, but this file does not touch it — check which version the file is for. Nothing written`);
    const unconfirmed = needsConfirm.filter((k) => !confirmed.has(k));
    if (!dry && unconfirmed.length)
      throw new Refusal(`${unconfirmed.join(", ")}: an ENDORSED version — its backtest is the record of what was endorsed. Nothing written`, {
        hint: "If the endorsed version is really the one to change (a backfill from the endorsed document), confirm it by name (confirm_endorsed). If you are iterating on a revision, write to the development version instead." });
    if (sealKey && cardOf.get(sealKey).status !== "endorsed")
      throw new Refusal(`${sealKey} is not endorsed: only an endorsed version's backtest is sealed`);

    const audit = (t, k, field, oldv, newv) => client.query(
      `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
       VALUES ($1,$2,$3,$4,$5,$6)`,
      [`entries-api: ${by}`, t, k, field, oldv == null ? null : JSON.stringify(oldv).slice(0, 4000),
       newv == null ? null : JSON.stringify(newv).slice(0, 4000)]);
    const match = (obj) => {
      const ks = Object.keys(obj);
      return [ks.map((c, j) => `${q(c)} IS NOT DISTINCT FROM $${j + 1}`).join(" AND "),
              ks.map((c) => param(obj[c]))];
    };
    for (const [i, item] of items.entries()) {
      const t = IDENT.test(item.table || "") ? sch[item.table] : null;
      if (!t) throw new Refusal(`item ${i}: unknown table ${item.table}`);
      if (!t.writable) throw new Refusal(`item ${i}: aa.${t.name} is read-only here (owned by ${t.owner})`);
      const cols = new Set(t.columns.map((c) => c.name));
      const known = (obj) => {
        const bad = Object.keys(obj || {}).filter((c) => !cols.has(c));
        if (bad.length) throw new Refusal(`item ${i}: aa.${t.name} has no column(s) ${bad.join(", ")}`);
      };
      const insert = async (row) => {
        known(row);
        const cs = Object.keys(row);
        if (!cs.length) throw new Refusal(`item ${i}: empty row`);
        await client.query(`INSERT INTO aa.${q(t.name)} (${cs.map(q).join(", ")})
                            VALUES (${cs.map((_, j) => `$${j + 1}`).join(", ")})`, cs.map((c) => param(row[c])));
        await audit(t.name, rowKey(t, row), "(row)", null, row);
      };
      if (item.delete) {                       // one row by its full key; a missing row fails
        const key = item.delete;
        known(key);
        if (Object.keys(key).length !== t.key.length || !t.key.every((k) => k in key))
          throw new Refusal(`item ${i}: a delete on aa.${t.name} must give exactly its key (${t.key.join(", ")})`);
        const [w, vals] = match(key);
        const gone = (await client.query(`DELETE FROM aa.${q(t.name)} WHERE ${w} RETURNING *`, vals)).rows;
        if (gone.length !== 1) throw new Refusal(`item ${i}: no aa.${t.name} row ${rowKey(t, key)} to delete`);
        await audit(t.name, rowKey(t, gone[0]), "(delete)", gone[0], null);
        plan.push({ op: "delete", table: t.name, key, before: gone[0] });
      } else if (item.op === "replace") {      // the rows BECOME the scope's rows
        const scope = item.scope || {};
        known(scope);
        if (!VERSION_COLS.every((c) => cols.has(c) && scope[c] != null))
          throw new Refusal(`item ${i}: a replace needs a scope naming one version (${VERSION_COLS.join(", ")})`);
        const rows = item.rows || [];
        for (const r of rows)
          for (const c of Object.keys(scope))
            if (r[c] !== scope[c]) throw new Refusal(`item ${i}: a row is outside the scope (${c})`);
        const [w, vals] = match(scope);
        const before = (await client.query(`DELETE FROM aa.${q(t.name)} WHERE ${w} RETURNING *`, vals)).rows;
        for (const b of before) await audit(t.name, rowKey(t, b), "(delete)", b, null);
        for (const r of rows) await insert(r);
        plan.push({ op: "replace", table: t.name, scope, before, after: rows });
      } else if (item.op == null || item.op === "upsert") {
        const row = item.row || {};
        known(row);
        const key = Object.fromEntries(t.key.map((k) => [k, row[k] ?? null]));
        const [w, vals] = match(key);
        const cur = (await client.query(`SELECT * FROM aa.${q(t.name)} WHERE ${w}`, vals)).rows;
        if (cur.length > 1) throw new Refusal(`item ${i}: key matches ${cur.length} rows in aa.${t.name}`);
        if (cur.length) {
          const sets = Object.keys(row).filter((c) => !t.key.includes(c));
          if (sets.length) {
            const upd = sets.map((c, j) => `${q(c)} = $${vals.length + j + 1}`);
            if (cols.has("updated_at") && !sets.includes("updated_at")) upd.push("updated_at = now()");
            await client.query(`UPDATE aa.${q(t.name)} SET ${upd.join(", ")} WHERE ${w}`,
                               [...vals, ...sets.map((c) => param(row[c]))]);
            await audit(t.name, rowKey(t, cur[0]), "(row)", cur[0], row);
          }
          plan.push({ op: "update", table: t.name, key, before: cur[0], after: row });
        } else {
          await insert(row);
          plan.push({ op: "insert", table: t.name, key, after: row });
        }
      } else throw new Refusal(`item ${i}: unknown op ${item.op} (a row, a delete, or op: replace)`);
    }
    await client.query("SET CONSTRAINTS ALL IMMEDIATE");   // span + foreign keys, now

    // ---- the backtest as it now stands (inside the transaction)
    const tk = [...touched.values()];
    const targ = [tk.map((x) => x.country_iso3), tk.map((x) => x.hazard), tk.map((x) => x.version)];
    const T = `(SELECT * FROM unnest($1::text[], $2::text[], $3::text[]) AS t(country_iso3, hazard, version))`;
    const windows = tk.length ? (await client.query(
      `SELECT pf.country_iso3, pf.hazard, pf.version, pf.window_name, pf.analysis_start, pf.analysis_end,
              pf.analysis_years, pf.n_activations::int AS n_activations, pf.return_period::float8 AS return_period,
              pf.activation_prob::float8 AS activation_prob, pf.rp_reported::float8 AS rp_reported,
              (SELECT array_agg(s.event_year ORDER BY s.event_year) FROM aa.simulated_activation s
               WHERE (s.country_iso3, s.hazard, s.version, s.window_name)
                   = (pf.country_iso3, pf.hazard, pf.version, pf.window_name)) AS years
       FROM aa.v_window_performance pf JOIN ${T} t USING (country_iso3, hazard, version)
       ORDER BY 1, 2, 3, 4`, targ)).rows : [];
    const overall = tk.length ? (await client.query(
      `SELECT fp.country_iso3, fp.hazard, fp.version, fp.analysis_years, fp.n_activation_years::int AS n_activation_years,
              fp.overall_return_period::float8 AS overall_return_period
       FROM aa.v_framework_performance fp JOIN ${T} t USING (country_iso3, hazard, version)`, targ)).rows : [];

    let sealed = null;
    if (sealKey) {
      const s = touched.get(sealKey), sv = [s.country_iso3, s.hazard, s.version];
      const mine = windows.filter((w) => vkey(w) === sealKey);
      if (!mine.length) throw new Refusal(`${sealKey} has no backtest windows to seal`);
      const open = mine.filter((w) => w.analysis_start == null || w.analysis_end == null);
      if (open.length) throw new Refusal(`${sealKey}: window(s) without an analysis span (${open.map((w) => w.window_name).join(", ")}) — complete before sealing`);
      if (!dry) {
        await client.query(
          `UPDATE aa.framework_version SET backtest_sealed_at = now(), backtest_sealed_by = $4,
                  backtest_sealed_against = $5
           WHERE country_iso3 = $1 AND hazard = $2 AND version = $3`, [...sv, by, String(seal.against).trim()]);
        await audit("framework_version", sealKey, "backtest_sealed_against", null, String(seal.against).trim());
      }
      sealed = { version: sealKey, against: String(seal.against).trim() };
    }
    await client.query(dry ? "ROLLBACK" : "COMMIT");
    send(res, 200, { ok: true, dry_run: dry, applied: !dry, items: plan.length, versions: cards,
                     needs_confirm_endorsed: needsConfirm, sealed, performance: { windows, overall }, plan });
  } catch (e) {
    await client.query("ROLLBACK").catch(() => {});
    const FK_HINT = {
      simulated_activation_window_fk: "Simulated years and their window go together: replace simulated_activation for the same version in the same file (a year needs its window; a window can't be dropped from under its years).",
      window_version_fk: "A window belongs to a registered framework version.",
      version_performance_reported_version_fk: "Reported performance belongs to a registered framework version.",
    };
    send(res, 400, { error: String(e.message || e),
                     hint: (e.extra && e.extra.hint) || e.hint || FK_HINT[e.constraint] || undefined,
                     detail: e.detail || undefined, versions: cards.length ? cards : undefined, dry_run: dry });
  } finally { client.release(); }
}

// ------------------------------------------------------------------- server
const server = http.createServer(async (req, res) => {
  const allowed = cors(req, res);
  if (req.method === "OPTIONS") { res.writeHead(allowed ? 204 : 403); return res.end(); }
  const url = new URL(req.url, "http://x");
  if (req.method === "GET" && url.pathname === "/health") {
    let db = false;
    if (pool) { try { await pool.query("SELECT 1"); db = true; } catch (e) {} }
    return send(res, 200, { ok: true, db, llm: !!API_KEY });
  }
  if (!allowed && req.headers.origin) return send(res, 403, { error: "origin not allowed" });
  const r = role(req);
  if (!r) return send(res, 401, { error: "bad site token" });
  if (req.method === "GET" && url.pathname === "/whoami") return send(res, 200, { ok: true, role: r });
  if (req.method === "GET" && url.pathname === "/framework") return framework(req, res, url.searchParams);
  if (!pool && ["/schema", "/rows", "/distinct", "/save", "/delete", "/entries", "/versions"].includes(url.pathname))
    return send(res, 500, { error: "DB not configured" });
  if (req.method === "GET" && url.pathname === "/schema") return adminSchema(req, res, url.searchParams);
  if (req.method === "GET" && url.pathname === "/rows") return adminRows(req, res, url.searchParams);
  if (req.method === "GET" && url.pathname === "/distinct") return adminDistinct(req, res, url.searchParams);
  if (req.method === "GET" && url.pathname === "/versions") return versions(req, res, url.searchParams);
  if (r !== "editor" && ["/extract", "/entry", "/save", "/delete", "/entries"].includes(url.pathname))
    return send(res, 401, { error: "editor token required" });   // 401: pages prompt for it
  if (req.method === "POST" && url.pathname === "/extract") return extract(req, res);
  if (req.method === "POST" && url.pathname === "/entry") return entry(req, res);
  if (req.method === "POST" && url.pathname === "/save") return adminSave(req, res);
  if (req.method === "POST" && url.pathname === "/delete") return adminDelete(req, res);
  if (req.method === "POST" && url.pathname === "/entries") return applyEntries(req, res);
  send(res, 404, { error: "not found" });
});

server.listen(process.env.PORT || 8080, () =>
  console.log("aa entry proxy listening", process.env.PORT || 8080));
