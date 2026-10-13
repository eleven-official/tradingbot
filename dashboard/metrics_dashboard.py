"""
Metrics Dashboard - Real-time monitoring and visualization
Web-based dashboard for system status, performance, and alerts
Adds lightweight paper-trading endpoints that simulate fills using live market prices (Binance) and a protected live-trading toggle.
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import json
import os

try:
    from aiohttp import web
    import aiohttp_cors
    import aiohttp as _aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp not available - dashboard will run in headless mode")


@dataclass
class DashboardMetrics:
    """Metrics for dashboard display."""
    timestamp: datetime
    system_state: str
    market_regime: str
    toxicity_level: float
    api_latency_ms: float
    active_positions: int
    total_drawdown: float
    total_pnl: float
    win_rate: float
    sharpe_ratio: float
    strategy_mutations: int
    toxicity_skips: int


class MetricsDashboard:
    """
    Web-based metrics dashboard for real-time monitoring.
    Provides REST API and WebSocket for live updates.

    Includes simple paper-trading API endpoints:
      - GET  /api/candles?symbol=...&interval=...&limit=...
      - POST /api/trade  {symbol, side, quantity, type}
      - POST /api/enable_live  (requires ALLOW_LIVE env and explicit confirmation)

    IMPORTANT: Live trading is disabled by default. API keys are not stored in the repo.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.dashboard_config = config.get('dashboard', {})
        
        # Configuration
        self.enabled = self.dashboard_config.get('enabled', True)
        self.port = self.dashboard_config.get('port', 8080)
        self.update_interval = self.dashboard_config.get('update_interval', 1)
        self.slippage_pct = float(self.dashboard_config.get('slippage_pct', 0.001))
        
        # Current metrics
        self.current_metrics: Optional[DashboardMetrics] = None
        
        # WebSocket clients
        self.websocket_clients = set()
        
        # HTTP server
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        # In-memory paper trading state (simple)
        self.paper_positions = {}
        self.order_seq = 0
        
        logging.info("Metrics Dashboard initialized")
    
    async def initialize(self):
        """Initialize the dashboard."""
        self.logger = logging.getLogger(__name__)
        
        if self.enabled:
            await self._setup_web_server()
        
        self.logger.info("Metrics Dashboard initialized")
    
    async def _setup_web_server(self):
        """Setup HTTP and WebSocket server."""
        if not AIOHTTP_AVAILABLE:
            self.logger.warning("aiohttp not available - web server disabled")
            return
        
        self.app = web.Application()
        
        # Setup CORS
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Add routes
        self.app.add_routes([
            web.get('/', self._index),
            web.get('/api/metrics', self._get_metrics),
            web.get('/api/status', self._get_status),
            web.get('/ws', self._websocket_handler),
            web.get('/api/candles', self._get_candles),
            web.post('/api/trade', self._post_trade),
            web.post('/api/enable_live', self._post_enable_live)
        ])
        
        # Add CORS to routes
        for route in list(self.app.router.routes()):
            cors.add(route)
    
    async def start(self):
        """Start the web server."""
        if not self.enabled or not AIOHTTP_AVAILABLE:
            return
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        # bind to 0.0.0.0 so remote hosts (or container orchestrators) can reach it
        host = os.environ.get('DASHBOARD_HOST', '0.0.0.0')
        self.site = web.TCPSite(self.runner, host, self.port)
        await self.site.start()
        
        self.logger.info(f"Dashboard started on http://{host}:{self.port}")
    
    async def _index(self, request):
        """Serve dashboard HTML."""
        if not AIOHTTP_AVAILABLE:
            return None
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Quantum Trading Bot Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                body { font-family: Arial, sans-serif; margin: 12px; background: #0f1724; color: #e6eef8; }
                .container { max-width: 1200px; margin: 0 auto; }
                header { display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px; }
                h1 { font-size: 20px; margin:0; }
                .controls { display:flex; gap:8px; }
                .metric { margin: 6px 0; padding: 10px; background: rgba(255,255,255,0.03); border-radius: 8px; }
                .value { font-weight: bold; color: #cfe8ff; }
                .good { color: #51d88a; }
                .warning { color: #ffb020; }
                .bad { color: #ff6b6b; }
                #chart { height: 420px; background: #071226; border-radius:8px; padding:8px; }
                #explain { margin-top:12px; padding:10px; background: rgba(255,255,255,0.02); border-radius:8px; }
                .flex { display:flex; gap:12px; }
                .col { flex:1; }
                .small { font-size: 13px; color: #99a3b3 }
                select, input { padding:6px; border-radius:6px; border: none; background: rgba(255,255,255,0.03); color: #e6eef8 }
                button { padding:8px 10px; border-radius:6px; border:none; background:#2563eb; color:white }
                form { display:flex; gap:8px; align-items:center; margin-top:8px }
                label.inline { font-size:13px }
            </style>
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
        </head>
        <body>
            <div class="container">
              <header>
                <h1>Quantum Trading Bot Dashboard</h1>
                <div class="controls">
                  <label class="small">Symbol: <select id="symbol"><option>BTCUSDT</option><option>ETHUSDT</option></select></label>
                  <label class="small">Interval: <select id="interval"><option value="1m">1m</option><option value="5m">5m</option><option value="15m">15m</option><option value="1h">1h</option><option value="1d">1d</option></select></label>
                  <button id="refresh">Refresh</button>
                </div>
              </header>

              <div class="flex">
                <div class="col">
                  <div id="chart"></div>
                  <div id="explain">
                    <strong>Candlestick explanation</strong>
                    <p class="small">Each candlestick represents price movement for the selected timeframe. It contains:</p>
                    <ul class="small">
                      <li><strong>Open</strong>: price at the start of the interval.</li>
                      <li><strong>High</strong>: highest price during the interval.</li>
                      <li><strong>Low</strong>: lowest price during the interval.</li>
                      <li><strong>Close</strong>: price at the end of the interval.</li>
                      <li><strong>Body</strong>: difference between open and close — green (bullish) if close &gt; open, red (bearish) if close &lt; open.</li>
                      <li><strong>Wicks (shadows)</strong>: lines above/below the body indicating high and low extremes.</li>
                    </ul>
                    <p class="small">Common patterns: Doji (small body), Hammer (long lower wick), Shooting Star (long upper wick). Patterns are not guarantees — always combine with risk management.</p>
                  </div>
                </div>
                <div class="col">
                  <div id="metrics"></div>

                  <div style="margin-top:12px;" class="metric small"><strong>Order / Paper Trading</strong>
                    <form id="orderForm">
                      <label class="inline small">Side:
                        <select id="side"><option value="BUY">BUY</option><option value="SELL">SELL</option></select>
                      </label>
                      <label class="inline small">Qty: <input id="qty" type="number" step="0.0001" value="0.001" /></label>
                      <label class="inline small">Type:
                        <select id="otype"><option value="market">market</option><option value="limit">limit</option></select>
                      </label>
                      <label class="inline small">Price: <input id="price" type="number" step="0.01" /></label>
                      <button type="button" id="placeOrder">Place (paper)</button>
                    </form>
                    <div id="orderResult" class="small" style="margin-top:8px"></div>

                    <div style="margin-top:12px;" class="small">Enable live trading: <button id="enableLive">Enable (requires server env ALLOW_LIVE=true)</button></div>
                  </div>

                  <div style="margin-top:12px;" class="metric small"><strong>Notes:</strong> Paper trading connects to live market data for candles; simulated fills use market price by default. API keys are never stored in the repo. To enable real trading, configure keys in environment variables (see docs/LIVE_TRADING.md).</div>
                </div>
              </div>

            </div>
            <script>
                const chartContainer = document.getElementById('chart');
                const chart = LightweightCharts.createChart(chartContainer, { width: chartContainer.clientWidth, height: 420, layout: { backgroundColor: '#071226', textColor: '#d1e6f6' }, grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } } });
                const candleSeries = chart.addCandlestickSeries({
                    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350'
                });

                async function fetchCandles(symbol, interval, limit=200) {
                    const res = await fetch(`/api/candles?symbol=${symbol}&interval=${interval}&limit=${limit}`);
                    if (!res.ok) return [];
                    const data = await res.json();
                    return data.map(c => ({ time: c.time, open: parseFloat(c.open), high: parseFloat(c.high), low: parseFloat(c.low), close: parseFloat(c.close) }));
                }

                async function update() {
                    const symbol = document.getElementById('symbol').value || 'BTCUSDT';
                    const interval = document.getElementById('interval').value || '1m';
                    const candles = await fetchCandles(symbol, interval);
                    if (candles && candles.length) {
                        candleSeries.setData(candles);
                        chart.timeScale().fitContent();
                    }
                }

                document.getElementById('refresh').addEventListener('click', update);
                window.addEventListener('resize', () => chart.applyOptions({ width: chartContainer.clientWidth }));

                // Metrics updater (keeps existing functionality)
                function updateMetrics() {
                    fetch('/api/metrics')
                        .then(r => r.json())
                        .then(data => {
                            document.getElementById('metrics').innerHTML = `
                                <div class="metric">System State: <span class="value">${data.system_state || 'unknown'}</span></div>
                                <div class="metric">Market Regime: <span class="value">${data.market_regime || 'unknown'}</span></div>
                                <div class="metric">Toxicity Level: <span class="value ${data.toxicity_level > 0.5 ? 'warning' : 'good'}">${(data.toxicity_level||0).toFixed(2)}</span></div>
                                <div class="metric">API Latency: <span class="value">${(data.api_latency_ms||0).toFixed(0)}ms</span></div>
                                <div class="metric">Active Positions: <span class="value">${data.active_positions||0}</span></div>
                                <div class="metric">Total Drawdown: <span class="value ${data.total_drawdown > 5 ? 'bad' : 'good'}">${(data.total_drawdown||0).toFixed(2)}%</span></div>
                                <div class="metric">Total P&L: <span class="value ${data.total_pnl >= 0 ? 'good' : 'bad'}">$${(data.total_pnl||0).toFixed(2)}</span></div>
                                <div class="metric">Win Rate: <span class="value">${(data.win_rate||0).toFixed(1)}%</span></div>
                                <div class="metric">Sharpe Ratio: <span class="value">${(data.sharpe_ratio||0).toFixed(2)}</span></div>
                                <div class="metric">Strategy Mutations: <span class="value">${data.strategy_mutations||0}</span></div>
                                <div class="metric">Toxicity Skips: <span class="value">${data.toxicity_skips||0}</span></div>
                            `;
                        }).catch(()=>{});
                }
                updateMetrics();
                setInterval(updateMetrics, 1000);

                // Order placement
                document.getElementById('placeOrder').addEventListener('click', async () => {
                    const symbol = document.getElementById('symbol').value || 'BTCUSDT';
                    const side = document.getElementById('side').value;
                    const qty = parseFloat(document.getElementById('qty').value);
                    const otype = document.getElementById('otype').value;
                    const price = document.getElementById('price').value ? parseFloat(document.getElementById('price').value) : undefined;

                    const payload = { symbol, side, quantity: qty, type: otype };
                    if (price) payload.price = price;

                    const res = await fetch('/api/trade', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    const data = await res.json();
                    document.getElementById('orderResult').innerText = JSON.stringify(data, null, 2);
                });

                // Enable live (protected)
                document.getElementById('enableLive').addEventListener('click', async () => {
                    if (!confirm('Enabling live trading requires server-side ALLOW_LIVE=true and valid API keys in the environment. Proceed?')) return;
                    const res = await fetch('/api/enable_live', { method: 'POST' });
                    const data = await res.json();
                    alert(JSON.stringify(data));
                });

                // initial load
                update();
                setInterval(update, 30*1000); // refresh candles every 30s
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def _get_candles(self, request):
        """Return recent candlesticks from Binance public REST API.
        Query params: symbol (default BTCUSDT), interval (default 1m), limit (default 200)
        """
        if not AIOHTTP_AVAILABLE:
            return web.json_response({'error': 'aiohttp not available'}, status=500)

        params = request.rel_url.query
        symbol = params.get('symbol', 'BTCUSDT')
        interval = params.get('interval', '1m')
        limit = int(params.get('limit', '200'))

        # Validate limit
        if limit <= 0 or limit > 1000:
            limit = 200

        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return web.json_response({'error': 'binance_error', 'status': resp.status, 'detail': text}, status=502)
                    klines = await resp.json()
        except Exception as e:
            self.logger.error(f"Error fetching candles: {e}")
            return web.json_response({'error': 'fetch_failed', 'detail': str(e)}, status=502)

        # Parse klines into OHLC data
        candles = []
        for k in klines:
            open_time = int(k[0])
            open_price = k[1]
            high_price = k[2]
            low_price = k[3]
            close_price = k[4]
            volume = k[5]
            # Binance open_time is in ms
            iso_time = datetime.utcfromtimestamp(open_time/1000).isoformat()
            candles.append({
                'time': iso_time,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })

        return web.json_response(candles)

    async def _post_trade(self, request):
        """Place a simulated paper trade or forward to exchange if live mode enabled.

        Body: {symbol, side:BUY/SELL, quantity, type:market|limit, price?}
        """
        if not AIOHTTP_AVAILABLE:
            return web.json_response({'error': 'aiohttp not available'}, status=500)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({'error': 'invalid_json'}, status=400)

        symbol = payload.get('symbol') or 'BTCUSDT'
        side = payload.get('side')
        qty = float(payload.get('quantity', 0))
        otype = payload.get('type', 'market')
        price = payload.get('price')

        if side not in ('BUY', 'SELL'):
            return web.json_response({'error': 'invalid_side'}, status=400)
        if qty <= 0:
            return web.json_response({'error': 'invalid_qty'}, status=400)

        live_enabled = os.environ.get('LIVE_TRADING', 'false').lower() == 'true'
        allow_live_on_server = os.environ.get('ALLOW_LIVE', 'false').lower() == 'true'

        # Simulate fill price using latest market price
        try:
            async with _aiohttp.ClientSession() as session:
                # get most recent trade price via klines limit=1
                kl_url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=1'
                async with session.get(kl_url, timeout=5) as resp:
                    if resp.status == 200:
                        k = await resp.json()
                        close_price = float(k[0][4])
                    else:
                        close_price = None
        except Exception as e:
            self.logger.error(f"Error fetching market price for trade: {e}")
            close_price = None

        executed_price = None
        status = 'simulated'
        if otype == 'market' or price is None:
            if close_price is None:
                return web.json_response({'error': 'market_price_unavailable'}, status=502)
            # apply slippage
            slippage = self.slippage_pct
            if side == 'BUY':
                executed_price = close_price * (1 + slippage)
            else:
                executed_price = close_price * (1 - slippage)
        else:
            # limit order: if price is favorable relative to market, fill immediately; otherwise keep open (not implemented fully)
            limit_price = float(price)
            if close_price is None:
                return web.json_response({'error': 'market_price_unavailable'}, status=502)
            fill = False
            if side == 'BUY' and limit_price >= close_price:
                fill = True
            if side == 'SELL' and limit_price <= close_price:
                fill = True
            if fill:
                executed_price = limit_price
            else:
                status = 'open'
                executed_price = None

        # If live trading requested and enabled on server, we'd forward to the exchange SDK (not storing keys here).
        if live_enabled and allow_live_on_server:
            # TODO: forward to chosen broker SDK (Alpaca, Binance, etc) using server env keys
            # For safety we do not implement automatic forwarding without explicit test/confirmation
            status = 'forwarded_to_exchange_pending'

        # Create an order record (in-memory)
        self.order_seq += 1
        oid = f"ORD{self.order_seq:06d}"
        order = {
            'order_id': oid,
            'symbol': symbol,
            'side': side,
            'quantity': qty,
            'type': otype,
            'requested_price': price,
            'executed_price': executed_price,
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Update simple paper position (naive aggregation)
        if status in ('simulated', 'filled', 'forwarded_to_exchange_pending') and executed_price is not None:
            pos = self.paper_positions.get(symbol, 0.0)
            signed_qty = qty if side == 'BUY' else -qty
            self.paper_positions[symbol] = pos + signed_qty

        return web.json_response(order)

    async def _post_enable_live(self, request):
        """Attempt to enable live trading on the server process.

        This endpoint will only succeed if the server process has ALLOW_LIVE=true
        set in its environment to prevent accidental remote enabling.
        """
        allow_live_on_server = os.environ.get('ALLOW_LIVE', 'false').lower() == 'true'
        if not allow_live_on_server:
            return web.json_response({'error': 'server_live_disabled', 'detail': 'Set ALLOW_LIVE=true in the server environment to allow enabling live trading'}, status=403)

        # Toggle LIVE_TRADING on the running process (in-memory only)
        # Note: This does not persist across restarts; prefer setting LIVE_TRADING in env for production
        os.environ['LIVE_TRADING'] = 'true'
        return web.json_response({'status': 'live_enabled', 'note': 'LIVE_TRADING set to true in process environment. Ensure API keys are configured in the server environment.'})
    
    async def _get_metrics(self, request):
        """Get current metrics."""
        if not AIOHTTP_AVAILABLE:
            return None
        
        if self.current_metrics:
            return web.json_response({
                'system_state': self.current_metrics.system_state,
                'market_regime': self.current_metrics.market_regime,
                'toxicity_level': self.current_metrics.toxicity_level,
                'api_latency_ms': self.current_metrics.api_latency_ms,
                'active_positions': self.current_metrics.active_positions,
                'total_drawdown': self.current_metrics.total_drawdown,
                'total_pnl': self.current_metrics.total_pnl,
                'win_rate': self.current_metrics.win_rate,
                'sharpe_ratio': self.current_metrics.sharpe_ratio,
                'strategy_mutations': self.current_metrics.strategy_mutations,
                'toxicity_skips': self.current_metrics.toxicity_skips
            })
        else:
            return web.json_response({})
    
    async def _get_status(self, request):
        """Get system status."""
        if not AIOHTTP_AVAILABLE:
            return None
        
        return web.json_response({
            'status': 'running' if self.current_metrics else 'initializing',
            'timestamp': datetime.now().isoformat()
        })
    
    async def _websocket_handler(self, request):
        """WebSocket handler for real-time updates."""
        if not AIOHTTP_AVAILABLE:
            return None
        
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_clients.add(ws)
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Handle client messages if needed
                    pass
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f'WebSocket error: {ws.exception()}')
        finally:
            self.websocket_clients.discard(ws)
        
        return ws
    
    async def update(self, market_state: Dict[str, Any], system_health: Dict[str, Any], 
                    metrics: Dict[str, Any]):
        """Update dashboard metrics."""
        self.current_metrics = DashboardMetrics(
            timestamp=datetime.now(),
            system_state=system_health.get('state', 'unknown'),
            market_regime=market_state.get('regime', 'unknown'),
            toxicity_level=market_state.get('toxicity_level', 0.0),
            api_latency_ms=system_health.get('api_latency_ms', 0.0),
            active_positions=system_health.get('active_positions', 0),
            total_drawdown=system_health.get('total_drawdown', 0.0),
            total_pnl=metrics.get('total_pnl', 0.0),
            win_rate=metrics.get('winning_trades', 0) / metrics.get('total_trades', 1) * 100 if metrics.get('total_trades', 0) > 0 else 0,
            sharpe_ratio=metrics.get('sharpe_ratio', 0.0),
            strategy_mutations=metrics.get('strategy_mutations', 0),
            toxicity_skips=metrics.get('toxicity_skips', 0)
        )
        
        # Broadcast to WebSocket clients
        if AIOHTTP_AVAILABLE and self.websocket_clients:
            message = json.dumps({
                'type': 'metrics_update',
                'data': {
                    'system_state': self.current_metrics.system_state,
                    'market_regime': self.current_metrics.market_regime,
                    'toxicity_level': self.current_metrics.toxicity_level,
                    'api_latency_ms': self.current_metrics.api_latency_ms,
                    'active_positions': self.current_metrics.active_positions,
                    'total_drawdown': self.current_metrics.total_drawdown,
                    'total_pnl': self.current_metrics.total_pnl,
                    'win_rate': self.current_metrics.win_rate,
                    'sharpe_ratio': self.current_metrics.sharpe_ratio,
                    'strategy_mutations': self.current_metrics.strategy_mutations,
                    'toxicity_skips': self.current_metrics.toxicity_skips
                }
            })
            
            for ws in list(self.websocket_clients):
                try:
                    await ws.send_str(message)
                except Exception as e:
                    self.logger.error(f"WebSocket send error: {e}")
                    self.websocket_clients.discard(ws)
    
    async def stop(self):
        """Stop the web server."""
        if AIOHTTP_AVAILABLE and self.runner:
            await self.runner.cleanup()
        
        # Close WebSocket clients
        if AIOHTTP_AVAILABLE:
            for ws in list(self.websocket_clients):
                await ws.close()
        
        self.websocket_clients.clear()
        
        self.logger.info("Dashboard stopped")
