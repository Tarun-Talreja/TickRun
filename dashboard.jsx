import React, { useState, useEffect, useMemo } from 'react';

// ============================================================
// SAMPLE DATA — shown before live GitHub data loads
// ============================================================
const SAMPLE_DAILY = {
  last_updated: "2026-04-22T08:00:00Z",
  market_context: {
    spy_price: 528.43, spy_change_pct: -0.42,
    qqq_price: 462.18, qqq_change_pct: -0.61,
    vix: 18.7, ten_year_yield: 4.31
  },
  tickers: [
    { symbol: "AAPL", price: 221.40, change_pct_1d: -1.2, change_pct_5d: 2.1, change_pct_ytd: -4.3, range_52w_low: 169.21, range_52w_high: 237.49, pe: 33.1, forward_pe: 28.4, rsi_14: 52, ma_50: 218.50, ma_200: 210.33, next_earnings: "2026-05-01", news_titles_24h: ["Apple reported stronger services growth", "New iPad lineup announced"] },
    { symbol: "MSFT", price: 412.80, change_pct_1d: 0.8, change_pct_5d: 3.2, change_pct_ytd: 1.8, range_52w_low: 362.90, range_52w_high: 468.35, pe: 34.9, forward_pe: 30.1, rsi_14: 58, ma_50: 408.12, ma_200: 405.77, next_earnings: "2026-04-28", news_titles_24h: ["Azure growth continues to beat estimates"] },
    { symbol: "GOOGL", price: 165.22, change_pct_1d: -0.5, change_pct_5d: 1.1, change_pct_ytd: -2.4, range_52w_low: 142.66, range_52w_high: 193.31, pe: 22.4, forward_pe: 19.8, rsi_14: 48, ma_50: 168.30, ma_200: 171.05, next_earnings: "2026-04-24", news_titles_24h: ["Antitrust ruling details emerging", "Cloud margin expansion noted"] },
    { symbol: "NVDA", price: 118.70, change_pct_1d: 3.4, change_pct_5d: 8.2, change_pct_ytd: 22.1, range_52w_low: 75.61, range_52w_high: 140.76, pe: 62.3, forward_pe: 38.9, rsi_14: 74, ma_50: 112.40, ma_200: 105.22, next_earnings: "2026-05-22", news_titles_24h: ["Blackwell ramp exceeding expectations"] },
    { symbol: "META", price: 548.30, change_pct_1d: 1.1, change_pct_5d: -2.3, change_pct_ytd: 4.7, range_52w_low: 414.50, range_52w_high: 602.95, pe: 26.8, forward_pe: 23.1, rsi_14: 51, ma_50: 545.00, ma_200: 520.40, next_earnings: "2026-04-30", news_titles_24h: [] }
  ],
  flags: [
    { symbol: "NVDA", type: "rsi_extreme", detail: "RSI 74" },
    { symbol: "GOOGL", type: "earnings_soon", detail: "2 days" },
    { symbol: "MSFT", type: "earnings_soon", detail: "6 days" },
    { symbol: "META", type: "earnings_soon", detail: "8 days" }
  ]
};

