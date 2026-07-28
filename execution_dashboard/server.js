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
const RESEARCH_AGENT_FILE = path.join(DATA_DIR, "research_agent.json");
const RESEARCH_FILE = path.join(DATA_DIR, "market_research_snapshot.json");
const RESEARCH_AGENT_MAX_AGE_MS = 86400000;
const RESEARCH_SIGNAL_MAX_AGE_MS = 5 * 86400000;
const RESEARCH_NEWS_MAX_AGE_MS = 86400000;
const MAX_DAILY_LOSS_PCT = 0.02;
const MAX_SPREAD_BPS = 20;
let autoOrderInFlight = false;
const NEWS_RSS_URL = process.env.NEWS_RSS_URL || "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US";
const NEWS_DISABLED = process.env.DISABLE_NEWS_FETCH === "1";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-5.4-mini";
const NEWS_TERMS = {
  AAPL: ["Apple"],
  MSFT: ["Microsoft"],
  NVDA: ["Nvidia"],
  AMZN: ["Amazon"],
  GOOGL: ["Google", "Alphabet"],
  META: ["Meta Platforms", "Facebook", "Instagram"],
  AVGO: ["Broadcom"],
  TSLA: ["Tesla"],
  JPM: ["JPMorgan", "JP Morgan"],
  BAC: ["Bank of America"],
  XOM: ["Exxon", "ExxonMobil"],
  CVX: ["Chevron"],
  LLY: ["Eli Lilly"],
  JNJ: ["Johnson & Johnson", "J&J"],
  PFE: ["Pfizer"],
  UNH: ["UnitedHealth", "United Healthcare"],
  WMT: ["Walmart"],
  COST: ["Costco"],
  HD: ["Home Depot"],
  PG: ["Procter & Gamble", "P&G"]
};

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

function filterRelevantNews(symbol, items, now = Date.now()) {
  const terms = [symbol, ...(NEWS_TERMS[symbol] || [])];
  return items.filter((item) => {
    const published = Date.parse(item.published_at || "");
    if (!Number.isFinite(published) || published > now + 300000 || now - published > 3 * 86400000) return false;
    return terms.some((term) => new RegExp(`(^|[^A-Z0-9])${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^A-Z0-9]|$)`, "i").test(item.title));
  }).slice(0, 3);
}

