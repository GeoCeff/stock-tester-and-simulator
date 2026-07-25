const assert = require("assert");
const app = require("./app.js");
const { validateLiveOrders, validateAutoOrder, parseRssItems, ibkrDiagnosis, ibkrStatusConnected } = require("./server.js");

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
