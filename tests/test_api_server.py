"""Tests for API server utilities."""
import pytest
from desktop_pet.api_server import ApiServer


class MockPet:
    """Mock pet object for testing."""
    class MockAPI:
        def get_position(self):
            return {"x": 100, "y": 200}

        def get_state(self):
            return "IDLE"

        def get_mode(self):
            return "random"

        def get_available_animations(self):
            return ["sit", "walk", "sleep"]

        def set_mode(self, mode):
            return True

        def move_to(self, x, y):
            return True

        def move_by(self, dx, dy):
            return True

        def move_to_edge(self, edge):
            return True

        def play_animation(self, name):
            return True

        def play_walk(self, direction):
            return True

    api = MockAPI()


def test_api_server_configure():
    """Test API server configuration."""
    server = ApiServer(MockPet())

    server.configure("127.0.0.1", 9000)

    assert server._host == "127.0.0.1"
    assert server._port == 9000


def test_api_server_ip_whitelist():
    """Test IP whitelist management."""
    server = ApiServer(MockPet())

    # Default whitelist
    assert "127.0.0.1" in server.get_allowed_ips()

    # Add IP
    server.add_allowed_ip("192.168.1.1")
    assert "192.168.1.1" in server.get_allowed_ips()

    # Remove IP
    server.remove_allowed_ip("192.168.1.1")
    assert "192.168.1.1" not in server.get_allowed_ips()

    # Set custom whitelist
    server.set_allowed_ips(["10.0.0.1"])
    assert server.get_allowed_ips() == ["10.0.0.1"]


def test_validate_coordinates():
    """Test coordinate validation."""
    server = ApiServer(MockPet())

    # Valid coordinates
    assert server._validate_coordinates({"x": 100, "y": 200}) == (100, 200)
    assert server._validate_coordinates({"x": 0, "y": 0}) == (0, 0)

    # Invalid coordinates
    assert server._validate_coordinates({"x": 99999, "y": 0}) is None
    assert server._validate_coordinates({"x": -99999, "y": 0}) is None


def test_validate_delta():
    """Test movement delta validation."""
    server = ApiServer(MockPet())

    assert server._validate_delta({"dx": 50, "dy": -30}) == (50, -30)
    assert server._validate_delta({"dx": 0, "dy": 0}) == (0, 0)


def test_is_safe_callback_url():
    """Test callback URL safety validation."""
    server = ApiServer(MockPet())

    # Safe URLs
    assert server._is_safe_callback_url("https://example.com/callback") is True
    assert server._is_safe_callback_url("http://api.example.com/webhook") is True

    # Unsafe URLs (internal networks)
    assert server._is_safe_callback_url("http://localhost/callback") is False
    assert server._is_safe_callback_url("http://127.0.0.1/callback") is False
    assert server._is_safe_callback_url("http://192.168.1.1/callback") is False
    assert server._is_safe_callback_url("http://10.0.0.1/callback") is False

    # Invalid schemes
    assert server._is_safe_callback_url("ftp://example.com/callback") is False
    assert server._is_safe_callback_url("javascript:alert(1)") is False


def test_get_client_ip_x_forwarded_for():
    """Test client IP extraction from X-Forwarded-For header."""
    server = ApiServer(MockPet())

    class MockRequest:
        headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "203.0.113.1"


def test_get_client_ip_x_real_ip():
    """Test client IP extraction from X-Real-IP header."""
    server = ApiServer(MockPet())

    class MockRequest:
        headers = {"X-Real-IP": "203.0.113.2"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "203.0.113.2"


def test_get_client_ip_remote():
    """Test client IP extraction from remote address."""
    server = ApiServer(MockPet())

    class MockRequest:
        headers = {}
        remote = "192.168.1.100"

    ip = server._get_client_ip(MockRequest())
    assert ip == "192.168.1.100"