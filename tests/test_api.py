"""
Comprehensive API tests for Loki Trading Platform
Tests REST endpoints, authentication, and WebSocket connections
"""
import pytest
from fastapi.testclient import TestClient
from loki.api.server import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health check and system status endpoints"""
    
    def test_root_endpoint(self):
        """Test root endpoint returns correct application info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["application"] == "Loki Trading Platform"
        assert data["version"] == "2.0.0"
        assert data["status"] == "operational"
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "active_strategies" in data
        assert data["market_connection"] is True


class TestAuthentication:
    """Test authentication and authorization"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_login_success(self):
        """Test successful login"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_failure(self):
        """Test login with wrong credentials"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 401
    
    def test_protected_endpoint_without_auth(self):
        """Test accessing protected endpoint without auth"""
        response = client.get("/api/v1/portfolio")
        assert response.status_code == 401
    
    def test_protected_endpoint_with_auth(self, admin_token):
        """Test accessing protected endpoint with valid token"""
        response = client.get(
            "/api/v1/portfolio",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200


class TestPortfolioEndpoints:
    """Test portfolio management endpoints"""
    
    @pytest.fixture
    def auth_headers(self):
        """Get authenticated headers"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "admin123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_portfolio(self, auth_headers):
        """Test portfolio retrieval"""
        response = client.get("/api/v1/portfolio", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_value" in data
        assert "daily_pnl" in data
        assert data["total_value"] > 0
    
    def test_get_positions(self, auth_headers):
        """Test positions retrieval"""
        response = client.get("/api/v1/positions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestTradingEndpoints:
    """Test trading order endpoints"""
    
    @pytest.fixture
    def auth_headers(self):
        """Get authenticated headers"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "admin123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_place_order(self, auth_headers):
        """Test order placement"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market"
        }
        response = client.post(
            "/api/v1/orders",
            json=order_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
        assert data["status"] == "submitted"
    
    def test_place_invalid_order(self, auth_headers):
        """Test invalid order placement"""
        order_data = {
            "symbol": "INVALID",
            "side": "invalid_side",
            "quantity": -10
        }
        response = client.post(
            "/api/v1/orders",
            json=order_data,
            headers=auth_headers
        )
        assert response.status_code == 422  # Validation error


class TestStrategyEndpoints:
    """Test strategy management endpoints"""
    
    @pytest.fixture
    def auth_headers(self):
        """Get authenticated headers"""
        response = client.post(
            "/token",
            data={"username": "admin", "password": "admin123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_strategies(self, auth_headers):
        """Test strategies list"""
        response = client.get("/api/v1/strategies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "name" in data[0]
            assert "enabled" in data[0]
    
    def test_update_strategy(self, auth_headers):
        """Test strategy update"""
        config = {
            "name": "QuantumMomentum",
            "enabled": True,
            "risk_per_trade": 0.02,
            "max_positions": 5,
            "symbols": ["AAPL", "MSFT"]
        }
        response = client.put(
            "/api/v1/strategies/QuantumMomentum",
            json=config,
            headers=auth_headers
        )
        assert response.status_code == 200
    
    def test_start_strategy(self, auth_headers):
        """Test strategy start"""
        response = client.post(
            "/api/v1/strategies/QuantumMomentum/start",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
    
    def test_stop_strategy(self, auth_headers):
        """Test strategy stop"""
        response = client.post(
            "/api/v1/strategies/QuantumMomentum/stop",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


@pytest.mark.asyncio
class TestWebSocket:
    """Test WebSocket connections"""
    
    async def test_websocket_connection(self):
        """Test WebSocket market data connection"""
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            with client.websocket_connect("/ws/market-data") as websocket:
                data = websocket.receive_json()
                assert "timestamp" in data
                assert "portfolio_value" in data


class TestMetrics:
    """Test Prometheus metrics endpoint"""
    
    def test_metrics_endpoint(self):
        """Test metrics are exposed"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=loki.api", "--cov-report=html"])