async function fetchNews(symbol) {
  if (NEWS_DISABLED) return { status: "news_unavailable", items: [], error: "news fetch disabled" };
  try {
    const url = NEWS_RSS_URL.replace(/\{symbol\}/g, encodeURIComponent(symbol));
    const xml = await fetchText(url);
    const items = filterRelevantNews(symbol, parseRssItems(xml, 20));
    return {
      status: items.length ? "ok" : "news_unavailable",
      items,
      error: items.length ? "" : "no recent symbol-relevant headlines"
    };
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

function mergeNews(row, news) {
    const next = { ...row };
    const reasons = Array.isArray(next.reasons) ? [...next.reasons] : [];
    if (news.status !== "ok") {
      if (!reasons.includes("news unavailable")) reasons.push("news unavailable");
      if (next.action === "pass") next.action = "news_unavailable";
    }
    if (news.items.some((item) => item.sentiment === "negative") && next.action === "pass") {
      next.action = "reduce";
      reasons.push("negative headline risk");
    }
    return {
      ...next,
      news: news.items,
      news_status: news.status,
      news_error: news.error,
      reasons
    };
}

function conservativeAiAction(current, proposed) {
  return current === "pass" ? proposed : ["reduce", "reject", "news_unavailable"].includes(current) ? current : "reduce";
}

async function attachNews(snapshot, symbols) {
  const next = snapshot && typeof snapshot === "object" ? snapshot : {};
  next.symbols = next.symbols && typeof next.symbols === "object" ? next.symbols : {};
  const requested = [...new Set((symbols || Object.keys(next.symbols)).map((symbol) => String(symbol || "").toUpperCase()).filter(Boolean))].slice(0, 25);
  await Promise.all(requested.map(async (symbol) => {
    next.symbols[symbol] = mergeNews(next.symbols[symbol] || {}, await fetchNews(symbol));
  }));
  next.created_at = next.created_at || new Date().toISOString();
  return next;
}

function agentNewsSnapshot(agent) {
  const symbols = {};
  for (const entry of agent.entries || []) {
    symbols[entry.symbol] = {
      action: "pass",
      reasons: ["walk-forward and final holdout passed"],
      candidate: entry
    };
  }
  return {
    schema_version: 1,
    created_at: new Date().toISOString(),
    research_version: "agent-news-v2",
    symbols
  };
}

async function refreshAgentNews() {
  const agent = readJsonFile(RESEARCH_AGENT_FILE);
  const validation = validateResearchAgent(agent);
  if (!validation.ok) throw new Error(validation.error);
  const snapshot = await attachAiResearch(await attachNews(agentNewsSnapshot(agent)));
  writeJsonFile(RESEARCH_FILE, snapshot);
  const counts = Object.values(snapshot.symbols).reduce((result, row) => {
    result[row.action] = (result[row.action] || 0) + 1;
    return result;
  }, {});
  return { symbols: Object.keys(snapshot.symbols).length, actions: counts };
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
          action: conservativeAiAction(row.action, ai.action),
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
  if (typeof body.auto !== "boolean") return { ok: false, status: 400, error: "auto must be boolean" };
  if (body.auto && !FULL_AUTO_ENABLED) return { ok: false, status: 403, error: "full auto disabled; restart with ENABLE_FULL_AUTO=1" };
  const symbol = String(body.symbol || "").toUpperCase();
  if (!body.auto && body.confirmation !== `LIVE ${symbol}`) return { ok: false, status: 403, error: `type LIVE ${symbol} to confirm this live order` };
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

function validateResearchAgent(result) {
  if (!result || typeof result !== "object" || Array.isArray(result)) return { ok: false, error: "research agent object required" };
  if (Number(result.schema_version ?? result.schemaVersion) !== 1) return { ok: false, error: "unsupported research agent schema" };
  const createdAt = Date.parse(result.created_at || result.createdAt || "");
  if (!Number.isFinite(createdAt) || createdAt > Date.now() + 300000) return { ok: false, error: "valid created_at required" };
  if (!Array.isArray(result.entries)) return { ok: false, error: "entries array required" };
  for (const [index, entry] of result.entries.entries()) {
    const label = `entry ${index + 1}`;
    if (!/^[A-Z0-9.-]{1,12}$/.test(String(entry.symbol || ""))) return { ok: false, error: `${label}: invalid symbol` };
    if (entry.side !== "LONG") return { ok: false, error: `${label}: only LONG is supported` };
    if (!MODEL_PACK_STYLES.has(entry.style)) return { ok: false, error: `${label}: unsupported style` };
    if (!Number.isFinite(Date.parse(entry.signal_date || entry.signalDate || ""))) return { ok: false, error: `${label}: valid signal_date required` };
    const price = Number(entry.entry);
    const stop = Number(entry.stop);
    const target = Number(entry.target);
    const riskPct = Number(entry.risk_pct ?? entry.riskPct);
    if (![price, stop, target].every(Number.isFinite) || stop <= 0 || stop >= price || target <= price) {
      return { ok: false, error: `${label}: invalid bracket prices` };
    }
    if (!Number.isFinite(riskPct) || riskPct <= 0 || riskPct > 0.1) return { ok: false, error: `${label}: invalid risk_pct` };
  }
  return { ok: true };
}

function validateResearchOrder(body, agent, accountEquity, now = Date.now()) {
  const validation = validateResearchAgent(agent);
  if (!validation.ok) return validation;
  const createdAt = Date.parse(agent.created_at || agent.createdAt || "");
  if (now - createdAt > RESEARCH_AGENT_MAX_AGE_MS) return { ok: false, error: "research agent result is stale" };
  const symbol = String(body.symbol || "").toUpperCase();
  const style = String(body.style || "");
  const planId = String(body.planId || body.plan_id || "");
  if (!planId.trim()) return { ok: false, error: "exact research plan ID required" };
  const candidate = agent.entries.find((entry) =>
    entry.symbol === symbol && entry.style === style && entry.plan_id === planId
  );
  if (!candidate) return { ok: false, error: "live order does not match a current research candidate" };
  const signalAt = Date.parse(candidate.signal_date || candidate.signalDate || "");
  if (signalAt > now + 300000 || now - signalAt > RESEARCH_SIGNAL_MAX_AGE_MS) {
    return { ok: false, error: "research candidate signal is stale" };
  }
  if (
    agent.paper_evidence?.status !== "validated"
    || !agent.paper_evidence?.validated_plans?.includes(planId)
  ) {
    return { ok: false, error: "exact research plan has not passed forward paper validation" };
  }
  const newsAt = Date.parse(candidate.news_created_at || candidate.newsCreatedAt || "");
  if (
    candidate.news_action !== "pass"
    || candidate.news_status !== "ok"
    || !Number.isFinite(newsAt)
    || newsAt > now + 300000
    || now - newsAt > RESEARCH_NEWS_MAX_AGE_MS
  ) return { ok: false, error: "current news gate does not approve live execution" };
  const orders = body.orders;
  if (!Array.isArray(orders) || orders.length !== 3) return { ok: false, error: "exact three-order bracket required" };
  const [entry, target, stop] = orders;
  const tif = candidate.style === "DAY_TRADE" ? "DAY" : "GTC";
  const clientIds = [entry.cOID, target.cOID, stop.cOID];
  const priceMatches = (actual, expected) => Math.abs(Number(actual) - Number(expected)) <= 0.011;
  if (
    entry.side !== "BUY" || entry.orderType !== "LMT" || !priceMatches(entry.price, candidate.entry)
    || target.side !== "SELL" || target.orderType !== "LMT" || !priceMatches(target.price, candidate.target)
    || stop.side !== "SELL" || stop.orderType !== "STP" || !priceMatches(stop.auxPrice, candidate.stop)
    || orders.some((order) => order.tif !== tif)
    || target.quantity !== entry.quantity || stop.quantity !== entry.quantity
    || !entry.cOID || target.parentId !== entry.cOID || stop.parentId !== entry.cOID
    || clientIds.some((id) => typeof id !== "string" || !/^[A-Za-z0-9._-]{1,64}$/.test(id))
    || new Set(clientIds).size !== 3
  ) {
    return { ok: false, error: "order bracket differs from the validated research candidate" };
  }
  const equity = Number(accountEquity);
  const quantity = Number(entry.quantity);
  const stopRisk = quantity * (Number(candidate.entry) - Number(candidate.stop));
  const riskBudget = equity * Number(candidate.risk_pct ?? candidate.riskPct);
  if (!Number.isFinite(equity) || equity <= 0) return { ok: false, error: "current IBKR net liquidation value required" };
  if (!Number.isFinite(stopRisk) || stopRisk > riskBudget + 0.01) {
    return { ok: false, error: "order quantity exceeds the validated research risk budget" };
  }
  return { ok: true, candidate };
}

function ibkrNetLiquidation(result) {
  const value = result?.data?.netliquidation;
  const amount = Number(value?.amount ?? value);
  return result?.ok && Number.isFinite(amount) && amount > 0 ? amount : NaN;
}

function marketDayKey(value) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

function ibkrRows(result, key) {
  if (!result?.ok) return null;
  if (Array.isArray(result.data)) return result.data;
  return Array.isArray(result.data?.[key]) ? result.data[key] : null;
}

function validateBrokerRisk(body, sources, now = Date.now()) {
  const accountId = String(body.accountId || "");
  const entry = body.orders?.[0] || {};
  const conid = Number(entry.conid);
  const equity = ibkrNetLiquidation(sources.accountSummary);
  const available = Number(sources.accountSummary?.data?.availablefunds?.amount);
  const core = sources.pnl?.ok ? sources.pnl.data?.upnl?.[`${accountId}.Core`] : null;
  const pnlEquity = Number(core?.nl);
  if (!Number.isFinite(equity) || !Number.isFinite(pnlEquity) || pnlEquity <= 0 || !Number.isFinite(Number(core?.dpl))) {
    return { ok: false, error: "current IBKR auto-risk P&L required" };
  }
  if (Number(core.dpl) <= -Math.min(equity, pnlEquity) * MAX_DAILY_LOSS_PCT) {
    return { ok: false, error: "live trading daily loss limit reached" };
  }
  if (!Number.isFinite(available) || available < Number(entry.quantity) * Number(entry.price)) return { ok: false, error: "insufficient confirmed available funds" };

  const positions = ibkrRows(sources.positions, "positions");
  const openOrders = ibkrRows(sources.openOrders, "orders");
  const quotes = ibkrRows(sources.quote, "quotes");
  if (!positions || positions.length >= 100 || !openOrders || !quotes) return { ok: false, error: "complete IBKR auto-risk state required" };
  if (positions.some((row) => Number(row.conid ?? row.contractId) === conid && Number(row.position ?? row.quantity ?? row.qty) !== 0)) {
    return { ok: false, error: "existing IBKR position in symbol" };
  }
  if (openOrders.some((row) =>
    Number(row.conid ?? row.contractId) === conid
    && !/filled|cancelled|inactive/i.test(String(row.status || row.order_status || ""))
  )) return { ok: false, error: "existing IBKR open order in symbol" };

  const quote = quotes.find((row) => Number(row.conid ?? row.conidEx ?? row._conid) === conid);
  const bid = Number(quote?.[84] ?? quote?.bid);
  const ask = Number(quote?.[86] ?? quote?.ask);
  const spreadBps = bid > 0 && ask >= bid ? (ask - bid) / ((ask + bid) / 2) * 10000 : Infinity;
  if (!Number.isFinite(spreadBps) || spreadBps > MAX_SPREAD_BPS) return { ok: false, error: "current IBKR spread is unavailable or too wide" };

  if (!body.auto) return { ok: true };
  const today = marketDayKey(now);
  const autoIntents = (sources.audit || []).filter((event) =>
    event.type === "live_order_intent"
    && event.auto === true
    && event.accountId === accountId
    && Number.isFinite(Date.parse(event.time))
    && marketDayKey(Date.parse(event.time)) === today
  ).length;
  return autoIntents < 1 ? { ok: true } : { ok: false, error: "automated trade limit reached for the market day" };
}

function validateResearchContract(orders, symbol, result) {
  const conids = new Set((orders || []).map((order) => Number(order.conid)));
  if (conids.size !== 1) return { ok: false, error: "all bracket legs must use the same contract" };
  const conid = [...conids][0];
  const match = result?.ok && Array.isArray(result.data) && result.data.some((row) =>
    Number(row.conid ?? row.conId) === conid
    && String(row.symbol || "").toUpperCase() === symbol
    && String(row.secType || "").toUpperCase() === "STK"
  );
  return match ? { ok: true } : { ok: false, error: "order contract does not match the validated research symbol" };
}

function canonicalResearchOrders([entry, target, stop]) {
  return [
    { conid: Number(entry.conid), side: "BUY", orderType: "LMT", price: Number(entry.price), quantity: Number(entry.quantity), tif: entry.tif, cOID: entry.cOID },
    { conid: Number(target.conid), side: "SELL", orderType: "LMT", price: Number(target.price), quantity: Number(target.quantity), tif: target.tif, parentId: entry.cOID, cOID: target.cOID },
    { conid: Number(stop.conid), side: "SELL", orderType: "STP", auxPrice: Number(stop.auxPrice), quantity: Number(stop.quantity), tif: stop.tif, parentId: entry.cOID, cOID: stop.cOID }
  ];
}

function validateIbkrOrderAcknowledgement(result) {
  if (!result?.ok) return { ok: false, status: 502, error: result?.error || "IBKR order request failed" };
  const rows = Array.isArray(result.data) ? result.data : [result.data];
  if (rows.some((row) => row?.id && row?.message && !row?.order_id && !row?.orderId)) {
    return { ok: false, status: 409, error: "IBKR returned an unacknowledged order warning; no order was submitted" };
  }
  const orderIds = rows.map((row) => row?.order_id ?? row?.orderId).filter((id) => id !== undefined && id !== null && String(id).trim());
  return rows.length && orderIds.length === rows.length
    ? { ok: true, orderIds }
    : { ok: false, status: 502, error: "IBKR did not acknowledge every order with an order ID" };
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
    return send(res, 200, { ok: true, ibkrBase: IBKR_BASE, liveOrdersEnabled: LIVE_ORDERS_ENABLED, fullAutoEnabled: FULL_AUTO_ENABLED, openAiEnabled: Boolean(OPENAI_API_KEY), openAiModel: OPENAI_MODEL, stateStore: "data/app_state.json", auditLog: "data/audit.jsonl", modelPack: "data/bot_model_pack.json", researchAgent: "data/research_agent.json", researchSnapshot: "data/market_research_snapshot.json" });
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
  if (url.pathname === "/api/research-agent" && req.method === "GET") {
    const stored = readJsonFile(RESEARCH_AGENT_FILE, null);
    const validation = stored ? validateResearchAgent(stored) : { ok: false, error: "research agent result not found" };
    return send(res, 200, { ok: true, exists: validation.ok, result: validation.ok ? stored : null, error: stored && !validation.ok ? validation.error : undefined });
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
    const symbol = String(body.symbol || "").toUpperCase();
    const autoValidation = validateAutoOrder(body);
    if (!autoValidation.ok) {
      appendAudit({ type: "auto_order_rejected", accountId, setupId: body.setupId, reason: autoValidation.error });
      return send(res, autoValidation.status, { ok: false, error: autoValidation.error });
    }
    if (!accountId) return send(res, 400, { ok: false, error: "accountId required" });
    if (!/^[A-Z0-9.-]{1,12}$/.test(symbol)) return send(res, 400, { ok: false, error: "valid symbol required" });
    const validation = validateLiveOrders(orders);
    if (!validation.ok) {
      appendAudit({ type: "live_order_rejected", accountId, setupId: body.setupId, reason: validation.error });
      return send(res, 400, validation);
    }
    if (body.auto && autoOrderInFlight) return send(res, 409, { ok: false, error: "automated order already in flight" });
    if (body.auto) autoOrderInFlight = true;
    try {
      const [accountSummary, contractSearch] = await Promise.all([
        ibkrRequest("GET", `portfolio/${encodeURIComponent(accountId)}/summary`),
        ibkrRequest("POST", "iserver/secdef/search", { symbol, name: false, secType: "STK" })
      ]);
      const researchValidation = validateResearchOrder(
        body,
        readJsonFile(RESEARCH_AGENT_FILE, null),
        ibkrNetLiquidation(accountSummary)
      );
      if (!researchValidation.ok) {
        appendAudit({ type: "live_order_rejected", accountId, setupId: body.setupId, reason: researchValidation.error });
        return send(res, 403, researchValidation);
      }
      const contractValidation = validateResearchContract(orders, researchValidation.candidate.symbol, contractSearch);
      if (!contractValidation.ok) {
        appendAudit({ type: "live_order_rejected", accountId, setupId: body.setupId, reason: contractValidation.error });
        return send(res, 403, contractValidation);
      }
      const conid = Number(orders[0].conid);
      const [pnl, positions, openOrders, quote] = await Promise.all([
        ibkrRequest("GET", "iserver/account/pnl/partitioned"),
        ibkrRequest("GET", `portfolio/${encodeURIComponent(accountId)}/positions/0`),
        ibkrRequest("GET", `iserver/account/orders?force=true&accountId=${encodeURIComponent(accountId)}`),
        ibkrRequest("GET", `iserver/marketdata/snapshot?conids=${conid}&fields=84,86`)
      ]);
      const brokerRisk = validateBrokerRisk(body, { accountSummary, pnl, positions, openOrders, quote, audit: readAudit(1000) });
      if (!brokerRisk.ok) {
        appendAudit({ type: body.auto ? "auto_order_rejected" : "live_order_rejected", accountId, setupId: body.setupId, reason: brokerRisk.error });
        return send(res, 403, brokerRisk);
      }
      const brokerOrders = canonicalResearchOrders(orders);
      const intent = appendAudit({ type: "live_order_intent", accountId, setupId: body.setupId, auto: body.auto === true, orders: brokerOrders });
      const result = await ibkrRequest("POST", `iserver/account/${encodeURIComponent(accountId)}/orders`, brokerOrders);
      appendAudit({ type: "live_order_response", accountId, setupId: body.setupId, intentTime: intent.time, result });
      const acknowledgement = validateIbkrOrderAcknowledgement(result);
      if (!acknowledgement.ok) {
        appendAudit({ type: "live_order_not_submitted", accountId, setupId: body.setupId, reason: acknowledgement.error });
        return send(res, acknowledgement.status, { ...acknowledgement, broker: result });
      }
      return send(res, 200, result);
    } finally {
      if (body.auto) autoOrderInFlight = false;
    }
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
  if (process.argv.includes("--refresh-agent-news")) {
    refreshAgentNews()
      .then((result) => console.log(`News gate: ${result.symbols} candidate(s) ${JSON.stringify(result.actions)}`))
      .catch((error) => {
        console.error(`News gate unavailable: ${error.message}`);
        process.exitCode = 1;
      });
  } else {
    server.listen(PORT, HOST, () => {
      console.log(`Stock Performance Analyzer: http://${HOST}:${PORT}`);
      console.log(`IBKR Client Portal Gateway expected at ${IBKR_BASE}`);
    });
  }
}

module.exports = { NEWS_TERMS, validateLiveOrders, validateAutoOrder, validateModelPack, validateResearchAgent, validateResearchOrder, ibkrNetLiquidation, validateBrokerRisk, validateResearchContract, canonicalResearchOrders, validateIbkrOrderAcknowledgement, parseRssItems, filterRelevantNews, newsSentiment, mergeNews, conservativeAiAction, agentNewsSnapshot, executionHistory, ibkrDiagnosis, ibkrStatusConnected };