const SAMPLE_WEEKLY = {
  last_updated: "2026-04-20T18:00:00Z",
  universe: "S&P 500",
  top_conviction: [
    { symbol: "BRK.B", company: "Berkshire Hathaway", sector: "Financials", price: 441.20, screens_passed: ["graham", "piotroski", "quality"], score: 3, one_line_thesis: "P/E 9.8, strong current ratio, high ROIC, improving margins — textbook compounder" },
    { symbol: "UNH", company: "UnitedHealth", sector: "Healthcare", price: 492.10, screens_passed: ["garp", "quality", "piotroski"], score: 3, one_line_thesis: "15% EPS growth, ROE 22%, PEG 1.1, clean balance sheet" },
    { symbol: "CVS", company: "CVS Health", sector: "Healthcare", price: 54.80, screens_passed: ["graham", "dividend"], score: 2, one_line_thesis: "P/E 9, 4.1% yield, payout 42%, 8-year dividend growth streak" },
    { symbol: "GOOGL", company: "Alphabet", sector: "Communication", price: 165.22, screens_passed: ["garp", "quality"], score: 2, one_line_thesis: "P/E 22, PEG 1.2, ROIC 28%, FCF margin 25%" },
    { symbol: "COST", company: "Costco", sector: "ConsumerStaples", price: 888.40, screens_passed: ["quality", "momentum"], score: 2, one_line_thesis: "ROIC 25%, 12M return 38%, above 200-day MA" }
  ],
  by_screen: {
    graham: [{symbol: "BRK.B", company: "Berkshire Hathaway", sector: "Financials"}, {symbol: "CVS", company: "CVS Health", sector: "Healthcare"}],
    magic_formula: [{symbol: "META", company: "Meta", sector: "Communication"}],
    piotroski: [{symbol: "BRK.B", company: "Berkshire Hathaway", sector: "Financials"}, {symbol: "UNH", company: "UnitedHealth", sector: "Healthcare"}],
    garp: [{symbol: "UNH", company: "UnitedHealth", sector: "Healthcare"}, {symbol: "GOOGL", company: "Alphabet", sector: "Communication"}],
    quality: [{symbol: "BRK.B", company: "Berkshire Hathaway", sector: "Financials"}, {symbol: "UNH", company: "UnitedHealth", sector: "Healthcare"}, {symbol: "GOOGL", company: "Alphabet", sector: "Communication"}, {symbol: "COST", company: "Costco", sector: "ConsumerStaples"}],
    momentum: [{symbol: "COST", company: "Costco", sector: "ConsumerStaples"}, {symbol: "NVDA", company: "NVIDIA", sector: "Technology"}],
    dividend: [{symbol: "CVS", company: "CVS Health", sector: "Healthcare"}]
  },
  sector_mix_top20: {
    Technology: 3, Financials: 4, Healthcare: 5, ConsumerDiscretionary: 1,
    ConsumerStaples: 2, Energy: 1, Industrials: 2, Materials: 0,
    RealEstate: 0, Utilities: 0, Communication: 2
  }
};

// ============================================================
// Small helpers
// ============================================================
const fmt = (n, d = 2) => n == null ? "—" : Number(n).toFixed(d);
const fmtPct = (n) => n == null ? "—" : `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`;
const pctColor = (n) => n == null ? "text-zinc-500" : n > 0 ? "text-emerald-400" : n < 0 ? "text-rose-400" : "text-zinc-300";
const timeAgo = (iso) => {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
};

const FLAG_LABEL = {
  earnings_soon: "EARNINGS",
  big_move: "MOVE",
  rsi_extreme: "",
  ma_cross: "MA CROSS"
};

const FLAG_COLOR = {
  earnings_soon: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  big_move: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  rsi_extreme: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40",
  ma_cross: "bg-teal-500/20 text-teal-300 border-teal-500/40"
};

// ============================================================
// UI Components
// ============================================================
const MarketStrip = ({ ctx }) => (
  <div className="grid grid-cols-4 gap-px bg-zinc-800 border border-zinc-800 rounded-lg overflow-hidden">
    {[
      { label: "SPY", price: ctx.spy_price, pct: ctx.spy_change_pct },
      { label: "QQQ", price: ctx.qqq_price, pct: ctx.qqq_change_pct },
      { label: "VIX", price: ctx.vix, pct: null },
      { label: "10Y", price: ctx.ten_year_yield, pct: null, suffix: "%" }
    ].map(it => (
      <div key={it.label} className="bg-zinc-950 px-3 py-2.5">
        <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium">{it.label}</div>
        <div className="font-mono text-base text-zinc-100 mt-0.5">{fmt(it.price)}{it.suffix || ""}</div>
        {it.pct != null && <div className={`font-mono text-xs ${pctColor(it.pct)}`}>{fmtPct(it.pct)}</div>}
      </div>
    ))}
  </div>
);

