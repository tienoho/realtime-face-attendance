"""Camera, processing and streaming service layer."""

import ipaddress
import socket
from urllib.parse import urlparse

try:
    from deployment.services.dto_service import error_response, success_response
except ImportError:
    from services.dto_service import error_response, success_response

# H-SSRF-001 FIX: Allowed IP ranges for camera URLs (whitelist)
ALLOWED_IP_RANGES = [
    # Private ranges
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    # Localhost
    ipaddress.ip_network('127.0.0.0/8'),
]

# Allowed hostnames (domain whitelist)
ALLOWED_HOSTS = {
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
}


def is_private_ip(host: str) -> bool:
    """
    Check if host is a private/internal IP address.
    H-SSRF-001 FIX: Prevent SSRF attacks by blocking internal network access.
    """
    try:
        # Try to resolve hostname first
        try:
            addr_info = socket.getaddrinfo(host, None)
            ips = set(info[4][0] for info in addr_info)
        except socket.gaierror:
            # If resolution fails, check if it's an IP directly
            ips = {host}
        
        for ip_str in ips:
            try:
                ip = ipaddress.ip_address(ip_str)
                for network in ALLOWED_IP_RANGES:
                    if ip in network:
                        return True
            except (ValueError, TypeError):
                continue
        
        return False
    except Exception:
        # If anything fails, assume it's not private (fail open for usability)
        return False


