const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const net = require("net");
const { execFile } = require("child_process");
const { URL } = require("url");

const HOST = "127.0.0.1";
const PORT = Number(process.env.PORT || 8787);
const IBKR_BASE = process.env.IBKR_BASE || "https://localhost:5000/v1/api";
const LIVE_ORDERS_ENABLED = process.env.ENABLE_LIVE_ORDERS === "1";
const FULL_AUTO_ENABLED = process.env.ENABLE_FULL_AUTO === "1";
const ROOT = __dirname;
const DATA_DIR = path.join(ROOT, "data");
const STATE_FILE = path.join(DATA_DIR, "app_state.json");
const AUDIT_FILE = path.join(DATA_DIR, "audit.jsonl");
const MODEL_PACK_FILE = path.join(DATA_DIR, "bot_model_pack.json");
const RESEARCH_FILE = path.join(DATA_DIR, "market_research_snapshot.json");
const NEWS_RSS_URL = process.env.NEWS_RSS_URL || "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US";
const NEWS_DISABLED = process.env.DISABLE_NEWS_FETCH === "1";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-5.4-mini";

fs.mkdirSync(DATA_DIR, { recursive: true });

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8"
};
const SIDES = new Set(["BUY", "SELL"]);
const ORDER_TYPES = new Set(["LMT", "MKT", "STP", "STOP", "STP LMT", "STOP_LIMIT"]);
const LIMIT_ORDER_TYPES = new Set(["LMT", "STP LMT", "STOP_LIMIT"]);
const STOP_ORDER_TYPES = new Set(["STP", "STOP", "STP LMT", "STOP_LIMIT"]);
const TIFS = new Set(["DAY", "GTC", "IOC"]);
const MODEL_PACK_STYLES = new Set(["DAY_TRADE", "OVERNIGHT_1D", "SWING_5D", "SWING_20D"]);

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, {
    "content-type": type,
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type"
  });
  res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) reject(new Error("request too large"));
    });
    req.on("end", () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(error);
      }
    });
  });
}

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
}

function readJsonFile(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonFile(filePath, value) {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2));
}

function writeState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify({ ...state, savedAt: new Date().toISOString() }, null, 2));
}

function appendAudit(event) {
  const row = { time: new Date().toISOString(), ...event };
  fs.appendFileSync(AUDIT_FILE, `${JSON.stringify(row)}\n`);
  return row;
}

function readAudit(limit = 500) {
  try {
    return fs.readFileSync(AUDIT_FILE, "utf8")
      .trim()
      .split(/\n+/)
      .filter(Boolean)
      .slice(-limit)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

function fetchText(targetUrl, timeoutMs = 6000) {
  return new Promise((resolve, reject) => {
    const target = new URL(targetUrl);
    const client = target.protocol === "http:" ? http : https;
    const req = client.request({
      hostname: target.hostname,
      port: target.port || (target.protocol === "http:" ? 80 : 443),
      path: `${target.pathname}${target.search}`,
      method: "GET",
      headers: { "user-agent": "StockPerformanceAnalyzer/1.0", "accept": "application/rss+xml, application/xml, text/xml, */*" }
    }, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        res.resume();
        reject(new Error(`news feed returned ${res.statusCode}`));
        return;
      }
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        text += chunk;
        if (text.length > 500000) req.destroy(new Error("news feed too large"));
      });
      res.on("end", () => resolve(text));
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error("news feed timeout")));
    req.on("error", reject);
    req.end();
  });
}

function postJson(targetUrl, body, headers = {}, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const target = new URL(targetUrl);
    const client = target.protocol === "http:" ? http : https;
    const payload = JSON.stringify(body);
    const req = client.request({
      hostname: target.hostname,
      port: target.port || (target.protocol === "http:" ? 80 : 443),
      path: `${target.pathname}${target.search}`,
      method: "POST",
      headers: {
        "content-type": "application/json",
        "accept": "application/json",
        "content-length": Buffer.byteLength(payload),
        ...headers
      }
    }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => { text += chunk; });
      res.on("end", () => {
        let data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch {
          data = text;
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(typeof data === "object" && data?.error?.message ? data.error.message : `HTTP ${res.statusCode}`));
          return;
        }
        resolve(data);
      });
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error("OpenAI request timeout")));
    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

