const assert = require("assert");
const app = require("./app.js");
const { validateLiveOrders, validateAutoOrder, validateModelPack, validateResearchAgent, parseRssItems, mergeNews, agentNewsSnapshot, ibkrDiagnosis, ibkrStatusConnected } = require("./server.js");

const rows = app.generateSampleData(new Date("2026-06-19"), 260);
const analysis = app.analyze(rows);

assert(rows.length > 1000, "sample data should include multiple symbols");
assert(analysis.metrics.length >= 5, "analysis should rank stocks");
assert(["BULLISH", "NEUTRAL", "BEARISH", "PANIC"].includes(analysis.regime.regime), "regime should be classified");
assert(analysis.setups.some((setup) => setup.style === "SWING_5D"), "swing setups should exist");
assert(analysis.setups.every((setup) => setup.gates && setup.entry > setup.stop && setup.target > setup.entry), "setups need gates and bracket prices");
assert(analysis.setups.every((setup) => setup.learning && setup.gates.tradeLearning), "trade learning graph should be attached");
assert(analysis.setups.every((setup) => setup.strategyStats && setup.gates.strategyValidation), "learning gates should be attached");
const sampleSetup = analysis.setups.find((setup) => setup.style === "SWING_5D");
assert(app.tradeFeatures(sampleSetup).probabilityBucket, "trade features should label probability buckets");
assert(analysis.metrics.some((metric) => metric.sector === "Healthcare"), "healthcare/medicine sector should be separated");
assert(analysis.setups.every((setup) => setup.fees && Number.isFinite(setup.fees.roundTrip)), "fee estimates should be attached");
assert.equal(analysis.setups.find((setup) => setup.style === "DAY_TRADE").gates.dayTrading, "reject");
assert(Number.isFinite(app.rsi(rows.filter((row) => row.symbol === "AAPL"), 14)), "RSI should be numeric");
const research = app.buildResearchSnapshot(rows, ["AAPL", "NVDA"]);
assert.equal(research.research_version, "ai-research-v1");
assert(research.symbols.AAPL.technical.sma50 > 0, "research snapshot should include SMA50");
assert(["pass", "reduce", "reject"].includes(research.symbols.AAPL.action), "research action should gate setups");
const graph = app.learningGraph([
  { pnl: 10, returnPct: 0.01, learningNodes: ["style:SWING_5D", "regime:BULLISH"] },
  { pnl: -5, returnPct: -0.01, learningNodes: ["style:SWING_5D", "regime:BEARISH"] }
]);
assert(graph.nodes.some((node) => node.id === "style:SWING_5D"), "learning graph should create nodes");
assert(graph.edges.some((edge) => edge.id.includes("style:SWING_5D")), "learning graph should create edges");

const imported = app.parseCsv("symbol,date,open,high,low,close,volume\nTST,2026-06-18,10,11,9,10.5,100000\n");
assert.equal(imported[0].symbol, "TST");
assert.equal(imported[0].close, 10.5);
const healthcare = app.parseCsv("symbol,date,open,high,low,close,volume\nLLY,2026-06-18,900,920,890,915,3000000\n");
assert.equal(healthcare[0].sector, "Healthcare");

const trade = app.normalizeIbkrTrades({ data: [{ ticker: "AAPL", buysell: "BOT", qty: 3, price: 192.25, order_ref: "SPA-AAPL-1", lastExecutionTime_r: 1702317649000 }] })[0];
assert.equal(trade.symbol, "AAPL");
assert.equal(trade.side, "BUY");
assert.equal(trade.clientOrderId, "SPA-AAPL-1");
assert.equal(trade.timeMs, 1702317649000);

