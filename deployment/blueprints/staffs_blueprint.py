"""Staff routes blueprint."""

from flask import Blueprint

try:
    from deployment.services import staff_service
except ImportError:
    from services import staff_service


def create_staffs_blueprint(runtime):
    staffs_bp = Blueprint("staffs_api", __name__, url_prefix="/api")

    @staffs_bp.route("/register-staff", methods=["POST"])
    @runtime.token_required
    def register_staff_route(current_user):
        return staff_service.register_staff(runtime, current_user)


    @staffs_bp.route("/register-staff-multi", methods=["POST"])
    @runtime.token_required
    def register_staff_multi_route(current_user):
        return staff_service.register_staff_multi(runtime, current_user)


    @staffs_bp.route("/register-face-capture", methods=["POST"])
    @runtime.token_required
    def register_face_capture_route(current_user):
        return staff_service.register_face_capture(runtime, current_user)


    @staffs_bp.route("/register-face", methods=["POST"])
    @runtime.token_required
    def register_face_route(current_user):
        return staff_service.register_face(runtime, current_user)


    @staffs_bp.route("/staffs", methods=["GET"])
    @runtime.token_required
    def get_staffs_route(current_user):
        return staff_service.get_staffs(runtime, current_user)

    return staffs_bp