function xmlDecode(value) {
  return String(value || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .trim();
}

function xmlTag(item, tag) {
  const match = item.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return match ? xmlDecode(match[1]) : "";
}

function newsSentiment(title) {
  const text = String(title || "").toLowerCase();
  if (/\b(beat|beats|upgrade|upgraded|raises|raised|rise|rises|surge|rally|record|approval|profit|growth)\b/.test(text)) return "positive";
  if (/\b(cut|cuts|downgrade|downgraded|miss|misses|probe|lawsuit|fall|falls|drop|weak|warning|loss|recall)\b/.test(text)) return "negative";
  return "neutral";
}

function parseRssItems(xml, limit = 3) {
  const items = String(xml || "").match(/<item\b[\s\S]*?<\/item>/gi) || [];
  return items.slice(0, limit).map((item) => {
    const title = xmlTag(item, "title");
    return {
      title,
      source: "Yahoo Finance RSS",
      url: xmlTag(item, "link"),
      published_at: xmlTag(item, "pubDate"),
      sentiment: newsSentiment(title)
    };
  }).filter((item) => item.title);
}

async function fetchNews(symbol) {
  if (NEWS_DISABLED) return { status: "news_unavailable", items: [], error: "news fetch disabled" };
  try {
    const url = NEWS_RSS_URL.replace(/\{symbol\}/g, encodeURIComponent(symbol));
    const xml = await fetchText(url);
    const items = parseRssItems(xml);
    return { status: items.length ? "ok" : "news_unavailable", items, error: "" };
  } catch (error) {
    return { status: "news_unavailable", items: [], error: error.message };
  }
}

function extractOpenAiText(response) {
  if (typeof response?.output_text === "string") return response.output_text;
  const parts = [];
  for (const item of response?.output || []) {
    for (const content of item.content || []) {
      if (typeof content.text === "string") parts.push(content.text);
    }
  }
  return parts.join("\n");
}

function parseJsonFromText(text) {
  const raw = String(text || "").trim();
  try {
    return JSON.parse(raw);
  } catch {
    const match = raw.match(/\{[\s\S]*\}/);
    return match ? JSON.parse(match[0]) : null;
  }
}

async function openAiResearch(symbol, row, market) {
  if (!OPENAI_API_KEY) return { ok: false, skipped: "OPENAI_API_KEY not set" };
  const response = await postJson("https://api.openai.com/v1/responses", {
    model: OPENAI_MODEL,
    reasoning: { effort: "low" },
    text: { verbosity: "low" },
    max_output_tokens: 700,
    input: [
      {
        role: "system",
        content: "You are a cautious market research assistant for a local stock dashboard. Return only JSON. You may pass, reduce, reject, or news_unavailable; you may not approve live trading. Use only supplied technicals and cited news."
      },
      {
        role: "user",
        content: JSON.stringify({
          task: "Return JSON with keys action, ai_view, reasons. action must be pass, reduce, reject, or news_unavailable.",
          symbol,
          market,
          technical: row.technical || {},
          news: (row.news || []).slice(0, 5).map((item) => ({
            title: item.title,
            source: item.source,
            url: item.url,
            published_at: item.published_at,
            sentiment: item.sentiment
          })),
          current_action: row.action || "reduce",
          current_reasons: row.reasons || []
        })
      }
    ]
  }, { authorization: `Bearer ${OPENAI_API_KEY}` });
  const parsed = parseJsonFromText(extractOpenAiText(response));
  const action = String(parsed?.action || row.action || "reduce").toLowerCase();
  return {
    ok: true,
    action: ["pass", "reduce", "reject", "news_unavailable"].includes(action) ? action : "reduce",
    ai_view: String(parsed?.ai_view || row.ai_view || "").slice(0, 500),
    reasons: Array.isArray(parsed?.reasons) ? parsed.reasons.map(String).slice(0, 8) : row.reasons || []
  };
}

async function attachNews(snapshot, symbols) {
  const next = snapshot && typeof snapshot === "object" ? snapshot : {};
  next.symbols = next.symbols && typeof next.symbols === "object" ? next.symbols : {};
  const requested = [...new Set((symbols || Object.keys(next.symbols)).map((symbol) => String(symbol || "").toUpperCase()).filter(Boolean))].slice(0, 25);
  await Promise.all(requested.map(async (symbol) => {
    const row = next.symbols[symbol] || {};
    const news = await fetchNews(symbol);
    const reasons = Array.isArray(row.reasons) ? row.reasons : [];
    if (news.status !== "ok" && !reasons.includes("news unavailable")) reasons.push("news unavailable");
    if (news.items.some((item) => item.sentiment === "negative") && row.action === "pass") {
      row.action = "reduce";
      reasons.push("negative headline risk");
    }
    next.symbols[symbol] = {
      ...row,
      news: news.items,
      news_status: news.status,
      news_error: news.error,
      reasons
    };
  }));
  next.created_at = next.created_at || new Date().toISOString();
  return next;
}

async function attachAiResearch(snapshot, symbols) {
  const next = snapshot && typeof snapshot === "object" ? snapshot : {};
  next.symbols = next.symbols && typeof next.symbols === "object" ? next.symbols : {};
  const requested = [...new Set((symbols || Object.keys(next.symbols)).map((symbol) => String(symbol || "").toUpperCase()).filter(Boolean))].slice(0, 25);
  if (!OPENAI_API_KEY) {
    next.ai_status = "openai_unavailable";
    next.ai_error = "OPENAI_API_KEY not set";
    return next;
  }
  await Promise.all(requested.map(async (symbol) => {
    const row = next.symbols[symbol] || {};
    try {
      const ai = await openAiResearch(symbol, row, next.market || {});
      if (ai.ok) {
        const existing = Array.isArray(row.reasons) ? row.reasons : [];
        next.symbols[symbol] = {
          ...row,
          action: ai.action,
          ai_view: ai.ai_view,
          reasons: [...new Set([...existing, ...ai.reasons])],
          ai_status: "ok",
          ai_model: OPENAI_MODEL
        };
      }
    } catch (error) {
      next.symbols[symbol] = { ...row, ai_status: "openai_error", ai_error: error.message };
    }
  }));
  next.ai_status = "ok";
  next.ai_model = OPENAI_MODEL;
  return next;
}

function executionHistory() {
  const state = readState();
  const audit = readAudit(1000);
  return {
    closedTrades: Array.isArray(state.closedTrades) ? state.closedTrades : [],
    submittedOrders: Array.isArray(state.orders) ? state.orders : [],
    fills: Array.isArray(state.ibkrTrades) ? state.ibkrTrades : [],
    audit: audit.filter((event) => String(event.type || "").includes("order") || String(event.type || "").includes("fill")),
    modelVersion: state.modelVersion || "heuristic-v2-learning"
  };
}

function validateLiveOrders(orders) {
  if (!Array.isArray(orders) || !orders.length) return { ok: false, error: "orders array required" };
  for (const [index, order] of orders.entries()) {
    const label = `order ${index + 1}`;
    const conid = Number(order.conid);
    const side = String(order.side || "").toUpperCase();
    const orderType = String(order.orderType || "").toUpperCase();
    const tif = String(order.tif || "").toUpperCase();
    const quantity = Number(order.quantity ?? order.totalQuantity);
    const price = Number(order.price);
    const auxPrice = Number(order.auxPrice ?? order.stopPrice);
    if (!Number.isInteger(conid) || conid <= 0) return { ok: false, error: `${label}: positive integer conid required` };
    if (!SIDES.has(side)) return { ok: false, error: `${label}: side must be BUY or SELL` };
    if (!ORDER_TYPES.has(orderType)) return { ok: false, error: `${label}: unsupported orderType ${orderType || "(blank)"}` };
    if (!TIFS.has(tif)) return { ok: false, error: `${label}: tif must be DAY, GTC, or IOC` };
    if (!Number.isInteger(quantity) || quantity <= 0) return { ok: false, error: `${label}: positive whole-share quantity required` };
    if (LIMIT_ORDER_TYPES.has(orderType) && (!Number.isFinite(price) || price <= 0)) return { ok: false, error: `${label}: positive limit price required` };
    if (STOP_ORDER_TYPES.has(orderType) && (!Number.isFinite(auxPrice) || auxPrice <= 0)) return { ok: false, error: `${label}: positive stop price required` };
  }
  return { ok: true };
}

function validateAutoOrder(body) {
  if (body.auto && !FULL_AUTO_ENABLED) return { ok: false, status: 403, error: "full auto disabled; restart with ENABLE_FULL_AUTO=1" };
  return { ok: true };
}

function validateModelPack(pack) {
  if (!pack || typeof pack !== "object" || Array.isArray(pack)) return { ok: false, error: "model pack object required" };
  if (Number(pack.schema_version ?? pack.schemaVersion) !== 1) return { ok: false, error: "unsupported model pack schema" };
  if (!String(pack.model_version || pack.modelVersion || "").trim()) return { ok: false, error: "model_version required" };
  const createdAt = Date.parse(pack.created_at || pack.createdAt || "");
  if (!Number.isFinite(createdAt) || createdAt > Date.now() + 300000) return { ok: false, error: "valid created_at required" };
  if (!pack.styles || typeof pack.styles !== "object" || Array.isArray(pack.styles)) return { ok: false, error: "styles object required" };

  const unknownStyles = Object.keys(pack.styles).filter((style) => !MODEL_PACK_STYLES.has(style));
  if (unknownStyles.length) return { ok: false, error: `unsupported style: ${unknownStyles[0]}` };

  const fields = [
    ["holdingPeriod", "holding_period", 0, 252],
    ["minProb", "min_probability", 0, 1],
    ["stopAtr", "stop_atr", 0, 20],
    ["targetR", "target_r", 0, 20],
    ["riskPct", "risk_pct", 0, 0.1]
  ];
  for (const style of MODEL_PACK_STYLES) {
    const row = pack.styles[style];
    if (!row || typeof row !== "object" || Array.isArray(row)) return { ok: false, error: `${style} config required` };
    if (typeof row.enabled !== "boolean") return { ok: false, error: `${style}.enabled must be boolean` };
    const status = String(row.acceptance?.status || "").toLowerCase();
    if (!["pass", "reject"].includes(status)) return { ok: false, error: `${style}.acceptance.status must be pass or reject` };
    for (const [camel, snake, min, max] of fields) {
      const value = Number(row[camel] ?? row[snake]);
      if (!Number.isFinite(value) || value < min || value > max) return { ok: false, error: `${style}.${snake} out of range` };
      if (snake === "holding_period" && !Number.isInteger(value)) return { ok: false, error: `${style}.holding_period must be an integer` };
      if (row.enabled && ["stop_atr", "target_r", "risk_pct"].includes(snake) && value === 0) {
        return { ok: false, error: `${style}.${snake} must be positive when enabled` };
      }
    }
  }

  const overrides = pack.symbol_overrides ?? pack.symbolOverrides ?? {};
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) return { ok: false, error: "symbol_overrides must be an object" };
  for (const [symbol, override] of Object.entries(overrides)) {
    if (!/^[A-Z0-9.-]{1,12}$/.test(symbol) || !override || typeof override !== "object" || Array.isArray(override)) {
      return { ok: false, error: `invalid symbol override: ${symbol}` };
    }
    const weight = override.maxPositionWeight ?? override.max_position_weight;
    if (weight !== undefined && (!Number.isFinite(Number(weight)) || Number(weight) < 0 || Number(weight) > 0.1)) {
      return { ok: false, error: `${symbol}.max_position_weight out of range` };
    }
    for (const flag of ["blocked", "enabled"]) {
      if (override[flag] !== undefined && typeof override[flag] !== "boolean") return { ok: false, error: `${symbol}.${flag} must be boolean` };
    }
  }
  return { ok: true };
}