const FlagPill = ({ flag }) => (
  <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-[10px] font-mono tracking-wider ${FLAG_COLOR[flag.type]}`}>
    <span className="font-bold">{flag.symbol}</span>
    {FLAG_LABEL[flag.type] && <>
      <span className="opacity-60">•</span>
      <span>{FLAG_LABEL[flag.type]}</span>
    </>}
    <span className="opacity-70">{flag.detail}</span>
  </div>
);

const TickerCard = ({ t, flags }) => {
  const rangePos = t.range_52w_high && t.range_52w_low
    ? ((t.price - t.range_52w_low) / (t.range_52w_high - t.range_52w_low)) * 100
    : 50;
  const tickerFlags = flags.filter(f => f.symbol === t.symbol);

  return (
    <div className="border border-zinc-800 rounded-lg bg-zinc-950 p-4 hover:border-zinc-700 transition-colors">
      <div className="flex items-baseline justify-between mb-3">
        <div className="flex items-baseline gap-2">
          <span className="font-bold text-zinc-100 tracking-tight text-lg">{t.symbol}</span>
          {tickerFlags.map((f, i) => (
            <span key={i} className={`text-[9px] px-1.5 py-0.5 rounded border font-mono ${FLAG_COLOR[f.type]}`}>
              {FLAG_LABEL[f.type]}
            </span>
          ))}
        </div>
        <div className="text-right">
          <div className="font-mono text-zinc-100 text-base">${fmt(t.price)}</div>
          <div className={`font-mono text-xs ${pctColor(t.change_pct_1d)}`}>{fmtPct(t.change_pct_1d)}</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs mb-3">
        <div><div className="text-zinc-500 text-[10px] tracking-wider">5D</div><div className={`font-mono ${pctColor(t.change_pct_5d)}`}>{fmtPct(t.change_pct_5d)}</div></div>
        <div><div className="text-zinc-500 text-[10px] tracking-wider">YTD</div><div className={`font-mono ${pctColor(t.change_pct_ytd)}`}>{fmtPct(t.change_pct_ytd)}</div></div>
        <div><div className="text-zinc-500 text-[10px] tracking-wider">RSI</div><div className={`font-mono ${t.rsi_14 > 70 ? "text-rose-400" : t.rsi_14 < 30 ? "text-emerald-400" : "text-zinc-300"}`}>{fmt(t.rsi_14, 0)}</div></div>
        <div><div className="text-zinc-500 text-[10px] tracking-wider">P/E</div><div className="font-mono text-zinc-300">{fmt(t.pe, 1)}</div></div>
        <div><div className="text-zinc-500 text-[10px] tracking-wider">FWD P/E</div><div className="font-mono text-zinc-300">{fmt(t.forward_pe, 1)}</div></div>
        <div><div className="text-zinc-500 text-[10px] tracking-wider">ERNG</div><div className="font-mono text-zinc-300 text-[11px]">{t.next_earnings || "—"}</div></div>
      </div>

      <div className="mb-1">
        <div className="flex justify-between text-[10px] text-zinc-500 mb-1 font-mono">
          <span>{fmt(t.range_52w_low)}</span>
          <span className="text-zinc-600">52W</span>
          <span>{fmt(t.range_52w_high)}</span>
        </div>
        <div className="h-1 bg-zinc-800 rounded-full relative">
          <div className="h-full bg-zinc-600 rounded-full" style={{ width: `${Math.max(0, Math.min(100, rangePos))}%` }} />
          <div className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 bg-zinc-100 rounded-sm" style={{ left: `${Math.max(0, Math.min(100, rangePos))}%`, transform: `translate(-50%, -50%)` }} />
        </div>
      </div>

      {t.news_titles_24h && t.news_titles_24h.length > 0 && (
        <div className="mt-3 pt-3 border-t border-zinc-800/60">
          {t.news_titles_24h.slice(0, 2).map((title, i) => (
            <div key={i} className="text-[11px] text-zinc-400 leading-tight mb-1 flex gap-2">
              <span className="text-zinc-600">›</span><span>{title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ConvictionRow = ({ stock }) => (
  <div className="border border-zinc-800 rounded-lg bg-zinc-950 p-4">
    <div className="flex items-baseline justify-between mb-2">
      <div className="flex items-baseline gap-3">
        <span className="font-bold text-zinc-100 text-lg">{stock.symbol}</span>
        <span className="text-zinc-400 text-sm">{stock.company}</span>
        <span className="text-zinc-600 text-[10px] tracking-widest uppercase">{stock.sector}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="font-mono text-zinc-100">${fmt(stock.price)}</span>
        <span className="font-mono text-[10px] px-2 py-1 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
          {stock.score}× PASS
        </span>
      </div>
    </div>
    <div className="flex gap-1.5 mb-2 flex-wrap">
      {stock.screens_passed.map(s => (
        <span key={s} className="text-[10px] font-mono px-2 py-0.5 bg-zinc-900 text-zinc-400 border border-zinc-800 rounded tracking-wider uppercase">
          {s}
        </span>
      ))}
    </div>
    <div className="text-sm text-zinc-300 leading-relaxed">{stock.one_line_thesis}</div>
  </div>
);

const SectorBar = ({ sectors }) => {
  const total = Object.values(sectors).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  const entries = Object.entries(sectors).filter(([_, v]) => v > 0).sort((a, b) => b[1] - a[1]);

  return (
    <div className="border border-zinc-800 rounded-lg bg-zinc-950 p-4">
      <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">SECTOR MIX · TOP 20</div>
      <div className="space-y-2">
        {entries.map(([sector, count]) => {
          const pct = (count / total) * 100;
          return (
            <div key={sector} className="flex items-center gap-3">
              <div className="w-32 text-xs text-zinc-400">{sector}</div>
              <div className="flex-1 h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                <div className="h-full bg-zinc-500" style={{ width: `${pct}%` }} />
              </div>
              <div className="w-8 text-right font-mono text-xs text-zinc-300">{count}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ConfigPanel = ({ setDaily, setWeekly }) => {
  const [dailyText, setDailyText] = useState("");
  const [weeklyText, setWeeklyText] = useState("");
  const [error, setError] = useState("");

  const pasteDaily = () => {
    try { setDaily(JSON.parse(dailyText)); setDailyText(""); setError(""); }
    catch (e) { setError("Daily JSON invalid: " + e.message); }
  };
  const pasteWeekly = () => {
    try { setWeekly(JSON.parse(weeklyText)); setWeeklyText(""); setError(""); }
    catch (e) { setError("Weekly JSON invalid: " + e.message); }
  };

  return (
    <div className="space-y-4">
      <div className="border border-zinc-800 rounded-lg bg-zinc-950 p-4">
        <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">DATA SOURCE</div>
        <div className="text-xs text-zinc-400 mb-1">Daily</div>
        <div className="font-mono text-[11px] text-zinc-500 break-all">{DAILY_URL}</div>
        <div className="text-xs text-zinc-400 mt-3 mb-1">Weekly Screens</div>
        <div className="font-mono text-[11px] text-zinc-500 break-all">{SCREENS_URL}</div>
        <div className="text-[11px] text-zinc-600 mt-3">
          Auto-fetches on load and every 5 minutes. Use manual paste below if GitHub is unreachable.
        </div>
      </div>

      <div className="border border-zinc-800 rounded-lg bg-zinc-950 p-4">
        <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">MANUAL PASTE (FALLBACK)</div>
        <textarea value={dailyText} onChange={e => setDailyText(e.target.value)} placeholder="Paste daily.json contents"
                  className="w-full h-24 bg-black border border-zinc-800 rounded px-3 py-2 text-xs font-mono text-zinc-200 focus:border-zinc-600 focus:outline-none" />
        <button onClick={pasteDaily} className="mt-2 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs rounded border border-zinc-700">Load daily.json</button>

        <textarea value={weeklyText} onChange={e => setWeeklyText(e.target.value)} placeholder="Paste weekly_screens.json contents"
                  className="w-full h-24 bg-black border border-zinc-800 rounded px-3 py-2 text-xs font-mono text-zinc-200 focus:border-zinc-600 focus:outline-none mt-3" />
        <button onClick={pasteWeekly} className="mt-2 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs rounded border border-zinc-700">Load weekly.json</button>
        {error && <div className="mt-2 text-xs text-rose-400 font-mono">{error}</div>}
      </div>

      <div className="text-[11px] text-zinc-600 leading-relaxed border border-zinc-900 rounded p-3">
        <div className="text-zinc-500 mb-1 tracking-wider text-[10px]">DISCLAIMER</div>
        This is a screener, not investment advice. Screens surface stocks worth researching — they do not predict returns. Always read the 10-Q and understand why a stock passed before buying.
      </div>
    </div>
  );
};

// ============================================================
// Main app — fetches from raw GitHub (CORS-friendly, always fresh)
// ============================================================
const DAILY_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/daily.json";
const SCREENS_URL = "https://raw.githubusercontent.com/Tarun-Talreja/TickRun/main/output/weekly_screens.json";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

export default function Dashboard() {
  const [tab, setTab] = useState("today");
  const [daily, setDaily] = useState(SAMPLE_DAILY);
  const [weekly, setWeekly] = useState(SAMPLE_WEEKLY);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState("");

  const refresh = async () => {
    setLoading(true); setFetchError("");
    try {
      const [dailyRes, weeklyRes] = await Promise.all([
        fetch(DAILY_URL),
        fetch(SCREENS_URL),
      ]);
      if (!dailyRes.ok) throw new Error(`Daily fetch HTTP ${dailyRes.status}`);
      if (!weeklyRes.ok) throw new Error(`Weekly fetch HTTP ${weeklyRes.status}`);
      setDaily(await dailyRes.json());
      setWeekly(await weeklyRes.json());
    } catch (e) {
      setFetchError(e.message);
    }
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const usingSample = daily === SAMPLE_DAILY || weekly === SAMPLE_WEEKLY;

  return (
    <div className="min-h-screen bg-black text-zinc-200" style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        .font-mono { font-family: 'JetBrains Mono', monospace; font-feature-settings: "tnum"; }
        .font-brand { font-family: 'Space Grotesk', system-ui, sans-serif; }
      `}</style>

      {/* Header */}
      <header className="border-b border-zinc-900 sticky top-0 bg-black/95 backdrop-blur z-10">
        <div className="max-w-6xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              {/* Logo mark */}
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="28" height="28" rx="6" fill="#18181b"/>
                <polyline points="4,20 10,13 15,17 24,7" stroke="#34d399" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <circle cx="24" cy="7" r="2" fill="#34d399"/>
              </svg>
              <span className="font-brand font-bold text-xl tracking-tight text-zinc-100">TickRun</span>
              <span className="text-[10px] tracking-[0.18em] text-zinc-600 font-medium hidden sm:block">PERSONAL SCREENER</span>
            </div>
            <button onClick={refresh} disabled={loading}
                    className="text-[11px] font-mono tracking-wider text-zinc-400 hover:text-zinc-200 disabled:opacity-50">
              {loading ? "LOADING…" : "↻ REFRESH"}
            </button>
          </div>
          <nav className="flex gap-1 mt-3">
            {[
              { id: "today", label: "TODAY" },
              { id: "screens", label: "SCREENS" },
              { id: "watchlist", label: "WATCHLIST" },
              { id: "config", label: "CONFIG" }
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                      className={`px-3 py-1.5 text-[11px] tracking-[0.15em] font-medium rounded transition-colors
                        ${tab === t.id ? "bg-zinc-100 text-black" : "text-zinc-500 hover:text-zinc-300"}`}>
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {usingSample && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 text-amber-200 text-xs px-4 py-2 text-center font-mono">
          SAMPLE DATA · Live data loads automatically from TickRun repo
        </div>
      )}
      {fetchError && (
        <div className="bg-rose-500/10 border-b border-rose-500/30 text-rose-200 text-xs px-4 py-2 text-center font-mono">
          FETCH ERROR: {fetchError}
        </div>
      )}

      <main className="max-w-6xl mx-auto px-4 py-6">
        {tab === "today" && (
          <div className="space-y-5">
            <div>
              <div className="flex items-baseline justify-between mb-3">
                <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium">MARKET</div>
                <div className="text-[10px] text-zinc-600 font-mono">updated {timeAgo(daily.last_updated)}</div>
              </div>
              <MarketStrip ctx={daily.market_context} />
            </div>

            {daily.flags && daily.flags.length > 0 && (
              <div>
                <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">FLAGS · {daily.flags.length}</div>
                <div className="flex flex-wrap gap-2">
                  {daily.flags.map((f, i) => <FlagPill key={i} flag={f} />)}
                </div>
              </div>
            )}

            <div>
              <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">WATCHLIST · {daily.tickers.length}</div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {daily.tickers.map(t => <TickerCard key={t.symbol} t={t} flags={daily.flags || []} />)}
              </div>
            </div>
          </div>
        )}

        {tab === "screens" && (
          <div className="space-y-5">
            <div className="flex items-baseline justify-between">
              <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium">TOP CONVICTION · MULTI-SCREEN PASSES</div>
              <div className="text-[10px] text-zinc-600 font-mono">screens refreshed {timeAgo(weekly.last_updated)}</div>
            </div>
            <div className="space-y-2">
              {weekly.top_conviction.map(s => <ConvictionRow key={s.symbol} stock={s} />)}
            </div>
            <SectorBar sectors={weekly.sector_mix_top20} />
            <div>
              <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium mb-3">BY SCREEN</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(weekly.by_screen).map(([screen, stocks]) => (
                  <div key={screen} className="border border-zinc-800 rounded-lg bg-zinc-950 p-3">
                    <div className="text-xs font-mono tracking-widest uppercase text-zinc-400 mb-2">{screen}</div>
                    {stocks.length === 0 ? <div className="text-[11px] text-zinc-600">no passes</div>
                      : <div className="space-y-1">
                          {stocks.map(s => (
                            <div key={s.symbol} className="flex justify-between text-xs">
                              <span className="text-zinc-200 font-medium">{s.symbol}</span>
                              <span className="text-zinc-500 text-[11px]">{s.company}</span>
                            </div>
                          ))}
                        </div>
                    }
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {tab === "watchlist" && (
          <div className="space-y-5">
            <div className="text-[10px] tracking-[0.2em] text-zinc-500 font-medium">YOUR TICKERS · SCREEN STATUS</div>
            <div className="space-y-2">
              {daily.tickers.map(t => {
                const passes = weekly.top_conviction.find(c => c.symbol === t.symbol);
                return (
                  <div key={t.symbol} className="border border-zinc-800 rounded-lg bg-zinc-950 p-3 flex items-center justify-between">
                    <div className="flex items-baseline gap-3">
                      <span className="font-bold text-zinc-100">{t.symbol}</span>
                      <span className="font-mono text-sm text-zinc-300">${fmt(t.price)}</span>
                      <span className={`font-mono text-xs ${pctColor(t.change_pct_1d)}`}>{fmtPct(t.change_pct_1d)}</span>
                    </div>
                    <div>
                      {passes ? (
                        <div className="flex gap-1">
                          {passes.screens_passed.map(s => (
                            <span key={s} className="text-[9px] font-mono px-1.5 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded tracking-wider uppercase">{s}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[10px] text-zinc-600 font-mono tracking-wider">NO PASSES</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {tab === "config" && (
          <ConfigPanel setDaily={setDaily} setWeekly={setWeekly} />
        )}
      </main>

      <footer className="max-w-6xl mx-auto px-4 py-8 text-center">
        <div className="flex items-center justify-center gap-2">
          <svg width="14" height="14" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <polyline points="4,20 10,13 15,17 24,7" stroke="#52525b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
          </svg>
          <span className="font-brand text-[10px] text-zinc-700 tracking-[0.15em]">TICKRUN · PERSONAL USE · NOT FINANCIAL ADVICE</span>
        </div>
      </footer>
    </div>
  );
}
