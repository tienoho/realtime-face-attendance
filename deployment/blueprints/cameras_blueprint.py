"""Camera and processing routes blueprint."""

from flask import Blueprint

try:
    from deployment.services import camera_service
except ImportError:
    from services import camera_service


def create_cameras_blueprint(runtime):
    cameras_bp = Blueprint("cameras_api", __name__, url_prefix="/api")

    @cameras_bp.route("/cameras", methods=["GET"])
    @runtime.token_required
    def get_cameras_route(current_user):
        return camera_service.get_cameras(runtime, current_user)


    @cameras_bp.route("/cameras", methods=["POST"])
    @runtime.token_required
    def add_camera_route(current_user):
        return camera_service.add_camera(runtime, current_user)


    @cameras_bp.route("/cameras/<camera_id>", methods=["DELETE"])
    @runtime.token_required
    def remove_camera_route(current_user, camera_id):
        return camera_service.remove_camera(runtime, current_user, camera_id)


    @cameras_bp.route("/cameras/<camera_id>/start", methods=["POST"])
    @runtime.token_required
    def start_camera_route(current_user, camera_id):
        return camera_service.start_camera(runtime, current_user, camera_id)


    @cameras_bp.route("/cameras/<camera_id>/stop", methods=["POST"])
    @runtime.token_required
    def stop_camera_route(current_user, camera_id):
        return camera_service.stop_camera(runtime, current_user, camera_id)


    @cameras_bp.route("/cameras/<camera_id>/frame", methods=["GET"])
    @runtime.token_required
    def get_camera_frame_route(current_user, camera_id):
        return camera_service.get_camera_frame(runtime, current_user, camera_id)


    @cameras_bp.route("/processing/stats", methods=["GET"])
    @runtime.token_required
    def get_processing_stats_route(current_user):
        return camera_service.get_processing_stats(runtime, current_user)


    @cameras_bp.route("/processing/config", methods=["GET"])
    @runtime.token_required
    def get_processing_config_route(current_user):
        return camera_service.get_processing_config(runtime, current_user)


    @cameras_bp.route("/processing/config", methods=["POST"])
    @runtime.token_required
    def update_processing_config_route(current_user):
        return camera_service.update_processing_config(runtime, current_user)


    @cameras_bp.route("/streaming/config", methods=["GET"])
    @runtime.token_required
    def get_streaming_config_route(current_user):
        return camera_service.get_streaming_config(runtime, current_user)


    @cameras_bp.route("/streaming/config", methods=["POST"])
    @runtime.token_required
    def update_streaming_config_route(current_user):
        return camera_service.update_streaming_config(runtime, current_user)

    @cameras_bp.route("/cameras/discover", methods=["POST"])
    @runtime.token_required
    def discover_cameras_route(current_user):
        return camera_service.discover_cameras(runtime, current_user)

    @cameras_bp.route("/cameras/discover/<job_id>", methods=["GET"])
    @runtime.token_required
    def get_discovery_result_route(current_user, job_id):
        return camera_service.get_discovery_result(runtime, current_user, job_id)

    return cameras_bp
