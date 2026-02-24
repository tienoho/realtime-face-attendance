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

    return auth_bp