function ibkrRequest(method, endpoint, body) {
  return new Promise((resolve) => {
    const target = new URL(`${IBKR_BASE.replace(/\/$/, "")}/${endpoint.replace(/^\//, "")}`);
    const payload = body ? JSON.stringify(body) : "";
    const req = https.request({
      hostname: target.hostname,
      port: target.port || 443,
      path: `${target.pathname}${target.search}`,
      method,
      rejectUnauthorized: false,
      headers: {
        "host": "api.ibkr.com",
        "user-agent": "StockPerformanceAnalyzer/1.0",
        "content-type": "application/json",
        "accept": "*/*",
        "connection": "keep-alive",
        "content-length": Buffer.byteLength(payload)
      }
    }, (res) => {
      let text = "";
      res.on("data", (chunk) => { text += chunk; });
      res.on("end", () => {
        try {
          resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data: text ? JSON.parse(text) : null });
        } catch {
          resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data: text });
        }
      });
    });
    req.setTimeout(15000, () => req.destroy(new Error("IBKR Gateway request timed out")));
    req.on("error", (error) => resolve({ ok: false, status: 0, error: error.message || error.code || "IBKR Gateway unreachable" }));
    if (payload) req.write(payload);
    req.end();
  });
}

function ibkrStatusConnected(result) {
  const data = result?.data || {};
  return Boolean(result?.ok && data.authenticated === true && data.connected === true && data.competing !== true);
}

