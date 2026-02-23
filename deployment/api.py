# Standard library imports
import os
import sys
import base64
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

# Third-party imports
import cv2
import numpy as np
import pymysql
import psycopg2  # For PostgreSQL support
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, Unauthorized, InternalServerError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

# Add parent directory to path for camera imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# DATABASE TYPE SELECTION
# ============================================================

# Set DB_TYPE to 'mysql' or 'postgresql' (default: mysql for backward compatibility)
DB_TYPE = os.getenv('DB_TYPE', 'mysql').lower()

# Import appropriate database module
if DB_TYPE == 'postgresql':
    try:
        from database import get_db_connection, init_db_pool, close_db_pool, get_table_list, check_db_health
        logger.info(f"Using PostgreSQL database (DB_TYPE={DB_TYPE})")
    except ImportError as e:
        logger.warning(f"PostgreSQL module error: {e}, falling back to MySQL")
        DB_TYPE = 'mysql'
        from database import get_db_connection, init_db_pool, close_db_pool
else:
    from database import get_db_connection, init_db_pool, close_db_pool
    logger.info(f"Using MySQL database (DB_TYPE={DB_TYPE})")

# ============================================================
# FLASK & SOCKETIO SETUP
# ============================================================

app = Flask(__name__)

# CORS configuration - require explicit origins in production
CORS_CONFIG = os.getenv('CORS_ORIGINS', '')
if not CORS_CONFIG:
    # In production, CORS_ORIGINS must be set. For development, allow common localhost ports.
    if os.getenv('FLASK_ENV') == 'development':
        CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"}})
    else:
        raise ValueError("CORS_ORIGINS environment variable must be set in production")
else:
    origins = CORS_CONFIG.split(',')
    CORS(app, resources={r"/api/*": {"origins": origins}})

