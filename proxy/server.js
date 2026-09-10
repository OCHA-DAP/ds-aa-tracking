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
 *   POST /entry      upsert aa.entered_version / entered_window /
 *                    entered_window_funding / entered_version_funding for one
 *                    (country, hazard, version); every field change is written
 *                    to aa.entry_audit (old, new, who, when). Replace-set
 *                    semantics per version: the posted windows/funding ARE the
 *                    version's rows. The nightly/manual ingest merges entered_*
 *                    into aa.framework_version (entered values win).
 *
 * Guards: site token (embedded in the staticrypt-encrypted page), origin
 * allowlist, model allowlist, size cap, per-IP rate limits. The Anthropic key
 * can never be used for arbitrary requests; the DB login only reaches the
 * entered_* tables through the queries below.
 */
const http = require("http");
const { Pool } = require("pg");

const API_KEY = process.env.ANTHROPIC_API_KEY;
const SITE_TOKEN = process.env.SITE_TOKEN || "";
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ||
  "https://ocha-dap.github.io").split(",");
const MODELS = new Set([
  "claude-sonnet-5",
  "claude-haiku-4-5-20251001",
  "claude-opus-5",
]);
const MAX_BODY = 45 * 1024 * 1024;
const RATE = { extract: 20, entry: 60, read: 300, windowMs: 60 * 60 * 1000 };
const hits = new Map();

const pool = process.env.DSCI_AZ_DB_DEV_HOST
  ? new Pool({
      host: process.env.DSCI_AZ_DB_DEV_HOST,
      user: process.env.DSCI_AZ_DB_DEV_UID_WRITE,
      password: process.env.DSCI_AZ_DB_DEV_PW_WRITE,
      database: "postgres",
      ssl: { rejectUnauthorized: false },
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
    res.setHeader("Access-Control-Allow-Headers", "content-type,x-site-token");
    res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
    return true;
  }
  return false;
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
        `SELECT version, window_name, fund_code, financier, amount_usd
         FROM aa.entered_window_funding WHERE country_iso3=$1 AND hazard=$2`, key),
      pool.query(
        `SELECT version, fund_code, financier, total_usd
         FROM aa.entered_version_funding WHERE country_iso3=$1 AND hazard=$2`, key),
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

    // --- window funding: replace-set
    const oldWF = (await client.query(
      `SELECT * FROM aa.entered_window_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key)).rows;
    const newWF = cleanFunding(p.window_funding, true)
      .filter((f) => newNames.has(f.window_name));
    const wfKey = (f) => `${f.window_name}|${f.fund_code}`;
    const oldWFBy = Object.fromEntries(oldWF.map((f) => [wfKey(f), f]));
    const newWFKeys = new Set(newWF.map(wfKey));
    for (const f of oldWF)
      if (!newWFKeys.has(wfKey(f)))
        audit("entered_window_funding", `${rowKey}/${f.window_name}/${f.fund_code}`,
          "amount_usd", f.amount_usd, null);
    for (const f of newWF)
      audit("entered_window_funding", `${rowKey}/${f.window_name}/${f.fund_code}`,
        "amount_usd", (oldWFBy[wfKey(f)] || {}).amount_usd, f.amount);
    await client.query(
      `DELETE FROM aa.entered_window_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key);
    for (const f of newWF)
      await client.query(
        `INSERT INTO aa.entered_window_funding (country_iso3, hazard, version,
            window_name, fund_code, financier, amount_usd, entered_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
        [...key, f.window_name, f.fund_code, f.financier, f.amount, by]);

    // --- version funding (explicit per-fund totals): replace-set
    const oldVF = (await client.query(
      `SELECT * FROM aa.entered_version_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key)).rows;
    const newVF = cleanFunding(p.version_funding, false);
    const oldVFBy = Object.fromEntries(oldVF.map((f) => [f.fund_code, f]));
    const newVFKeys = new Set(newVF.map((f) => f.fund_code));
    for (const f of oldVF)
      if (!newVFKeys.has(f.fund_code))
        audit("entered_version_funding", `${rowKey}/${f.fund_code}`, "total_usd", f.total_usd, null);
    for (const f of newVF)
      audit("entered_version_funding", `${rowKey}/${f.fund_code}`, "total_usd",
        (oldVFBy[f.fund_code] || {}).total_usd, f.amount);
    await client.query(
      `DELETE FROM aa.entered_version_funding
       WHERE country_iso3=$1 AND hazard=$2 AND version=$3`, key);
    for (const f of newVF)
      await client.query(
        `INSERT INTO aa.entered_version_funding (country_iso3, hazard, version,
            fund_code, financier, total_usd, entered_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7)`,
        [...key, f.fund_code, f.financier, f.amount, by]);

    for (const a of audits)
      await client.query(
        `INSERT INTO aa.entry_audit (entered_by, table_name, row_key, field, old_value, new_value)
         VALUES ($1,$2,$3,$4,$5,$6)`, a);
    await client.query("COMMIT");
    send(res, 200, { ok: true, changes: audits.length,
      saved: { windows: newWin.length, window_funding: newWF.length, version_funding: newVF.length } });
  } catch (e) {
    await client.query("ROLLBACK").catch(() => {});
    send(res, 502, { error: String(e.message || e) });
  } finally {
    client.release();
  }
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
  if (SITE_TOKEN && req.headers["x-site-token"] !== SITE_TOKEN)
    return send(res, 401, { error: "bad site token" });
  if (req.method === "POST" && url.pathname === "/extract") return extract(req, res);
  if (req.method === "GET" && url.pathname === "/framework") return framework(req, res, url.searchParams);
  if (req.method === "POST" && url.pathname === "/entry") return entry(req, res);
  send(res, 404, { error: "not found" });
});

server.listen(process.env.PORT || 8080, () =>
  console.log("aa entry proxy listening", process.env.PORT || 8080));
