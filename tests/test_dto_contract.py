"""
DTO contract tests for standardized FE-BE envelope responses.
"""

from deployment.services import auth_service, student_service
from deployment.services.dto_service import error_response, success_response


class TestDTOEnvelopeContracts:
    def test_login_success_envelope_shape(self, client, monkeypatch):
        def fake_login(rt):
            del rt
            return success_response(
                {"token": "fake-token", "user_id": 1, "username": "testuser"},
                message="Login successful",
                status=200,
            )

        monkeypatch.setattr(auth_service, "login", fake_login)

        response = client.post(
            "/api/login",
            json={"username": "testuser", "password": "password"},
            content_type="application/json",
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert isinstance(payload["message"], str)
        assert isinstance(payload["data"], dict)
        assert "token" in payload["data"]
        assert "error" not in payload

    def test_login_error_envelope_shape(self, client, monkeypatch):
        def fake_login(rt):
            del rt
            return error_response("INVALID_CREDENTIALS", "Invalid credentials", 401)

        monkeypatch.setattr(auth_service, "login", fake_login)

        response = client.post(
            "/api/login",
            json={"username": "testuser", "password": "wrong"},
            content_type="application/json",
        )

        assert response.status_code == 401
        payload = response.get_json()
        assert payload["success"] is False
        assert isinstance(payload["message"], str)
        assert isinstance(payload["error"], dict)
        assert payload["error"]["code"] == "INVALID_CREDENTIALS"
        assert payload["error"]["message"] == "Invalid credentials"

    def test_students_missing_token_returns_error_envelope(self, client):
        response = client.get("/api/students")

        assert response.status_code == 401
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "TOKEN_MISSING"
        assert "data" not in payload

    def test_students_success_envelope_shape(self, client, auth_headers, monkeypatch):
        def fake_get_students(rt, current_user):
            del rt, current_user
            return success_response(
                {"students": [{"student_id": "S001", "name": "Test User", "is_active": True}]},
                message="Students fetched successfully",
                status=200,
            )

        monkeypatch.setattr(student_service, "get_students", fake_get_students)

        response = client.get("/api/students", headers=auth_headers)

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert isinstance(payload["data"], dict)
        assert "students" in payload["data"]
        assert isinstance(payload["data"]["students"], list)

    def test_health_endpoint_keeps_envelope_and_legacy_fields(self, client):
        response = client.get("/api/health")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert "data" in payload
        # Backward-compatible top-level fields
        assert "status" in payload
        assert "timestamp" in payload
