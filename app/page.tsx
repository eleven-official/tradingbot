const overview = [
  { label: 'Portfolio Value', value: '$482,360', change: '+4.8%', tone: 'up' },
  { label: 'Daily P&L', value: '$8,420', change: '+1.3%', tone: 'up' },
  { label: 'Win Rate', value: '64.2%', change: '+2.1%', tone: 'up' },
  { label: 'Active Risk', value: 'Moderate', change: '-0.6%', tone: 'down' }
];

const positions = [
  { symbol: 'BTCUSDT', side: 'Long', size: '1.42', pnl: '+$4,260', confidence: 'High' },
  { symbol: 'ETHUSDT', side: 'Long', size: '8.80', pnl: '+$2,140', confidence: 'Medium' },
  { symbol: 'SOLUSDT', side: 'Short', size: '320', pnl: '+$1,160', confidence: 'High' },
  { symbol: 'ADAUSDT', side: 'Long', size: '9,400', pnl: '-$340', confidence: 'Low' }
];

const signals = [
  { name: 'Trend Bias', value: 'Bullish', status: 'stable' },
  { name: 'Regime', value: 'Momentum', status: 'hot' },
  { name: 'Volatility', value: 'Elevated', status: 'watch' },
  { name: 'Execution Mode', value: 'Paper', status: 'neutral' }
];

const activity = [
  'Trend model rebalanced with stronger momentum filters.',
  'Paper trading position on BTC confirmed by strategy engine.',
  'Risk manager reduced exposure after volatility spike.',
  'Webhook health check passed from TradingView integration.'
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-8 flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-glow backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-cyan-400">Loki trading platform</p>
            <h1 className="mt-2 text-2xl font-semibold text-white sm:text-3xl">Market intelligence dashboard</h1>
          </div>

          <div className="flex items-center gap-3">
            <div className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
              System online
            </div>
            <button className="rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-500/20 transition hover:opacity-90">
              View live feed
            </button>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {overview.map((item) => (
            <div key={item.label} className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-glow">
              <p className="text-sm text-slate-400">{item.label}</p>
              <div className="mt-4 flex items-end justify-between gap-4">
                <div className="text-3xl font-semibold text-white">{item.value}</div>
                <span
                  className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    item.tone === 'up'
                      ? 'bg-emerald-500/10 text-emerald-300'
                      : 'bg-rose-500/10 text-rose-300'
                  }`}
                >
                  {item.change}
                </span>
              </div>
            </div>
          ))}
        </section>

        <section className="mt-8 grid gap-6 xl:grid-cols-[1.5fr_0.9fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-glow">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Portfolio overview</h2>
              <span className="text-sm text-slate-400">Last 24h</span>
            </div>

            <div className="grid grid-cols-12 gap-2">
              {[55, 68, 52, 78, 75, 88, 82, 96, 90, 102, 95, 108].map((bar, index) => (
                <div key={index} className="flex flex-col items-center gap-2">
                  <div className="flex h-36 w-full items-end rounded-t-xl bg-slate-800/80 p-1">
                    <div
                      className="w-full rounded-t-xl bg-gradient-to-t from-cyan-500 via-blue-500 to-violet-500"
                      style={{ height: `${bar}%` }}
                    />
                  </div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-500">
                    {['M', 'T', 'W', 'T', 'F', 'S', 'S'][index % 7]}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-glow">
            <h2 className="text-lg font-semibold text-white">Signal status</h2>
            <div className="mt-5 space-y-4">
              {signals.map((signal) => (
                <div key={signal.name} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div>
                    <div className="text-sm text-slate-400">{signal.name}</div>
                    <div className="mt-1 font-medium text-white">{signal.value}</div>
                  </div>
                  <span
                    className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${
                      signal.status === 'stable'
                        ? 'bg-emerald-500/10 text-emerald-300'
                        : signal.status === 'hot'
                          ? 'bg-orange-500/10 text-orange-300'
                          : signal.status === 'watch'
                            ? 'bg-amber-500/10 text-amber-300'
                            : 'bg-slate-500/10 text-slate-300'
                    }`}
                  >
                    {signal.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-6 lg:grid-cols-[1.45fr_0.9fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-glow">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Open positions</h2>
              <span className="text-sm text-slate-400">Synced</span>
            </div>

            <div className="overflow-hidden rounded-xl border border-slate-800">
              <table className="min-w-full divide-y divide-slate-800 text-sm">
                <thead className="bg-slate-950/80 text-slate-400">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Symbol</th>
                    <th className="px-4 py-3 text-left font-medium">Side</th>
                    <th className="px-4 py-3 text-left font-medium">Size</th>
                    <th className="px-4 py-3 text-left font-medium">P&L</th>
                    <th className="px-4 py-3 text-left font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                  {positions.map((position) => (
                    <tr key={position.symbol} className="text-slate-200">
                      <td className="px-4 py-3 font-medium text-white">{position.symbol}</td>
                      <td className="px-4 py-3">{position.side}</td>
                      <td className="px-4 py-3">{position.size}</td>
                      <td className={`px-4 py-3 font-medium ${position.pnl.startsWith('-') ? 'text-rose-300' : 'text-emerald-300'}`}>
                        {position.pnl}
                      </td>
                      <td className="px-4 py-3">{position.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-glow">
            <h2 className="text-lg font-semibold text-white">Recent activity</h2>
            <div className="mt-5 space-y-4">
              {activity.map((item, index) => (
                <div key={item} className="flex gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="mt-1 h-2.5 w-2.5 rounded-full bg-cyan-400 shadow-[0_0_20px_rgba(34,211,238,0.8)]" />
                  <div>
                    <p className="text-sm text-slate-200">{item}</p>
                    <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-slate-500">{index + 1} min ago</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