function probeTcp(host, port, timeoutMs = 600) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    let settled = false;
    const done = (listening, error = "") => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve({ port, listening, error });
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false, "timeout"));
    socket.once("error", (error) => done(false, error.code || error.message));
  });
}

function ibkrDiagnosis({ ibkrBase = IBKR_BASE, configuredStatus = {}, ports = [], processes = [] } = {}) {
  const configured = ports.find((row) => row.configured);
  const cp = ports.find((row) => row.service === "Client Portal Gateway" && row.listening);
  const tws = ports.find((row) => row.service !== "Client Portal Gateway" && row.listening);
  const desktopOpen = processes.some((row) => /ibkr desktop/i.test(`${row.title} ${row.name}`) || /ntws/i.test(row.name || ""));
  const loginUrl = ibkrBase.replace(/\/v1\/api\/?$/, "");

  if (ibkrStatusConnected(configuredStatus)) {
    return { summary: "Client Portal Gateway is connected and authenticated.", nextSteps: ["Click Sync IBKR again if the dashboard has not refreshed."] };
  }
  if (configured?.listening) {
    if ([401, 403].includes(Number(configuredStatus.status)) && desktopOpen) {
      return { summary: "Client Portal Gateway is running, but IBKR is denying API access while IBKR Desktop is open.", nextSteps: ["Log out of IBKR Desktop using its Log Out command, refresh the Gateway login page, finish 2FA again, then click Sync IBKR."] };
    }
    if ([401, 403].includes(Number(configuredStatus.status))) {
      return { summary: "Client Portal Gateway is running, but IBKR did not create an API brokerage session after login.", nextSteps: ["Confirm you are using an IBKR Pro, opened, funded username with trading permissions.", "For paper trading, log in with the separate Paper Trading username, not the live username.", "Try IBKR's Beta Client Portal Gateway if the standard Gateway keeps returning Access Denied."] };
    }
    return { summary: "Client Portal Gateway port is reachable, but the brokerage session is not authenticated.", nextSteps: [`Open ${loginUrl} and finish IBKR login/2FA, then click Sync IBKR.`] };
  }
  if (cp) {
    return { summary: `Client Portal Gateway is listening on port ${cp.port}, but the dashboard is configured for ${ibkrBase}.`, nextSteps: [`Set IBKR_BASE=https://localhost:${cp.port}/v1/api, restart the dashboard, then click Sync IBKR.`] };
  }
  if (desktopOpen) {
    return { summary: "IBKR Desktop is open, but no supported IBKR API service is listening locally.", nextSteps: ["Start and log into Client Portal Gateway on port 5000, then click Sync IBKR."] };
  }
  if (tws) {
    return { summary: `${tws.service} is listening on port ${tws.port}, but this dashboard currently uses Client Portal Web API.`, nextSteps: ["Start Client Portal Gateway for this dashboard, or add a separate TWS API bridge later."] };
  }
  return { summary: "No local IBKR API service is listening.", nextSteps: ["Start and log into Client Portal Gateway, then click Sync IBKR."] };
}