# SocketIO setup
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),  # PostgreSQL default
    'user': os.getenv('DB_USER', 'postgres'),  # PostgreSQL default
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'face_attendance'),
    'charset': 'utf8mb4',
    'autocommit': True,
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
        logging.FileHandler('api.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# MODEL CACHE
# ============================================================

_model_cache = {
    'face_detector': None,
    'face_recognizer': None,
    'mp_face_detection': None
}

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

def get_mediapipe_detector():
    if _model_cache['mp_face_detection'] is None:
        _model_cache['mp_face_detection'] = mp.solutions.face_detection
    return _model_cache['mp_face_detection']

# ============================================================
# CAMERA MANAGER (Realtime Support)
# ============================================================

try:
    from cameras.camera_manager import CameraManager
    from cameras.frame_processor import FrameProcessor, AdaptiveFrameProcessor
    from cameras.attendance_engine import AttendanceEngine
    
    camera_manager = CameraManager(max_cameras=16, frame_queue_size=5)
    
    # Initialize frame processor with InsightFace (recommended)
    # Set use_insightface=False to use legacy detection
    frame_processor = FrameProcessor(
        num_workers=4,
        use_insightface=True,
        det_threshold=0.5,
        recognition_threshold=0.6
    )
    
    # Initialize attendance engine
    attendance_engine = AttendanceEngine(dedup_window=300)
    
    camera_manager.register_frame_callback(on_frame_captured)
    camera_manager.register_frame_callback(on_frame_for_streaming)
    frame_processor.register_detection_callback(on_faces_detected)
    frame_processor.register_recognition_callback(on_faces_recognized)
    
    CAMERA_SYSTEM_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Camera system not available: {e}")
    CAMERA_SYSTEM_AVAILABLE = False
    camera_manager = None
    frame_processor = None
    attendance_engine = None

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

# Use get_db_connection from the imported database module (mysql or postgresql)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_student_id(student_id):
    if not student_id or len(student_id) < 3 or len(student_id) > 50:
        return False, "Student ID must be 3-50 characters"
    if not re.match(r'^[a-zA-Z0-9_-]+$', student_id):
        return False, "Student ID can only contain alphanumeric, underscore, hyphen"
    forbidden = [';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute', 'insert', 'delete', 'update', 'drop']
    for word in forbidden:
        if word.lower() in student_id.lower():
            return False, "Student ID contains forbidden characters"
    return True, None

def validate_name(name):
    if not name or len(name) < 2 or len(name) > 100:
        return False, "Name must be 2-100 characters"
    if not re.match(r'^[a-zA-Z\s]+$', name):
        return False, "Name can only contain letters and spaces"
    dangerous_chars = ['<', '>', '"', "'", '&', ';', 'script', 'javascript']
    for char in dangerous_chars:
        if char in name.lower():
            return False, "Name contains forbidden characters"
    return True, None

def validate_subject(subject):
    if not subject or len(subject) < 2 or len(subject) > 100:
        return False, "Subject must be 2-100 characters"
    if not re.match(r'^[a-zA-Z0-9\s_-]+$', subject):
        return False, "Subject can only contain letters, numbers, spaces, underscore, hyphen"
    return True, None

def detect_faces_mediapipe(image):
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
        return label, confidence
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
    if recognized:
        for face in recognized:
            socketio.emit('attendance', {
                'camera_id': camera_id,
                'person_id': face.get('person_id'),
                'confidence': face.get('confidence'),
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
        
        # Get all image files
        faces = []
        labels = []
        
        # Walk through all subdirectories (each student has their own folder)
        for student_id in os.listdir(training_folder):
            student_path = os.path.join(training_folder, student_id)
            if not os.path.isdir(student_path):
                continue
            
            # Try to extract numeric label from student_id
            try:
                # Use the student_id as-is or convert to numeric
                label = int(student_id) if student_id.isdigit() else hash(student_id) % 10000
            except (ValueError, TypeError):
                label = hash(student_id) % 10000
            
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
        
        # Update the cached recognizer
        global _model_cache
        _model_cache['face_recognizer'] = recognizer
        
        logger.info(f"Model trained successfully with {len(faces)} images")
        
        return {
            'status': 'success',
            'message': 'Model trained successfully',
            'images_trained': len(faces),
            'unique_labels': len(set(labels))
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
# AUTHENTICATION
# ============================================================

def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            if token.startswith('Bearer '):
                token = token.split(" ")[1]

            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return jsonify({'message': 'Token validation failed'}), 401

        return f(current_user, *args, **kwargs)
    return decorator

# ============================================================
# REST API ENDPOINTS
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    try:
        auth = request.get_json()
        if not auth or not auth.get('username') or not auth.get('password'):
            return jsonify({'message': 'Missing credentials'}), 400

        username = auth.get('username')
        password = auth.get('password')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password_hash FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()

            if not user:
                return jsonify({'message': 'Invalid credentials'}), 401
            
            stored_hash = user[2]
            # Always use password hash verification - reject plaintext hashes
            if not stored_hash.startswith('$2b'):
                logger.error(f"User {username} has insecure plaintext password hash")
                return jsonify({'message': 'Invalid credentials'}), 401
            
            if not check_password_hash(stored_hash, password):
                return jsonify({'message': 'Invalid credentials'}), 401

            token = jwt.encode({
                'user_id': user[0],
                'username': user[1],
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')

            logger.info(f"User {username} logged in successfully")
            return jsonify({
                'token': token,
                'user_id': user[0],
                'username': user[1]
            }), 200
            
    except (pymysql.Error, psycopg2.Error) as e:
        logger.error(f"Database error during login: {e}")
        return jsonify({'message': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'message': 'Server error'}), 500

@app.route('/api/register-student', methods=['POST'])
@token_required
def register_student(current_user):
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'No file provided'}), 400

        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        subject = request.form.get('subject', 'General').strip()

        valid, error = validate_student_id(student_id)
        if not valid:
            return jsonify({'message': error}), 400

        valid, error = validate_name(name)
        if not valid:
            return jsonify({'message': error}), 400

        file = request.files['file']
        if not allowed_file(file.filename):
            return jsonify({'message': 'Invalid file type. Allowed: png, jpg, jpeg'}), 400

        img_bytes = file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'message': 'Invalid image file'}), 400

        face_boxes = detect_faces_mediapipe(img)
        
        if not face_boxes:
            return jsonify({'message': 'No face detected in image'}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM students WHERE student_id = %s', (student_id,))
            if cursor.fetchone():
                return jsonify({'message': f'Student ID {student_id} already exists'}), 409

            cursor.execute(
                'INSERT INTO students (student_id, name) VALUES (%s, %s)',
                (student_id, name)
            )
            
            student_folder = os.path.join(app.config['UPLOAD_FOLDER'], student_id)
            os.makedirs(student_folder, exist_ok=True)
            
            saved_count = 0
            for i, (x, y, w, h) in enumerate(face_boxes[:1]):
                pad = 20
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(img.shape[1], x + w + pad)
                y2 = min(img.shape[0], y + h + pad)
                
                face_img = img[y1:y2, x1:x2]
                gray_face = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
                
                img_filename = f"{student_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                img_path = os.path.join(student_folder, img_filename)
                cv2.imwrite(img_path, gray_face)
                
                cursor.execute(
                    'INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)',
                    (student_id, img_path)
                )
                saved_count += 1

            logger.info(f"Student {student_id} ({name}) registered with {saved_count} images")

        # Auto-train model after successful registration
        logger.info("Starting auto-training after student registration...")
        training_result = train_face_recognition_model()
        
        if training_result['status'] == 'success':
            logger.info(f"Auto-training completed: {training_result['images_trained']} images")
        else:
            logger.warning(f"Auto-training failed: {training_result['message']}")

        return jsonify({
            'message': 'Student registered successfully',
            'student_id': student_id,
            'name': name,
            'images_saved': saved_count,
            'model_trained': training_result['status'] == 'success',
            'training_details': training_result
        }), 201

    except (pymysql.Error, psycopg2.Error) as e:
        logger.error(f"Database error during registration: {e}")
        return jsonify({'message': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'message': f'Server error: {str(e)}'}), 500

# ============================================================
# PHASE 2: MULTI-IMAGE REGISTRATION ENDPOINT
# ============================================================

# Initialize Face Recognition Pipeline (singleton)
_face_pipeline = None
_face_pipeline_lock = threading.Lock()

# Initialize Face Detector (singleton) - for multi-image processing
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

@app.route('/api/register-student-multi', methods=['POST'])
@token_required
def register_student_multi(current_user):
    """
    Register a student with multiple images.
    
    Accepts:
    - student_id: Student ID
    - name: Student name
    - images: Multiple image files (at least 5 recommended)
    - apply_augmentation: Whether to apply data augmentation
    
    Returns:
    - Student registration result with training details
    """
    try:
        # Check for images
        files = request.files.getlist('images')
        if not files or len(files) == 0:
            return jsonify({'message': 'No images provided'}), 400
        
        # Limit number of images to prevent DoS
        if len(files) > 20:
            return jsonify({'message': 'Maximum 20 images allowed'}), 400
        
        if len(files) < 3:
            logger.warning(f"Only {len(files)} images provided, recommend at least 5-10")
        
        # Get form data
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        apply_augmentation = request.form.get('apply_augmentation', 'true').lower() == 'true'
        
        # Validate inputs
        valid, error = validate_student_id(student_id)
        if not valid:
            return jsonify({'message': error}), 400
        
        valid, error = validate_name(name)
        if not valid:
            return jsonify({'message': error}), 400
        
        # Check if student already exists
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM students WHERE student_id = %s', (student_id,))
            if cursor.fetchone():
                return jsonify({'message': f'Student ID {student_id} already exists'}), 409
        
        # Process images using cached detector
        valid_images = []
        
        # Use cached face detector
        face_detector = get_face_detector()
        if face_detector is None:
            logger.warning("InsightFace not available, using MediaPipe fallback")
        
        for i, file in enumerate(files):
            if not allowed_file(file.filename):
                continue
                
            try:
                # Read and decode image
                img_bytes = file.read()
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    logger.warning(f"Invalid image {i}: could not decode")
                    continue
                
                # Detect face
                if face_detector:
                    faces = face_detector.detect(img)
                    if faces:
                        # Use largest face
                        face = max(faces, key=lambda f: f.confidence)
                        face_crop = face_detector.get_face_crop(img, face.bbox, padding=20)
                        if face_crop is not None and face_crop.size > 0:
                            valid_images.append(face_crop)
                            logger.debug(f"Image {i}: face detected, crop size: {face_crop.shape}")
                else:
                    # Fallback to MediaPipe
                    face_boxes = detect_faces_mediapipe(img)
                    if face_boxes:
                        x, y, w, h = face_boxes[0]
                        pad = 20
                        x1 = max(0, x - pad)
                        y1 = max(0, y - pad)
                        x2 = min(img.shape[1], x + w + pad)
                        y2 = min(img.shape[0], y + h + pad)
                        face_crop = img[y1:y2, x1:x2]
                        if face_crop.size > 0:
                            valid_images.append(face_crop)
                            logger.debug(f"Image {i}: face detected (MediaPipe), crop size: {face_crop.shape}")
                            
            except Exception as img_err:
                logger.warning(f"Error processing image {i}: {img_err}")
        
        if len(valid_images) < 1:
            return jsonify({'message': 'No valid faces detected in any image'}), 400
        
        logger.info(f"Detected {len(valid_images)} valid face images from {len(files)} uploaded")
        
        # Apply data augmentation if requested
        original_count = len(valid_images)
        if apply_augmentation and augment_face_batch:
            try:
                # Target 10-15 images for good recognition
                target = min(15, max(10, original_count * 3))
                valid_images = augment_face_batch(valid_images, target_count=target)
                logger.info(f"Applied augmentation: {original_count} -> {len(valid_images)} images")
            except Exception as aug_err:
                logger.warning(f"Augmentation failed: {aug_err}")
        
        # Save images to disk
        student_folder = os.path.join(app.config['UPLOAD_FOLDER'], student_id)
        os.makedirs(student_folder, exist_ok=True)
        
        saved_count = 0
        for i, img in enumerate(valid_images):
            try:
                img_filename = f"{student_id}_{i:03d}.jpg"
                img_path = os.path.join(student_folder, img_filename)
                cv2.imwrite(img_path, img)
                saved_count += 1
            except Exception as save_err:
                logger.warning(f"Failed to save image {i}: {save_err}")
        
        # Insert student into database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO students (student_id, name) VALUES (%s, %s)',
                (student_id, name)
            )
            
            # Insert training image records
            for i in range(saved_count):
                img_path = os.path.join(student_folder, f"{student_id}_{i:03d}.jpg")
                cursor.execute(
                    'INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)',
                    (student_id, img_path)
                )
        
        # Register with Face Recognition Pipeline (FAISS)
        pipeline_result = {'status': 'not_available'}
        pipeline = get_face_pipeline()
        
        if pipeline:
            try:
                # Use original images (without augmentation) for embedding
                result = pipeline.register_face(student_id, name, valid_images[:original_count])
                pipeline_result = {
                    'status': 'success' if result.get('success') else 'error',
                    'message': result.get('message', ''),
                    'images_processed': result.get('images_processed', 0)
                }
                logger.info(f"FAISS registration: {pipeline_result}")
            except Exception as pipeline_err:
                logger.error(f"Pipeline registration failed: {pipeline_err}")
                pipeline_result = {'status': 'error', 'message': str(pipeline_err)}
        
        # Also train legacy LBPH model for backward compatibility (async)
        def run_training():
            try:
                training_result = train_face_recognition_model()
                if training_result.get('status') == 'success':
                    logger.info(f"Background training completed: {training_result.get('images_trained')} images")
                else:
                    logger.warning(f"Background training failed: {training_result.get('message')}")
            except Exception as train_err:
                logger.error(f"Background training error: {train_err}")
        
        # Run training in background thread
        threading.Thread(target=run_training, daemon=True).start()
        
        return jsonify({
            'message': 'Student registered successfully',
            'student_id': student_id,
            'name': name,
            'images_uploaded': len(files),
            'faces_detected': len(valid_images),
            'images_saved': saved_count,
            'augmentation_applied': apply_augmentation,
            'faiss_registration': pipeline_result,
            'lbph_training': {'status': 'queued', 'message': 'Training started in background'}
        }), 201
        
    except (pymysql.Error, psycopg2.Error) as e:
        logger.error(f"Database error during multi-registration: {e}")
        return jsonify({'message': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Multi-registration error: {str(e)}")
        return jsonify({'message': f'Server error: {str(e)}'}), 500


@app.route('/api/register-face-capture', methods=['POST'])
@token_required
def register_face_capture(current_user):
    """
    Register a face from captured frame data (base64).
    
    Accepts:
    - student_id: Student ID
    - name: Student name
    - image_data: Base64 encoded image
    
    Returns:
    - Registration result
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('image_data'):
            return jsonify({'message': 'No image data provided'}), 400
        
        student_id = data.get('student_id', '').strip()
        name = data.get('name', '').strip()
        image_data = data.get('image_data', '')
        
        # Validate
        valid, error = validate_student_id(student_id)
        if not valid:
            return jsonify({'message': error}), 400
        
        valid, error = validate_name(name)
        if not valid:
            return jsonify({'message': error}), 400
        
        # Decode base64 image
        try:
            # Remove data URL prefix if present
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            img_bytes = base64.b64decode(image_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as decode_err:
            return jsonify({'message': f'Invalid image data: {decode_err}'}), 400
        
        if img is None:
            return jsonify({'message': 'Could not decode image'}), 400
        
        # Detect face using cached detector
        face_detector = get_face_detector()
        face_crop = None
        if face_detector:
            faces = face_detector.detect(img)
            if faces:
                face = max(faces, key=lambda f: f.confidence)
                face_crop = face_detector.get_face_crop(img, face.bbox, padding=20)
        else:
            face_boxes = detect_faces_mediapipe(img)
            if face_boxes:
                x, y, w, h = face_boxes[0]
                pad = 20
                x1, y1 = max(0, x - pad), max(0, y - pad)
                x2, y2 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
                face_crop = img[y1:y2, x1:x2]
        
        if face_crop is None or face_crop.size == 0:
            return jsonify({'message': 'No face detected in image'}), 400
        
        # Check if student exists
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM students WHERE student_id = %s', (student_id,))
            exists = cursor.fetchone()
            
            if not exists:
                cursor.execute('INSERT INTO students (student_id, name) VALUES (%s, %s)', (student_id, name))
        
        # Save image
        student_folder = os.path.join(app.config['UPLOAD_FOLDER'], student_id)
        os.makedirs(student_folder, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        img_filename = f"{student_id}_{timestamp}.jpg"
        img_path = os.path.join(student_folder, img_filename)
        cv2.imwrite(img_path, face_crop)
        
        # Record in DB
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)',
                (student_id, img_path)
            )
        
        # Register with FAISS if available
        pipeline = get_face_pipeline()
        faiss_result = {'status': 'not_available'}
        
        if pipeline:
            try:
                result = pipeline.register_face(student_id, name, [face_crop])
                faiss_result = {
                    'status': 'success' if result.get('success') else 'error',
                    'message': result.get('message', '')
                }
            except Exception as e:
                faiss_result = {'status': 'error', 'message': str(e)}
        
        return jsonify({
            'message': 'Face captured successfully',
            'student_id': student_id,
            'name': name,
            'image_path': img_path,
            'faiss_registration': faiss_result
        }), 201
        
    except Exception as e:
        logger.error(f"Face capture error: {str(e)}")
        return jsonify({'message': f'Server error: {str(e)}'}), 500


@app.route('/api/register-face', methods=['POST'])
@token_required
def register_face(current_user):
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'No file provided'}), 400

        student_id = request.form.get('student_id', '').strip()
        
        file = request.files['file']
        if not allowed_file(file.filename):
            return jsonify({'message': 'Invalid file type'}), 400

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{student_id}_{timestamp}.jpg" if student_id else f"{timestamp}.jpg"
        filename = secure_filename(filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        image = cv2.imread(filepath)
        face_boxes = detect_faces_mediapipe(image)
        
        if not face_boxes:
            os.remove(filepath)
            return jsonify({'message': 'No face detected'}), 400

        if student_id:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    # Use database-agnostic upsert logic
                    cursor.execute('SELECT id FROM training_images WHERE student_id = %s', (student_id,))
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute(
                            'UPDATE training_images SET image_path = %s WHERE student_id = %s',
                            (filepath, student_id)
                        )
                    else:
                        cursor.execute(
                            'INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)',
                            (student_id, filepath)
                        )
            except Exception as db_err:
                logger.warning(f"Could not save to database: {db_err}")

        return jsonify({
            'message': 'Face registered successfully',
            'filename': filename,
            'faces_detected': len(face_boxes)
        }), 201
        
    except Exception as e:
        logger.error(f"Face registration error: {str(e)}")
        return jsonify({'message': f'Server error: {str(e)}'}), 500

@app.route('/api/attendance', methods=['POST'])
@token_required
def mark_attendance(current_user):
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'No file provided'}), 400

        subject = request.form.get('subject', 'General').strip()
        
        valid, error = validate_subject(subject)
        if not valid:
            return jsonify({'message': error}), 400
        
        file = request.files['file']
        if not allowed_file(file.filename):
            return jsonify({'message': 'Invalid file type'}), 400

        img_bytes = file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'message': 'Invalid image file'}), 400

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_boxes = detect_faces_haar(gray)
        
        if not face_boxes:
            return jsonify({'message': 'No face detected', 'status': 'no_face'}), 200

        x, y, w, h = face_boxes[0]
        face_roi = gray[y:y+h, x:x+w]

        student_id, confidence = recognize_face(face_roi)
        
        if student_id is None or confidence >= 70:
            return jsonify({
                'message': 'Face not recognized',
                'status': 'unknown',
                'confidence': float(confidence) if confidence else None
            }), 200

        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT student_id, name FROM students WHERE student_id = %s AND is_active = TRUE',
                (student_id,)
            )
            student = cursor.fetchone()
            
            if not student:
                return jsonify({'message': 'Student not found or inactive', 'status': 'not_found'}), 200

            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                '''SELECT id FROM attendance WHERE student_id = %s AND date = %s AND subject = %s''',
                (student_id, today, subject)
            )
            
            if cursor.fetchone():
                return jsonify({
                    'message': 'Already marked attendance today',
                    'status': 'already_marked',
                    'student_id': student[0],
                    'name': student[1]
                }), 200

            now = datetime.now()
            cursor.execute(
                '''INSERT INTO attendance (student_id, enrollment, name, date, time, subject, status, confidence_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (student_id, student_id, student[1], now.strftime('%Y-%m-%d'), 
                 now.strftime('%H:%M:%S'), subject, 'Present', float(confidence))
            )
            
            logger.info(f"Attendance marked: {student[1]} ({student_id}) for {subject}")

        return jsonify({
            'message': 'Attendance marked successfully',
            'status': 'success',
            'student_id': student[0],
            'name': student[1],
            'subject': subject,
            'time': now.strftime('%H:%M:%S'),
            'confidence': float(confidence)
        }), 200

    except (pymysql.Error, psycopg2.Error) as e:
        logger.error(f"Database error during attendance: {e}")
        return jsonify({'message': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Attendance error: {str(e)}")
        return jsonify({'message': f'Server error: {str(e)}'}), 500

@app.route('/api/students', methods=['GET'])
@token_required
def get_students(current_user):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT student_id, name, is_active, created_at FROM students ORDER BY created_at DESC')
            students = cursor.fetchall()
            
        return jsonify({
            'students': [
                {
                    'student_id': s[0],
                    'name': s[1],
                    'is_active': bool(s[2]),
                    'created_at': s[3].isoformat() if s[3] else None
                }
                for s in students
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching students: {e}")
        return jsonify({'message': 'Server error'}), 500

@app.route('/api/attendance/report', methods=['GET'])
@token_required
def get_attendance_report(current_user):
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        subject = request.args.get('subject', None)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if subject:
                cursor.execute(
                    '''SELECT a.student_id, a.name, a.date, a.time, a.subject, a.status, a.confidence_score
                       FROM attendance a WHERE a.date = %s AND a.subject = %s ORDER BY a.time''',
                    (date, subject)
                )
            else:
                cursor.execute(
                    '''SELECT student_id, name, date, time, subject, status, confidence_score
                       FROM attendance WHERE date = %s ORDER BY time''',
                    (date,)
                )
            
            records = cursor.fetchall()
            
        return jsonify({
            'date': date,
            'subject': subject,
            'count': len(records),
            'records': [
                {
                    'student_id': r[0], 'name': r[1], 'date': r[2], 'time': r[3],
                    'subject': r[4], 'status': r[5], 'confidence': float(r[6]) if r[6] else None
                }
                for r in records
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching report: {e}")
        return jsonify({'message': 'Server error'}), 500

# ============================================================
# CAMERA API ENDPOINTS
# ============================================================

@app.route('/api/cameras', methods=['GET'])
@token_required
def get_cameras(current_user):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    return jsonify(camera_manager.get_status())

@app.route('/api/cameras', methods=['POST'])
@token_required
def add_camera(current_user):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    
    data = request.get_json()
    camera_id = data.get('camera_id')
    camera_type = data.get('type', 'usb')
    
    if not camera_id:
        return jsonify({'error': 'camera_id is required'}), 400
    
    if camera_manager.add_camera(camera_id, camera_type, data):
        camera_manager.start_camera(camera_id)
        return jsonify({'message': f'Camera {camera_id} added', 'camera_id': camera_id})
    
    return jsonify({'error': 'Failed to add camera'}), 500

@app.route('/api/cameras/<camera_id>', methods=['DELETE'])
@token_required
def remove_camera(current_user, camera_id):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    
    if camera_manager.remove_camera(camera_id):
        return jsonify({'message': f'Camera {camera_id} removed'})
    
    return jsonify({'error': 'Camera not found'}), 404

@app.route('/api/cameras/<camera_id>/start', methods=['POST'])
@token_required
def start_camera(current_user, camera_id):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    
    if camera_manager.start_camera(camera_id):
        return jsonify({'message': f'Camera {camera_id} started'})
    
    return jsonify({'error': 'Failed to start camera'}), 500

@app.route('/api/cameras/<camera_id>/stop', methods=['POST'])
@token_required
def stop_camera(current_user, camera_id):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    
    camera_manager.stop_camera(camera_id)
    return jsonify({'message': f'Camera {camera_id} stopped'})

@app.route('/api/cameras/<camera_id>/frame', methods=['GET'])
@token_required
def get_camera_frame(current_user, camera_id):
    if not camera_manager:
        return jsonify({'error': 'Camera system not available'}), 500
    
    if camera_id not in camera_manager.cameras:
        return jsonify({'error': 'Camera not found'}), 404
    
    frame, timestamp = camera_manager.get_latest_frame(camera_id)
    
    if frame is None:
        return jsonify({'error': 'No frame available'}), 404
    
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    _, buffer = cv2.imencode('.jpg', frame, encode_param)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return jsonify({
        'camera_id': camera_id,
        'frame': f'data:image/jpeg;base64,{frame_base64}',
        'timestamp': timestamp
    })

@app.route('/api/processing/stats', methods=['GET'])
@token_required
def get_processing_stats(current_user):
    if not frame_processor:
        return jsonify({})
    return jsonify(frame_processor.get_stats())

@app.route('/api/attendance/recent', methods=['GET'])
@token_required
def get_recent_attendance(current_user):
    return jsonify({'records': [], 'count': 0})


# ============================================================
# PHASE 5: PROCESSING CONFIGURATION ENDPOINTS
# ============================================================

@app.route('/api/processing/config', methods=['GET'])
@token_required
def get_processing_config(current_user):
    """
    Get current frame processing configuration.
    """
    if not frame_processor:
        return jsonify({'error': 'Frame processor not available'}), 500
    
    config = frame_processor.get_config()
    return jsonify(config)


@app.route('/api/processing/config', methods=['POST'])
@token_required
def update_processing_config(current_user):
    """
    Update frame processing configuration.
    """
    if not frame_processor:
        return jsonify({'error': 'Frame processor not available'}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No configuration provided'}), 400
    
    if 'det_threshold' in data:
        threshold = float(data['det_threshold'])
        if 0.0 <= threshold <= 1.0:
            frame_processor.set_detection_threshold(threshold)
        else:
            return jsonify({'message': 'det_threshold must be between 0.0 and 1.0'}), 400
    
    if 'recognition_threshold' in data:
        threshold = float(data['recognition_threshold'])
        if 0.0 <= threshold <= 1.0:
            frame_processor.set_recognition_threshold(threshold)
        else:
            return jsonify({'message': 'recognition_threshold must be between 0.0 and 1.0'}), 400
    
    if 'frame_skip' in data:
        skip = int(data['frame_skip'])
        if 1 <= skip <= 10:
            frame_processor.set_frame_skip(skip)
        else:
            return jsonify({'message': 'frame_skip must be between 1 and 10'}), 400
    
    logger.info(f"Processing config updated: {data}")
    
    return jsonify({
        'message': 'Configuration updated',
        'config': frame_processor.get_config()
    })


@app.route('/api/streaming/config', methods=['GET'])
@token_required
def get_streaming_config(current_user):
    """Get current streaming configuration"""
    return jsonify({
        'quality': ENCODE_QUALITY,
        'fps': STREAM_FPS,
        'resize_width': FRAME_RESIZE_WIDTH
    })


@app.route('/api/streaming/config', methods=['POST'])
@token_required
def update_streaming_config(current_user):
    """Update streaming configuration"""
    global ENCODE_QUALITY, STREAM_FPS, FRAME_RESIZE_WIDTH
    
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No configuration provided'}), 400
    
    if 'quality' in data:
        quality = int(data['quality'])
        if 10 <= quality <= 100:
            ENCODE_QUALITY = quality
        else:
            return jsonify({'message': 'Quality must be between 10 and 100'}), 400
    
    if 'fps' in data:
        fps = int(data['fps'])
        if 1 <= fps <= 30:
            STREAM_FPS = fps
        else:
            return jsonify({'message': 'FPS must be between 1 and 30'}), 400
    
    if 'resize_width' in data:
        width = int(data['resize_width'])
        if 320 <= width <= 1920:
            FRAME_RESIZE_WIDTH = width
        else:
            return jsonify({'message': 'Resize width must be between 320 and 1920'}), 400
    
    logger.info(f"Streaming config updated: quality={ENCODE_QUALITY}, fps={STREAM_FPS}, width={FRAME_RESIZE_WIDTH}")
    
    return jsonify({
        'message': 'Configuration updated',
        'quality': ENCODE_QUALITY,
        'fps': STREAM_FPS,
        'resize_width': FRAME_RESIZE_WIDTH
    })

# ============================================================
# WEBSOCKET EVENTS
# ============================================================

@socketio.on('connect')
def handle_connect():
    with client_lock:
        connected_clients.add(request.sid)
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'sid': request.sid})

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
    camera_id = data.get('camera_id')
    if camera_id:
        socketio.join_room(f'camera_{camera_id}')
        emit('subscribed', {'camera_id': camera_id})
        logger.info(f"Client {request.sid} subscribed to camera {camera_id}")

@socketio.on('unsubscribe_camera')
def handle_unsubscribe_camera(data):
    camera_id = data.get('camera_id')
    if camera_id:
        socketio.leave_room(f'camera_{camera_id}')
        emit('unsubscribed', {'camera_id': camera_id})

@socketio.on('subscribe_person')
def handle_subscribe_person(data):
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
    camera_id = data.get('camera_id')
    if not camera_id:
        emit('stream_error', {'message': 'camera_id is required'})
        return
    
    # Check if camera exists
    if camera_manager and camera_id in camera_manager.cameras:
        with streaming_lock:
            if camera_id not in streaming_subscriptions:
                streaming_subscriptions[camera_id] = {}
            streaming_subscriptions[request.sid] = True
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
    logger.error(f"Error: {str(e)}")
    return jsonify({'message': str(e)}), getattr(e, 'code', 500)

@app.errorhandler(404)
def not_found(e):
    return jsonify({'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'message': 'Internal server error'}), 500

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
    except Exception as e:
        db_status = f'error: {str(e)}'
    
    return jsonify({
        'status': 'healthy' if db_status == 'ok' else 'degraded',
        'database': db_status,
        'cameras': len(camera_manager.cameras) if camera_manager else 0,
        'clients': len(connected_clients),
        'timestamp': datetime.utcnow().isoformat()
    }), 200

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    logger.info(f"Starting Face Attendance API on port {port}")
    
    # Start default camera for testing
    if CAMERA_SYSTEM_AVAILABLE and camera_manager:
        camera_manager.add_camera('webcam1', 'usb', {'device_index': 0})
        camera_manager.start_camera('webcam1')
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
