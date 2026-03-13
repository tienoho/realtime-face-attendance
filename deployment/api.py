# Standard library imports
import os
import sys
import base64
import json
import logging
from logging.handlers import RotatingFileHandler
import re
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

# Third-party imports
import cv2
import numpy as np
import psycopg2  # For PostgreSQL support
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, Unauthorized, InternalServerError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Module logger must exist before any optional imports use it.
logger = logging.getLogger(__name__)

# Add deployment directory and project root to path as early as possible.
# This allows optional sibling imports (e.g. face_recognition.*) in script mode.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# MediaPipe import (used by legacy detection path)
try:
    import mediapipe as mp
except ImportError:
    mp = None

# InsightFace imports
try:
    from insightface.app import FaceAnalysis
except ImportError:
    logger.warning("InsightFace not installed, using legacy methods")
    FaceAnalysis = None

# Data augmentation imports
try:
    from face_recognition.augmentation import DataAugmentor, augment_face_batch
except ImportError:
    logger.warning("Data augmentation module not found")
    DataAugmentor = None
    augment_face_batch = None

# ============================================================
# DATABASE TYPE SELECTION
# ============================================================

# Set DB_TYPE to 'postgresql' (only PostgreSQL is supported)
DB_TYPE = os.getenv('DB_TYPE', 'postgresql').lower()

# Import appropriate database module
if DB_TYPE == 'postgresql':
    try:
        from database import get_db_connection, init_db_pool, close_db_pool, get_table_list, check_db_health
        logger.info(f"Using PostgreSQL database (DB_TYPE={DB_TYPE})")
    except ImportError as e:
        logger.error(f"PostgreSQL module error: {e}")
        raise
else:
    logger.error(f"Unsupported DB_TYPE: {DB_TYPE}. Only 'postgresql' is supported.")
    raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}. Only 'postgresql' is supported.")

# ============================================================
# FLASK & SOCKETIO SETUP
# ============================================================

app = Flask(__name__)

# CORS configuration - require explicit origins in production
CORS_CONFIG = os.getenv('CORS_ORIGINS', '').strip()
if not CORS_CONFIG:
    # Require explicit CORS origins only in production; default localhost origins in dev/test/local.
    flask_env = (os.getenv('FLASK_ENV') or os.getenv('ENV') or '').strip().lower()
    if flask_env in {'production', 'prod'}:
        raise ValueError("CORS_ORIGINS environment variable must be set in production")
    else:
        cors_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
else:
    cors_origins = [origin.strip() for origin in CORS_CONFIG.split(',') if origin.strip()]
    if not cors_origins:
        raise ValueError("CORS_ORIGINS contains no valid origins")

CORS(app, resources={r"/api/*": {"origins": cors_origins}})

# SocketIO setup
socketio = SocketIO(app, cors_allowed_origins=cors_origins, async_mode='eventlet')

# ============================================================
# CONFIGURATION
# ============================================================

def validate_config():
    required_vars = ['SECRET_KEY', 'DB_PASSWORD']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")
    
    if os.getenv('SECRET_KEY') == 'your-secret-key-change-this':
        raise ValueError("SECRET_KEY must be changed from default value in production")

try:
    validate_config()
except ValueError as e:
    logging.warning(f"Configuration validation warning: {e}")

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("SECRET_KEY environment variable is required")

app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'TrainingImage')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MODEL_PATH'] = os.getenv('MODEL_PATH', 'model/Trainer.yml')
app.config['CASCADE_PATH'] = os.getenv('CASCADE_PATH', 'model/Haarcascade.xml')
app.config['LABEL_MAP_PATH'] = os.getenv('LABEL_MAP_PATH', 'model/label_map.json')

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),  # PostgreSQL default
    'user': os.getenv('DB_USER', 'faceuser'),  # PostgreSQL default user
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'face_attendance'),
    'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
    'client_encoding': 'UTF8',
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv('REDIS_URL', 'memory://')
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('api.log', maxBytes=10 * 1024 * 1024, backupCount=5),
        logging.StreamHandler()
    ]
)
# ============================================================
# MODEL CACHE
# ============================================================

_model_cache = {
    'face_detector': None,
    'face_recognizer': None,
    'mp_face_detection': None,
    'label_map': None,
}
_mediapipe_unavailable_logged = False