function listIbkrProcesses() {
  if (process.platform !== "win32") return Promise.resolve([]);
  const script = "Get-Process | Where-Object { $_.ProcessName -match 'ib|tws|java|gateway|ntws' -or $_.MainWindowTitle -match 'Interactive|Trader|IBKR|Gateway|TWS' } | Select-Object Id,ProcessName,MainWindowTitle,Path | ConvertTo-Json -Compress";
  return new Promise((resolve) => {
    execFile("powershell.exe", ["-NoProfile", "-Command", script], { timeout: 3000, windowsHide: true }, (error, stdout) => {
      if (error || !stdout.trim()) return resolve([]);
      try {
        const rows = JSON.parse(stdout);
        resolve((Array.isArray(rows) ? rows : [rows]).map((row) => ({
          id: row.Id,
          name: row.ProcessName || "",
          title: row.MainWindowTitle || "",
          path: row.Path || ""
        })));
      } catch {
        resolve([]);
      }
    });
  });
}

async function ibkrDiagnostics() {
  const base = new URL(IBKR_BASE);
  const configuredPort = Number(base.port || 443);
  const rows = [
    { service: "Client Portal Gateway", port: 5000 },
    { service: "Client Portal Gateway", port: 5001 },
    { service: "Trader Workstation", port: 7496 },
    { service: "Trader Workstation paper", port: 7497 },
    { service: "IB Gateway", port: 4001 },
    { service: "IB Gateway paper", port: 4002 }
  ];
  if (!rows.some((row) => row.port === configuredPort)) rows.unshift({ service: "Configured IBKR_BASE", port: configuredPort });
  const [ports, processes, configuredStatus] = await Promise.all([
    Promise.all(rows.map(async (row) => ({ ...row, configured: row.port === configuredPort, ...(await probeTcp(base.hostname, row.port)) }))),
    listIbkrProcesses(),
    ibkrRequest("GET", "iserver/auth/status")
  ]);
  const diagnosis = ibkrDiagnosis({ ibkrBase: IBKR_BASE, configuredStatus, ports, processes });
  return { ok: ibkrStatusConnected(configuredStatus), ibkrBase: IBKR_BASE, configuredStatus, ports, processes, ...diagnosis };
}

