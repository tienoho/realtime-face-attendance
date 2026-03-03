"""Authentication routes blueprint."""

from flask import Blueprint

try:
    from deployment.services import auth_service
except ImportError:
    from services import auth_service


def create_auth_blueprint(runtime):
    auth_bp = Blueprint("auth_api", __name__, url_prefix="/api")

    @auth_bp.route("/login", methods=["POST"])
    @runtime.limiter.limit("10 per minute")
    def login_route():
        return auth_service.login(runtime)

    # H-AUTH-001: Add refresh token endpoint
    @auth_bp.route("/refresh", methods=["POST"])
    @runtime.limiter.limit("20 per minute")
    def refresh_route():
        return auth_service.refresh_access_token(runtime)

    # H-AUTH-001: Add logout endpoint
    @auth_bp.route("/logout", methods=["POST"])
    @runtime.jwt_required()
    def logout_route():
        return auth_service.logout(runtime)

    return auth_bp