def validate_camera_url(url: str) -> tuple[bool, str]:
    """
    Validate camera URL for SSRF protection.
    H-SSRF-001 FIX: Only allow specific URLs or private networks.
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not url:
        return True, ""  # No URL is valid (e.g., USB camera)
    
    try:
        parsed = urlparse(url)
        host = parsed.hostname or parsed.host
        
        if not host:
            return True, ""  # No host in URL
        
        # Allow localhost
        if host in ALLOWED_HOSTS:
            return True, ""
        
        # Check if it's a private IP
        if is_private_ip(host):
            return True, ""
        
        # Block external URLs
        return False, f"Camera URL host '{host}' is not allowed. Only localhost or private network URLs are permitted."
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"


def get_cameras(rt, current_user):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)
    return success_response(rt.camera_manager.get_status(), message="Cameras fetched successfully", status=200)


def add_camera(rt, current_user):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)

    data = rt.request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response("INVALID_PAYLOAD", "Invalid request payload", 400)

    camera_id = data.get("camera_id")
    if not isinstance(camera_id, str) or not camera_id.strip():
        return error_response("MISSING_CAMERA_ID", "camera_id is required", 400)
    camera_id = camera_id.strip()

    camera_type = str(data.get("type", "usb")).lower()

    # DTO normalization for FE-BE compatibility.
    # FE may send stream_url/host while camera connectors expect url/ip.
    camera_config = dict(data)
    if "stream_url" in camera_config and "url" not in camera_config:
        camera_config["url"] = camera_config.get("stream_url")
    if "host" in camera_config and "ip" not in camera_config:
        camera_config["ip"] = camera_config.get("host")
    
    # H-SSRF-001 FIX: Validate camera URLs before connecting
    url_to_check = camera_config.get("url") or camera_config.get("rtsp_url") or camera_config.get("stream_url")
    if url_to_check:
        is_valid, error = validate_camera_url(url_to_check)
        if not is_valid:
            rt.logger.warning(f"SSRF protection blocked camera {camera_id}: {error}")
            return error_response("INVALID_CAMERA_URL", error, 400)

    if rt.camera_manager.add_camera(camera_id, camera_type, camera_config):
        started = rt.camera_manager.start_camera(camera_id)
        message = (
            f"Camera {camera_id} added and started"
            if started
            else f"Camera {camera_id} added but failed to start"
        )
        return success_response(
            {"camera_id": camera_id, "started": bool(started)},
            message=message,
            status=200,
        )

    return error_response("ADD_CAMERA_FAILED", "Failed to add camera", 500)


def remove_camera(rt, current_user, camera_id):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)

    if rt.camera_manager.remove_camera(camera_id):
        return success_response(
            {"camera_id": camera_id},
            message=f"Camera {camera_id} removed",
            status=200,
        )

    return error_response("CAMERA_NOT_FOUND", "Camera not found", 404)


def start_camera(rt, current_user, camera_id):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)

    if rt.camera_manager.start_camera(camera_id):
        return success_response(
            {"camera_id": camera_id},
            message=f"Camera {camera_id} started",
            status=200,
        )

    return error_response("START_CAMERA_FAILED", "Failed to start camera", 500)


def stop_camera(rt, current_user, camera_id):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)

    if camera_id not in rt.camera_manager.cameras:
        return error_response("CAMERA_NOT_FOUND", "Camera not found", 404)

    rt.camera_manager.stop_camera(camera_id)
    return success_response(
        {"camera_id": camera_id},
        message=f"Camera {camera_id} stopped",
        status=200,
    )


def get_camera_frame(rt, current_user, camera_id):
    del current_user
    if not rt.camera_manager:
        return error_response("CAMERA_SYSTEM_UNAVAILABLE", "Camera system not available", 500)

    if camera_id not in rt.camera_manager.cameras:
        return error_response("CAMERA_NOT_FOUND", "Camera not found", 404)

    frame, timestamp = rt.camera_manager.get_latest_frame(camera_id)
    if frame is None:
        return error_response("FRAME_NOT_AVAILABLE", "No frame available", 404)

    encode_param = [int(rt.cv2.IMWRITE_JPEG_QUALITY), 80]
    _, buffer = rt.cv2.imencode(".jpg", frame, encode_param)
    frame_base64 = rt.base64.b64encode(buffer).decode("utf-8")

    return success_response(
        {
            "camera_id": camera_id,
            "frame": f"data:image/jpeg;base64,{frame_base64}",
            "timestamp": timestamp,
        },
        message="Camera frame fetched successfully",
        status=200,
    )


def get_processing_stats(rt, current_user):
    del current_user
    if not rt.frame_processor:
        return success_response({}, message="Frame processor unavailable", status=200)
    return success_response(rt.frame_processor.get_stats(), message="Processing stats fetched successfully", status=200)


def get_processing_config(rt, current_user):
    del current_user
    if not rt.frame_processor:
        return error_response("FRAME_PROCESSOR_UNAVAILABLE", "Frame processor not available", 500)

    config = rt.frame_processor.get_config()
    return success_response(config, message="Processing config fetched successfully", status=200)


def update_processing_config(rt, current_user):
    del current_user
    if not rt.frame_processor:
        return error_response("FRAME_PROCESSOR_UNAVAILABLE", "Frame processor not available", 500)

    data = rt.request.get_json(silent=True)
    if not data:
        return error_response("MISSING_CONFIGURATION", "No configuration provided", 400)

    try:
        if "det_threshold" in data:
            threshold = float(data["det_threshold"])
            if 0.0 <= threshold <= 1.0:
                rt.frame_processor.set_detection_threshold(threshold)
            else:
                return error_response(
                    "VALIDATION_ERROR",
                    "det_threshold must be between 0.0 and 1.0",
                    400,
                )

        if "recognition_threshold" in data:
            threshold = float(data["recognition_threshold"])
            if 0.0 <= threshold <= 1.0:
                rt.frame_processor.set_recognition_threshold(threshold)
            else:
                return error_response(
                    "VALIDATION_ERROR",
                    "recognition_threshold must be between 0.0 and 1.0",
                    400,
                )

        if "frame_skip" in data:
            skip = int(data["frame_skip"])
            if 1 <= skip <= 10:
                rt.frame_processor.set_frame_skip(skip)
            else:
                return error_response(
                    "VALIDATION_ERROR",
                    "frame_skip must be between 1 and 10",
                    400,
                )
    except (TypeError, ValueError):
        return error_response("VALIDATION_ERROR", "Invalid processing configuration values", 400)

    rt.logger.info(f"Processing config updated: {data}")
    return success_response(
        rt.frame_processor.get_config(),
        message="Configuration updated",
        status=200,
    )


def get_streaming_config(rt, current_user):
    del current_user
    return success_response(
        {
            "quality": rt.ENCODE_QUALITY,
            "fps": rt.STREAM_FPS,
            "resize_width": rt.FRAME_RESIZE_WIDTH,
        },
        message="Streaming config fetched successfully",
        status=200,
    )


def update_streaming_config(rt, current_user):
    del current_user

    data = rt.request.get_json(silent=True)
    if not data:
        return error_response("MISSING_CONFIGURATION", "No configuration provided", 400)

    try:
        if "quality" in data:
            quality = int(data["quality"])
            if 10 <= quality <= 100:
                rt.ENCODE_QUALITY = quality
            else:
                return error_response("VALIDATION_ERROR", "Quality must be between 10 and 100", 400)

        if "fps" in data:
            fps = int(data["fps"])
            if 1 <= fps <= 30:
                rt.STREAM_FPS = fps
            else:
                return error_response("VALIDATION_ERROR", "FPS must be between 1 and 30", 400)

        if "resize_width" in data:
            width = int(data["resize_width"])
            if 320 <= width <= 1920:
                rt.FRAME_RESIZE_WIDTH = width
            else:
                return error_response(
                    "VALIDATION_ERROR",
                    "Resize width must be between 320 and 1920",
                    400,
                )
    except (TypeError, ValueError):
        return error_response("VALIDATION_ERROR", "Invalid streaming configuration values", 400)

    rt.logger.info(
        f"Streaming config updated: quality={rt.ENCODE_QUALITY}, fps={rt.STREAM_FPS}, "
        f"width={rt.FRAME_RESIZE_WIDTH}"
    )

    return success_response(
        {
            "quality": rt.ENCODE_QUALITY,
            "fps": rt.STREAM_FPS,
            "resize_width": rt.FRAME_RESIZE_WIDTH,
        },
        message="Configuration updated",
        status=200,
    )