async function handleApi(req, res, url) {
  if (url.pathname === "/api/health") {
    return send(res, 200, { ok: true, ibkrBase: IBKR_BASE, liveOrdersEnabled: LIVE_ORDERS_ENABLED, fullAutoEnabled: FULL_AUTO_ENABLED, openAiEnabled: Boolean(OPENAI_API_KEY), openAiModel: OPENAI_MODEL, stateStore: "data/app_state.json", auditLog: "data/audit.jsonl", modelPack: "data/bot_model_pack.json", researchSnapshot: "data/market_research_snapshot.json" });
  }
  if (url.pathname === "/api/state" && req.method === "GET") {
    return send(res, 200, { ok: true, state: readState(), audit: readAudit(200) });
  }
  if (url.pathname === "/api/state" && req.method === "POST") {
    const body = await readJson(req);
    writeState(body);
    appendAudit({ type: "state_save", source: "dashboard", summary: "state persisted" });
    return send(res, 200, { ok: true });
  }
  if (url.pathname === "/api/audit" && req.method === "GET") {
    return send(res, 200, { ok: true, audit: readAudit(Number(url.searchParams.get("limit") || 500)) });
  }
  if (url.pathname === "/api/audit" && req.method === "POST") {
    const body = await readJson(req);
    return send(res, 200, { ok: true, event: appendAudit(body) });
  }
  if (url.pathname === "/api/model-pack" && req.method === "GET") {
    const stored = readJsonFile(MODEL_PACK_FILE, null);
    const validation = stored ? validateModelPack(stored) : { ok: false, error: "model pack not found" };
    return send(res, 200, { ok: true, exists: validation.ok, modelPack: validation.ok ? stored : null, error: stored && !validation.ok ? validation.error : undefined });
  }
  if (url.pathname === "/api/model-pack" && req.method === "POST") {
    const body = await readJson(req);
    const modelPack = body.modelPack || body;
    const validation = validateModelPack(modelPack);
    if (!validation.ok) return send(res, 400, validation);
    writeJsonFile(MODEL_PACK_FILE, modelPack);
    appendAudit({ type: "model_pack_write", source: "dashboard", modelVersion: modelPack.model_version || modelPack.modelVersion || "" });
    return send(res, 200, { ok: true, modelPack });
  }
  if (url.pathname === "/api/execution-history" && req.method === "GET") {
    return send(res, 200, { ok: true, ...executionHistory() });
  }
  if (url.pathname === "/api/research-snapshot" && req.method === "GET") {
    const snapshot = readJsonFile(RESEARCH_FILE, null);
    return send(res, 200, { ok: true, exists: Boolean(snapshot), snapshot });
  }
  if (url.pathname === "/api/research-snapshot" && req.method === "POST") {
    const body = await readJson(req);
    const snapshot = body.snapshot || body;
    writeJsonFile(RESEARCH_FILE, snapshot);
    appendAudit({ type: "research_snapshot_write", source: "dashboard", researchVersion: snapshot.research_version || "" });
    return send(res, 200, { ok: true, snapshot });
  }
  if (url.pathname === "/api/research-refresh" && req.method === "POST") {
    const body = await readJson(req);
    const base = body.snapshot || readJsonFile(RESEARCH_FILE, { schema_version: 1, created_at: new Date().toISOString(), research_version: "ai-research-v1", symbols: {} });
    const withNews = await attachNews(base, body.symbols);
    const snapshot = await attachAiResearch(withNews, body.symbols);
    writeJsonFile(RESEARCH_FILE, snapshot);
    appendAudit({ type: "research_refresh", source: "dashboard", symbols: Object.keys(snapshot.symbols || {}).length });
    return send(res, 200, { ok: true, snapshot });
  }
  if (url.pathname === "/api/ai-research" && req.method === "POST") {
    const body = await readJson(req);
    const base = body.snapshot || readJsonFile(RESEARCH_FILE, { schema_version: 1, created_at: new Date().toISOString(), research_version: "ai-research-v1", symbols: {} });
    const snapshot = await attachAiResearch(base, body.symbols);
    writeJsonFile(RESEARCH_FILE, snapshot);
    appendAudit({ type: "ai_research", source: "dashboard", enabled: Boolean(OPENAI_API_KEY), symbols: Object.keys(snapshot.symbols || {}).length });
    return send(res, 200, { ok: true, openAiEnabled: Boolean(OPENAI_API_KEY), snapshot });
  }
  if (url.pathname === "/api/ibkr/status") {
    return send(res, 200, await ibkrRequest("GET", "iserver/auth/status"));
  }
  if (url.pathname === "/api/ibkr/diagnostics") {
    return send(res, 200, await ibkrDiagnostics());
  }
  if (url.pathname === "/api/ibkr/tickle") {
    return send(res, 200, await ibkrRequest("GET", "tickle"));
  }
  if (url.pathname === "/api/ibkr/accounts") {
    return send(res, 200, await ibkrRequest("GET", "portfolio/accounts"));
  }
  if (url.pathname === "/api/ibkr/trading-accounts") {
    return send(res, 200, await ibkrRequest("GET", "iserver/accounts"));
  }
  if (url.pathname === "/api/ibkr/orders") {
    const accountId = url.searchParams.get("accountId");
    const filters = url.searchParams.get("filters") || "";
    const force = url.searchParams.get("force") || "true";
    const query = new URLSearchParams({ force });
    if (accountId) query.set("accountId", accountId);
    if (filters) query.set("filters", filters);
    return send(res, 200, await ibkrRequest("GET", `iserver/account/orders?${query.toString()}`));
  }
  if (url.pathname === "/api/ibkr/trades") {
    return send(res, 200, await ibkrRequest("GET", "iserver/trades"));
  }
  if (url.pathname === "/api/ibkr/positions") {
    const accountId = url.searchParams.get("accountId");
    const page = url.searchParams.get("page") || "0";
    if (!accountId) return send(res, 400, { ok: false, error: "accountId required" });
    return send(res, 200, await ibkrRequest("GET", `portfolio/${encodeURIComponent(accountId)}/positions/${encodeURIComponent(page)}`));
  }
  if (url.pathname === "/api/ibkr/search") {
    const symbol = url.searchParams.get("symbol");
    if (!symbol) return send(res, 400, { ok: false, error: "symbol required" });
    return send(res, 200, await ibkrRequest("POST", "iserver/secdef/search", { symbol, name: false, secType: "STK" }));
  }
  if (url.pathname === "/api/ibkr/snapshot") {
    const conids = url.searchParams.get("conids");
    const fields = url.searchParams.get("fields") || "31,55,84,86,6509,7635";
    if (!conids) return send(res, 400, { ok: false, error: "conids required" });
    return send(res, 200, await ibkrRequest("GET", `iserver/marketdata/snapshot?conids=${encodeURIComponent(conids)}&fields=${encodeURIComponent(fields)}`));
  }
  if (url.pathname === "/api/ibkr/history") {
    const conid = url.searchParams.get("conid");
    const period = url.searchParams.get("period") || "1y";
    const bar = url.searchParams.get("bar") || "1d";
    if (!conid) return send(res, 400, { ok: false, error: "conid required" });
    return send(res, 200, await ibkrRequest("GET", `iserver/marketdata/history?conid=${encodeURIComponent(conid)}&period=${encodeURIComponent(period)}&bar=${encodeURIComponent(bar)}`));
  }
  if (url.pathname === "/api/ibkr/order-preview") {
    const body = await readJson(req);
    return send(res, 200, { ok: true, liveSubmission: false, message: "Preview only. Review and transmit inside IBKR TWS.", orderPlan: body });
  }
  if (url.pathname === "/api/ibkr/live-order") {
    if (!LIVE_ORDERS_ENABLED) return send(res, 403, { ok: false, error: "live orders disabled; restart with ENABLE_LIVE_ORDERS=1" });
    const body = await readJson(req);
    const accountId = body.accountId;
    const orders = body.orders;
    const autoValidation = validateAutoOrder(body);
    if (!autoValidation.ok) {
      appendAudit({ type: "auto_order_rejected", accountId, setupId: body.setupId, reason: "full auto disabled" });
      return send(res, autoValidation.status, { ok: false, error: autoValidation.error });
    }
    if (!accountId) return send(res, 400, { ok: false, error: "accountId required" });
    const validation = validateLiveOrders(orders);
    if (!validation.ok) {
      appendAudit({ type: "live_order_rejected", accountId, setupId: body.setupId, reason: validation.error });
      return send(res, 400, validation);
    }
    const intent = appendAudit({ type: "live_order_intent", accountId, setupId: body.setupId, orders });
    const result = await ibkrRequest("POST", `iserver/account/${encodeURIComponent(accountId)}/orders`, orders);
    appendAudit({ type: "live_order_response", accountId, setupId: body.setupId, intentTime: intent.time, result });
    return send(res, 200, result);
  }
  if (url.pathname === "/api/ibkr/reply") {
    if (!LIVE_ORDERS_ENABLED) return send(res, 403, { ok: false, error: "live orders disabled; restart with ENABLE_LIVE_ORDERS=1" });
    const body = await readJson(req);
    if (!body.replyId) return send(res, 400, { ok: false, error: "replyId required" });
    appendAudit({ type: "live_order_reply", replyId: body.replyId, confirmed: Boolean(body.confirmed) });
    return send(res, 200, await ibkrRequest("POST", `iserver/reply/${encodeURIComponent(body.replyId)}`, { confirmed: Boolean(body.confirmed) }));
  }
  return send(res, 404, { ok: false, error: "unknown api route" });
}

function serveStatic(req, res, url) {
  const requested = url.pathname === "/" ? "/index.html" : decodeURIComponent(url.pathname);
  const filePath = path.resolve(ROOT, `.${requested}`);
  if (!filePath.startsWith(ROOT)) return send(res, 403, "Forbidden", "text/plain; charset=utf-8");
  fs.readFile(filePath, (error, data) => {
    if (error) return send(res, 404, "Not found", "text/plain; charset=utf-8");
    send(res, 200, data, MIME[path.extname(filePath)] || "application/octet-stream");
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") return send(res, 204, "");
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (url.pathname.startsWith("/api/")) return await handleApi(req, res, url);
    return serveStatic(req, res, url);
  } catch (error) {
    return send(res, 500, { ok: false, error: error.message });
  }
});

if (require.main === module) {
  server.listen(PORT, HOST, () => {
    console.log(`Stock Performance Analyzer: http://${HOST}:${PORT}`);
    console.log(`IBKR Client Portal Gateway expected at ${IBKR_BASE}`);
  });
}

module.exports = { validateLiveOrders, validateAutoOrder, validateModelPack, parseRssItems, newsSentiment, executionHistory, ibkrDiagnosis, ibkrStatusConnected };
