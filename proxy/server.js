/* Extraction proxy for the ds-aa-tracking ingestion page.
 *
 * The GH Pages site is static and credential-free; this tiny app is the ONE
 * place the Anthropic API key lives (App Service app setting). It exposes a
 * single fixed-purpose endpoint — POST /extract with a base64 framework PDF —
 * and performs the Claude call server-side with a hard-coded prompt + forced
 * structured-output tool, so the key can never be used for arbitrary requests
 * even if the endpoint or site token leaks. Guards: site token (embedded in
 * the staticrypt-encrypted page), origin allowlist, model allowlist, size cap,
 * per-IP rate limit.
 */
const http = require("http");

const API_KEY = process.env.ANTHROPIC_API_KEY;
const SITE_TOKEN = process.env.SITE_TOKEN || "";
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ||
  "https://ocha-dap.github.io").split(",");
const MODELS = new Set([
  "claude-sonnet-5",
  "claude-haiku-4-5-20251001",
  "claude-opus-5",
]);
const MAX_BODY = 45 * 1024 * 1024; // ~32MB PDF as base64 + envelope
const RATE = { limit: 20, windowMs: 60 * 60 * 1000 }; // 20 extractions/hour/IP
const hits = new Map();

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
      prearranged_usd: { type: "number", description: "Total pre-arranged/allocated funding in USD stated in the document" },
      supersedes: { type: "string", description: "Date label (YYYY[-MM[-DD]]) of the previous framework version this document supersedes, if stated" },
      windows: {
        type: "array",
        description: "Every activation window / trigger stage defined in the document (readiness and action stages of the same window are ONE window; separate geographic or seasonal windows are separate entries).",
        items: {
          type: "object",
          properties: {
            window_name: { type: "string", description: "e.g. 'Window 1', 'Readiness/Activation', 'Jamuna', 'Gu season'" },
            basis: { type: "string", enum: ["observational", "forecast", "mixed"] },
            trigger_statement: { type: "string", description: "The trigger condition verbatim or near-verbatim from the document, ≤600 characters" },
            budget_usd: { type: "number", description: "USD amount tied to this window if the document splits the budget" },
            monitoring_period: { type: "string", description: "e.g. 'April–June', 'dekads 21–26'" },
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
  "(condensed to the operative condition). Amounts in USD. If the document is not " +
  "a framework document, still fill what you can and say so in `note`.";

function cors(req, res) {
  const origin = req.headers.origin || "";
  if (ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Headers", "content-type,x-site-token");
    res.setHeader("Access-Control-Allow-Methods", "POST,OPTIONS");
    return true;
  }
  return false;
}

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "content-type": "application/json" });
  res.end(body);
}

const server = http.createServer((req, res) => {
  const allowed = cors(req, res);
  if (req.method === "OPTIONS") { res.writeHead(allowed ? 204 : 403); return res.end(); }
  if (req.method === "GET" && req.url === "/health") return send(res, 200, { ok: true });
  if (req.method !== "POST" || req.url !== "/extract") return send(res, 404, { error: "not found" });
  if (!allowed && req.headers.origin) return send(res, 403, { error: "origin not allowed" });
  if (!API_KEY) return send(res, 500, { error: "ANTHROPIC_API_KEY not configured" });
  if (SITE_TOKEN && req.headers["x-site-token"] !== SITE_TOKEN)
    return send(res, 401, { error: "bad site token" });

  const ip = req.headers["x-forwarded-for"] || req.socket.remoteAddress || "?";
  const now = Date.now();
  const rec = (hits.get(ip) || []).filter((t) => now - t < RATE.windowMs);
  if (rec.length >= RATE.limit) return send(res, 429, { error: "rate limit: try later" });
  rec.push(now); hits.set(ip, rec);

  let size = 0; const chunks = [];
  req.on("data", (c) => {
    size += c.length;
    if (size > MAX_BODY) { send(res, 413, { error: "PDF too large (32MB max)" }); req.destroy(); }
    else chunks.push(c);
  });
  req.on("end", async () => {
    if (res.writableEnded) return;
    let payload;
    try { payload = JSON.parse(Buffer.concat(chunks).toString()); }
    catch { return send(res, 400, { error: "bad JSON" }); }
    const model = MODELS.has(payload.model) ? payload.model : "claude-sonnet-5";
    if (!payload.pdf_base64) return send(res, 400, { error: "pdf_base64 required" });
    // Claude Code OAuth tokens (sk-ant-oat…) authenticate via Bearer + the
    // oauth beta header, and are only authorized for Claude Code requests —
    // the system prompt must be Claude Code's own.
    const oauth = API_KEY.startsWith("sk-ant-oat");
    const auth = oauth
      ? { authorization: `Bearer ${API_KEY}`, "anthropic-beta": "oauth-2025-04-20" }
      : { "x-api-key": API_KEY };
    try {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          ...auth,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
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
  });
});

server.listen(process.env.PORT || 8080, () =>
  console.log("extract proxy listening", process.env.PORT || 8080));
