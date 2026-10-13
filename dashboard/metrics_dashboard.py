"""
Metrics Dashboard - Real-time monitoring and visualization
Web-based dashboard for system status, performance, and alerts
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import json

try:
    from aiohttp import web
    import aiohttp_cors
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
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.dashboard_config = config.get('dashboard', {})
        
        # Configuration
        self.enabled = self.dashboard_config.get('enabled', True)
        self.port = self.dashboard_config.get('port', 8080)
        self.update_interval = self.dashboard_config.get('update_interval', 1)
        
        # Current metrics
        self.current_metrics: Optional[DashboardMetrics] = None
        
        # WebSocket clients
        self.websocket_clients = set()
        
        # HTTP server
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
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
            web.get('/ws', self._websocket_handler)
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
        
        self.site = web.TCPSite(self.runner, 'localhost', self.port)
        await self.site.start()
        
        self.logger.info(f"Dashboard started on http://localhost:{self.port}")
    
    async def _index(self, request):
        """Serve dashboard HTML."""
        if not AIOHTTP_AVAILABLE:
            return None
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Quantum Trading Bot Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .metric { margin: 10px 0; padding: 10px; background: #f0f0f0; border-radius: 5px; }
                .value { font-weight: bold; color: #333; }
                .good { color: green; }
                .warning { color: orange; }
                .bad { color: red; }
            </style>
        </head>
        <body>
            <h1>Quantum Trading Bot Dashboard</h1>
            <div id="metrics"></div>
            <script>
                function updateMetrics() {
                    fetch('/api/metrics')
                        .then(r => r.json())
                        .then(data => {
                            document.getElementById('metrics').innerHTML = `
                                <div class="metric">System State: <span class="value">${data.system_state}</span></div>
                                <div class="metric">Market Regime: <span class="value">${data.market_regime}</span></div>
                                <div class="metric">Toxicity Level: <span class="value ${data.toxicity_level > 0.5 ? 'warning' : 'good'}">${data.toxicity_level.toFixed(2)}</span></div>
                                <div class="metric">API Latency: <span class="value">${data.api_latency_ms.toFixed(0)}ms</span></div>
                                <div class="metric">Active Positions: <span class="value">${data.active_positions}</span></div>
                                <div class="metric">Total Drawdown: <span class="value ${data.total_drawdown > 5 ? 'bad' : 'good'}">${data.total_drawdown.toFixed(2)}%</span></div>
                                <div class="metric">Total P&L: <span class="value ${data.total_pnl >= 0 ? 'good' : 'bad'}">$${data.total_pnl.toFixed(2)}</span></div>
                                <div class="metric">Win Rate: <span class="value">${data.win_rate.toFixed(1)}%</span></div>
                                <div class="metric">Sharpe Ratio: <span class="value">${data.sharpe_ratio.toFixed(2)}</span></div>
                                <div class="metric">Strategy Mutations: <span class="value">${data.strategy_mutations}</span></div>
                                <div class="metric">Toxicity Skips: <span class="value">${data.toxicity_skips}</span></div>
                            `;
                        });
                }
                updateMetrics();
                setInterval(updateMetrics, 1000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
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
            
            for ws in self.websocket_clients:
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
            for ws in self.websocket_clients:
                await ws.close()
        
        self.websocket_clients.clear()
        
        self.logger.info("Dashboard stopped")