# Validation patterns and blocked tokens
STUDENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
NAME_PATTERN = re.compile(r'^[a-zA-Z\s]+$')
SUBJECT_PATTERN = re.compile(r'^[a-zA-Z0-9\s_-]+$')
FORBIDDEN_STUDENT_ID_TOKENS = (
    ';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute', 'insert', 'delete', 'update', 'drop'
)
DANGEROUS_NAME_TOKENS = ('<', '>', '"', "'", '&', ';', 'script', 'javascript')

def get_cached_face_detector():
    if _model_cache['face_detector'] is None:
        cascade_path = app.config['CASCADE_PATH']
        if os.path.exists(cascade_path):
            _model_cache['face_detector'] = cv2.CascadeClassifier(cascade_path)
            logger.info(f"Loaded Haar Cascade from {cascade_path}")
        else:
            _model_cache['face_detector'] = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
    return _model_cache['face_detector']

def get_cached_face_recognizer():
    if _model_cache['face_recognizer'] is None:
        model_path = app.config['MODEL_PATH']
        if os.path.exists(model_path):
            try:
                recognizer = cv2.face.LBPHFaceRecognizer_create()
                recognizer.read(model_path)
                _model_cache['face_recognizer'] = recognizer
                logger.info(f"Face recognition model loaded from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load face recognition model: {e}")
    return _model_cache['face_recognizer']

