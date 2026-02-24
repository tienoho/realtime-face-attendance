"""Attendance routes blueprint."""

from flask import Blueprint

try:
    from deployment.services import attendance_service
except ImportError:
    from services import attendance_service


def create_attendance_blueprint(runtime):
    attendance_bp = Blueprint("attendance_api", __name__, url_prefix="/api")

    @attendance_bp.route("/attendance", methods=["POST"])
    @runtime.token_required
    def mark_attendance_route(current_user):
        return attendance_service.mark_attendance(runtime, current_user)


    @attendance_bp.route("/attendance/report", methods=["GET"])
    @runtime.token_required
    def get_attendance_report_route(current_user):
        return attendance_service.get_attendance_report(runtime, current_user)


    @attendance_bp.route("/attendance/recent", methods=["GET"])
    @runtime.token_required
    def get_recent_attendance_route(current_user):
        return attendance_service.get_recent_attendance(runtime, current_user)

    return attendance_bp
