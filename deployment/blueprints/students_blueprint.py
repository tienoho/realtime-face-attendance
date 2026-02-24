"""Student routes blueprint."""

from flask import Blueprint

try:
    from deployment.services import student_service
except ImportError:
    from services import student_service


def create_students_blueprint(runtime):
    students_bp = Blueprint("students_api", __name__, url_prefix="/api")

    @students_bp.route("/register-student", methods=["POST"])
    @runtime.token_required
    def register_student_route(current_user):
        return student_service.register_student(runtime, current_user)


    @students_bp.route("/register-student-multi", methods=["POST"])
    @runtime.token_required
    def register_student_multi_route(current_user):
        return student_service.register_student_multi(runtime, current_user)


    @students_bp.route("/register-face-capture", methods=["POST"])
    @runtime.token_required
    def register_face_capture_route(current_user):
        return student_service.register_face_capture(runtime, current_user)


    @students_bp.route("/register-face", methods=["POST"])
    @runtime.token_required
    def register_face_route(current_user):
        return student_service.register_face(runtime, current_user)


    @students_bp.route("/students", methods=["GET"])
    @runtime.token_required
    def get_students_route(current_user):
        return student_service.get_students(runtime, current_user)

    return students_bp