def get_cached_label_map():
    if _model_cache['label_map'] is None:
        label_map_path = app.config.get('LABEL_MAP_PATH')
        if label_map_path and os.path.exists(label_map_path):
            try:
                with open(label_map_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    _model_cache['label_map'] = {str(k): str(v) for k, v in loaded.items()}
                else:
                    logger.warning(f"Invalid label map format in {label_map_path}, expected object")
                    _model_cache['label_map'] = {}
            except Exception as e:
                logger.warning(f"Could not load label map from {label_map_path}: {e}")
                _model_cache['label_map'] = {}
        else:
            _model_cache['label_map'] = {}
    return _model_cache['label_map']

def get_mediapipe_detector():
    if mp is None:
        raise RuntimeError("MediaPipe is not installed")
    if _model_cache['mp_face_detection'] is None:
        _model_cache['mp_face_detection'] = mp.solutions.face_detection
    return _model_cache['mp_face_detection']

# ============================================================
# CAMERA MANAGER (Realtime Support)
# ============================================================

camera_manager = None
frame_processor = None
attendance_engine = None
CAMERA_SYSTEM_AVAILABLE = False

# Connected clients for streaming
connected_clients = set()
client_lock = threading.Lock()
STREAM_QUALITY = 80
STREAM_FPS = 10

# Lock for streaming config
config_lock = threading.Lock()

# Streaming client subscriptions
# {camera_id: {sid: True}}
streaming_subscriptions = {}
streaming_lock = threading.Lock()

# Frame encoding settings
ENCODE_QUALITY = 80
FRAME_RESIZE_WIDTH = 640

# Use get_db_connection from the imported database module (PostgreSQL only)

def allowed_file(filename):
    if not isinstance(filename, str) or not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_student_id(student_id):
    if not isinstance(student_id, str):
        return False, "Student ID must be 3-50 characters"
    student_id = student_id.strip()
    if not student_id or len(student_id) < 3 or len(student_id) > 50:
        return False, "Student ID must be 3-50 characters"
    if not STUDENT_ID_PATTERN.match(student_id):
        return False, "Student ID can only contain alphanumeric, underscore, hyphen"
    student_id_lower = student_id.lower()
    for word in FORBIDDEN_STUDENT_ID_TOKENS:
        if word in student_id_lower:
            return False, "Student ID contains forbidden characters"
    return True, None

def validate_name(name):
    if not isinstance(name, str):
        return False, "Name must be 2-100 characters"
    name = name.strip()
    if not name or len(name) < 2 or len(name) > 100:
        return False, "Name must be 2-100 characters"
    if not NAME_PATTERN.match(name):
        return False, "Name can only contain letters and spaces"
    name_lower = name.lower()
    for char in DANGEROUS_NAME_TOKENS:
        if char in name_lower:
            return False, "Name contains forbidden characters"
    return True, None

def validate_subject(subject):
    if not isinstance(subject, str):
        return False, "Subject must be 2-100 characters"
    subject = subject.strip()
    if not subject or len(subject) < 2 or len(subject) > 100:
        return False, "Subject must be 2-100 characters"
    if not SUBJECT_PATTERN.match(subject):
        return False, "Subject can only contain letters, numbers, spaces, underscore, hyphen"
    return True, None

def detect_faces_mediapipe(image):
    global _mediapipe_unavailable_logged

    if image is None or image.size == 0:
        return []

    if mp is None:
        if not _mediapipe_unavailable_logged:
            logger.warning("MediaPipe is not installed. Falling back to Haar Cascade face detection.")
            _mediapipe_unavailable_logged = True
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return detect_faces_haar(gray)

    try:
        mp_face_detection = get_mediapipe_detector()
        with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
            results = face_detection.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            if results.detections:
                boxes = []
                h, w, _ = image.shape
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    x = int(bbox.xmin * w)
                    y = int(bbox.ymin * h)
                    width = int(bbox.width * w)
                    height = int(bbox.height * h)
                    boxes.append((x, y, width, height))
                return boxes
    except Exception as e:
        logger.warning(f"MediaPipe detection failed, falling back to Haar Cascade: {e}")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return detect_faces_haar(gray)

    return []

def detect_faces_haar(gray_image):
    cascade = get_cached_face_detector()
    faces = cascade.detectMultiScale(gray_image, 1.3, 5)
    return list(faces) if faces is not None else []

def recognize_face(gray_face):
    recognizer = get_cached_face_recognizer()
    if recognizer is None:
        return None, 0
    try:
        label, confidence = recognizer.predict(gray_face)
        label_map = get_cached_label_map()
        if not label_map:
            logger.error("Label map is unavailable. Rejecting LBPH recognition result.")
            return None, 0

        student_id = label_map.get(str(label))
        if not student_id:
            logger.error(f"Predicted label {label} is not in label map. Rejecting recognition result.")
            return None, 0

        return student_id, confidence
    except Exception as e:
        logger.error(f"Face recognition error: {e}")
        return None, 0

# ============================================================
# CALLBACKS FOR CAMERA SYSTEM
# ============================================================

def on_frame_captured(camera_id, frame):
    if frame_processor:
        frame_processor.process_frame_async(camera_id, frame)

def on_faces_detected(camera_id, result):
    if result.get('faces_detected', 0) > 0:
        socketio.emit('faces_detected', {
            'camera_id': camera_id,
            'count': result['faces_detected'],
            'timestamp': result.get('timestamp')
        })

def on_faces_recognized(camera_id, recognized):
    """
    Callback when faces are recognized.
    H-ATT-001 FIX: Also record attendance to database via attendance_engine.
    """
    if recognized:
        for face in recognized:
            person_id = face.get('person_id')
            confidence = face.get('confidence')
            
            # H-ATT-001 FIX: Record attendance to database
            if attendance_engine and person_id:
                try:
                    attendance_engine.record_attendance(
                        person_id=person_id,
                        camera_id=camera_id,
                        confidence=confidence,
                        metadata={'bbox': face.get('bbox')}
                    )
                except Exception as e:
                    logger.error(f"Failed to record attendance: {e}")
            
            # Also emit to socket for real-time notifications
            socketio.emit('attendance', {
                'camera_id': camera_id,
                'person_id': person_id,
                'confidence': confidence,
                'timestamp': time.time()
            })


def on_frame_for_streaming(camera_id, frame):
    """
    Callback to emit camera frames to subscribed WebSocket clients.
    This is registered with the camera manager to receive all frames.
    """
    with streaming_lock:
        if camera_id not in streaming_subscriptions:
            return
        subscribers = streaming_subscriptions.get(camera_id, {})
        if not subscribers:
            return
    
    # Encode frame to JPEG
    try:
        # Resize frame if too large (for bandwidth optimization)
        h, w = frame.shape[:2]
        if w > FRAME_RESIZE_WIDTH:
            ratio = FRAME_RESIZE_WIDTH / w
            new_w = FRAME_RESIZE_WIDTH
            new_h = int(h * ratio)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        # Encode to JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), ENCODE_QUALITY]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        frame_data = f'data:image/jpeg;base64,{frame_base64}'
        timestamp = time.time()
        
        # Emit to all subscribers
        with streaming_lock:
            subscribers = streaming_subscriptions.get(camera_id, {})
        
        for sid in list(subscribers.keys()):
            try:
                socketio.emit('camera_frame', {
                    'camera_id': camera_id,
                    'frame': frame_data,
                    'timestamp': timestamp
                }, room=sid)
            except Exception as e:
                logger.warning(f"Error emitting frame to {sid}: {e}")
                # Remove disconnected client
                with streaming_lock:
                    if sid in streaming_subscriptions.get(camera_id, {}):
                        del streaming_subscriptions[camera_id][sid]
                        
    except Exception as e:
        logger.error(f"Error encoding frame for streaming: {e}")


def initialize_camera_system():
    """Initialize camera manager and processing callbacks."""
    global camera_manager, frame_processor, attendance_engine, CAMERA_SYSTEM_AVAILABLE

    try:
        from cameras.camera_manager import CameraManager
        from cameras.frame_processor import FrameProcessor
        from cameras.attendance_engine import AttendanceEngine

        camera_manager = CameraManager(max_cameras=16, frame_queue_size=5)
        frame_processor = FrameProcessor(
            num_workers=4,
            use_insightface=True,
            det_threshold=0.5,
            recognition_threshold=0.6
        )
        
        # H-ATT-001 FIX: Pass db_pool to attendance engine for DB persistence
        # Get db_pool from the database module
        try:
            from database import get_db_pool
            db_pool = get_db_pool()
        except (ImportError, AttributeError):
            db_pool = None
            logger.warning("DB pool not available for attendance engine")
        
        attendance_engine = AttendanceEngine(db_pool=db_pool, dedup_window=300)

        camera_manager.register_frame_callback(on_frame_captured)
        camera_manager.register_frame_callback(on_frame_for_streaming)
        frame_processor.register_detection_callback(on_faces_detected)
        frame_processor.register_recognition_callback(on_faces_recognized)

        CAMERA_SYSTEM_AVAILABLE = True
        logger.info("Camera system initialized successfully")
    except ImportError as e:
        logger.warning(f"Camera system dependencies are not available: {e}")
        CAMERA_SYSTEM_AVAILABLE = False
        camera_manager = None
        frame_processor = None
        attendance_engine = None
    except RuntimeError as e:
        logger.warning(f"Camera system disabled due to runtime dependency issue: {e}")
        CAMERA_SYSTEM_AVAILABLE = False
        camera_manager = None
        frame_processor = None
        attendance_engine = None
    except Exception:
        logger.exception("Unexpected error while initializing camera system")
        raise


initialize_camera_system()

# ============================================================
# MODEL TRAINING
# ============================================================

def train_face_recognition_model():
    """
    Train face recognition model from all images in TrainingImage folder.
    This function loads all training images and their labels, then trains
    the LBPH recognizer and saves the model.
    
    Returns:
        dict: Training result with status and details
    """
    try:
        training_folder = app.config['UPLOAD_FOLDER']
        model_path = app.config['MODEL_PATH']
        label_map_path = app.config['LABEL_MAP_PATH']
        
        # Get all image files
        faces = []
        labels = []
        label_to_student_id = {}
        
        # Walk through all subdirectories (each student has their own folder)
        student_ids = sorted([
            student_id for student_id in os.listdir(training_folder)
            if os.path.isdir(os.path.join(training_folder, student_id))
        ])

        for idx, student_id in enumerate(student_ids, start=1):
            student_path = os.path.join(training_folder, student_id)
            label = idx
            label_to_student_id[label] = student_id
            
            # Load all images for this student
            for img_name in os.listdir(student_path):
                if not img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                    
                img_path = os.path.join(student_path, img_name)
                img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                
                if img is not None:
                    faces.append(img)
                    labels.append(label)
        
        if not faces:
            logger.warning("No training images found")
            return {'status': 'error', 'message': 'No training images found', 'images_trained': 0}
        
        # Train the model
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(faces, np.array(labels))
        
        # Ensure model directory exists
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        # Save the model
        recognizer.save(model_path)

        # Persist label -> student_id mapping for inference.
        label_map_dir = os.path.dirname(label_map_path)
        if label_map_dir:
            os.makedirs(label_map_dir, exist_ok=True)
        serializable_label_map = {str(k): v for k, v in label_to_student_id.items()}
        with open(label_map_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_label_map, f, indent=2)
        
        # Update the cached recognizer
        global _model_cache
        _model_cache['face_recognizer'] = recognizer
        _model_cache['label_map'] = serializable_label_map
        
        logger.info(f"Model trained successfully with {len(faces)} images")
        
        return {
            'status': 'success',
            'message': 'Model trained successfully',
            'images_trained': len(faces),
            'unique_labels': len(label_to_student_id)
        }
        
    except Exception as e:
        logger.error(f"Error training model: {str(e)}")
        return {'status': 'error', 'message': str(e), 'images_trained': 0}


def train_model_async():
    """
    Background thread function for model training.
    """
    result = train_face_recognition_model()
    if result['status'] == 'success':
        socketio.emit('model_trained', result)
    else:
        socketio.emit('training_error', result)


# ============================================================
# PIPELINE ACCESSORS (USED BY SERVICE LAYER)
# ============================================================

_face_pipeline = None
_face_pipeline_lock = threading.Lock()

_face_detector = None
_face_detector_lock = threading.Lock()


def get_face_pipeline():
    """Get or create the face recognition pipeline."""
    global _face_pipeline
    with _face_pipeline_lock:
        if _face_pipeline is None:
            try:
                from face_recognition.pipeline import FaceRecognitionPipeline
                _face_pipeline = FaceRecognitionPipeline()
                logger.info("Face Recognition Pipeline initialized for registration")
            except Exception as e:
                logger.error(f"Failed to initialize face pipeline: {e}")
                return None
        return _face_pipeline


def get_face_detector():
    """Get or create the face detector (cached for performance)."""
    global _face_detector
    with _face_detector_lock:
        if _face_detector is None:
            try:
                from face_recognition.detector import FaceDetector
                _face_detector = FaceDetector()
                logger.info("Face Detector initialized and cached")
            except Exception as e:
                logger.warning(f"InsightFace not available: {e}")
                _face_detector = None
        return _face_detector


# ============================================================
# AUTHENTICATION
# ============================================================

def token_required(f):
    try:
        from deployment.services.dto_service import error_response
    except ImportError:
        from services.dto_service import error_response

    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return error_response("TOKEN_MISSING", "Token is missing", 401)

        try:
            if token.startswith('Bearer '):
                token = token.split(" ")[1]

            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except ExpiredSignatureError:
            return error_response("TOKEN_EXPIRED", "Token has expired", 401)
        except InvalidTokenError:
            return error_response("TOKEN_INVALID", "Invalid token", 401)
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return error_response("TOKEN_VALIDATION_FAILED", "Token validation failed", 401)

        return f(current_user, *args, **kwargs)
    return decorator

# ============================================================
# REST API ENDPOINTS
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

# Register API blueprints (route layer)
try:
    from deployment.blueprints.auth_blueprint import create_auth_blueprint
    from deployment.blueprints.students_blueprint import create_students_blueprint
    from deployment.blueprints.attendance_blueprint import create_attendance_blueprint
    from deployment.blueprints.cameras_blueprint import create_cameras_blueprint
except ImportError:
    from blueprints.auth_blueprint import create_auth_blueprint
    from blueprints.students_blueprint import create_students_blueprint
    from blueprints.attendance_blueprint import create_attendance_blueprint
    from blueprints.cameras_blueprint import create_cameras_blueprint

runtime_module = sys.modules[__name__]
app.register_blueprint(create_auth_blueprint(runtime_module))
app.register_blueprint(create_students_blueprint(runtime_module))
app.register_blueprint(create_attendance_blueprint(runtime_module))
app.register_blueprint(create_cameras_blueprint(runtime_module))

# ============================================================
# WEBSOCKET EVENTS
# ============================================================

@socketio.on('connect')
def handle_connect():
    """
    Handle WebSocket connection with JWT authentication.
    Rejects connections without valid token.
    """
    # C-SEC-001 FIX: WebSocket Authentication
    try:
        # Get token from query params or headers
        token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            logger.warning(f"WS connection rejected: missing token from {request.remote_addr}")
            return False  # Reject connection
        
        # Verify JWT token
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user_id = payload.get('user_id')
            request.username = payload.get('username')
            
            # Rate limiting check per user
            if not check_ws_rate_limit(request.user_id):
                logger.warning(f"WS rate limit exceeded for user {request.user_id}")
                return False
            
            logger.info(f"WS authenticated: user={request.username} sid={request.sid}")
            
        except ExpiredSignatureError:
            logger.warning(f"WS connection rejected: expired token from {request.remote_addr}")
            return False
        except InvalidTokenError as e:
            logger.warning(f"WS connection rejected: invalid token from {request.remote_addr}: {e}")
            return False
        
        with client_lock:
            connected_clients.add(request.sid)
        
        emit('connected', {
            'sid': request.sid,
            'user_id': request.user_id,
            'authenticated': True
        })
        
    except Exception as e:
        logger.error(f"WS connection error: {e}")
        return False


def check_ws_rate_limit(user_id: str) -> bool:
    """Simple rate limiting for WebSocket connections."""
    # Implementation using in-memory store (use Redis in production)
    now = time.time()
    key = f"ws_rate_{user_id}"
    
    # Get recent connection attempts
    if not hasattr(check_ws_rate_limit, 'rate_store'):
        check_ws_rate_limit.rate_store = {}
    
    attempts = check_ws_rate_limit.rate_store.get(key, [])
    
    # Filter to last minute
    attempts = [t for t in attempts if now - t < 60]
    
    # Check limit (max 10 connections per minute)
    if len(attempts) >= 10:
        return False
    
    # Record attempt
    attempts.append(now)
    check_ws_rate_limit.rate_store[key] = attempts
    
    return True

@socketio.on('disconnect')
def handle_disconnect():
    with client_lock:
        connected_clients.discard(request.sid)
    
    # Clean up streaming subscriptions
    with streaming_lock:
        for camera_id in list(streaming_subscriptions.keys()):
            if request.sid in streaming_subscriptions.get(camera_id, {}):
                del streaming_subscriptions[camera_id][request.sid]
            if not streaming_subscriptions.get(camera_id, {}):
                if camera_id in streaming_subscriptions:
                    del streaming_subscriptions[camera_id]
    
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('subscribe_camera')
def handle_subscribe_camera(data):
    if not isinstance(data, dict):
        emit('stream_error', {'message': 'Invalid payload'})
        return

    camera_id = data.get('camera_id')
    if camera_id:
        socketio.join_room(f'camera_{camera_id}')
        emit('subscribed', {'camera_id': camera_id})
        logger.info(f"Client {request.sid} subscribed to camera {camera_id}")

@socketio.on('unsubscribe_camera')
def handle_unsubscribe_camera(data):
    if not isinstance(data, dict):
        emit('stream_error', {'message': 'Invalid payload'})
        return

    camera_id = data.get('camera_id')
    if camera_id:
        socketio.leave_room(f'camera_{camera_id}')
        emit('unsubscribed', {'camera_id': camera_id})

@socketio.on('subscribe_person')
def handle_subscribe_person(data):
    if not isinstance(data, dict):
        emit('stream_error', {'message': 'Invalid payload'})
        return

    person_id = data.get('person_id')
    if person_id:
        socketio.join_room(f'person_{person_id}')
        emit('subscribed_person', {'person_id': person_id})


@socketio.on('stream_camera')
def handle_stream_camera(data):
    """
    Start streaming camera frames to this client.
    Client sends: {camera_id: 'camera1'}
    Server emits: 'camera_frame' events with base64 frame data
    """
    if not isinstance(data, dict):
        emit('stream_error', {'message': 'Invalid payload'})
        return

    camera_id = data.get('camera_id')
    if not camera_id:
        emit('stream_error', {'message': 'camera_id is required'})
        return
    
    # Check if camera exists
    if camera_manager and camera_id in camera_manager.cameras:
        with streaming_lock:
            if camera_id not in streaming_subscriptions:
                streaming_subscriptions[camera_id] = {}
            streaming_subscriptions[camera_id][request.sid] = True
        
        emit('stream_started', {
            'camera_id': camera_id,
            'message': f'Started streaming from camera {camera_id}'
        })
        logger.info(f"Client {request.sid} started streaming camera {camera_id}")
    else:
        emit('stream_error', {'message': f'Camera {camera_id} not found'})


@socketio.on('stop_stream_camera')
def handle_stop_stream_camera(data):
    """
    Stop streaming camera frames from this client.
    """
    if not isinstance(data, dict):
        emit('stream_error', {'message': 'Invalid payload'})
        return

    camera_id = data.get('camera_id')
    
    with streaming_lock:
        if camera_id in streaming_subscriptions:
            if request.sid in streaming_subscriptions[camera_id]:
                del streaming_subscriptions[camera_id][request.sid]
            # Clean up empty entries
            if not streaming_subscriptions[camera_id]:
                del streaming_subscriptions[camera_id]
    
    emit('stream_stopped', {'camera_id': camera_id})
    logger.info(f"Client {request.sid} stopped streaming camera {camera_id}")


@socketio.on('get_streaming_cameras')
def handle_get_streaming_cameras():
    """
    Get list of cameras this client is streaming from.
    """
    with streaming_lock:
        cameras = []
        for cam_id, subscribers in streaming_subscriptions.items():
            if request.sid in subscribers:
                cameras.append(cam_id)
    emit('streaming_cameras', {'cameras': cameras})

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(BadRequest)
@app.errorhandler(Unauthorized)
@app.errorhandler(InternalServerError)
def handle_error(e):
    try:
        from deployment.services.dto_service import error_response
    except ImportError:
        from services.dto_service import error_response

    code = getattr(e, 'code', 500)
    if code >= 500:
        logger.exception("Unhandled server error")
        return error_response("INTERNAL_SERVER_ERROR", "Internal server error", code)

    logger.warning(f"Request error ({code}): {e}")
    message = getattr(e, 'description', 'Request error')
    return error_response("REQUEST_ERROR", message, code)

@app.errorhandler(404)
def not_found(e):
    del e
    try:
        from deployment.services.dto_service import error_response
    except ImportError:
        from services.dto_service import error_response
    return error_response("NOT_FOUND", "Endpoint not found", 404)

@app.errorhandler(500)
def internal_error(e):
    del e
    try:
        from deployment.services.dto_service import error_response
    except ImportError:
        from services.dto_service import error_response
    return error_response("INTERNAL_SERVER_ERROR", "Internal server error", 500)

# ============================================================
# HEALTH CHECK
# ============================================================

@app.route('/api/health', methods=['GET'])
@limiter.exempt
def health_check():
    db_status = 'ok'
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
    except Exception:
        logger.exception("Database health check failed")
        db_status = 'error'

    payload = {
        'status': 'healthy' if db_status == 'ok' else 'degraded',
        'database': db_status,
        'cameras': len(camera_manager.cameras) if camera_manager else 0,
        'clients': len(connected_clients),
        'timestamp': datetime.utcnow().isoformat(),
    }

    # Backward compatibility: keep top-level health fields while also exposing standardized envelope.
    return jsonify({
        'success': True,
        'message': 'Health check completed',
        'data': payload,
        **payload,
    }), 200

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    logger.info(f"Starting Face Attendance API on port {port}")
    
    # H-CAM-003 FIX: Only start default camera if explicitly enabled
    # By default, don't start webcam to avoid errors when no camera available
    enable_default_camera = os.getenv('ENABLE_DEFAULT_CAMERA', 'false').lower() == 'true'
    
    if CAMERA_SYSTEM_AVAILABLE and camera_manager and enable_default_camera:
        # Try to add default webcam, but don't fail if no camera available
        try:
            camera_manager.add_camera('webcam1', 'usb', {'device_index': 0})
            camera_manager.start_camera('webcam1')
            logger.info("Default webcam added and started (ENABLE_DEFAULT_CAMERA=true)")
        except Exception as e:
            logger.warning(f"Could not start default webcam: {e}. Continuing without camera.")
    elif CAMERA_SYSTEM_AVAILABLE and camera_manager:
        logger.info("Camera system available but default camera disabled (ENABLE_DEFAULT_CAMERA=false)")
    else:
        logger.info("Camera system not available - running in headless mode")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