assert.equal(validateLiveOrders([{ conid: 265598, side: "BUY", orderType: "LMT", price: 192.25, quantity: 3, tif: "DAY" }]).ok, true);
assert.equal(validateLiveOrders([{ conid: 0, side: "BUY", orderType: "LMT", price: 192.25, quantity: 3, tif: "DAY" }]).ok, false);
assert.equal(validateLiveOrders([{ conid: 265598, side: "BUY", orderType: "STOP_LIMIT", price: 192.25, quantity: 3, tif: "DAY" }]).ok, false);
assert.equal(validateLiveOrders([{ conid: 265598, side: "BUY", orderType: "STOP_LIMIT", price: 192.25, auxPrice: 191.75, quantity: 3, tif: "DAY" }]).ok, true);
assert.equal(validateAutoOrder({ auto: true }).ok, process.env.ENABLE_FULL_AUTO === "1");
const modelStyle = { enabled: false, holding_period: 0, min_probability: 0, stop_atr: 0, target_r: 0, risk_pct: 0, acceptance: { status: "reject" } };
const modelPack = {
  schema_version: 1,
  created_at: "2026-06-21T00:00:00Z",
  model_version: "self-check",
  styles: Object.fromEntries(["DAY_TRADE", "OVERNIGHT_1D", "SWING_5D", "SWING_20D"].map((style) => [style, { ...modelStyle }]))
};
assert.equal(validateModelPack(modelPack).ok, true);
assert.equal(validateModelPack({ ...modelPack, styles: { ...modelPack.styles, SWING_5D: { ...modelStyle, enabled: true, risk_pct: 2 } } }).ok, false);
const researchAgent = { schema_version: 1, created_at: "2026-07-25T00:00:00Z", entries: [{ symbol: "AAPL", side: "LONG", style: "SWING_5D", signal_date: "2026-07-25", entry: 200, stop: 190, target: 220 }] };
assert.equal(validateResearchAgent(researchAgent).ok, true);
assert.equal(validateResearchAgent({ ...researchAgent, entries: [{ ...researchAgent.entries[0], stop: 210 }] }).ok, false);
assert.equal(agentNewsSnapshot(researchAgent).symbols.AAPL.action, "pass");
assert.equal(mergeNews({ action: "pass" }, { status: "news_unavailable", items: [], error: "offline" }).action, "news_unavailable");
assert.equal(mergeNews({ action: "pass" }, { status: "ok", items: [{ sentiment: "negative" }], error: "" }).action, "reduce");
assert.equal(parseRssItems("<rss><channel><item><title>AAPL shares rise</title><link>https://example.com</link><pubDate>today</pubDate></item></channel></rss>")[0].sentiment, "positive");
assert.equal(ibkrStatusConnected({ ok: true, data: { authenticated: true, connected: true, competing: false } }), true);
assert.equal(ibkrStatusConnected({ ok: true, data: { authenticated: false, connected: true, competing: false } }), false);
assert.equal(ibkrStatusConnected({ ok: true, data: { competing: false } }), false);
assert.equal(ibkrStatusConnected({ ok: false, data: { authenticated: true, connected: true, competing: false } }), false);
assert(ibkrDiagnosis({ processes: [{ name: "ntws", title: "IBKR Desktop" }] }).summary.includes("IBKR Desktop"), "IBKR doctor should identify Desktop without API");
assert(ibkrDiagnosis({ configuredStatus: { ok: true, data: { authenticated: true, connected: true } } }).summary.includes("connected"), "IBKR doctor should identify authenticated Gateway");
assert(app.dailyLimitReasons({ equity: 1000, dailyLossLimit: 0.02, dailyMaxLossDollars: 25, dayPL: -30, dailyProfitTargetDollars: 0, dailyMaxProfitDollars: 0 })[0].includes("daily max loss"));
assert(app.dailyLimitReasons({ equity: 1000, dailyLossLimit: 0.02, dailyMaxLossDollars: 0, dayPL: 55, dailyProfitTargetDollars: 50, dailyMaxProfitDollars: 0 })[0].includes("profit target"));
assert.equal(app.estimateSetupFees(10, 20, 22).roundTrip > 0, true);

console.log("self-check passed");
