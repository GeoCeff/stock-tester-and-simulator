(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.StockAnalyzer = api;
})(this, function () {
  const BENCHMARKS = new Set(["SPY", "QQQ", "XLK", "XLF", "XLE", "XLV"]);
  const STYLE_LABELS = {
    DAY_TRADE: "Day trade",
    OVERNIGHT_1D: "Overnight 1D",
    SWING_5D: "Swing 5D",
    SWING_20D: "Swing 20D"
  };
  const STYLE_CONFIG = {
    DAY_TRADE: { horizon: 1, riskPct: 0.0025, stopAtr: 0.7, targetR: 1.4, minProb: 0.53, flatten: true },
    OVERNIGHT_1D: { horizon: 1, riskPct: 0.003, stopAtr: 1.2, targetR: 1.6, minProb: 0.55 },
    SWING_5D: { horizon: 5, riskPct: 0.005, stopAtr: 2.0, targetR: 2.0, minProb: 0.56 },
    SWING_20D: { horizon: 20, riskPct: 0.005, stopAtr: 2.5, targetR: 2.5, minProb: 0.58 }
  };
  const DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "JPM", "BAC", "XOM", "CVX", "LLY", "JNJ", "PFE", "UNH", "WMT", "COST", "HD", "PG"];
  const SECTOR_BY_SYMBOL = {
    AAPL: "Technology", MSFT: "Technology", NVDA: "Technology", AMD: "Technology", AVGO: "Technology", ORCL: "Technology",
    AMZN: "Consumer", TSLA: "Consumer", HD: "Consumer", NKE: "Consumer",
    GOOGL: "Communication", META: "Communication", NFLX: "Communication", DIS: "Communication",
    JPM: "Financials", BAC: "Financials", GS: "Financials", MS: "Financials", V: "Financials",
    XOM: "Energy", CVX: "Energy", COP: "Energy",
    LLY: "Healthcare", JNJ: "Healthcare", PFE: "Healthcare", MRK: "Healthcare", ABBV: "Healthcare", UNH: "Healthcare", TMO: "Healthcare",
    MRNA: "Biotech", REGN: "Biotech", GILD: "Biotech",
    WMT: "Staples", COST: "Staples", PG: "Staples", KO: "Staples",
    BA: "Industrials", CAT: "Industrials", GE: "Industrials", LMT: "Industrials",
    NEE: "Utilities", DUK: "Utilities", PLD: "Real Estate"
  };
  const MODEL_VERSION = "heuristic-v2-learning";
  const RESEARCH_VERSION = "ai-research-v1";
  const MODEL_PACK_MAX_AGE_DAYS = 30;
  const RESEARCH_AGENT_MAX_AGE_DAYS = 1;
  const RESEARCH_NEWS_MAX_AGE_MS = 24 * 60 * 60 * 1000;
  const RESEARCH_MAX_AGE_MINUTES = 30;
  const RESEARCH_REFRESH_MS = 60 * 60 * 1000;
  const QUOTE_MAX_AGE_MS = 5000;
  const ACCOUNT = {
    equity: 100000,
    buyingPower: 100000,
    dayPL: 0,
    ibkrMode: "PAPER",
    dayTradingEligible: false,
    dayTradingMinimum: 25000,
    commissionPlan: "IBKR_PRO_FIXED",
    commissionPerShare: 0.005,
    minCommission: 1,
    maxCommissionPct: 0.01,
    maxFeeDragPct: 0.01,
    dailyMaxLossDollars: 0,
    dailyProfitTargetDollars: 0,
    dailyMaxProfitDollars: 0,
    maxAutoTradesPerDay: 1,
    maxPositionWeight: 0.05,
    maxSectorWeight: 0.25,
    maxTotalStopRisk: 0.03,
    dailyLossLimit: 0.02,
    maxSpreadBps: 20,
    maxSlippageBps: 25,
    minTradesToValidate: 10,
    minPaperTradesForLive: 30,
    minGraphTradesToBoost: 8,
    minGraphTradesToReject: 12,
    minExpectancy: 0.001,
    minProfitFactor: 1.05,
    maxConsecutiveLosses: 3,
    maxRejectedSetupRatio: 0.85
  };
  const API_BASE = typeof location !== "undefined" && location.protocol === "file:" ? "http://127.0.0.1:8787" : "";

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function formatMoney(value) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value || 0);
  }

  function formatPct(value, digits = 2) {
    return `${((value || 0) * 100).toFixed(digits)}%`;
  }

  function formatNumber(value, digits = 2) {
    return Number.isFinite(value) ? value.toFixed(digits) : "-";
  }

  function dayTradingAllowed() {
    return ACCOUNT.dayTradingEligible && ACCOUNT.equity >= ACCOUNT.dayTradingMinimum;
  }

  function estimateTradeFee(shares, price) {
    if (ACCOUNT.commissionPlan === "IBKR_LITE") return 0;
    const value = Math.max(0, Number(shares) * Number(price));
    if (!value) return 0;
    const raw = Math.max(ACCOUNT.minCommission, Number(shares) * ACCOUNT.commissionPerShare);
    return Math.min(raw, value * ACCOUNT.maxCommissionPct);
  }

  function estimateSetupFees(shares, buyPrice, sellPrice) {
    const buyFee = estimateTradeFee(shares, buyPrice);
    const sellFee = estimateTradeFee(shares, sellPrice);
    const roundTrip = buyFee + sellFee;
    const positionValue = Math.max(0, Number(shares) * Number(buyPrice));
    return { buyFee, sellFee, roundTrip, dragPct: positionValue ? roundTrip / positionValue : 0 };
  }

  function dailyLossLimitDollars(account = ACCOUNT) {
    return account.dailyMaxLossDollars > 0 ? account.dailyMaxLossDollars : account.equity * account.dailyLossLimit;
  }

  function dailyLimitReasons(account = ACCOUNT) {
    const reasons = [];
    const maxLoss = dailyLossLimitDollars(account);
    if (maxLoss > 0 && account.dayPL <= -maxLoss) reasons.push(`daily max loss hit (${formatMoney(maxLoss)})`);
    if (account.dailyProfitTargetDollars > 0 && account.dayPL >= account.dailyProfitTargetDollars) reasons.push(`daily profit target hit (${formatMoney(account.dailyProfitTargetDollars)})`);
    if (account.dailyMaxProfitDollars > 0 && account.dayPL >= account.dailyMaxProfitDollars) reasons.push(`daily max profit hit (${formatMoney(account.dailyMaxProfitDollars)})`);
    return reasons;
  }

  function todayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  function resetAutoTradeCountIfNeeded() {
    const today = todayKey();
    if (state.autoTradeDate !== today) {
      state.autoTradeDate = today;
      state.autoTradeCount = 0;
    }
  }

  function ageMs(isoTime) {
    const ms = Date.parse(isoTime || "");
    return Number.isFinite(ms) ? Date.now() - ms : Infinity;
  }

  function camelOrSnake(row, camel, snake, fallback) {
    const value = row && row[camel] !== undefined ? row[camel] : row && row[snake] !== undefined ? row[snake] : fallback;
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function styleConfig(style, symbol = "") {
    const base = STYLE_CONFIG[style];
    const packStyle = state.modelPack?.styles?.[style] || {};
    return {
      ...base,
      horizon: camelOrSnake(packStyle, "holdingPeriod", "holding_period", base.horizon),
      riskPct: camelOrSnake(packStyle, "riskPct", "risk_pct", base.riskPct),
      stopAtr: camelOrSnake(packStyle, "stopAtr", "stop_atr", base.stopAtr),
      targetR: camelOrSnake(packStyle, "targetR", "target_r", base.targetR),
      minProb: camelOrSnake(packStyle, "minProb", "min_probability", base.minProb),
      maxPositionWeight: symbolPositionWeight(symbol)
    };
  }

  function symbolOverride(symbol) {
    return state.modelPack?.symbol_overrides?.[String(symbol || "").toUpperCase()] || {};
  }

  function symbolPositionWeight(symbol) {
    const override = symbolOverride(symbol);
    return camelOrSnake(override, "maxPositionWeight", "max_position_weight", ACCOUNT.maxPositionWeight);
  }

  function modelPackAgeDays() {
    return ageMs(state.modelPack?.created_at || state.modelPack?.createdAt) / 86400000;
  }

  function modelPackLabel(setup) {
    if (!state.modelPack) return "heuristic fallback";
    const style = setup?.style || Object.keys(state.modelPack.styles || {})[0] || "";
    const row = state.modelPack.styles?.[style] || {};
    const status = row.acceptance?.status || "unknown";
    const version = state.modelPack.model_version || state.modelPack.modelVersion || "model pack";
    const date = String(state.modelPack.created_at || state.modelPack.createdAt || "").slice(0, 10) || "unknown date";
    return `${version} / ${row.strategy || style || "no style"} ${status} / ${date}`;
  }

  function modelPackGateStatus(metric, style) {
    const pack = state.modelPack;
    if (!pack) return "pass";
    if (modelPackAgeDays() > MODEL_PACK_MAX_AGE_DAYS) return "reject";
    const row = pack.styles?.[style];
    if (!row || row.enabled === false) return "reject";
    const acceptance = String(row.acceptance?.status || "").toLowerCase();
    if (acceptance !== "pass") return "reject";
    const override = symbolOverride(metric.symbol);
    if (override.blocked || override.enabled === false) return "reject";
    return "pass";
  }

  function researchAgentCandidate(symbol, style) {
    return state.researchAgent?.entries?.find((entry) => entry.symbol === symbol && entry.style === style) || null;
  }

  function researchAgentGateStatus(metric, style) {
    if (!state.researchAgent) {
      const requiresAgent = Object.values(state.modelPack?.styles || {}).some((row) => row.strategy);
      return requiresAgent ? "reject" : "pass";
    }
    const modelCreatedAt = state.modelPack?.created_at || state.modelPack?.createdAt;
    const agentCreatedAt = state.researchAgent.created_at || state.researchAgent.createdAt;
    if (modelCreatedAt && Object.values(state.modelPack?.styles || {}).some((row) => row.strategy) && modelCreatedAt !== agentCreatedAt) return "reject";
    if (ageMs(agentCreatedAt) > RESEARCH_AGENT_MAX_AGE_DAYS * 86400000) return "reject";
    const candidate = researchAgentCandidate(metric.symbol, style);
    if (!candidate) return "reject";
    const newsCreatedAt = candidate.news_created_at || candidate.newsCreatedAt || "";
    const newsAt = Date.parse(newsCreatedAt);
    if (
      state.researchAgent.paper_evidence?.status !== "validated"
      || !state.researchAgent.paper_evidence?.validated_plans?.includes(candidate.plan_id)
      || candidate.news_action !== "pass"
      || candidate.news_status !== "ok"
      || !Number.isFinite(newsAt)
      || newsAt < Date.parse(agentCreatedAt)
      || ageMs(newsCreatedAt) > RESEARCH_NEWS_MAX_AGE_MS
    ) return "reject";
    return Math.abs(metric.price - candidate.entry) / candidate.entry <= 0.03 ? "pass" : "reject";
  }

  function researchAgeMinutes() {
    return ageMs(state.researchSnapshot?.created_at || state.researchSnapshot?.createdAt) / 60000;
  }

  function researchForSymbol(symbol) {
    return state.researchSnapshot?.symbols?.[String(symbol || "").toUpperCase()] || null;
  }

  function researchEvidence(agent) {
    const primary = agent?.styles?.SWING_20D || {};
    const diagnostic = agent?.development_diagnostics?.find((row) => (
      row.style === "SWING_20D" && row.strategy === primary.strategy
    )) || {};
    const publishedPlan = primary.metrics?.execution_plan || {};
    const rawPlan = Object.keys(publishedPlan).length ? publishedPlan : diagnostic.execution_plan || {};
    const plan = {
      ...rawPlan,
      development_validation: rawPlan.development_validation || rawPlan.final || {}
    };
    const paper = agent?.paper_evidence || {};
    const shadow = agent?.shadow_evidence || {};
    const provenance = agent?.data_provenance || {};
    const coverage = Object.values(provenance.coverage || {});
    const holdoutExposed = primary.metrics?.holdout_exposed === true;
    const signalStatus = diagnostic.signal_status || "not evaluated";
    const executionStatus = diagnostic.execution_status || (Object.keys(plan).length ? "pass" : "not evaluated");
    let nextAction = "Run a real-data preflight before research.";
    if (agent && executionStatus !== "pass") {
      nextAction = "Keep the rules frozen; review the failed development gate.";
    } else if (agent && !holdoutExposed) {
      nextAction = "Collect shadow outcomes and wait for materially new data before a predeclared final holdout.";
    } else if (primary.acceptance?.status !== "pass") {
      nextAction = "Record the holdout failure and keep the strategy frozen.";
    } else if (paper.status !== "validated") {
      nextAction = `Collect exact-plan paper evidence: ${Number(paper.current_closed_trades || 0)} of 30 closes.`;
    } else {
      nextAction = "Review fresh news-gated candidates with manual confirmation.";
    }
    return {
      strategy: primary.strategy || "low_vol_trend",
      signalStatus,
      executionStatus,
      holdoutExposed,
      holdoutStatus: holdoutExposed ? primary.acceptance?.status || "exposed" : "protected / not exposed",
      paperStatus: paper.status || "warming_up",
      paperClosed: Number(paper.current_closed_trades || 0),
      shadowClosed: Number(shadow.current_closed_trades || 0),
      shadowPlans: shadow.by_plan || {},
      source: provenance.source || "unavailable",
      isDemo: provenance.is_demo === true,
      datasetHash: provenance.dataset_sha256 || "",
      coverageLabel: coverage.length === 21 ? "20 stocks + SPY" : `${coverage.length} symbols`,
      coverageStart: coverage.map((row) => row.first).filter(Boolean).sort().at(-1) || "-",
      coverageEnd: coverage.map((row) => row.last).filter(Boolean).sort().at(0) || "-",
      holdout: agent?.holdout || {},
      plan,
      nextAction
    };
  }

  function researchGateStatus(metric) {
    const row = researchForSymbol(metric.symbol);
    if (!row || researchAgeMinutes() > RESEARCH_MAX_AGE_MINUTES) return "reduce";
    const action = String(row.action || "").toLowerCase();
    if (action === "reject") return "reject";
    if (action === "reduce" || action === "news_unavailable") return "reduce";
    return "pass";
  }

  function quoteFreshnessReason(symbol) {
    const quote = state.ibkr.quotes[symbol];
    if (!quote?.timeMs) return "fresh live quote required";
    const age = Date.now() - quote.timeMs;
    return age > QUOTE_MAX_AGE_MS ? `quote stale (${Math.round(age / 1000)}s old)` : "";
  }

  function quoteAgeSeconds(symbol) {
    const time = state.ibkr.quotes[symbol]?.timeMs;
    return time ? Math.round((Date.now() - time) / 1000) : null;
  }

  function newsTone(symbol) {
    const news = researchForSymbol(symbol)?.news || [];
    if (news.some((item) => item.sentiment === "negative")) return "negative";
    if (news.some((item) => item.sentiment === "positive")) return "positive";
    return news.length ? "neutral" : "unavailable";
  }

  function tradeFeatures(setup) {
    const metric = setup.metric || {};
    const quote = state.ibkr.quotes[setup.symbol] || {};
    const spreadPct = quote.bid && quote.ask ? (quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2) : metric.spreadBps / 10000;
    return {
      symbol: setup.symbol,
      style: setup.style,
      sector: metric.sector || setup.sector || "Unknown",
      regime: setup.marketRegime || "UNKNOWN",
      probability: setup.probability || 0,
      probabilityBucket: probabilityBucket(setup.probability || 0),
      expectedReturn: setup.expectedReturn || 0,
      netExpectedReturn: setup.netExpectedReturn || 0,
      trend: metric.trend || 0,
      trendBucket: band(metric.trend || 0.5, 0.45, 0.7),
      volatility: metric.vol20 || 0,
      volatilityBucket: band(metric.vol20 || 0, 0.2, 0.45),
      relative20: metric.relative20 || 0,
      liquidity: metric.liquidity || 0,
      spreadBps: metric.spreadBps || spreadPct * 10000,
      slippageBps: metric.slippageBps || 0,
      quoteAgeSeconds: quoteAgeSeconds(setup.symbol),
      stopDistancePct: setup.entry ? Math.abs(setup.entry - setup.stop) / setup.entry : 0,
      riskPct: setup.accountRiskPct || 0,
      feeDragPct: setup.fees?.dragPct || 0,
      eventRisk: eventRiskStatus(setup.symbol, setup.style),
      researchAction: researchForSymbol(setup.symbol)?.action || "none",
      newsTone: newsTone(setup.symbol),
      modelPack: state.modelPack ? modelPackLabel(setup) : "heuristic fallback"
    };
  }

  function fullAutoReasons(setup) {
    resetAutoTradeCountIfNeeded();
    const reasons = [];
    if (state.mode !== "FULL_AUTO") reasons.push("bot mode is not full auto");
    if (!state.fullAutoEnabled) reasons.push("server full auto lock is off");
    if (!state.liveOrdersEnabled) reasons.push("server live orders are off");
    if (!state.autoScout) reasons.push("auto scout is off");
    if (ACCOUNT.ibkrMode !== "LIVE_CONFIRM") reasons.push("IBKR mode is not live confirm");
    if (ACCOUNT.maxAutoTradesPerDay <= 0) reasons.push("max auto trades/day is zero");
    if (state.autoTradeCount >= ACCOUNT.maxAutoTradesPerDay) reasons.push("max auto trades/day reached");
    if (state.autoOrderInFlight) reasons.push("auto order already in flight");
    if (setup) reasons.push(...ibkrReadiness(setup).reasons);
    return reasons;
  }

  function hashSymbol(symbol) {
    return String(symbol).split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  }

  function seededNoise(seed) {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  }

  function previousTradingDays(endDate, count) {
    const days = [];
    const date = new Date(endDate);
    date.setHours(0, 0, 0, 0);
    while (days.length < count) {
      const day = date.getDay();
      if (day !== 0 && day !== 6) days.unshift(date.toISOString().slice(0, 10));
      date.setDate(date.getDate() - 1);
    }
    return days;
  }

  function sectorForSymbol(symbol, fallback = "Imported") {
    return SECTOR_BY_SYMBOL[String(symbol || "").toUpperCase()] || fallback;
  }

  function generateSampleData(endDate = new Date(), count = 320) {
    const profiles = {
      SPY: [520, 0.00025, 0.008, "Market"],
      QQQ: [455, 0.00032, 0.010, "Market"],
      XLK: [228, 0.00035, 0.012, "Technology"],
      XLF: [42, 0.00012, 0.009, "Financials"],
      XLE: [94, 0.00005, 0.013, "Energy"],
      XLV: [155, 0.00018, 0.009, "Healthcare"],
      AAPL: [215, 0.00034, 0.014, "Technology"],
      MSFT: [480, 0.00038, 0.013, "Technology"],
      NVDA: [140, 0.00058, 0.026, "Technology"],
      AMZN: [190, 0.00028, 0.017, "Consumer"],
      GOOGL: [178, 0.00024, 0.016, "Communication"],
      JPM: [205, 0.00017, 0.012, "Financials"],
      XOM: [113, 0.00008, 0.014, "Energy"],
      LLY: [910, 0.00036, 0.015, "Healthcare"],
      JNJ: [148, 0.00008, 0.008, "Healthcare"],
      PFE: [28, 0.00004, 0.014, "Healthcare"],
      MRK: [130, 0.00016, 0.011, "Healthcare"],
      MRNA: [135, 0.00010, 0.032, "Biotech"]
    };
    const dates = previousTradingDays(endDate, count);
    const rows = [];
    Object.entries(profiles).forEach(([symbol, [start, drift, vol, sector]]) => {
      let close = start;
      const baseVolume = 5000000 + hashSymbol(symbol) * 65000;
      dates.forEach((date, index) => {
        const cycle = Math.sin(index / 21 + hashSymbol(symbol) / 9) * vol * 0.35;
        const shock = (seededNoise(index * 17 + hashSymbol(symbol)) - 0.48) * vol * 2;
        close = Math.max(3, close * (1 + drift + cycle + shock));
        const open = close * (1 + (seededNoise(index * 19 + hashSymbol(symbol)) - 0.5) * vol);
        const high = Math.max(open, close) * (1 + seededNoise(index * 23 + hashSymbol(symbol)) * vol);
        const low = Math.min(open, close) * (1 - seededNoise(index * 29 + hashSymbol(symbol)) * vol);
        const volume = Math.round(baseVolume * (0.65 + seededNoise(index * 31 + hashSymbol(symbol)) * 0.9));
        rows.push({ symbol, date, open, high, low, close, adjustedClose: close, volume, sector });
      });
    });
    return rows;
  }

  function parseCsv(text) {
    const rows = [];
    let field = "";
    let row = [];
    let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      const next = text[i + 1];
      if (char === '"' && quoted && next === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = !quoted;
      } else if (char === "," && !quoted) {
        row.push(field);
        field = "";
      } else if ((char === "\n" || char === "\r") && !quoted) {
        if (char === "\r" && next === "\n") i += 1;
        row.push(field);
        if (row.some(Boolean)) rows.push(row);
        row = [];
        field = "";
      } else {
        field += char;
      }
    }
    row.push(field);
    if (row.some(Boolean)) rows.push(row);
    if (rows.length < 2) return [];

    const headers = rows[0].map((header) => header.trim().toLowerCase().replace(/[\s-]+/g, "_"));
    return rows.slice(1).map((values) => {
      const item = {};
      headers.forEach((header, index) => { item[header] = (values[index] || "").trim(); });
      return {
        symbol: item.symbol || item.ticker,
        date: item.date,
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close: Number(item.close),
        adjustedClose: Number(item.adjusted_close || item.adj_close || item.close),
        volume: Number(item.volume || 0),
        sector: sectorForSymbol(item.symbol, item.sector || "Imported")
      };
    }).filter((row) => row.symbol && row.date && row.close > 0 && row.high >= row.low);
  }

  function parseGenericCsv(text) {
    const rows = [];
    let field = "";
    let row = [];
    let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      const next = text[i + 1];
      if (char === '"' && quoted && next === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = !quoted;
      } else if (char === "," && !quoted) {
        row.push(field);
        field = "";
      } else if ((char === "\n" || char === "\r") && !quoted) {
        if (char === "\r" && next === "\n") i += 1;
        row.push(field);
        if (row.some(Boolean)) rows.push(row);
        row = [];
        field = "";
      } else {
        field += char;
      }
    }
    row.push(field);
    if (row.some(Boolean)) rows.push(row);
    if (rows.length < 2) return [];
    const headers = rows[0].map((header) => header.trim().toLowerCase().replace(/[\s-]+/g, "_"));
    return rows.slice(1).map((values) => {
      const item = {};
      headers.forEach((header, index) => { item[header] = (values[index] || "").trim(); });
      return item;
    });
  }

  function groupBySymbol(rows) {
    const groups = new Map();
    rows.forEach((row) => {
      const symbol = String(row.symbol || "").trim().toUpperCase();
      if (!symbol) return;
      if (!groups.has(symbol)) groups.set(symbol, []);
      groups.get(symbol).push({ ...row, symbol });
    });
    groups.forEach((items) => items.sort((a, b) => a.date.localeCompare(b.date)));
    return groups;
  }

  function mean(values) {
    const clean = values.filter(Number.isFinite);
    return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : 0;
  }

  function std(values) {
    const avg = mean(values);
    const clean = values.filter(Number.isFinite);
    if (clean.length < 2) return 0;
    return Math.sqrt(mean(clean.map((value) => (value - avg) ** 2)));
  }

  function pctChange(rows, days) {
    if (rows.length <= days) return 0;
    const last = rows[rows.length - 1].adjustedClose;
    const prior = rows[rows.length - 1 - days].adjustedClose;
    return prior ? last / prior - 1 : 0;
  }

  function sma(rows, days) {
    if (rows.length < days) return mean(rows.map((row) => row.adjustedClose));
    return mean(rows.slice(-days).map((row) => row.adjustedClose));
  }

  function dailyReturns(rows, days) {
    const slice = rows.slice(Math.max(1, rows.length - days));
    return slice.map((row, index) => {
      const prior = rows[rows.length - slice.length + index - 1];
      return prior ? row.adjustedClose / prior.adjustedClose - 1 : 0;
    });
  }

  function atr(rows, days = 14) {
    const slice = rows.slice(Math.max(1, rows.length - days));
    const ranges = slice.map((row, index) => {
      const prior = rows[rows.length - slice.length + index - 1];
      const prevClose = prior ? prior.close : row.close;
      return Math.max(row.high - row.low, Math.abs(row.high - prevClose), Math.abs(row.low - prevClose));
    });
    return mean(ranges);
  }

  function maxDrawdown(rows) {
    let peak = 0;
    let drawdown = 0;
    rows.forEach((row) => {
      peak = Math.max(peak, row.adjustedClose);
      if (peak) drawdown = Math.min(drawdown, row.adjustedClose / peak - 1);
    });
    return drawdown;
  }

  function averageDollarVolume(rows, days = 20) {
    return mean(rows.slice(-days).map((row) => row.close * row.volume));
  }

  function trendScore(rows) {
    const last = rows[rows.length - 1]?.adjustedClose || 0;
    const sma50 = sma(rows, 50);
    const sma200 = sma(rows, 200);
    let score = 0.5;
    if (last > sma50) score += 0.18;
    if (last > sma200) score += 0.22;
    if (pctChange(rows, 20) > 0) score += 0.1;
    if (pctChange(rows, 5) < -0.03) score -= 0.12;
    return clamp(score, 0, 1);
  }

  function marketRegime(groups) {
    const spy = groups.get("SPY") || firstGroup(groups);
    const qqq = groups.get("QQQ") || spy;
    const stocks = [...groups.entries()].filter(([symbol]) => !BENCHMARKS.has(symbol));
    const breadth = stocks.length
      ? stocks.filter(([, rows]) => rows[rows.length - 1].adjustedClose > sma(rows, 50)).length / stocks.length
      : 0.5;
    const spyTrend = trendScore(spy);
    const qqqTrend = trendScore(qqq);
    const vol20 = std(dailyReturns(spy, 20)) * Math.sqrt(252);
    const inverseVol = clamp(1 - vol20 / 0.45, 0, 1);
    const sectorConfirmation = mean(["XLK", "XLF", "XLE"].map((symbol) => {
      const rows = groups.get(symbol);
      return rows ? trendScore(rows) : 0.5;
    }));
    const score = 0.30 * spyTrend + 0.20 * qqqTrend + 0.20 * breadth + 0.15 * inverseVol + 0.15 * sectorConfirmation;
    const regime = score >= 0.70 ? "BULLISH" : score >= 0.45 ? "NEUTRAL" : score >= 0.20 ? "BEARISH" : "PANIC";
    return { regime, score, spyTrend, qqqTrend, breadth, vol20, sectorConfirmation };
  }

  function firstGroup(groups) {
    return groups.values().next().value || [];
  }

  function metricForSymbol(symbol, rows, groups, regime) {
    const last = rows[rows.length - 1];
    const ret1 = pctChange(rows, 1);
    const ret5 = pctChange(rows, 5);
    const ret20 = pctChange(rows, 20);
    const ret60 = pctChange(rows, 60);
    const spyRows = groups.get("SPY") || rows;
    const relative20 = ret20 - pctChange(spyRows, 20);
    const vol20 = std(dailyReturns(rows, 20)) * Math.sqrt(252);
    const liquidity = averageDollarVolume(rows, 20);
    const priceAtr = atr(rows, 14);
    const trend = trendScore(rows);
    const expected20 = 0.35 * ret20 + 0.20 * ret60 + 0.20 * relative20 + 0.12 * (trend - 0.5) + 0.10 * (regime.score - 0.5) - 0.06 * vol20;
    const probability = clamp(0.5 + expected20 * 2.4 + (trend - 0.5) * 0.16 + (regime.score - 0.5) * 0.14, 0.05, 0.95);
    const score = clamp(50 + expected20 * 260 + relative20 * 110 + trend * 28 + regime.score * 18 - vol20 * 24, 0, 100);
    return {
      symbol,
      sector: last.sector || "Unknown",
      rows,
      last,
      price: last.close,
      ret1,
      ret5,
      ret20,
      ret60,
      relative20,
      vol20,
      liquidity,
      atr: priceAtr,
      drawdown: maxDrawdown(rows.slice(-252)),
      trend,
      expected20,
      probability,
      score,
      spreadBps: clamp(4 + vol20 * 26 + 25000000 / Math.max(liquidity, 1), 2, 80),
      slippageBps: clamp(3 + vol20 * 18 + 15000000 / Math.max(liquidity, 1), 2, 70)
    };
  }

  function expectedForStyle(metric, style, regime) {
    if (style === "DAY_TRADE") return metric.expected20 / 9 + metric.ret1 * 0.15;
    if (style === "OVERNIGHT_1D") return metric.expected20 / 6 + metric.ret5 * 0.08;
    if (style === "SWING_5D") return metric.expected20 / 2.4 + metric.ret5 * 0.12 + (regime.score - 0.5) * 0.015;
    return metric.expected20 + metric.ret20 * 0.08 + (regime.score - 0.5) * 0.025;
  }

  function eventRiskStatus(symbol, style) {
    const text = state.eventBlocklist.join("\n").toUpperCase();
    if (!text.includes(symbol.toUpperCase())) return "pass";
    return style === "DAY_TRADE" ? "reduce" : "reject";
  }

  function strategyStats(style) {
    const trades = state.closedTrades.filter((trade) => trade.style === style);
    const wins = trades.filter((trade) => trade.pnl > 0);
    const losses = trades.filter((trade) => trade.pnl < 0);
    const grossWin = wins.reduce((sum, trade) => sum + trade.pnl, 0);
    const grossLoss = Math.abs(losses.reduce((sum, trade) => sum + trade.pnl, 0));
    const expectancy = trades.length ? trades.reduce((sum, trade) => sum + trade.returnPct, 0) / trades.length : 0;
    const profitFactor = grossLoss ? grossWin / grossLoss : wins.length ? 99 : 0;
    const winRate = trades.length ? wins.length / trades.length : 0;
    return { trades: trades.length, winRate, expectancy, profitFactor };
  }

  function closedTradesForStyle(style) {
    return state.closedTrades.filter((trade) => trade.style === style);
  }

  function paperFirstReason(setup) {
    const trades = closedTradesForStyle(setup.style).length;
    return trades >= ACCOUNT.minPaperTradesForLive ? "" : `paper/live-small warmup: ${trades}/${ACCOUNT.minPaperTradesForLive} closed ${setup.label} trades`;
  }

  function strategyValidationStatus(style) {
    const stats = strategyStats(style);
    if (stats.trades < ACCOUNT.minTradesToValidate) return "reduce";
    if (stats.expectancy < ACCOUNT.minExpectancy || stats.profitFactor < ACCOUNT.minProfitFactor) return "reject";
    return "pass";
  }

  function probabilityBucket(value) {
    if (value >= 0.8) return "80+";
    if (value >= 0.7) return "70-80";
    if (value >= 0.6) return "60-70";
    return "50-60";
  }

  function band(value, low, high) {
    if (value >= high) return "high";
    if (value <= low) return "low";
    return "mid";
  }

  function setupLearningNodes(setup) {
    const features = setup.features || tradeFeatures(setup);
    return [
      `symbol:${features.symbol}`,
      `style:${features.style}`,
      `sector:${features.sector}`,
      `regime:${features.regime}`,
      `prob:${features.probabilityBucket}`,
      `trend:${features.trendBucket}`,
      `vol:${features.volatilityBucket}`,
      `event:${features.eventRisk}`,
      `research:${features.researchAction}`,
      `news:${features.newsTone}`
    ];
  }

  function addGraphStats(map, key, trade) {
    const row = map.get(key) || { id: key, count: 0, wins: 0, pnl: 0, returnSum: 0 };
    row.count += 1;
    row.wins += trade.pnl > 0 ? 1 : 0;
    row.pnl += Number(trade.pnl || 0);
    row.returnSum += Number(trade.returnPct || 0);
    map.set(key, row);
  }

  function finalizeGraphStats(row) {
    return {
      ...row,
      winRate: row.count ? row.wins / row.count : 0,
      expectancy: row.count ? row.returnSum / row.count : 0
    };
  }

  function learningGraph(trades = state.closedTrades) {
    const nodes = new Map();
    const edges = new Map();
    trades.forEach((trade) => {
      const tradeNodes = Array.isArray(trade.learningNodes) && trade.learningNodes.length
        ? trade.learningNodes
        : setupLearningNodes(trade);
      const all = [...new Set([...tradeNodes, trade.pnl > 0 ? "outcome:win" : "outcome:loss"])];
      all.forEach((node) => addGraphStats(nodes, node, trade));
      // ponytail: tiny feature sets; if trade history gets large, move this graph build server-side.
      for (let i = 0; i < all.length; i += 1) {
        for (let j = i + 1; j < all.length; j += 1) {
          addGraphStats(edges, [all[i], all[j]].sort().join(" -> "), trade);
        }
      }
    });
    return {
      nodes: [...nodes.values()].map(finalizeGraphStats),
      edges: [...edges.values()].map(finalizeGraphStats)
    };
  }

  function learningSignal(setup) {
    const graph = learningGraph();
    const nodeIds = new Set(setupLearningNodes(setup));
    const matched = graph.nodes.filter((node) => nodeIds.has(node.id) && node.count >= 3);
    if (!matched.length) return { status: "reduce", multiplier: 0.75, score: -3, reason: "learning warmup" };
    const count = matched.reduce((sum, node) => sum + node.count, 0);
    const expectancy = matched.reduce((sum, node) => sum + node.expectancy * node.count, 0) / count;
    const winRate = matched.reduce((sum, node) => sum + node.winRate * node.count, 0) / count;
    if (count < ACCOUNT.minGraphTradesToBoost) return { status: "reduce", multiplier: 0.75, score: -3, reason: "learning sample too small" };
    if (count >= ACCOUNT.minGraphTradesToReject && expectancy < -0.004) return { status: "reject", multiplier: 0, score: -20, reason: "similar trade graph is losing" };
    if (count >= 5 && expectancy < 0) return { status: "reduce", multiplier: 0.5, score: -8, reason: "similar trade graph underperforming" };
    if (count >= ACCOUNT.minGraphTradesToBoost && expectancy > 0.003 && winRate > 0.55) return { status: "pass", multiplier: 1.05, score: 4, reason: "similar trade graph working" };
    return { status: "pass", multiplier: 1, score: 0, reason: "similar trade graph neutral" };
  }

  function gateResults(metric, style, expected, probability, regime) {
    const config = styleConfig(style, metric.symbol);
    const learning = learningSignal({ symbol: metric.symbol, style, probability, marketRegime: regime.regime, metric });
    const gates = {
      data: metric.rows.length >= 80 ? "pass" : "reject",
      liquidity: metric.liquidity >= 10000000 ? "pass" : "reject",
      volatility: metric.vol20 <= 0.75 ? "pass" : "reduce",
      prediction: expected > 0 && probability >= config.minProb ? "pass" : "reject",
      execution: metric.spreadBps <= ACCOUNT.maxSpreadBps && metric.slippageBps <= ACCOUNT.maxSlippageBps ? "pass" : "reject",
      eventRisk: eventRiskStatus(metric.symbol, style),
      strategyValidation: strategyValidationStatus(style),
      modelPack: modelPackGateStatus(metric, style),
      researchAgent: researchAgentGateStatus(metric, style),
      aiResearch: researchGateStatus(metric),
      tradeLearning: learning.status,
      dayTrading: style === "DAY_TRADE" ? dayTradingAllowed() ? "pass" : "reject" : "pass",
      accountRisk: "pass",
      exitPlan: "pass"
    };

    if (style === "DAY_TRADE") {
      gates.marketRegime = regime.regime === "PANIC" ? "reject" : "pass";
    } else if (style === "OVERNIGHT_1D") {
      gates.marketRegime = regime.regime === "PANIC" ? "reject" : regime.regime === "BEARISH" ? "reduce" : "pass";
    } else if (style === "SWING_5D") {
      gates.marketRegime = regime.regime === "BULLISH" ? "pass" : regime.regime === "NEUTRAL" ? "reduce" : "reject";
    } else {
      gates.marketRegime = regime.regime === "BULLISH" ? "pass" : "reject";
    }
    return gates;
  }

  function summarizeGateStatus(gates) {
    if (Object.values(gates).includes("reject")) return "REJECT";
    if (Object.values(gates).includes("reduce")) return "REDUCE";
    return "PASS";
  }

  function firstReject(gates) {
    const entry = Object.entries(gates).find(([, status]) => status === "reject");
    return entry ? entry[0] : "";
  }

  function buildSetup(metric, style, regime) {
    const config = styleConfig(style, metric.symbol);
    const agentCandidate = researchAgentCandidate(metric.symbol, style);
    const expected = expectedForStyle(metric, style, regime);
    const probability = clamp(metric.probability + expected * 1.8, 0.05, 0.95);
    const gates = gateResults(metric, style, expected, probability, regime);
    const learning = learningSignal({ symbol: metric.symbol, style, probability, marketRegime: regime.regime, metric });
    let gateStatus = summarizeGateStatus(gates);
    const stats = strategyStats(style);
    const recent = state.closedTrades.slice(0, 8);
    const recentLosses = recent.filter((trade) => trade.pnl < 0).length;
    const styleMultiplier = stats.trades >= ACCOUNT.minTradesToValidate && stats.expectancy > ACCOUNT.minExpectancy ? 1 : 0.5;
    const streakMultiplier = recentLosses >= ACCOUNT.maxConsecutiveLosses ? 0.35 : 1;
    const reduction = (gateStatus === "REDUCE" ? 0.5 : 1) * styleMultiplier * streakMultiplier * learning.multiplier;
    const entry = agentCandidate ? Number(agentCandidate.entry) : metric.price;
    const stopDistance = agentCandidate
      ? entry - Number(agentCandidate.stop)
      : Math.max(metric.atr * config.stopAtr, metric.price * 0.004);
    const stop = agentCandidate ? Number(agentCandidate.stop) : entry - stopDistance;
    const target = agentCandidate ? Number(agentCandidate.target) : entry + stopDistance * config.targetR;
    const riskDollars = ACCOUNT.equity * config.riskPct * reduction;
    const rawShares = Math.floor(riskDollars / stopDistance);
    const maxValueShares = Math.floor((ACCOUNT.equity * config.maxPositionWeight) / entry);
    const liquidityShares = Math.floor((metric.liquidity / entry) * 0.01);
    const shares = Math.max(0, Math.min(rawShares, maxValueShares, liquidityShares));
    const fees = estimateSetupFees(shares, entry, target);
    gates.fees = shares > 0 && fees.dragPct <= ACCOUNT.maxFeeDragPct && expected > fees.dragPct ? "pass" : shares > 0 && fees.dragPct <= ACCOUNT.maxFeeDragPct ? "reduce" : "reject";
    gateStatus = summarizeGateStatus(gates);
    const rewardToRisk = (target - entry) / stopDistance;
    const setupScore = clamp(metric.score * 0.45 + probability * 30 + rewardToRisk * 7 + regime.score * 14 - metric.vol20 * 12 - fees.dragPct * 500 + learning.score, 0, 100);
    const rejectionReason = gateStatus === "REJECT" ? firstReject(gates) : "";
    return {
      id: `${metric.symbol}-${style}-${metric.last.date}`,
      symbol: metric.symbol,
      side: "LONG",
      style,
      label: STYLE_LABELS[style],
      status: gateStatus,
      rejectionReason,
      entry,
      stop,
      target,
      shares,
      positionValue: shares * entry,
      riskDollars: shares * stopDistance,
      fees,
      accountRiskPct: ACCOUNT.equity ? shares * stopDistance / ACCOUNT.equity : 0,
      maxHold: config.horizon,
      expectedReturn: expected,
      netExpectedReturn: expected - fees.dragPct,
      probability,
      rewardToRisk,
      setupScore,
      confidence: clamp(metric.score / 100 * 0.55 + probability * 0.30 + regime.score * 0.15, 0, 1),
      gates,
      strategyStats: stats,
      researchAgent: agentCandidate,
      learning,
      metric,
      marketRegime: regime.regime,
      orderType: style === "DAY_TRADE" ? "limit intraday bracket" : "limit bracket"
    };
  }

  function analyze(rows, universeSymbols = []) {
    const groups = groupBySymbol(rows);
    const regime = marketRegime(groups);
    const allowed = new Set(universeSymbols.map((symbol) => symbol.toUpperCase()).filter(Boolean));
    const metrics = [...groups.entries()]
      .filter(([symbol, items]) => items.length > 30 && !BENCHMARKS.has(symbol) && (!allowed.size || allowed.has(symbol)))
      .map(([symbol, items]) => metricForSymbol(symbol, items, groups, regime))
      .sort((a, b) => b.score - a.score);
    const setups = metrics.flatMap((metric) => Object.keys(STYLE_CONFIG).map((style) => buildSetup(metric, style, regime)))
      .sort((a, b) => {
        const passRank = { PASS: 2, REDUCE: 1, REJECT: 0 };
        return passRank[b.status] - passRank[a.status] || b.setupScore - a.setupScore;
      });
    return { groups, regime, metrics, setups, latestDate: latestDate(rows) };
  }

  function latestDate(rows) {
    return rows.reduce((latest, row) => row.date > latest ? row.date : latest, "");
  }

  const state = {
    data: [],
    analysis: null,
    selectedSymbol: "",
    selectedStyle: "ALL",
    selectedSetupId: "",
    activeTab: "journal",
    mode: "ALERT_ONLY",
    paused: false,
    orders: [],
    closedTrades: [],
    positions: [],
    ibkrOpenOrders: [],
    ibkrTrades: [],
    universe: [...DEFAULT_UNIVERSE],
    liveQuotes: false,
    liveTimer: null,
    quotePollInFlight: false,
    autoScout: false,
    autoScoutSeen: new Set(),
    viewMode: "DETAILED",
    liveOrdersEnabled: false,
    fullAutoEnabled: false,
    autoOrderInFlight: false,
    autoTradeDate: "",
    autoTradeCount: 0,
    serverStore: false,
    auditCount: 0,
    modelPack: null,
    researchAgent: null,
    researchSnapshot: null,
    researchInFlight: false,
    openAiEnabled: false,
    openAiModel: "",
    lastStateSave: "",
    killSwitch: false,
    eventBlocklist: [],
    ibkr: {
      connected: false,
      status: "Offline",
      accounts: [],
      accountId: "",
      conids: {},
      quotes: {},
      lastSync: "",
      error: "",
      diagnostics: null
    },
    journal: []
  };

  async function initDashboard() {
    if (location.protocol === "file:") {
      try {
        const response = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
        if (response.ok) {
          location.replace(API_BASE);
          return;
        }
      } catch {
        // ponytail: keep the read-only file fallback when the local server is not running.
      }
    }
    await loadState();
    await syncServerHealth();
    await loadModelPack();
    await loadResearchAgent();
    await loadResearchSnapshot();
    state.data = generateSampleData();
    state.analysis = analyze(state.data, state.universe);
    selectBotPick();
    state.journal.unshift(journalLine("Loaded sample market data", "Data"));
    wireEvents();
    render();
    refreshResearch(true).then(() => render()).catch(() => {});
    setInterval(() => refreshResearch(true).then(() => render()).catch(() => {}), RESEARCH_REFRESH_MS);
  }

  async function loadState() {
    try {
      let saved = JSON.parse(localStorage.getItem("spa_state") || "{}");
      if (typeof fetch !== "undefined") {
        try {
          const response = await fetch(`${API_BASE}/api/state`);
          if (response.ok) {
            const serverState = await response.json();
            state.serverStore = true;
            saved = serverState.state && Object.keys(serverState.state).length ? serverState.state : saved;
            state.auditCount = Array.isArray(serverState.audit) ? serverState.audit.length : 0;
            if (Array.isArray(serverState.audit) && serverState.audit.length) {
              state.journal = serverState.audit.slice(-200).reverse().map((event) => ({
                time: new Date(event.time).toLocaleTimeString(),
                type: event.type || event.source || "Audit",
                message: event.summary || event.message || JSON.stringify(event).slice(0, 180)
              }));
            }
          }
        } catch {
          state.serverStore = false;
          // ponytail: server store unavailable in file mode; localStorage fallback covers it.
        }
      }
      state.universe = Array.isArray(saved.universe) && saved.universe.length ? saved.universe : state.universe;
      state.viewMode = saved.viewMode === "FOCUS" ? "FOCUS" : "DETAILED";
      state.orders = Array.isArray(saved.orders) ? saved.orders : [];
      state.closedTrades = Array.isArray(saved.closedTrades) ? saved.closedTrades : [];
      state.ibkrTrades = Array.isArray(saved.ibkrTrades) ? saved.ibkrTrades : [];
      state.journal = state.journal.length ? state.journal : Array.isArray(saved.journal) ? saved.journal.slice(0, 200) : [];
      state.eventBlocklist = Array.isArray(saved.eventBlocklist) ? saved.eventBlocklist : [];
      if (saved.auto) {
        state.autoTradeDate = saved.auto.autoTradeDate || "";
        state.autoTradeCount = Number(saved.auto.autoTradeCount || 0);
      }
      if (saved.account) Object.assign(ACCOUNT, saved.account);
      if (saved.ibkr) {
        state.ibkr.accountId = saved.ibkr.accountId || state.ibkr.accountId;
        state.ibkr.conids = saved.ibkr.conids && typeof saved.ibkr.conids === "object" ? saved.ibkr.conids : state.ibkr.conids;
      }
    } catch {
      // ponytail: local persistence is convenience only; corrupted state falls back to defaults.
    }
  }

  function saveState() {
    const payload = {
      account: ACCOUNT,
      viewMode: state.viewMode,
      universe: state.universe,
      orders: state.orders.slice(0, 100),
      closedTrades: state.closedTrades.slice(0, 500),
      ibkrTrades: state.ibkrTrades.slice(0, 500),
      journal: state.journal.slice(0, 200),
      modelVersion: MODEL_VERSION,
      ibkr: { accountId: state.ibkr.accountId, conids: state.ibkr.conids },
      auto: { autoTradeDate: state.autoTradeDate, autoTradeCount: state.autoTradeCount },
      eventBlocklist: state.eventBlocklist
    };
    state.lastStateSave = new Date().toLocaleTimeString();
    try {
      localStorage.setItem("spa_state", JSON.stringify(payload));
    } catch {
      // ponytail: storage full should not block trading gates.
    }
    if (typeof fetch !== "undefined") {
      fetch(`${API_BASE}/api/state`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload)
      }).catch(() => {});
    }
  }

  function bestSetupForSymbol(symbol) {
    const style = state.selectedStyle;
    return state.analysis.setups.find((setup) => setup.symbol === symbol && (style === "ALL" || setup.style === style))
      || state.analysis.setups.find((setup) => setup.symbol === symbol)
      || state.analysis.setups[0];
  }

  function selectedSetup() {
    return state.analysis.setups.find((setup) => setup.id === state.selectedSetupId) || bestSetupForSymbol(state.selectedSymbol);
  }

  async function syncServerHealth() {
    try {
      const health = await apiGet("/api/health");
      state.liveOrdersEnabled = Boolean(health.liveOrdersEnabled);
      state.fullAutoEnabled = Boolean(health.fullAutoEnabled);
      state.openAiEnabled = Boolean(health.openAiEnabled);
      state.openAiModel = health.openAiModel || "";
    } catch {
      state.liveOrdersEnabled = false;
      state.fullAutoEnabled = false;
      state.openAiEnabled = false;
      state.openAiModel = "";
    }
  }

  async function loadModelPack() {
    try {
      const result = await apiGet("/api/model-pack");
      state.modelPack = result.modelPack || null;
    } catch {
      state.modelPack = null;
    }
  }

  async function loadResearchAgent() {
    try {
      const result = await apiGet("/api/research-agent");
      state.researchAgent = result.result || null;
    } catch {
      state.researchAgent = null;
    }
  }

  async function loadResearchSnapshot() {
    try {
      const result = await apiGet("/api/research-snapshot");
      state.researchSnapshot = result.snapshot || null;
    } catch {
      state.researchSnapshot = null;
    }
  }

  function rsi(rows, days = 14) {
    const returns = dailyReturns(rows, days);
    const gains = returns.map((value) => Math.max(0, value));
    const losses = returns.map((value) => Math.max(0, -value));
    const avgLoss = mean(losses);
    if (!avgLoss) return 100;
    return 100 - (100 / (1 + mean(gains) / avgLoss));
  }

  function volumeTrend(rows) {
    const recent = mean(rows.slice(-5).map((row) => row.volume));
    const base = mean(rows.slice(-20).map((row) => row.volume));
    return base ? recent / base - 1 : 0;
  }

  function technicalForSymbol(symbol, rows, groups) {
    const spyRows = groups.get("SPY") || rows;
    return {
      price: rows.at(-1)?.adjustedClose || rows.at(-1)?.close || 0,
      sma20: sma(rows, 20),
      sma50: sma(rows, 50),
      sma200: sma(rows, 200),
      rsi14: rsi(rows, 14),
      atr14: atr(rows, 14),
      relative_20d: pctChange(rows, 20) - pctChange(spyRows, 20),
      volume_trend: volumeTrend(rows)
    };
  }

  function researchDecision(technical) {
    const reasons = [];
    let action = "pass";
    if (technical.price < technical.sma200) {
      action = "reject";
      reasons.push("below SMA200");
    } else if (technical.price < technical.sma50) {
      action = "reduce";
      reasons.push("below SMA50");
    }
    if (technical.rsi14 > 72) {
      action = action === "reject" ? "reject" : "reduce";
      reasons.push("RSI extended");
    }
    if (technical.relative_20d < -0.04) {
      action = action === "reject" ? "reject" : "reduce";
      reasons.push("weak 20D relative strength");
    }
    if (!reasons.length) reasons.push("trend and relative strength acceptable");
    return { action, reasons };
  }

  function researchView(symbol, technical, decision) {
    const trend = technical.price >= technical.sma50 ? "constructive trend" : "trend under pressure";
    const rsiText = technical.rsi14 > 72 ? "RSI extended" : technical.rsi14 < 35 ? "RSI washed out" : "RSI neutral";
    return `${symbol} ${trend}; ${rsiText}; ${decision.action === "pass" ? "no research reduction" : "sizing/trade gate tightened"}.`;
  }

  function buildResearchSnapshot(rows, universeSymbols = []) {
    const groups = groupBySymbol(rows);
    const regime = marketRegime(groups);
    const symbols = {};
    universeSymbols.forEach((symbol) => {
      const clean = String(symbol || "").toUpperCase();
      const symbolRows = groups.get(clean);
      if (!symbolRows?.length) return;
      const technical = technicalForSymbol(clean, symbolRows, groups);
      const decision = researchDecision(technical);
      symbols[clean] = {
        technical,
        news: [],
        news_status: "news_unavailable",
        ai_view: researchView(clean, technical, decision),
        action: decision.action,
        reasons: decision.reasons
      };
    });
    const spy = groups.get("SPY") || firstGroup(groups);
    return {
      schema_version: 1,
      created_at: new Date().toISOString(),
      research_version: RESEARCH_VERSION,
      market: {
        regime: regime.regime,
        breadth: regime.breadth,
        spy_sma50: spy.length ? sma(spy, 50) : 0,
        spy_sma200: spy.length ? sma(spy, 200) : 0
      },
      symbols
    };
  }

  function withCachedNews(snapshot) {
    const previous = state.researchSnapshot?.symbols || {};
    Object.entries(snapshot.symbols || {}).forEach(([symbol, row]) => {
      const old = previous[symbol];
      if (!old) return;
      row.news = Array.isArray(old.news) ? old.news : row.news;
      row.news_status = old.news_status || row.news_status;
      row.news_error = old.news_error || "";
      if ((row.news || []).some((item) => item.sentiment === "negative") && row.action === "pass") {
        row.action = "reduce";
        row.reasons = [...new Set([...(row.reasons || []), "negative headline risk"])];
      }
    });
    return snapshot;
  }

  function refreshLocalResearch() {
    if (!state.data.length || !state.universe.length) return;
    state.researchSnapshot = withCachedNews(buildResearchSnapshot(state.data, state.universe));
  }

  async function refreshResearch(silent = false) {
    if (!state.analysis || state.researchInFlight) return;
    state.researchInFlight = true;
    try {
      await Promise.all([loadModelPack(), loadResearchAgent()]);
      const local = withCachedNews(buildResearchSnapshot(state.data, state.universe));
      state.researchSnapshot = local;
      try {
        const result = await apiPost("/api/research-refresh", { snapshot: local, symbols: state.universe });
        state.researchSnapshot = result.snapshot || local;
      } catch {
        // ponytail: local technical snapshot is enough when server/news is unavailable.
      }
      state.analysis = analyze(state.data, state.universe);
      selectBotPick();
      if (!silent) state.journal.unshift(journalLine(`AI research refreshed for ${Object.keys(state.researchSnapshot.symbols || {}).length} symbol(s)`, "Research"));
    } finally {
      state.researchInFlight = false;
    }
  }

  function wireEvents() {
    document.getElementById("bot-mode").addEventListener("change", (event) => {
      if (event.target.value === "FULL_AUTO" && !state.fullAutoEnabled) {
        event.target.value = state.mode;
        state.journal.unshift(journalLine("Full auto is locked: restart server with ENABLE_FULL_AUTO=1", "Auto"));
        render();
        return;
      }
      state.mode = event.target.value;
      state.journal.unshift(journalLine(`Mode changed to ${state.mode}`, "Mode"));
      render();
    });
    document.getElementById("pause-bot").addEventListener("click", () => {
      state.paused = !state.paused;
      state.journal.unshift(journalLine(state.paused ? "Bot paused" : "Bot resumed", "Mode"));
      render();
    });
    document.querySelectorAll(".style-filter").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedStyle = button.dataset.style;
        state.selectedSetupId = bestSetupForSymbol(state.selectedSymbol)?.id || "";
        render();
      });
    });
    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeTab = button.dataset.tab;
        renderBlotter();
      });
    });
    document.querySelectorAll(".section-link").forEach((button) => {
      button.addEventListener("click", () => {
        const analysisTab = button.dataset.analysisTab;
        if (analysisTab) {
          state.viewMode = "DETAILED";
          state.activeTab = analysisTab;
          render();
        }
        document.querySelectorAll(".section-link").forEach((item) => item.classList.toggle("is-active", item === button));
        document.getElementById(button.dataset.section)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
    document.getElementById("symbol-search").addEventListener("input", renderRankings);
    document.getElementById("paper-order").addEventListener("click", submitPaperOrder);
    document.getElementById("queue-live").addEventListener("click", queueLiveOrder);
    document.getElementById("live-submit").addEventListener("click", submitLiveOrder);
    document.getElementById("copy-plan").addEventListener("click", copyOrderPlan);
    document.getElementById("export-plan").addEventListener("click", exportOrderPlan);
    document.getElementById("reject-setup").addEventListener("click", rejectSetup);
    document.getElementById("csv-file").addEventListener("change", importCsv);
    document.getElementById("positions-file").addEventListener("change", importPositions);
    document.getElementById("orders-file").addEventListener("change", importOpenOrders);
    document.getElementById("sync-ibkr").addEventListener("click", syncIbkr);
    document.getElementById("live-quotes").addEventListener("click", toggleLiveQuotes);
    document.getElementById("auto-scout").addEventListener("click", toggleAutoScout);
    document.getElementById("view-mode").addEventListener("click", () => {
      state.viewMode = state.viewMode === "DETAILED" ? "FOCUS" : "DETAILED";
      state.journal.unshift(journalLine(`View mode changed to ${state.viewMode.toLowerCase()}`, "View"));
      saveState();
      render();
    });
    document.getElementById("apply-universe").addEventListener("click", applyUniverse);
    document.getElementById("fetch-history").addEventListener("click", fetchIbkrHistoryForUniverse);
    document.getElementById("refresh-research").addEventListener("click", async () => {
      await refreshResearch(false);
      render();
    });
    document.getElementById("event-blocklist").addEventListener("change", applyEventBlocklist);
    document.getElementById("ibkr-account").addEventListener("change", (event) => {
      state.ibkr.accountId = event.target.value;
      syncIbkr();
    });
    document.getElementById("account-equity-input").addEventListener("change", updateAccountInputs);
    document.getElementById("buying-power-input").addEventListener("change", updateAccountInputs);
    document.getElementById("day-pl-input").addEventListener("change", updateAccountInputs);
    document.getElementById("daily-max-loss-input").addEventListener("change", updateAccountInputs);
    document.getElementById("daily-profit-target-input").addEventListener("change", updateAccountInputs);
    document.getElementById("daily-max-profit-input").addEventListener("change", updateAccountInputs);
    document.getElementById("max-auto-trades-input").addEventListener("change", updateAccountInputs);
    document.getElementById("day-trade-eligible").addEventListener("change", updateAccountInputs);
    document.getElementById("day-trade-min-input").addEventListener("change", updateAccountInputs);
    document.getElementById("commission-plan").addEventListener("change", updateAccountInputs);
    document.getElementById("commission-per-share-input").addEventListener("change", updateAccountInputs);
    document.getElementById("min-commission-input").addEventListener("change", updateAccountInputs);
    document.getElementById("ibkr-mode").addEventListener("change", updateAccountInputs);
    window.addEventListener("resize", () => drawChart());
  }

  function render() {
    resetAutoTradeCountIfNeeded();
    const activeSetup = selectedSetup();
    if (activeSetup) {
      state.selectedSymbol = activeSetup.symbol;
      state.selectedSetupId = activeSetup.id;
    }
    document.body.classList.toggle("simple-mode", state.viewMode !== "DETAILED");
    if (state.mode === "FULL_AUTO" && !state.fullAutoEnabled) state.mode = "ALERT_ONLY";
    const fullAutoOption = document.querySelector('#bot-mode option[value="FULL_AUTO"]');
    if (fullAutoOption) {
      fullAutoOption.disabled = !state.fullAutoEnabled;
      fullAutoOption.textContent = state.fullAutoEnabled ? "Full auto" : "Full auto (locked)";
    }
    document.getElementById("bot-mode").value = state.mode;
    document.getElementById("account-equity-input").value = ACCOUNT.equity;
    document.getElementById("buying-power-input").value = ACCOUNT.buyingPower;
    document.getElementById("day-pl-input").value = ACCOUNT.dayPL;
    document.getElementById("daily-max-loss-input").value = ACCOUNT.dailyMaxLossDollars;
    document.getElementById("daily-profit-target-input").value = ACCOUNT.dailyProfitTargetDollars;
    document.getElementById("daily-max-profit-input").value = ACCOUNT.dailyMaxProfitDollars;
    document.getElementById("max-auto-trades-input").value = ACCOUNT.maxAutoTradesPerDay;
    document.getElementById("day-trade-eligible").value = ACCOUNT.dayTradingEligible ? "YES" : "NO";
    document.getElementById("day-trade-min-input").value = ACCOUNT.dayTradingMinimum;
    document.getElementById("commission-plan").value = ACCOUNT.commissionPlan;
    document.getElementById("commission-per-share-input").value = ACCOUNT.commissionPerShare;
    document.getElementById("min-commission-input").value = ACCOUNT.minCommission;
    document.getElementById("ibkr-mode").value = ACCOUNT.ibkrMode;
    renderIbkrAccounts();
    renderIbkrDiagnosticsPanel();
    document.getElementById("ibkr-status-top").textContent = state.ibkr.status;
    document.getElementById("live-quotes").textContent = state.liveQuotes ? "Live Quotes On" : "Live Quotes Off";
    document.getElementById("auto-scout").textContent = state.autoScout ? "Auto Scout On" : "Auto Scout Off";
    document.getElementById("view-mode").textContent = state.viewMode === "DETAILED" ? "Focus View" : "Full Workspace";
    const universeInput = document.getElementById("universe-input");
    if (document.activeElement !== universeInput) universeInput.value = state.universe.join(", ");
    const eventInput = document.getElementById("event-blocklist");
    if (document.activeElement !== eventInput) eventInput.value = state.eventBlocklist.join("\n");
    document.getElementById("market-regime").textContent = `${state.analysis.regime.regime} ${formatPct(state.analysis.regime.score, 0)}`;
    document.getElementById("account-equity").textContent = formatMoney(ACCOUNT.equity);
    document.getElementById("open-risk").textContent = formatPct(ACCOUNT.equity ? totalOpenRisk() / ACCOUNT.equity : 0);
    document.getElementById("data-freshness").textContent = state.analysis.latestDate;
    document.getElementById("pause-bot").textContent = state.paused ? "Resume" : "Pause";
    renderCommandSummary();
    renderDecisionPanel();
    renderResearchPanel();
    renderWorkflow();
    renderWatchlist();
    renderSetupList();
    renderRankings();
    renderTicket();
    renderRisk();
    renderBlotter();
    drawChart();
  }

  function renderCommandSummary() {
    const banner = document.getElementById("system-banner");
    const fileMode = typeof location !== "undefined" && location.protocol === "file:";
    banner.textContent = fileMode
      ? "Offline file mode: open http://127.0.0.1:8787 for IBKR sync, live quotes, and live-order controls."
      : "";
    banner.classList.toggle("is-hidden", !fileMode);

    const evidence = researchEvidence(state.researchAgent);
    document.getElementById("summary-primary-strategy").textContent = `${evidence.strategy} / rules frozen`;
    document.getElementById("summary-evidence").textContent = `${evidence.paperStatus} / ${evidence.paperClosed} of 30 paper closes • ${evidence.shadowClosed} shadow`;
    document.getElementById("summary-universe").textContent = `${state.universe.length} liquid stocks / no cherry-picking`;
    document.getElementById("summary-next-action").textContent = evidence.nextAction;
  }

  function renderDecisionPanel() {
    const setup = bestReadySetup();
    const status = document.getElementById("decision-status");
    const title = document.getElementById("decision-title");
    const trade = document.getElementById("decision-trade");
    const numbers = document.getElementById("decision-numbers");
    const actions = document.getElementById("decision-actions");
    if (!status || !title || !trade || !numbers || !actions) return;

    if (!setup) {
      const evidence = researchEvidence(state.researchAgent);
      status.textContent = "No trade";
      title.textContent = "No setup is ready";
      trade.textContent = evidence.nextAction;
      numbers.innerHTML = "";
      actions.textContent = `Research gate: ${evidence.holdoutStatus}; paper ${evidence.paperClosed}/30; shadow ${evidence.shadowClosed} closed.`;
      return;
    }

    const readiness = ibkrReadiness(setup);
    const quote = state.ibkr.quotes[setup.symbol]?.last || setup.entry;
    const source = state.ibkr.connected ? "IBKR synced" : "sample/offline data";
    const buyText = `Buy ${setup.shares} shares of ${setup.symbol} near ${formatMoney(setup.entry)}. Stop ${formatMoney(setup.stop)}. Target ${formatMoney(setup.target)}.`;
    status.textContent = `${source} / ${readiness.status}`;
    title.textContent = readiness.ok ? `Bot pick: ${setup.symbol} ${setup.label}` : `No live trade yet: ${setup.symbol} candidate`;
    trade.textContent = readiness.ok ? buyText : `Do not trade yet. ${readiness.reason}. Candidate plan: ${buyText}`;
    numbers.innerHTML = [
      decisionKpi("Last", formatMoney(quote)),
      decisionKpi("Shares", setup.shares),
      decisionKpi("Risk", formatMoney(setup.riskDollars)),
      decisionKpi("Fees", formatMoney(setup.fees.roundTrip)),
      decisionKpi("Net edge", formatPct(setup.netExpectedReturn)),
      decisionKpi("Hold", `${setup.maxHold}d`)
    ].join("");
    actions.textContent = decisionActionText(setup, readiness);
  }

  function renderResearchPanel() {
    const setup = selectedSetup() || bestReadySetup();
    const row = setup ? researchForSymbol(setup.symbol) : null;
    const technical = row?.technical || {};
    const modelStatus = document.getElementById("model-status");
    const title = document.getElementById("research-title");
    const summary = document.getElementById("research-summary");
    const numbers = document.getElementById("research-numbers");
    const button = document.getElementById("refresh-research");
    if (!modelStatus || !title || !summary || !numbers || !button) return;
    modelStatus.textContent = `Model: ${modelPackLabel(setup)} / GPT: ${state.openAiEnabled ? state.openAiModel : "off"}`;
    button.disabled = state.researchInFlight;
    button.textContent = state.researchInFlight ? "Refreshing" : "Refresh Research";
    if (!setup) {
      title.textContent = "AI research";
      summary.textContent = "No selected setup.";
      numbers.innerHTML = "";
      return;
    }
    const age = Number.isFinite(researchAgeMinutes()) ? `${Math.round(researchAgeMinutes())}m old` : "not refreshed";
    const newsStatus = row?.news_status === "ok" ? `${row.news.length} headline(s)` : "news unavailable";
    title.textContent = `AI research: ${setup.symbol}`;
    summary.textContent = row?.ai_view || "Research snapshot unavailable; live orders stay gated.";
    numbers.innerHTML = [
      decisionKpi("Action", row?.action || "reduce"),
      decisionKpi("RSI14", formatNumber(technical.rsi14, 1)),
      decisionKpi("SMA50", formatMoney(technical.sma50)),
      decisionKpi("Rel 20D", formatPct(technical.relative_20d)),
      decisionKpi("News", newsStatus),
      decisionKpi("GPT", row?.ai_status === "ok" ? row.ai_model || "on" : state.openAiEnabled ? "pending" : "off"),
      decisionKpi("Updated", age)
    ].join("");
  }

  function decisionKpi(label, value) {
    return `<span><small>${label}</small><strong>${value}</strong></span>`;
  }

  function decisionActionText(setup, readiness) {
    if (!readiness.ok) return `Fix first: ${readiness.reason}`;
    if (state.mode === "PAPER") return "Paper mode: click Approve Paper, or turn Auto Scout on to paper-trade automatically.";
    if (state.mode === "LIVE_WITH_CONFIRM") {
      return state.liveOrdersEnabled
        ? `Live confirm: review ${setup.symbol}, type the confirmation phrase, then Transmit Live.`
        : "Live confirm selected, but server live orders are locked. Start with start_live_dashboard.ps1.";
    }
    if (state.mode === "FULL_AUTO") {
      return state.fullAutoEnabled
        ? "Full auto armed: Auto Scout can place this if every gate still passes."
        : "Full auto is disabled. Start with start_full_auto_dashboard.ps1 only when you intentionally want automation.";
    }
    return "Alert only: switch to Paper or Live confirm when you want the app to act.";
  }

  function workflowCard(id, label, value, status) {
    const node = document.getElementById(id);
    if (!node) return;
    node.className = status || "";
    node.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  }

  function renderWorkflow() {
    const setup = selectedSetup();
    const readiness = setup ? ibkrReadiness(setup) : { ok: false, reason: "select setup" };
    const kill = killSwitchReasons();
    workflowCard("step-universe", "1. Choose stocks", state.universe.length ? `${state.universe.length} symbols` : "add symbols", state.universe.length ? "pass" : "warn");
    workflowCard("step-data", "2. Load data", state.ibkr.connected ? "IBKR synced" : state.data.length ? "sample data" : "needs data", state.ibkr.connected ? "pass" : "warn");
    workflowCard("step-review", "3. Review setup", setup ? `${setup.symbol} ${setup.label}` : "select trade", setup ? "pass" : "warn");
    workflowCard("step-risk", "4. Risk gates", kill[0] || readiness.reason, readiness.ok && !kill.length ? "pass" : "warn");
    workflowCard("step-execute", "5. Execute", executionModeLabel(), state.mode === "ALERT_ONLY" ? "warn" : "pass");
  }

  function executionModeLabel() {
    if (state.mode === "PAPER") return "paper only";
    if (state.mode === "LIVE_WITH_CONFIRM") return state.liveOrdersEnabled ? "live confirm" : "live locked";
    if (state.mode === "FULL_AUTO") return state.fullAutoEnabled ? "full auto armed" : "full auto locked";
    return "alerts only";
  }

  function renderIbkrAccounts() {
    const select = document.getElementById("ibkr-account");
    if (!select) return;
    const current = state.ibkr.accountId;
    const options = state.ibkr.accounts.map((account) => {
      const id = account.id || account.accountId || account.accountID || account.acctId || account.account || "";
      const label = account.accountTitle || account.displayName || account.alias || id;
      return `<option value="${id}">${label}</option>`;
    }).join("");
    select.innerHTML = `<option value="">${state.ibkr.accounts.length ? "Select account" : "Not synced"}</option>${options}`;
    select.value = current;
  }

  function ibkrDiagnosticsHtml() {
    const diag = state.ibkr.diagnostics;
    if (!diag) return state.ibkr.error ? table(["IBKR status"], [[state.ibkr.error]]) : "";
    return `
      ${table(["IBKR doctor"], [[diag.summary], ...(diag.nextSteps || []).map((step) => [step])])}
      ${table(["Service", "Port", "State"], (diag.ports || []).map((row) => [row.configured ? `${row.service} *` : row.service, row.port, row.listening ? "listening" : row.error || "closed"]))}
      ${(diag.processes || []).length ? table(["Process", "Window"], diag.processes.map((row) => [row.name, row.title || row.path || "-"])) : ""}
    `;
  }

  function renderIbkrDiagnosticsPanel() {
    const target = document.getElementById("ibkr-diagnostics");
    if (target) target.innerHTML = ibkrDiagnosticsHtml();
  }

  function parseUniverse(text) {
    return [...new Set(String(text || "")
      .toUpperCase()
      .split(/[\s,;]+/)
      .map((symbol) => symbol.replace(/[^A-Z0-9.\-]/g, ""))
      .filter(Boolean)
      .filter((symbol) => !BENCHMARKS.has(symbol)))];
  }

  function requiredSymbols() {
    return [...new Set([...state.universe, "SPY", "QQQ", "XLK", "XLF", "XLE"])];
  }

  function applyUniverse() {
    const next = parseUniverse(document.getElementById("universe-input").value);
    if (!next.length) {
      state.journal.unshift(journalLine("Universe unchanged: enter at least one stock symbol", "Universe"));
      renderBlotter();
      return;
    }
    state.universe = next;
    state.autoScoutSeen.clear();
    refreshLocalResearch();
    state.analysis = analyze(state.data, state.universe);
    selectBotPick();
    state.journal.unshift(journalLine(`Universe set to ${state.universe.join(", ")}`, "Universe"));
    saveState();
    render();
    refreshResearch(true).then(() => render()).catch(() => {});
  }

  function applyEventBlocklist() {
    state.eventBlocklist = document.getElementById("event-blocklist").value
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
    refreshLocalResearch();
    state.analysis = analyze(state.data, state.universe);
    selectBotPick();
    state.journal.unshift(journalLine(`Event blocklist updated: ${state.eventBlocklist.length} item(s)`, "Risk"));
    saveState();
    render();
  }

  async function toggleLiveQuotes() {
    state.liveQuotes = !state.liveQuotes;
    if (state.liveQuotes) {
      state.journal.unshift(journalLine("Live quote polling enabled at 1 second", "IBKR"));
      await syncIbkr();
      clearInterval(state.liveTimer);
      state.liveTimer = setInterval(refreshLiveQuotes, 1000);
    } else {
      clearInterval(state.liveTimer);
      state.liveTimer = null;
      state.journal.unshift(journalLine("Live quote polling disabled", "IBKR"));
    }
    render();
  }

  function toggleAutoScout() {
    state.autoScout = !state.autoScout;
    state.autoScoutSeen.clear();
    state.journal.unshift(journalLine(state.autoScout ? "Auto Scout enabled" : "Auto Scout disabled", "Scout"));
    if (state.autoScout) runAutoScout();
    render();
  }

  async function refreshLiveQuotes() {
    if (!state.liveQuotes || state.quotePollInFlight) return;
    state.quotePollInFlight = true;
    try {
      if (!state.ibkr.connected) await syncIbkr();
      else {
        await resolveUniverseConids();
        await applyIbkrSnapshots();
        markOpenOrdersToMarket();
        state.ibkr.lastSync = new Date().toLocaleTimeString();
        if (state.autoScout) runAutoScout();
        render();
      }
    } catch (error) {
      state.ibkr.status = "Quote error";
      state.ibkr.error = error.message;
    } finally {
      state.quotePollInFlight = false;
    }
  }

  function markOpenOrdersToMarket() {
    const remaining = [];
    state.orders.forEach((order) => {
      if (String(order.status || "").startsWith("live_")) return remaining.push(order);
      const quote = state.ibkr.quotes[order.symbol];
      const price = quote?.last || order.metric?.price || order.entry;
      const ageDays = Math.max(0, Math.floor((Date.now() - Number(order.createdAt || order.createdAtMs || Date.now())) / 86400000));
      let exitReason = "";
      if (price <= order.stop) exitReason = "stop";
      else if (price >= order.target) exitReason = "target";
      else if (ageDays >= order.maxHold) exitReason = "time";
      if (!exitReason) return remaining.push(order);
      closeTrackedTrade(order, price, exitReason);
    });
    if (remaining.length !== state.orders.length) {
      state.orders = remaining;
      saveState();
    }
  }

  function tradeOutcomeMetrics(order, exitPrice) {
    const entry = Number(order.fillPrice || order.entry);
    const groups = groupBySymbol(state.data);
    const rows = groups.get(order.symbol) || [];
    const entryDate = order.entryDate || order.metric?.last?.date || "";
    const exitDate = latestDate(rows);
    const windowRows = entryDate ? rows.filter((row) => row.date >= entryDate && (!exitDate || row.date <= exitDate)) : [];
    const high = windowRows.length ? Math.max(...windowRows.map((row) => row.high || row.close || entry)) : Math.max(entry, exitPrice);
    const low = windowRows.length ? Math.min(...windowRows.map((row) => row.low || row.close || entry)) : Math.min(entry, exitPrice);
    const actualReturn = entry ? exitPrice / entry - 1 : 0;
    const expectedReturn = Number(order.netExpectedReturn ?? order.expectedReturn ?? 0);
    return {
      expectedReturn,
      actualReturn,
      predictionError: actualReturn - expectedReturn,
      maxFavorableReturn: entry ? high / entry - 1 : 0,
      maxAdverseReturn: entry ? low / entry - 1 : 0,
      expectedHit: expectedReturn >= 0 ? actualReturn >= expectedReturn * 0.5 : actualReturn > 0,
      entryDate,
      exitDate
    };
  }

  function closeTrackedTrade(order, exitPrice, exitReason) {
    const entryPrice = Number(order.fillPrice || order.entry);
    const grossPnl = (exitPrice - entryPrice) * order.shares * (order.side === "LONG" ? 1 : -1);
    const fees = (order.fees?.buyFee || estimateTradeFee(order.shares, entryPrice)) + estimateTradeFee(order.shares, exitPrice);
    const pnl = grossPnl - fees;
    const returnPct = entryPrice && order.shares ? pnl / (entryPrice * order.shares) : 0;
    const outcome = tradeOutcomeMetrics(order, exitPrice);
    state.closedTrades.unshift({
      id: `${order.id}-CLOSED`,
      symbol: order.symbol,
      style: order.style,
      entry: entryPrice,
      exit: exitPrice,
      shares: order.shares,
      source: order.source || "",
      grossPnl,
      fees,
      pnl,
      returnPct,
      outcome,
      features: order.features || tradeFeatures(order),
      probability: order.probability,
      marketRegime: order.marketRegime,
      sector: order.metric?.sector || order.sector || "Unknown",
      learningNodes: Array.isArray(order.learningNodes) ? order.learningNodes : setupLearningNodes(order),
      exitReason,
      closedAt: new Date().toLocaleString()
    });
    state.journal.unshift(journalLine(`Closed tracked ${order.symbol} ${order.label}: ${exitReason}, P/L ${formatMoney(pnl)}`, "Performance"));
  }

  function bestReadySetup() {
    return state.analysis.setups.find((setup) => setup.status !== "REJECT" && ibkrReadiness(setup).ok)
      || state.analysis.setups.find((setup) => setup.status !== "REJECT")
      || null;
  }

  function selectBotPick() {
    const setup = bestReadySetup();
    if (!setup) return;
    state.selectedSymbol = setup.symbol;
    state.selectedSetupId = setup.id;
  }

  function killSwitchReasons() {
    const reasons = [];
    if (state.killSwitch) reasons.push("manual kill switch active");
    if (state.paused) reasons.push("bot paused");
    reasons.push(...dailyLimitReasons());
    if (state.ibkr.status === "Quote error") reasons.push("quote sync error");
    if (state.liveQuotes && !state.ibkr.connected) reasons.push("IBKR disconnected");
    const rejected = state.analysis.setups.filter((setup) => setup.status === "REJECT").length;
    if (state.analysis.setups.length && rejected / state.analysis.setups.length > ACCOUNT.maxRejectedSetupRatio) reasons.push("too many rejected setups");
    return reasons;
  }

  function calibrationBuckets() {
    const buckets = [
      { label: "50-60", min: 0.5, max: 0.6 },
      { label: "60-70", min: 0.6, max: 0.7 },
      { label: "70-80", min: 0.7, max: 0.8 },
      { label: "80+", min: 0.8, max: 1.01 }
    ];
    return buckets.map((bucket) => {
      const trades = state.closedTrades.filter((trade) => trade.probability >= bucket.min && trade.probability < bucket.max);
      const wins = trades.filter((trade) => trade.pnl > 0).length;
      return { ...bucket, count: trades.length, winRate: trades.length ? wins / trades.length : 0 };
    });
  }

  function returnsFor(rows, days = 60) {
    return dailyReturns(rows, days).filter(Number.isFinite);
  }

  function correlation(a, b) {
    const n = Math.min(a.length, b.length);
    if (n < 3) return 0;
    const x = a.slice(-n);
    const y = b.slice(-n);
    const mx = mean(x);
    const my = mean(y);
    const num = x.reduce((sum, value, index) => sum + (value - mx) * (y[index] - my), 0);
    const den = Math.sqrt(x.reduce((sum, value) => sum + (value - mx) ** 2, 0) * y.reduce((sum, value) => sum + (value - my) ** 2, 0));
    return den ? num / den : 0;
  }

  function realizedReturnFor(metric, horizon) {
    const rows = metric.rows;
    if (rows.length <= horizon + 1) return 0;
    const start = rows[rows.length - 1 - horizon].adjustedClose;
    const end = rows[rows.length - 1].adjustedClose;
    return start ? end / start - 1 : 0;
  }

  function replaySetups() {
    const groups = groupBySymbol(state.data);
    const rows = [];
    const styles = Object.keys(STYLE_CONFIG);
    for (const symbol of state.universe) {
      const data = groups.get(symbol);
      if (!data || data.length < 120) continue;
      for (let i = 80; i < data.length - 22; i += 5) {
        const windowRows = data.slice(0, i);
        const metric = metricForSymbol(symbol, windowRows, groups, state.analysis.regime);
        for (const style of styles) {
          const horizon = styleConfig(style, symbol).horizon;
          const future = data[i + horizon]?.adjustedClose && windowRows.at(-1)?.adjustedClose
            ? data[i + horizon].adjustedClose / windowRows.at(-1).adjustedClose - 1
            : 0;
          const expected = expectedForStyle(metric, style, state.analysis.regime);
          rows.push({
            symbol,
            style,
            date: windowRows.at(-1).date,
            expected,
            probability: clamp(metric.probability + expected * 1.8, 0.05, 0.95),
            actual: future,
            win: future > 0,
            regime: state.analysis.regime.regime,
            trend: metric.trend,
            vol20: metric.vol20,
            spreadBps: metric.spreadBps
          });
        }
      }
    }
    return rows;
  }

  function summarizeRows(rows) {
    const wins = rows.filter((row) => row.win);
    const losses = rows.filter((row) => !row.win);
    const avgWin = mean(wins.map((row) => row.actual));
    const avgLoss = Math.abs(mean(losses.map((row) => row.actual)));
    return {
      count: rows.length,
      winRate: rows.length ? wins.length / rows.length : 0,
      expectancy: mean(rows.map((row) => row.actual)),
      profitFactor: avgLoss ? (avgWin * wins.length) / (avgLoss * Math.max(losses.length, 1)) : wins.length ? 99 : 0
    };
  }

  function replaySummary() {
    const rows = replaySetups();
    return Object.keys(STYLE_CONFIG).map((style) => ({ style, ...summarizeRows(rows.filter((row) => row.style === style)) }));
  }

  function featureImportance() {
    const replay = replaySetups();
    const actual = replay.map((row) => row.actual);
    return [
      ["Probability", correlation(replay.map((row) => row.probability), actual)],
      ["Expected return", correlation(replay.map((row) => row.expected), actual)],
      ["Trend", correlation(replay.map((row) => row.trend), actual)],
      ["Volatility", correlation(replay.map((row) => row.vol20), actual)],
      ["Spread", correlation(replay.map((row) => row.spreadBps), actual)]
    ].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  }

  function attributeTrade(trade) {
    if (trade.exitReason === "stop") return "Stop hit: entry timing, stop distance, or market reversal";
    if (trade.exitReason === "target") return "Target hit: setup followed expected path";
    if (trade.marketRegime === "BEARISH" || trade.marketRegime === "PANIC") return "Regime drag: market state was hostile";
    if (trade.probability < 0.58) return "Weak confidence: probability was low";
    if (trade.returnPct < 0) return "Unfavorable outcome: review sector, spread, and event risk";
    return "Positive outcome: keep tracking sample size";
  }

  function attributionRows() {
    return state.closedTrades.map((trade) => [trade.symbol, STYLE_LABELS[trade.style] || trade.style, formatMoney(trade.pnl), trade.exitReason, attributeTrade(trade)]);
  }

  function whatWorksRows() {
    return Object.keys(STYLE_CONFIG)
      .map((style) => ({ style, ...strategyStats(style) }))
      .filter((row) => row.trades || row.expectancy > 0)
      .sort((a, b) => b.expectancy - a.expectancy)
      .map((row) => [STYLE_LABELS[row.style], row.trades, formatPct(row.winRate, 0), formatPct(row.expectancy), formatNumber(row.profitFactor)]);
  }

  function whatFailsRows() {
    return Object.keys(STYLE_CONFIG)
      .map((style) => ({ style, ...strategyStats(style) }))
      .sort((a, b) => a.expectancy - b.expectancy)
      .map((row) => [STYLE_LABELS[row.style], row.trades, formatPct(row.winRate, 0), formatPct(row.expectancy), formatNumber(row.profitFactor), strategyValidationStatus(row.style)]);
  }

  function learningGraphRows(kind, direction = "best") {
    const graph = learningGraph();
    return graph[kind]
      .filter((row) => row.count >= 2)
      .sort((a, b) => direction === "best" ? b.expectancy - a.expectancy : a.expectancy - b.expectancy)
      .slice(0, 12)
      .map((row) => [row.id, row.count, formatPct(row.winRate, 0), formatPct(row.expectancy), formatMoney(row.pnl)]);
  }

  function slippageRows() {
    return state.closedTrades.map((trade) => {
      const expected = trade.entry;
      const actual = trade.fillPrice || trade.entry;
      return [trade.symbol, STYLE_LABELS[trade.style] || trade.style, formatMoney(expected), formatMoney(actual), formatPct(expected ? actual / expected - 1 : 0)];
    });
  }

  function predictionRows() {
    return state.closedTrades.slice(0, 40).map((trade) => {
      const outcome = trade.outcome || {};
      return [
        trade.symbol,
        STYLE_LABELS[trade.style] || trade.style,
        formatPct(trade.probability || 0, 0),
        formatPct(outcome.expectedReturn ?? trade.netExpectedReturn ?? trade.expectedReturn ?? 0),
        formatPct(outcome.actualReturn ?? trade.returnPct ?? 0),
        formatPct(outcome.predictionError || 0),
        formatPct(outcome.maxFavorableReturn || 0),
        formatPct(outcome.maxAdverseReturn || 0),
        outcome.expectedHit ? "yes" : "no"
      ];
    });
  }

  function quoteQualityRows() {
    return Object.entries(state.ibkr.quotes).map(([symbol, quote]) => [
      symbol,
      formatMoney(quote.last),
      formatMoney(quote.bid),
      formatMoney(quote.ask),
      quote.bid && quote.ask ? formatPct((quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2)) : "-",
      quote.time || "-",
      quote.timeMs ? `${Math.round((Date.now() - quote.timeMs) / 1000)}s` : "-"
    ]);
  }

  function researchRows() {
    return Object.entries(state.researchSnapshot?.symbols || {}).map(([symbol, row]) => [
      symbol,
      String(row.action || "reduce").toUpperCase(),
      formatMoney(row.technical?.price),
      formatMoney(row.technical?.sma50),
      formatMoney(row.technical?.sma200),
      formatNumber(row.technical?.rsi14, 1),
      formatPct(row.technical?.relative_20d),
      row.news_status === "ok" ? (row.news || []).map((item) => item.title).slice(0, 2).join(" | ") : "news unavailable",
      (row.reasons || []).join("; ")
    ]);
  }

  function exposureRows() {
    const groups = groupBySymbol(state.data);
    const selected = state.analysis.metrics.slice(0, 12);
    return selected.map((metric) => {
      const corr = selected
        .filter((other) => other.symbol !== metric.symbol)
        .map((other) => correlation(returnsFor(groups.get(metric.symbol) || [], 60), returnsFor(groups.get(other.symbol) || [], 60)));
      return [metric.symbol, metric.sector, formatPct(metric.vol20), formatNumber(mean(corr), 2), formatPct(metric.drawdown)];
    });
  }

  function modelRegistryRows() {
    const replay = replaySummary();
    const best = replay.slice().sort((a, b) => b.expectancy - a.expectancy)[0];
    return [
      ["Model version", MODEL_VERSION],
      ["Feature set", "price-volume-regime-v2"],
      ["Model pack", modelPackLabel(selectedSetup())],
      ["AI research", state.researchSnapshot ? `${RESEARCH_VERSION} / ${Math.round(researchAgeMinutes())}m old` : "not refreshed"],
      ["OpenAI API", state.openAiEnabled ? state.openAiModel : "off"],
      ["Universe", state.universe.join(", ")],
      ["Replay samples", replay.reduce((sum, row) => sum + row.count, 0)],
      ["Best replay style", best ? STYLE_LABELS[best.style] : "-"],
      ["Live orders armed", state.liveOrdersEnabled ? "Yes" : "No"]
    ];
  }

  function sectorRows() {
    const setupsBySymbol = new Map();
    state.analysis.setups.forEach((setup) => setupsBySymbol.set(setup.symbol, [...(setupsBySymbol.get(setup.symbol) || []), setup]));
    const sectors = new Map();
    state.analysis.metrics.forEach((metric) => {
      const row = sectors.get(metric.sector) || { sector: metric.sector, metrics: [], ready: 0 };
      row.metrics.push(metric);
      if ((setupsBySymbol.get(metric.symbol) || []).some((setup) => setup.status !== "REJECT")) row.ready += 1;
      sectors.set(metric.sector, row);
    });
    return [...sectors.values()].map((row) => {
      const best = row.metrics.slice().sort((a, b) => b.score - a.score)[0];
      return [
        row.sector,
        row.metrics.map((metric) => metric.symbol).join(", "),
        row.ready,
        best ? best.symbol : "-",
        formatNumber(mean(row.metrics.map((metric) => metric.score)), 0),
        formatPct(mean(row.metrics.map((metric) => metric.expected20))),
        formatPct(mean(row.metrics.map((metric) => metric.vol20))),
        formatPct(mean(row.metrics.map((metric) => metric.drawdown)))
      ];
    }).sort((a, b) => Number(b[4]) - Number(a[4]));
  }

  async function runAutoScout() {
    const killReasons = killSwitchReasons();
    if (!state.autoScout || killReasons.length) {
      if (state.autoScout && killReasons.length) state.journal.unshift(journalLine(`Auto Scout blocked: ${killReasons[0]}`, "Kill"));
      return;
    }
    const setup = bestReadySetup();
    if (!setup) return;
    if (state.mode === "FULL_AUTO") {
      const reasons = fullAutoReasons(setup);
      if (reasons.length) {
        state.journal.unshift(journalLine(`Full auto blocked: ${reasons[0]}`, "Auto"));
        return;
      }
      if (state.autoScoutSeen.has(setup.id)) return;
      state.autoScoutSeen.add(setup.id);
      await submitLiveOrderFor(setup, "Full Auto", true);
      return;
    }
    if (state.autoScoutSeen.has(setup.id)) return;
    state.autoScoutSeen.add(setup.id);
    if (state.mode === "PAPER") {
      submitPaperOrderFor(setup, "Auto Scout");
    } else if (state.mode === "LIVE_WITH_CONFIRM" && ACCOUNT.ibkrMode === "LIVE_CONFIRM" && ibkrReadiness(setup).ok) {
      state.journal.unshift(journalLine(`Auto Scout queued live approval: ${setup.symbol} ${setup.label}`, "Scout"));
    } else {
      state.journal.unshift(journalLine(`Best setup: ${setup.symbol} ${setup.label}, ${setup.status}, score ${formatNumber(setup.setupScore, 0)}`, "Scout"));
    }
  }

  function renderWatchlist() {
    const body = document.getElementById("watchlist-body");
    body.innerHTML = state.analysis.metrics.map((metric) => `
      <tr class="${metric.symbol === state.selectedSymbol ? "is-selected" : ""}" data-symbol="${metric.symbol}">
        <td><strong>${metric.symbol}</strong></td>
        <td>${formatMoney(metric.price)}</td>
        <td class="${metric.ret20 >= 0 ? "positive" : "negative"}">${formatPct(metric.ret20)}</td>
        <td>${formatNumber(metric.score, 0)}</td>
      </tr>
    `).join("");
    body.querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => selectSymbol(row.dataset.symbol)));
  }

  function renderRankings() {
    const query = (document.getElementById("symbol-search")?.value || "").trim().toUpperCase();
    const body = document.getElementById("rankings-body");
    if (!body) return;
    body.innerHTML = state.analysis.metrics
      .filter((metric) => !query || metric.symbol.includes(query))
      .map((metric) => {
        const setup = bestSetupFor(metric.symbol);
        return `
          <tr class="${metric.symbol === state.selectedSymbol ? "is-selected" : ""}" data-symbol="${metric.symbol}">
            <td><strong>${metric.symbol}</strong></td>
            <td>${formatMoney(metric.price)}</td>
            <td class="${metric.ret1 >= 0 ? "positive" : "negative"}">${formatPct(metric.ret1)}</td>
            <td class="${metric.ret5 >= 0 ? "positive" : "negative"}">${formatPct(metric.ret5)}</td>
            <td class="${metric.ret20 >= 0 ? "positive" : "negative"}">${formatPct(metric.ret20)}</td>
            <td>${formatPct(metric.vol20)}</td>
            <td>${formatNumber(metric.trend * 100, 0)}</td>
            <td>${compactMoney(metric.liquidity)}</td>
            <td><span class="mini-badge ${setup.status.toLowerCase()}">${setup.status} ${setup.label}</span></td>
          </tr>
        `;
      }).join("");
    body.querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => selectSymbol(row.dataset.symbol)));
  }

  function compactMoney(value) {
    if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    return formatMoney(value);
  }

  function renderSetupList() {
    const list = document.getElementById("setup-list");
    const setups = state.analysis.setups
      .filter((setup) => state.selectedStyle === "ALL" || setup.style === state.selectedStyle)
      .slice(0, 12);
    list.innerHTML = setups.map((setup) => `
      <article class="setup-card ${setup.id === state.selectedSetupId ? "is-selected" : ""}" data-id="${setup.id}" data-symbol="${setup.symbol}">
        <div class="setup-card-top">
          <div>
            <h3>${setup.symbol}</h3>
            <small>${setup.label} / ${setup.side}</small>
          </div>
          <span class="mini-badge ${setup.status.toLowerCase()}">${setup.status}</span>
        </div>
        <div class="setup-stats">
          <span><b>${formatNumber(setup.setupScore, 0)}</b> score</span>
          <span><b>${formatPct(setup.probability, 0)}</b> prob</span>
          <span><b>${formatMoney(setup.fees.roundTrip)}</b> fees</span>
          <span><b>${formatNumber(setup.rewardToRisk, 1)}R</b> R/R</span>
        </div>
        <div class="setup-meta">
          <span>Entry ${formatMoney(setup.entry)}</span>
          <span>Stop ${formatMoney(setup.stop)}</span>
          <span>Target ${formatMoney(setup.target)}</span>
          <span>Net ${formatPct(setup.netExpectedReturn)}</span>
        </div>
      </article>
    `).join("");
    list.querySelectorAll(".setup-card").forEach((card) => {
      card.addEventListener("click", () => {
        state.selectedSetupId = card.dataset.id;
        state.selectedSymbol = card.dataset.symbol;
        render();
      });
    });
  }

  function bestSetupFor(symbol) {
    return state.analysis.setups.find((setup) => setup.symbol === symbol && setup.status !== "REJECT")
      || state.analysis.setups.find((setup) => setup.symbol === symbol)
      || state.analysis.setups[0];
  }

  function renderTicket() {
    const setup = selectedSetup();
    if (!setup) {
      document.getElementById("ticket-status").textContent = "NO SETUP";
      document.getElementById("ticket-status").className = "status-badge reject";
      document.getElementById("ticket-body").innerHTML = `<div class="empty">No setup available. Add symbols to the universe, sync IBKR, or import CSV/history bars.</div>`;
      document.getElementById("paper-order").disabled = true;
      document.getElementById("queue-live").disabled = true;
      document.getElementById("copy-plan").disabled = true;
      document.getElementById("export-plan").disabled = true;
      return;
    }
    const readiness = ibkrReadiness(setup);
    const status = document.getElementById("ticket-status");
    status.textContent = readiness.status;
    status.className = `status-badge ${readiness.statusClass}`;
    document.getElementById("ibkr-readiness").textContent = readiness.status;
    document.getElementById("ibkr-readiness").className = `status-badge ${readiness.statusClass}`;
    const quoteText = state.ibkr.quotes[setup.symbol]
      ? `${formatMoney(state.ibkr.quotes[setup.symbol].last)} bid ${formatMoney(state.ibkr.quotes[setup.symbol].bid)} ask ${formatMoney(state.ibkr.quotes[setup.symbol].ask)}`
      : "not synced";
    document.getElementById("ticket-body").innerHTML = `
      <div class="ticket-hero">
        <div>
          <span>${setup.side} / ${setup.label}</span>
          <strong>${setup.symbol}</strong>
          <small>${setup.marketRegime} market / ${setup.status}</small>
        </div>
        <div class="ticket-entry">
          <span>Entry</span>
          <strong>${formatMoney(setup.entry)}</strong>
        </div>
      </div>
      <div class="ticket-section-title">Trade plan</div>
      <div class="ticket-quick">
        <span><b>${formatMoney(setup.stop)}</b> stop</span>
        <span><b>${formatMoney(setup.target)}</b> target</span>
        <span><b>${setup.shares}</b> shares</span>
        <span><b>${formatMoney(setup.fees.roundTrip)}</b> fees</span>
        <span><b>${formatNumber(setup.rewardToRisk, 1)}R</b> reward</span>
      </div>
      <div class="ticket-section-title">Economics</div>
      <div class="ticket-grid compact">
        ${kv("Position", formatMoney(setup.positionValue))}
        ${kv("Risk", `${formatMoney(setup.riskDollars)} (${formatPct(setup.accountRiskPct)})`)}
        ${kv("Reward/Risk", `${formatNumber(setup.rewardToRisk)}R`)}
        ${kv("Fees", `${formatMoney(setup.fees.roundTrip)} (${formatPct(setup.fees.dragPct)})`)}
        ${kv("Gross edge", formatPct(setup.expectedReturn))}
        ${kv("Net edge", formatPct(setup.netExpectedReturn))}
        ${kv("Probability", formatPct(setup.probability))}
        ${kv("Confidence", formatPct(setup.confidence))}
      </div>
      <div class="ticket-section-title">Execution readiness</div>
      <div class="ticket-grid compact">
        ${kv("Market", setup.marketRegime)}
        ${kv("Day trading", dayTradingAllowed() ? "eligible" : "blocked")}
        ${kv("IBKR mode", ACCOUNT.ibkrMode)}
        ${kv("Quote", quoteText)}
        ${kv("Readiness", readiness.reason)}
      </div>
      ${readiness.reasons.length ? `<div class="reason-list">${readiness.reasons.map((reason) => `<span>${reason}</span>`).join("")}</div>` : ""}
      <details class="ticket-details">
        <summary>Gate results</summary>
        <div class="gate-list">
          ${Object.entries(setup.gates).map(([name, value]) => `
            <div class="gate-row">
              <span>${labelize(name)}</span>
              <span class="mini-badge ${value}">${value.toUpperCase()}</span>
            </div>
          `).join("")}
        </div>
      </details>
      <details class="ticket-details">
        <summary>IBKR order plan</summary>
        <pre class="plan-block">${ibkrOrderPlan(setup)}</pre>
      </details>
    `;
    const canSubmit = readiness.ok && !state.paused;
    document.getElementById("paper-order").disabled = !canSubmit || state.mode === "ALERT_ONLY";
    document.getElementById("queue-live").disabled = !canSubmit || state.mode !== "LIVE_WITH_CONFIRM" || ACCOUNT.ibkrMode !== "LIVE_CONFIRM";
    document.getElementById("live-submit").disabled = !canSubmit || !state.liveOrdersEnabled || state.mode !== "LIVE_WITH_CONFIRM" || ACCOUNT.ibkrMode !== "LIVE_CONFIRM";
    document.getElementById("copy-plan").disabled = !setup;
    document.getElementById("export-plan").disabled = !setup;
  }

  function ibkrReadiness(setup) {
    if (!setup) return { ok: false, status: "NO SETUP", statusClass: "reject", reason: "no analyzed setup", reasons: ["no analyzed setup"] };
    const reasons = [];
    const liveIntent = state.mode === "LIVE_WITH_CONFIRM" || state.mode === "FULL_AUTO" || ACCOUNT.ibkrMode === "LIVE_CONFIRM";
    if (setup.style === "DAY_TRADE" && !dayTradingAllowed()) reasons.push(`day trading blocked: account not eligible or below ${formatMoney(ACCOUNT.dayTradingMinimum)}`);
    if (setup.status === "REJECT" && setup.rejectionReason !== "dayTrading") reasons.push(`setup gate rejected: ${setup.rejectionReason || "risk gate"}`);
    if (setup.shares < 1) reasons.push("position size is zero");
    if (setup.positionValue > ACCOUNT.buyingPower) reasons.push("not enough buying power");
    reasons.push(...dailyLimitReasons());
    if (state.paused) reasons.push("bot paused");
    if (state.mode === "FULL_AUTO" && !state.fullAutoEnabled) reasons.push("full auto server lock is off");
    if (liveIntent && !state.ibkr.connected) reasons.push("IBKR Gateway not connected/authenticated");
    if (liveIntent && !state.ibkr.accountId) reasons.push("no IBKR account selected");
    if (liveIntent && !state.ibkr.conids[setup.symbol]) reasons.push("IBKR contract ID not resolved");
    if (liveIntent) {
      const quoteReason = quoteFreshnessReason(setup.symbol);
      if (quoteReason) reasons.push(quoteReason);
      if (state.modelPack && modelPackAgeDays() > MODEL_PACK_MAX_AGE_DAYS) reasons.push("model pack stale");
      if (!researchForSymbol(setup.symbol) || researchAgeMinutes() > RESEARCH_MAX_AGE_MINUTES) reasons.push("AI research stale");
      const warmup = paperFirstReason(setup);
      if (warmup) reasons.push(warmup);
    }
    if (state.positions.some((position) => position.symbol === setup.symbol && Math.abs(position.quantity) > 0)) reasons.push("existing IBKR position in symbol");
    if (state.ibkrOpenOrders.some((order) => order.symbol === setup.symbol)) reasons.push("existing IBKR open order in symbol");
    if (setup.metric.spreadBps > ACCOUNT.maxSpreadBps) reasons.push("spread too wide");
    if (setup.metric.slippageBps > ACCOUNT.maxSlippageBps) reasons.push("slippage too high");
    if (setup.style !== "DAY_TRADE" && setup.marketRegime === "PANIC") reasons.push("market regime panic");

    if (reasons.length) {
      return { ok: false, status: "NOT READY", statusClass: "reject", reason: reasons[0], reasons };
    }
    if (setup.status === "REDUCE") {
      return { ok: true, status: "READY REDUCED", statusClass: "reduce", reason: "passes with reduced sizing", reasons: [] };
    }
    return { ok: true, status: "READY", statusClass: "pass", reason: "all IBKR checks pass", reasons: [] };
  }

  function ibkrOrderPlan(setup) {
    const action = setup.side === "LONG" ? "BUY" : "SELL";
    const exitAction = action === "BUY" ? "SELL" : "BUY";
    const tif = setup.style === "DAY_TRADE" ? "DAY" : "GTC";
    const conid = state.ibkr.conids[setup.symbol] || "unresolved";
    return [
      "IBKR manual bracket plan",
      `Account mode: ${ACCOUNT.ibkrMode}`,
      `Account: ${state.ibkr.accountId || "not selected"}`,
      `Conid: ${conid}`,
      `Parent: ${action} ${setup.shares} ${setup.symbol} STK SMART USD LMT ${formatNumber(setup.entry)}`,
      `Profit taker: ${exitAction} ${setup.shares} ${setup.symbol} LMT ${formatNumber(setup.target)}`,
      `Stop loss: ${exitAction} ${setup.shares} ${setup.symbol} STP ${formatNumber(setup.stop)}`,
      `TIF: ${tif}`,
      `Hold max: ${setup.maxHold} trading day(s)`,
      `Risk: ${formatMoney(setup.riskDollars)} / ${formatPct(setup.accountRiskPct)}`,
      `Estimated buy fee: ${formatMoney(setup.fees.buyFee)}`,
      `Estimated sell fee: ${formatMoney(setup.fees.sellFee)}`,
      `Estimated round-trip fees: ${formatMoney(setup.fees.roundTrip)} / ${formatPct(setup.fees.dragPct)} drag`,
      `Expected after fees: ${formatPct(setup.netExpectedReturn)}`,
      "Review inside TWS before transmitting."
    ].join("\n");
  }

  function orderPlanRows(setup) {
    const action = setup.side === "LONG" ? "BUY" : "SELL";
    const exitAction = action === "BUY" ? "SELL" : "BUY";
    const tif = setup.style === "DAY_TRADE" ? "DAY" : "GTC";
    return [
      ["role", "action", "symbol", "secType", "exchange", "currency", "orderType", "quantity", "limitPrice", "stopPrice", "estimatedFee", "timeInForce", "transmit", "notes"],
      ["parent_entry", action, setup.symbol, "STK", "SMART", "USD", "LMT", setup.shares, formatNumber(setup.entry), "", formatNumber(setup.fees.buyFee), tif, "false", "Review in TWS"],
      ["profit_target", exitAction, setup.symbol, "STK", "SMART", "USD", "LMT", setup.shares, formatNumber(setup.target), "", formatNumber(setup.fees.sellFee), tif, "false", "Attached exit"],
      ["stop_loss", exitAction, setup.symbol, "STK", "SMART", "USD", "STP", setup.shares, "", formatNumber(setup.stop), formatNumber(setup.fees.sellFee), tif, "false", "Attached exit"]
    ];
  }

  function ibkrLiveOrders(setup) {
    const conid = Number(state.ibkr.conids[setup.symbol]);
    const action = setup.side === "LONG" ? "BUY" : "SELL";
    const exitAction = action === "BUY" ? "SELL" : "BUY";
    const tif = setup.style === "DAY_TRADE" ? "DAY" : "GTC";
    const oid = `SPA-${setup.symbol}-${Date.now()}`;
    return [
      {
        conid,
        side: action,
        orderType: "LMT",
        price: Number(formatNumber(setup.entry)),
        quantity: setup.shares,
        tif,
        cOID: oid
      },
      {
        conid,
        side: exitAction,
        orderType: "LMT",
        price: Number(formatNumber(setup.target)),
        quantity: setup.shares,
        tif,
        parentId: oid,
        cOID: `${oid}-TP`
      },
      {
        conid,
        side: exitAction,
        orderType: "STP",
        auxPrice: Number(formatNumber(setup.stop)),
        quantity: setup.shares,
        tif,
        parentId: oid,
        cOID: `${oid}-SL`
      }
    ];
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function copyOrderPlan() {
    const setup = selectedSetup();
    const text = ibkrOrderPlan(setup);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => {
          state.journal.unshift(journalLine(`Copied IBKR plan for ${setup.symbol}`, "IBKR"));
          renderBlotter();
        })
        .catch(() => {
          state.journal.unshift(journalLine("Clipboard copy failed; use the visible ticket plan", "IBKR"));
          renderBlotter();
        });
    } else {
      state.journal.unshift(journalLine("Clipboard unavailable; use the visible ticket plan", "IBKR"));
      renderBlotter();
    }
  }

  function exportOrderPlan() {
    const setup = selectedSetup();
    const csv = orderPlanRows(setup).map((row) => row.map(csvEscape).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ibkr_trade_plan_${setup.symbol}_${setup.style}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    state.journal.unshift(journalLine(`Exported IBKR review CSV for ${setup.symbol}`, "IBKR"));
    renderBlotter();
  }

  function kv(label, value) {
    return `<div class="kv"><span>${label}</span><strong>${value}</strong></div>`;
  }

  function labelize(value) {
    return value.replace(/([A-Z])/g, " $1").replace(/^./, (char) => char.toUpperCase());
  }

  function renderRisk() {
    const approved = state.analysis.setups.filter((setup) => setup.status !== "REJECT");
    const openRisk = totalOpenRisk();
    document.getElementById("risk-panel").innerHTML = [
      kv("Approved setups", approved.length),
      kv("Open orders", state.orders.length),
      kv("IBKR positions", state.positions.length),
      kv("IBKR open orders", state.ibkrOpenOrders.length),
      kv("Worst stop risk", formatPct(ACCOUNT.equity ? openRisk / ACCOUNT.equity : 0)),
      kv("Buying power", formatMoney(ACCOUNT.buyingPower)),
      kv("Day P/L", formatMoney(ACCOUNT.dayPL)),
      kv("Max loss/day", formatMoney(dailyLossLimitDollars())),
      kv("Profit target/day", ACCOUNT.dailyProfitTargetDollars ? formatMoney(ACCOUNT.dailyProfitTargetDollars) : "Off"),
      kv("Max profit/day", ACCOUNT.dailyMaxProfitDollars ? formatMoney(ACCOUNT.dailyMaxProfitDollars) : "Off"),
      kv("Full auto", state.fullAutoEnabled ? `Armed ${state.autoTradeCount}/${ACCOUNT.maxAutoTradesPerDay}` : "Locked"),
      kv("Day trading", dayTradingAllowed() ? "Eligible" : `Blocked below ${formatMoney(ACCOUNT.dayTradingMinimum)}`),
      kv("Fee plan", ACCOUNT.commissionPlan === "IBKR_LITE" ? "IBKR Lite est." : `$${formatNumber(ACCOUNT.commissionPerShare, 3)} / share, ${formatMoney(ACCOUNT.minCommission)} min`),
      kv("Max position", formatPct(ACCOUNT.maxPositionWeight)),
      kv("Max spread", `${ACCOUNT.maxSpreadBps} bps`),
      kv("Regime score", formatPct(state.analysis.regime.score)),
      kv("Paused", state.paused ? "Yes" : "No")
    ].join("");
  }

  function totalOpenRisk() {
    return state.orders.reduce((sum, order) => sum + order.riskDollars, 0);
  }

  function renderBlotter() {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.tab === state.activeTab));
    const target = document.getElementById("blotter-content");
    if (state.activeTab === "orders") {
      target.innerHTML = state.orders.length ? table(["Time", "Symbol", "Style", "Shares", "Entry", "Fees", "Stop", "Status"], state.orders.map((order) => [
        order.time, order.symbol, order.label, order.shares, formatMoney(order.entry), formatMoney(order.fees?.roundTrip || 0), formatMoney(order.stop), order.status
      ])) : `<div class="empty">No open orders.</div>`;
    } else if (state.activeTab === "leaderboard") {
      const rows = state.analysis.setups.slice(0, 20).map((setup) => [
        setup.symbol,
        setup.label,
        setup.status,
        formatNumber(setup.setupScore, 0),
        formatPct(setup.probability, 0),
        formatPct(setup.expectedReturn),
        formatMoney(setup.fees.roundTrip),
        formatPct(setup.netExpectedReturn),
        ibkrReadiness(setup).reason
      ]);
      target.innerHTML = table(["Symbol", "Style", "Gate", "Score", "Prob", "Expected", "Fees", "Net", "Readiness"], rows);
    } else if (state.activeTab === "strategy") {
      const paper = state.researchAgent?.paper_evidence || {};
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Primary strategy</span><strong>low_vol_trend</strong></div>
          <div class="health-card"><span>Posture</span><strong>shadow only</strong></div>
          <div class="health-card"><span>Paper evidence</span><strong>${Number(paper.current_closed_trades || 0)} / 30 closed</strong></div>
          <div class="health-card"><span>Future challenger</span><strong>defensive / low beta</strong></div>
        </div>
        ${table(["Priority", "Strategy", "Status", "Rules", "Next valid evidence"], [
          ["A", "Low-volatility trend", "Rules frozen", "200D trend + 63D momentum + below-median 20D volatility", "Prospective shadow, then exact-plan paper evidence"],
          ["B", "Defensive / low beta", "Future challenger", "Separately registered experiment only", "Materially new point-in-time data"],
          ["Parked", "Other trend and mean-reversion variants", "Cooling down", "No nearby filters or threshold tuning", "A distinct predeclared hypothesis"]
        ])}
      `;
    } else if (state.activeTab === "evidence") {
      const evidence = researchEvidence(state.researchAgent);
      const development = evidence.plan.development || {};
      const validation = evidence.plan.development_validation || {};
      const shadowRows = Object.entries(evidence.shadowPlans).map(([planId, row]) => [
        planId.match(/@([0-9a-f]{12})/)?.[1] || "exact plan",
        row.closed_trades || 0,
        formatPct(row.expectancy),
        formatNumber(row.profit_factor),
        formatPct(row.positive_symbol_ratio),
        formatPct(row.max_drawdown)
      ]);
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Signal development</span><strong>${evidence.signalStatus}</strong></div>
          <div class="health-card"><span>Execution plan</span><strong>${evidence.executionStatus}</strong></div>
          <div class="health-card"><span>Holdout access</span><strong>${evidence.holdoutStatus}</strong></div>
          <div class="health-card"><span>Paper evidence</span><strong>${evidence.paperClosed} / 30 closes</strong></div>
          <div class="health-card"><span>Shadow observations</span><strong>${evidence.shadowClosed} closed / diagnostic only</strong></div>
          <div class="health-card"><span>Data source</span><strong>${evidence.source}${evidence.isDemo ? " / demo rejected" : " / real"}</strong></div>
          <div class="health-card"><span>Dataset fingerprint</span><strong>${evidence.datasetHash.slice(0, 12) || "unavailable"}</strong></div>
        </div>
        ${table(["Exact plan", "Trades", "Expectancy", "Profit factor", "Positive symbols", "Max drawdown"], [
          ["Development", development.trades || 0, formatPct(development.expectancy), formatNumber(development.profit_factor), formatPct(development.positive_symbol_ratio), formatPct(development.max_drawdown)],
          ["Internal validation", validation.trades || 0, formatPct(validation.expectancy), formatNumber(validation.profit_factor), formatPct(validation.positive_symbol_ratio), formatPct(validation.max_drawdown)]
        ])}
        ${shadowRows.length ? `<h3>Prospective shadow evidence</h3>${table(["Plan", "Closes", "Expectancy", "Profit factor", "Positive symbols", "Portfolio drawdown"], shadowRows)}` : ""}
        <div class="health-grid">
          <div class="health-card"><span>Validated common coverage</span><strong>${evidence.coverageLabel} / ${evidence.coverageStart} to ${evidence.coverageEnd}</strong></div>
          <div class="health-card"><span>${evidence.holdoutExposed ? "Exposed final holdout" : "Current protected window"}</span><strong>${evidence.holdout.start || "-"} to ${evidence.holdout.end || "-"} / ${evidence.holdout.rows || 0} rows</strong></div>
          <div class="health-card"><span>${evidence.holdoutExposed ? "Holdout ID" : "Window ID"}</span><strong>${evidence.holdout.id || "unavailable"}</strong></div>
          <div class="health-card"><span>Next valid action</span><strong>${evidence.nextAction}</strong></div>
        </div>
      `;
    } else if (state.activeTab === "sectors") {
      target.innerHTML = table(["Sector", "Symbols", "Ready", "Best", "Avg score", "Avg expected", "Avg vol", "Avg drawdown"], sectorRows());
    } else if (state.activeTab === "why") {
      const setup = selectedSetup();
      target.innerHTML = setup ? `
        <div class="health-grid">
          <div class="health-card"><span>Why this trade</span><strong>${setup.symbol} ${setup.label}</strong></div>
          <div class="health-card"><span>Edge</span><strong>${formatPct(setup.expectedReturn)}</strong></div>
          <div class="health-card"><span>Probability</span><strong>${formatPct(setup.probability, 0)}</strong></div>
          <div class="health-card"><span>Risk gate</span><strong>${setup.status}</strong></div>
        </div>
        ${table(["Gate", "Result"], Object.entries(setup.gates).map(([key, value]) => [labelize(key), value.toUpperCase()]))}
      ` : `<div class="empty">No selected setup.</div>`;
    } else if (state.activeTab === "performance") {
      const totalPnl = state.closedTrades.reduce((sum, trade) => sum + trade.pnl, 0);
      const byStyle = Object.keys(STYLE_CONFIG).map((style) => {
        const stats = strategyStats(style);
        return [STYLE_LABELS[style], stats.trades, formatPct(stats.winRate, 0), formatPct(stats.expectancy), formatNumber(stats.profitFactor)];
      });
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Closed trades</span><strong>${state.closedTrades.length}</strong></div>
          <div class="health-card"><span>Total tracked P/L</span><strong>${formatMoney(totalPnl)}</strong></div>
          <div class="health-card"><span>Open tracked</span><strong>${state.orders.length}</strong></div>
          <div class="health-card"><span>Kill switch</span><strong>${killSwitchReasons()[0] || "Clear"}</strong></div>
        </div>
        ${table(["Style", "Trades", "Win", "Expectancy", "Profit factor"], byStyle)}
      `;
    } else if (state.activeTab === "prediction") {
      target.innerHTML = predictionRows().length
        ? table(["Symbol", "Style", "Prob", "Expected", "Actual", "Error", "MFE", "MAE", "Hit"], predictionRows())
        : `<div class="empty">No closed trades yet. Prediction-vs-reality starts after paper/live-small trades close.</div>`;
    } else if (state.activeTab === "validator") {
      const validationRows = Object.keys(STYLE_CONFIG).map((style) => {
        const stats = strategyStats(style);
        return [STYLE_LABELS[style], strategyValidationStatus(style).toUpperCase(), stats.trades, formatPct(stats.expectancy), formatNumber(stats.profitFactor), formatPct(stats.winRate, 0)];
      });
      const calibrationRows = calibrationBuckets().map((bucket) => [bucket.label, bucket.count, formatPct(bucket.winRate, 0)]);
      target.innerHTML = `${table(["Style", "Validator", "Trades", "Expectancy", "Profit factor", "Win rate"], validationRows)}${table(["Probability bucket", "Trades", "Realized win"], calibrationRows)}`;
    } else if (state.activeTab === "learning") {
      const graph = learningGraph();
      target.innerHTML = state.closedTrades.length ? `
        <div class="health-grid">
          <div class="health-card"><span>Closed trades</span><strong>${state.closedTrades.length}</strong></div>
          <div class="health-card"><span>Nodes</span><strong>${graph.nodes.length}</strong></div>
          <div class="health-card"><span>Edges</span><strong>${graph.edges.length}</strong></div>
          <div class="health-card"><span>Current setup</span><strong>${selectedSetup()?.learning?.reason || "learning warmup"}</strong></div>
        </div>
        ${table(["Best node", "Trades", "Win", "Expectancy", "P/L"], learningGraphRows("nodes", "best"))}
        ${table(["Weak node", "Trades", "Win", "Expectancy", "P/L"], learningGraphRows("nodes", "worst"))}
        ${table(["Best edge", "Trades", "Win", "Expectancy", "P/L"], learningGraphRows("edges", "best"))}
        ${table(["Weak edge", "Trades", "Win", "Expectancy", "P/L"], learningGraphRows("edges", "worst"))}
      ` : `<div class="empty">Learning graph is warming up. Close paper/live trades first; then nodes and edges will start gating similar setups.</div>`;
    } else if (state.activeTab === "works") {
      target.innerHTML = table(["Style", "Trades", "Win", "Expectancy", "Profit factor"], whatWorksRows());
    } else if (state.activeTab === "fails") {
      target.innerHTML = table(["Style", "Trades", "Win", "Expectancy", "Profit factor", "Validator"], whatFailsRows());
    } else if (state.activeTab === "replay") {
      const rows = replaySummary().map((row) => [STYLE_LABELS[row.style], row.count, formatPct(row.winRate, 0), formatPct(row.expectancy), formatNumber(row.profitFactor)]);
      target.innerHTML = table(["Style", "Replay samples", "Win", "Expectancy", "Profit factor"], rows);
    } else if (state.activeTab === "protocol") {
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Universe</span><strong>${state.universe.length} objective liquid stocks</strong></div>
          <div class="health-card"><span>Minimum evidence</span><strong>30 closes / 5 symbols / 90 days</strong></div>
          <div class="health-card"><span>Acceptance</span><strong>60% positive symbols / PF 1.20+</strong></div>
          <div class="health-card"><span>Risk ceiling</span><strong>15% max drawdown</strong></div>
        </div>
        ${table(["Rule", "Policy"], [
          ["Strategy changes", "Changing an evidence-producing rule starts a new evidence lane"],
          ["Stock selection", "Exclude only for predeclared liquidity, spread, data, corporate-action, or broker constraints"],
          ["News", "Execution veto or size reduction only; never creates a trade signal"],
          ["Live use", "Blocked until the exact unchanged plan passes prospective paper validation"],
          ["Scaling", "Manual confirmation first; increase capital only after reconciled live evidence"]
        ])}
      `;
    } else if (state.activeTab === "attribution") {
      target.innerHTML = attributionRows().length
        ? table(["Symbol", "Style", "P/L", "Exit", "Attribution"], attributionRows())
        : `<div class="empty">No closed trades yet. Paper trade first; the system will attribute outcomes as they close.</div>`;
    } else if (state.activeTab === "model") {
      target.innerHTML = `${table(["Item", "Value"], modelRegistryRows())}${table(["Feature", "Correlation to future return"], featureImportance().map(([name, value]) => [name, formatNumber(value, 3)]))}`;
    } else if (state.activeTab === "research") {
      target.innerHTML = researchRows().length
        ? table(["Symbol", "Action", "Price", "SMA50", "SMA200", "RSI14", "Rel 20D", "News", "Reasons"], researchRows())
        : `<div class="empty">No AI research snapshot yet.</div>`;
    } else if (state.activeTab === "exposure") {
      target.innerHTML = `${table(["Symbol", "Sector", "Volatility", "Avg corr", "Drawdown"], exposureRows())}${table(["Symbol", "Last", "Bid", "Ask", "Spread", "Quote time", "Age"], quoteQualityRows())}${table(["Symbol", "Style", "Expected fill", "Actual fill", "Slippage"], slippageRows())}`;
    } else if (state.activeTab === "ibkr") {
      const setup = selectedSetup();
      const readiness = ibkrReadiness(setup);
      const diagHtml = ibkrDiagnosticsHtml();
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Readiness</span><strong>${readiness.status}</strong></div>
          <div class="health-card"><span>Gateway</span><strong>${state.ibkr.status}</strong></div>
          <div class="health-card"><span>Account</span><strong>${state.ibkr.accountId || "-"}</strong></div>
          <div class="health-card"><span>Conid</span><strong>${setup ? state.ibkr.conids[setup.symbol] || "-" : "-"}</strong></div>
          <div class="health-card"><span>IBKR quotes</span><strong>${Object.keys(state.ibkr.quotes).length}</strong></div>
          <div class="health-card"><span>Imported positions</span><strong>${state.positions.length}</strong></div>
          <div class="health-card"><span>Open orders</span><strong>${state.ibkrOpenOrders.length}</strong></div>
          <div class="health-card"><span>Last sync</span><strong>${state.ibkr.lastSync || "-"}</strong></div>
          <div class="health-card"><span>Error</span><strong>${state.ibkr.error || "None"}</strong></div>
        </div>
        ${diagHtml}
        ${readiness.reasons.length ? table(["Blocking reason"], readiness.reasons.map((reason) => [reason])) : `<div class="empty">Selected setup is ready for manual IBKR review.</div>`}
      `;
    } else if (state.activeTab === "health") {
      const rejected = state.analysis.setups.filter((setup) => setup.status === "REJECT").length;
      target.innerHTML = `
        <div class="health-grid">
          <div class="health-card"><span>Data rows</span><strong>${state.data.length}</strong></div>
          <div class="health-card"><span>Latest date</span><strong>${state.analysis.latestDate}</strong></div>
          <div class="health-card"><span>Rejected setups</span><strong>${rejected}</strong></div>
          <div class="health-card"><span>Model state</span><strong>Heuristic MVP</strong></div>
          <div class="health-card"><span>Live orders</span><strong>${state.liveOrdersEnabled ? "Armed" : "Disabled"}</strong></div>
          <div class="health-card"><span>Full auto</span><strong>${state.fullAutoEnabled ? `Armed ${state.autoTradeCount}/${ACCOUNT.maxAutoTradesPerDay}` : "Locked"}</strong></div>
          <div class="health-card"><span>State store</span><strong>${state.serverStore ? "Server" : "Browser"}</strong></div>
          <div class="health-card"><span>Audit events</span><strong>${state.auditCount}</strong></div>
          <div class="health-card"><span>Broker trades</span><strong>${state.ibkrTrades.length}</strong></div>
          <div class="health-card"><span>Last save</span><strong>${state.lastStateSave || "-"}</strong></div>
          <div class="health-card"><span>Kill switch</span><strong>${killSwitchReasons()[0] || "Clear"}</strong></div>
          <div class="health-card"><span>Event blocks</span><strong>${state.eventBlocklist.length}</strong></div>
          <div class="health-card"><span>Calibration buckets</span><strong>${calibrationBuckets().filter((bucket) => bucket.count).length}</strong></div>
          <div class="health-card"><span>Live warmup</span><strong>${ACCOUNT.minPaperTradesForLive} closed/style</strong></div>
          <div class="health-card"><span>Graph boost min</span><strong>${ACCOUNT.minGraphTradesToBoost} matches</strong></div>
          <div class="health-card"><span>Graph reject min</span><strong>${ACCOUNT.minGraphTradesToReject} matches</strong></div>
        </div>
      `;
    } else {
      target.innerHTML = table(["Time", "Type", "Message"], state.journal.map((item) => [item.time, item.type, item.message]));
    }
  }

  function table(headers, rows) {
    return `
      <div class="analysis-table-wrap">
        <table>
          <thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
          <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>
    `;
  }

  function selectSymbol(symbol) {
    state.selectedSymbol = symbol;
    state.selectedSetupId = bestSetupForSymbol(symbol)?.id || "";
    render();
  }

  function submitPaperOrder() {
    const setup = selectedSetup();
    submitPaperOrderFor(setup, "Manual");
  }

  function submitPaperOrderFor(setup, source) {
    const readiness = setup ? ibkrReadiness(setup) : { ok: false };
    if (!setup || !readiness.ok || state.mode === "ALERT_ONLY") return;
    const order = {
      id: `PAPER-${Date.now()}`,
      time: new Date().toLocaleTimeString(),
      createdAtMs: Date.now(),
      status: "paper_submitted",
      source,
      entryDate: setup.metric?.last?.date || state.analysis.latestDate,
      fillPrice: setup.entry,
      plannedSlippageBps: setup.metric.slippageBps,
      modelVersion: MODEL_VERSION,
      ...setup,
      features: tradeFeatures(setup),
      learningNodes: setupLearningNodes(setup)
    };
    state.orders.unshift(order);
    state.journal.unshift(journalLine(`${source} paper order submitted for ${setup.symbol} ${setup.label}`, "Order"));
    saveState();
    render();
  }

  function queueLiveOrder() {
    const setup = selectedSetup();
    const readiness = setup ? ibkrReadiness(setup) : { ok: false };
    if (!setup || !readiness.ok || state.mode !== "LIVE_WITH_CONFIRM" || ACCOUNT.ibkrMode !== "LIVE_CONFIRM") return;
    state.journal.unshift(journalLine(`Live approval queued for ${setup.symbol}; no order submitted`, "Approval"));
    saveState();
    render();
  }

  async function submitLiveOrder() {
    const setup = selectedSetup();
    if (!setup) return;
    const typed = document.getElementById("live-confirm-text").value.trim().toUpperCase();
    if (typed !== `LIVE ${setup.symbol}`) {
      state.journal.unshift(journalLine(`Live submit blocked: type LIVE ${setup.symbol}`, "Live"));
      return renderBlotter();
    }
    return submitLiveOrderFor(setup, "Live", false);
  }

  async function submitLiveOrderFor(setup, source, auto) {
    const readiness = setup ? ibkrReadiness(setup) : { ok: false };
    if (!setup || !readiness.ok) return;
    if (!state.liveOrdersEnabled) {
      state.journal.unshift(journalLine("Live submit blocked: restart server with ENABLE_LIVE_ORDERS=1", source));
      return renderBlotter();
    }
    if (auto) {
      const autoReasons = fullAutoReasons(setup);
      if (autoReasons.length) {
        state.journal.unshift(journalLine(`Full auto blocked: ${autoReasons[0]}`, "Auto"));
        return renderBlotter();
      }
      state.autoOrderInFlight = true;
    }
    try {
      const orders = ibkrLiveOrders(setup);
      const candidate = researchAgentCandidate(setup.symbol, setup.style);
      const result = await apiPost("/api/ibkr/live-order", {
        accountId: state.ibkr.accountId,
        setupId: setup.id,
        symbol: setup.symbol,
        style: setup.style,
        planId: candidate?.plan_id || "",
        orders,
        auto,
        confirmation: auto ? "" : `LIVE ${setup.symbol}`
      });
      state.orders.unshift({
        id: `${auto ? "AUTO" : "LIVE"}-${Date.now()}`,
        time: new Date().toLocaleTimeString(),
        createdAtMs: Date.now(),
        status: auto ? "auto_live_submitted" : "live_submitted",
        source,
        entryDate: setup.metric?.last?.date || state.analysis.latestDate,
        brokerResponse: result,
        brokerClientOrderId: orders[0]?.cOID || "",
        brokerExitIds: orders.slice(1).map((order) => order.cOID).filter(Boolean),
        fillPrice: setup.entry,
        plannedSlippageBps: setup.metric.slippageBps,
        modelVersion: MODEL_VERSION,
        ...setup,
        features: tradeFeatures(setup),
        learningNodes: setupLearningNodes(setup)
      });
      if (auto) {
        resetAutoTradeCountIfNeeded();
        state.autoTradeCount += 1;
      }
      state.journal.unshift(journalLine(`${auto ? "FULL AUTO" : "LIVE"} order submitted to IBKR for ${setup.symbol}; verify status in IBKR`, source));
      saveState();
      render();
    } catch (error) {
      state.journal.unshift(journalLine(`Live submit failed: ${error.message}`, source));
      renderBlotter();
    } finally {
      if (auto) state.autoOrderInFlight = false;
    }
  }

  function rejectSetup() {
    const setup = selectedSetup();
    if (!setup) return;
    state.journal.unshift(journalLine(`Setup rejected manually: ${setup.symbol} ${setup.label}`, "Setup"));
    saveState();
    renderBlotter();
  }

  function journalLine(message, type) {
    const item = { time: new Date().toLocaleTimeString(), type, message };
    if (typeof fetch !== "undefined") {
      fetch(`${API_BASE}/api/audit`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type, message, source: "dashboard" })
      }).catch(() => {});
    }
    return item;
  }

  function importCsv(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const rows = parseCsv(String(reader.result || ""));
      if (!rows.length) {
        state.journal.unshift(journalLine("CSV import failed: expected symbol,date,open,high,low,close,volume", "Data"));
      } else {
        state.data = rows;
        refreshLocalResearch();
        state.analysis = analyze(rows, state.universe);
        selectBotPick();
        state.journal.unshift(journalLine(`Imported ${rows.length} rows from CSV`, "Data"));
      }
      render();
    };
    reader.readAsText(file);
  }

  async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  async function apiPost(path, body) {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
    return data;
  }

  function ibkrPayload(result) {
    return result && Object.prototype.hasOwnProperty.call(result, "data") ? result.data : result;
  }

  function ibkrErrorMessage(result, label = "IBKR request") {
    const data = ibkrPayload(result);
    const detail = result?.error || data?.error || data?.message || (typeof data === "string" ? data : "");
    const status = Number(result?.status || 0);
    return `${label} failed${status ? ` (${status})` : ""}${detail ? `: ${detail}` : ""}`;
  }

  function assertIbkrOk(result, label) {
    if (!result?.ok) throw new Error(ibkrErrorMessage(result, label));
    return result;
  }

  function ibkrStatusConnected(data) {
    return Boolean(data?.authenticated === true && data?.connected === true && data?.competing !== true);
  }

  async function refreshIbkrDiagnostics(fallback = "") {
    try {
      state.ibkr.diagnostics = await apiGet("/api/ibkr/diagnostics");
      state.ibkr.error = state.ibkr.diagnostics.summary || fallback;
    } catch (error) {
      state.ibkr.error = fallback || error.message;
    }
  }

  async function syncIbkr() {
    try {
      state.ibkr.status = "Syncing";
      state.ibkr.error = "";
      render();
      const health = await apiGet("/api/health");
      state.liveOrdersEnabled = Boolean(health.liveOrdersEnabled);
      state.fullAutoEnabled = Boolean(health.fullAutoEnabled);
      const status = await apiGet("/api/ibkr/status");
      if (!status.ok) {
        await refreshIbkrDiagnostics(ibkrErrorMessage(status, "IBKR auth status"));
        throw new Error(state.ibkr.error);
      }
      const statusData = ibkrPayload(status) || {};
      state.ibkr.connected = ibkrStatusConnected(statusData);
      state.ibkr.status = state.ibkr.connected ? "Connected" : "Needs login";
      if (!state.ibkr.connected) {
        await refreshIbkrDiagnostics("Client Portal Gateway needs login");
        throw new Error(state.ibkr.error);
      }
      state.ibkr.diagnostics = null;

      const accounts = assertIbkrOk(await apiGet("/api/ibkr/accounts"), "IBKR accounts");
      state.ibkr.accounts = Array.isArray(ibkrPayload(accounts)) ? ibkrPayload(accounts) : [];
      if (!state.ibkr.accountId && state.ibkr.accounts[0]) {
        state.ibkr.accountId = accountIdOf(state.ibkr.accounts[0]);
      }

      if (state.ibkr.accountId) {
        const positions = assertIbkrOk(await apiGet(`/api/ibkr/positions?accountId=${encodeURIComponent(state.ibkr.accountId)}`), "IBKR positions");
        state.positions = normalizeIbkrPositions(ibkrPayload(positions));
      }

      const orders = assertIbkrOk(await apiGet(`/api/ibkr/orders${state.ibkr.accountId ? `?accountId=${encodeURIComponent(state.ibkr.accountId)}` : ""}`), "IBKR open orders");
      state.ibkrOpenOrders = normalizeIbkrOrders(ibkrPayload(orders));
      const trades = assertIbkrOk(await apiGet("/api/ibkr/trades"), "IBKR trades");
      state.ibkrTrades = normalizeIbkrTrades(ibkrPayload(trades));
      reconcileIbkrTrades();
      await resolveUniverseConids();
      await applyIbkrSnapshots();
      state.ibkr.lastSync = new Date().toLocaleTimeString();
      state.journal.unshift(journalLine(`IBKR synced: ${state.positions.length} positions, ${state.ibkrOpenOrders.length} open orders, ${state.ibkrTrades.length} trades`, "IBKR"));
    } catch (error) {
      state.ibkr.connected = false;
      state.ibkr.status = "Offline";
      state.ibkr.error = error.message;
      state.journal.unshift(journalLine(`IBKR sync failed: ${error.message}`, "IBKR"));
    }
    render();
  }

  function accountIdOf(account) {
    return account.id || account.accountId || account.accountID || account.acctId || account.account || "";
  }

  function symbolFromIbkr(row) {
    const raw = row.symbol || row.ticker || row.contractDesc || row.localSymbol || row.description || row.conidex || "";
    return String(raw).split(" ")[0].trim().toUpperCase();
  }

  function normalizeIbkrPositions(payload) {
    const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.positions) ? payload.positions : [];
    return rows.map((row) => ({
      symbol: symbolFromIbkr(row),
      quantity: Number(row.position || row.quantity || row.qty || 0),
      marketValue: Number(row.mktValue || row.marketValue || row.market_value || 0),
      averageCost: Number(row.avgCost || row.averageCost || row.average_cost || 0),
      conid: row.conid || row.contractId || ""
    })).filter((row) => row.symbol);
  }

  function normalizeIbkrOrders(payload) {
    const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.orders) ? payload.orders : [];
    return rows.map((row) => ({
      symbol: symbolFromIbkr(row),
      action: String(row.side || row.action || "").toUpperCase(),
      quantity: Number(row.totalSize || row.quantity || row.qty || 0),
      status: String(row.status || row.orderStatus || "OPEN"),
      conid: row.conid || row.contractId || ""
    })).filter((row) => row.symbol);
  }

  function asTimeMs(value) {
    if (!value) return 0;
    if (Number.isFinite(Number(value))) return Number(value);
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function normalizeSide(value) {
    const side = String(value || "").toUpperCase();
    if (side === "BOT" || side === "B") return "BUY";
    if (side === "SLD" || side === "S") return "SELL";
    return side;
  }

  function normalizeIbkrTrades(payload) {
    const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.trades) ? payload.trades : Array.isArray(payload?.data) ? payload.data : [];
    return rows.map((row) => ({
      symbol: symbolFromIbkr(row),
      side: normalizeSide(row.side || row.action || row.buysell || row.transactionType),
      quantity: Number(row.quantity || row.size || row.qty || 0),
      price: Number(row.price || row.execution_price || row.tradePrice || row.avgPrice || 0),
      time: row.time || row.dateTime || row.execution_time || new Date().toISOString(),
      timeMs: asTimeMs(row.lastExecutionTime_r || row.time_r || row.time || row.dateTime || row.execution_time),
      orderId: String(row.orderId || row.order_id || ""),
      clientOrderId: String(row.cOID || row.order_ref || row.orderRef || row.order_reference || "")
    })).filter((row) => row.symbol && row.price > 0);
  }

  function tradeMatchesOrder(trade, order) {
    if (trade.symbol !== order.symbol) return false;
    const refs = [order.brokerClientOrderId, ...(order.brokerExitIds || [])].filter(Boolean).map(String);
    const tradeRefs = [trade.clientOrderId, trade.orderId].filter(Boolean).map(String);
    if (refs.length && tradeRefs.length) return tradeRefs.some((ref) => refs.includes(ref));
    const created = Number(order.createdAtMs || 0);
    return created > 0 && trade.timeMs > 0 && trade.timeMs >= created - 60000;
  }

  function reconcileIbkrTrades() {
    let changed = false;
    for (const order of state.orders) {
      if (!String(order.status || "").startsWith("live_")) continue;
      const fills = state.ibkrTrades.filter((trade) => tradeMatchesOrder(trade, order));
      if (!fills.length) continue;
      const entryFill = fills.find((trade) => trade.side === "BUY") || fills[0];
      if (entryFill && !order.brokerFillSeen) {
        order.fillPrice = entryFill.price;
        order.brokerFillSeen = true;
        order.status = order.status === "live_submitted" ? "live_filled_or_working" : order.status;
        state.journal.unshift(journalLine(`IBKR fill matched for ${order.symbol} at ${formatMoney(entryFill.price)}`, "IBKR"));
        changed = true;
      }
      const exitFill = fills.find((trade) => trade.side === "SELL" && Math.abs(trade.price - order.fillPrice) > 0.0001);
      if (exitFill) {
        closeTrackedTrade(order, exitFill.price, "ibkr_fill");
        order._closedByIbkr = true;
        changed = true;
      }
    }
    if (changed) {
      state.orders = state.orders.filter((order) => !order._closedByIbkr);
      saveState();
    }
  }

  async function resolveUniverseConids() {
    const symbols = requiredSymbols().slice(0, 40);
    for (const symbol of symbols) {
      if (state.ibkr.conids[symbol]) continue;
      try {
        const result = assertIbkrOk(await apiGet(`/api/ibkr/search?symbol=${encodeURIComponent(symbol)}`), `IBKR ${symbol} lookup`);
        const rows = ibkrPayload(result);
        const match = Array.isArray(rows) ? rows.find((row) => String(row.symbol || row.ticker || "").toUpperCase() === symbol) || rows[0] : null;
        const conid = match && (match.conid || match.conId);
        if (conid) state.ibkr.conids[symbol] = conid;
      } catch {
        // ponytail: conid lookup is advisory; readiness still blocks live auto-trading elsewhere.
      }
    }
  }

  async function applyIbkrSnapshots() {
    const pairs = Object.entries(state.ibkr.conids);
    if (!pairs.length) return;
    const conids = pairs.map(([, conid]) => conid).join(",");
    const result = await apiGet(`/api/ibkr/snapshot?conids=${encodeURIComponent(conids)}`);
    if (!result.ok) {
      state.journal.unshift(journalLine(ibkrErrorMessage(result, "IBKR snapshot"), "IBKR"));
      return;
    }
    const rows = ibkrPayload(result);
    if (!Array.isArray(rows)) return;
    const byConid = Object.fromEntries(pairs.map(([symbol, conid]) => [String(conid), symbol]));
    const groups = groupBySymbol(state.data);
    rows.forEach((quote) => {
      const conid = String(quote.conid || quote.conidEx || quote._conid || "");
      const symbol = String(quote[55] || quote.symbol || byConid[conid] || "").toUpperCase();
      const last = Number(quote[31] || quote.last || quote.lastPrice);
      const bid = Number(quote[84] || quote.bid);
      const ask = Number(quote[86] || quote.ask);
      if (!symbol || !Number.isFinite(last) || last <= 0) return;
      state.ibkr.quotes[symbol] = { last, bid, ask, conid, time: new Date().toLocaleTimeString(), timeMs: Date.now() };
      const symbolRows = groups.get(symbol);
      if (!symbolRows?.length) return;
      const latest = symbolRows[symbolRows.length - 1];
      latest.close = last;
      latest.adjustedClose = last;
      latest.high = Math.max(latest.high, last, ask || last);
      latest.low = Math.min(latest.low, last, bid || last);
    });
    state.data = [...groups.values()].flat();
    refreshLocalResearch();
    state.analysis = analyze(state.data, state.universe);
    selectBotPick();
  }

  function normalizeHistoryBars(symbol, payload) {
    const data = Array.isArray(payload) ? payload : Array.isArray(payload?.data) ? payload.data : [];
    return data.map((bar) => {
      const time = bar.t || bar.time || bar.date;
      const date = typeof time === "number" ? new Date(time).toISOString().slice(0, 10) : String(time || "").slice(0, 10);
      const close = Number(bar.c ?? bar.close);
      const open = Number(bar.o ?? bar.open ?? close);
      const high = Number(bar.h ?? bar.high ?? Math.max(open, close));
      const low = Number(bar.l ?? bar.low ?? Math.min(open, close));
      const volume = Number(bar.v ?? bar.volume ?? 0);
      return { symbol, date, open, high, low, close, adjustedClose: close, volume, sector: existingSector(symbol) };
    }).filter((row) => row.date && row.close > 0);
  }

  function existingSector(symbol) {
    const row = state.data.find((item) => item.symbol === symbol);
    return row?.sector || sectorForSymbol(symbol, "IBKR");
  }

  async function fetchIbkrHistoryForUniverse() {
    try {
      state.journal.unshift(journalLine("Fetching IBKR daily bars for universe", "IBKR"));
      await resolveUniverseConids();
      const groups = groupBySymbol(state.data);
      let imported = 0;
      for (const symbol of state.universe) {
        const conid = state.ibkr.conids[symbol];
        if (!conid) continue;
        const result = assertIbkrOk(await apiGet(`/api/ibkr/history?conid=${encodeURIComponent(conid)}&period=1y&bar=1d`), `IBKR ${symbol} history`);
        const bars = normalizeHistoryBars(symbol, ibkrPayload(result));
        if (bars.length) {
          groups.set(symbol, bars);
          imported += bars.length;
        }
      }
      state.data = [...groups.values()].flat();
      refreshLocalResearch();
      state.analysis = analyze(state.data, state.universe);
      selectBotPick();
      state.journal.unshift(journalLine(`Fetched ${imported} IBKR historical bars`, "IBKR"));
    } catch (error) {
      state.journal.unshift(journalLine(`IBKR history fetch failed: ${error.message}`, "IBKR"));
    }
    render();
  }

  function updateAccountInputs() {
    ACCOUNT.equity = Math.max(0, Number(document.getElementById("account-equity-input").value) || ACCOUNT.equity);
    ACCOUNT.buyingPower = Math.max(0, Number(document.getElementById("buying-power-input").value) || 0);
    ACCOUNT.dayPL = Number(document.getElementById("day-pl-input").value) || 0;
    ACCOUNT.dailyMaxLossDollars = Math.max(0, Number(document.getElementById("daily-max-loss-input").value) || 0);
    ACCOUNT.dailyProfitTargetDollars = Math.max(0, Number(document.getElementById("daily-profit-target-input").value) || 0);
    ACCOUNT.dailyMaxProfitDollars = Math.max(0, Number(document.getElementById("daily-max-profit-input").value) || 0);
    ACCOUNT.maxAutoTradesPerDay = Math.max(0, Number(document.getElementById("max-auto-trades-input").value) || 0);
    ACCOUNT.dayTradingEligible = document.getElementById("day-trade-eligible").value === "YES";
    ACCOUNT.dayTradingMinimum = Math.max(0, Number(document.getElementById("day-trade-min-input").value) || ACCOUNT.dayTradingMinimum);
    ACCOUNT.commissionPlan = document.getElementById("commission-plan").value;
    ACCOUNT.commissionPerShare = Math.max(0, Number(document.getElementById("commission-per-share-input").value) || 0);
    ACCOUNT.minCommission = Math.max(0, Number(document.getElementById("min-commission-input").value) || 0);
    ACCOUNT.ibkrMode = document.getElementById("ibkr-mode").value;
    state.journal.unshift(journalLine("Updated IBKR account inputs", "IBKR"));
    state.analysis = analyze(state.data, state.universe);
    selectBotPick();
    saveState();
    render();
  }

  function importPositions(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const rows = parseGenericCsv(String(reader.result || ""));
      state.positions = rows.map((row) => ({
        symbol: String(row.symbol || row.ticker || row.underlying || "").trim().toUpperCase(),
        quantity: Number(row.quantity || row.position || row.qty || 0),
        marketValue: Number(row.market_value || row.marketvalue || row.value || 0),
        averageCost: Number(row.average_cost || row.avg_cost || row.avgcost || 0)
      })).filter((row) => row.symbol);
      state.journal.unshift(journalLine(`Imported ${state.positions.length} IBKR position rows`, "IBKR"));
      render();
    };
    reader.readAsText(file);
  }

  function importOpenOrders(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const rows = parseGenericCsv(String(reader.result || ""));
      state.ibkrOpenOrders = rows.map((row) => ({
        symbol: String(row.symbol || row.ticker || row.underlying || "").trim().toUpperCase(),
        action: String(row.action || row.side || "").trim().toUpperCase(),
        quantity: Number(row.quantity || row.qty || 0),
        status: String(row.status || row.order_status || "OPEN").trim()
      })).filter((row) => row.symbol);
      state.journal.unshift(journalLine(`Imported ${state.ibkrOpenOrders.length} IBKR open order rows`, "IBKR"));
      render();
    };
    reader.readAsText(file);
  }

  function drawChart() {
    const canvas = document.getElementById("price-chart");
    if (!canvas || !state.analysis) return;
    const metric = state.analysis.metrics.find((item) => item.symbol === state.selectedSymbol) || state.analysis.metrics[0];
    if (!metric) return;
    const rows = metric.rows.slice(-90);
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, rect.width * ratio);
    canvas.height = Math.max(1, rect.height * ratio);
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const pad = { left: 48, right: 14, top: 18, bottom: 54 };
    const chartW = rect.width - pad.left - pad.right;
    const chartH = rect.height - pad.top - pad.bottom;
    const prices = rows.flatMap((row) => [row.high, row.low]);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const priceToY = (price) => pad.top + (max - price) / Math.max(max - min, 0.0001) * chartH;
    const candleW = Math.max(3, chartW / rows.length * 0.58);

    ctx.strokeStyle = "#283024";
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i += 1) {
      const y = pad.top + chartH * i / 4;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(rect.width - pad.right, y);
      ctx.stroke();
    }

    rows.forEach((row, index) => {
      const x = pad.left + index / Math.max(rows.length - 1, 1) * chartW;
      const up = row.close >= row.open;
      ctx.strokeStyle = up ? "#4fc37a" : "#ef6a62";
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath();
      ctx.moveTo(x, priceToY(row.high));
      ctx.lineTo(x, priceToY(row.low));
      ctx.stroke();
      const yOpen = priceToY(row.open);
      const yClose = priceToY(row.close);
      ctx.fillRect(x - candleW / 2, Math.min(yOpen, yClose), candleW, Math.max(1, Math.abs(yClose - yOpen)));
      const volH = clamp(row.volume / Math.max(...rows.map((item) => item.volume)), 0, 1) * 34;
      ctx.globalAlpha = 0.35;
      ctx.fillRect(x - candleW / 2, rect.height - 14 - volH, candleW, volH);
      ctx.globalAlpha = 1;
    });

    drawAverage(ctx, rows, 20, pad, chartW, priceToY, "#e2b84f");
    drawAverage(ctx, rows, 50, pad, chartW, priceToY, "#72a7ff");

    ctx.fillStyle = "#9da894";
    ctx.font = "12px Inter, sans-serif";
    ctx.fillText(formatMoney(max), 8, pad.top + 5);
    ctx.fillText(formatMoney(min), 8, pad.top + chartH);
    document.getElementById("chart-title").textContent = `${metric.symbol} ${formatMoney(metric.price)}`;
    document.getElementById("chart-subtitle").textContent = `${metric.sector} | 20D ${formatPct(metric.ret20)} | Vol ${formatPct(metric.vol20)} | Drawdown ${formatPct(metric.drawdown)}`;
    document.getElementById("selected-score").textContent = `Score ${formatNumber(metric.score, 0)}`;
    document.getElementById("selected-confidence").textContent = `Confidence ${formatPct(selectedSetup()?.confidence || 0, 0)}`;
  }

  function drawAverage(ctx, rows, period, pad, chartW, priceToY, color) {
    if (rows.length < period) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    rows.forEach((row, index) => {
      const local = rows.slice(Math.max(0, index - period + 1), index + 1);
      const avg = mean(local.map((item) => item.close));
      const x = pad.left + index / Math.max(rows.length - 1, 1) * chartW;
      const y = priceToY(avg);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  if (typeof window !== "undefined") {
    window.addEventListener("DOMContentLoaded", initDashboard);
  }

  return {
    DEFAULT_UNIVERSE,
    generateSampleData,
    parseCsv,
    analyze,
    marketRegime,
    buildSetup,
    normalizeIbkrTrades,
    asTimeMs,
    dailyLimitReasons,
    estimateSetupFees,
    rsi,
    buildResearchSnapshot,
    styleConfig,
    learningGraph,
    setupLearningNodes,
    tradeFeatures,
    researchEvidence,
    formatPct,
    formatMoney
  };
});
