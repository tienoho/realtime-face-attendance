"""
Frame Processor - Multi-camera video processing pipeline
Handles face detection and recognition for multiple camera streams

NOTE: This module now supports two modes:
1. Legacy mode: Haar Cascade + MediaPipe + LBPH (original)
2. InsightFace mode: RetinaFace + ArcFace + FAISS (recommended)

C-ML-001 FIX: Bounded thread pool to prevent memory overflow
"""
import cv2
import numpy as np
import logging
import threading
import time
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue
from threading import Semaphore

logger = logging.getLogger(__name__)


# C-ML-001 FIX: Use Semaphore + ThreadPoolExecutor for proper backpressure
class BoundedThreadPoolExecutor:
    """
    ThreadPoolExecutor with bounded queue to prevent memory overflow.
    Uses Semaphore for backpressure control instead of trying to access internal classes.
    """
    
    def __init__(self, max_workers=None, max_queue_size=100, thread_name_prefix=''):
        self._max_workers = max_workers or 4
        self._max_queue_size = max_queue_size
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix=thread_name_prefix
        )
        self._semaphore = Semaphore(max_queue_size)
        self._dropped_tasks = 0
        self._dropped_lock = threading.Lock()
        self._shutdown = False
        self._shutdown_lock = threading.Lock()
    
    def submit(self, fn, *args, **kwargs):
        """
        Submit a task to the executor.
        
        Returns:
            Future if task submitted, None if queue is full (backpressure)
        """
        with self._shutdown_lock:
            if self._shutdown:
                raise RuntimeError('cannot schedule new futures after shutdown')
            
            # Try to acquire semaphore without blocking
            if not self._semaphore.acquire(blocking=False):
                # Queue is full - apply backpressure
                with self._dropped_lock:
                    self._dropped_tasks += 1
                    dropped = self._dropped_tasks
                
                if dropped % 100 == 0:
                    logger.warning(
                        f"FrameProcessor backpressure: dropped {dropped} tasks "
                        f"(queue full: {self._max_queue_size})"
                    )
                return None  # Signal caller to skip this frame
            
            # Wrap the function to release semaphore when done
            def wrapped_fn():
                try:
                    return fn(*args, **kwargs)
                finally:
                    self._semaphore.release()
            
            return self._executor.submit(wrapped_fn)
    
    def shutdown(self, wait=True):
        """Shutdown the executor."""
        with self._shutdown_lock:
            self._shutdown = True
        self._executor.shutdown(wait=wait)
    
    def get_dropped_count(self):
        """Get number of dropped tasks due to backpressure."""
        with self._dropped_lock:
            return self._dropped_tasks

# Try to import InsightFace pipeline
try:
    from face_recognition.pipeline import FaceRecognitionPipeline
    from face_recognition.detector import FaceDetector
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    logger.warning("InsightFace not available, using legacy detection")
    INSIGHTFACE_AVAILABLE = False
    FaceRecognitionPipeline = None
    FaceDetector = None

# Module-level singleton for pipeline (used by FrameProcessor)
_pipeline_instance = None
_pipeline_lock = threading.Lock()


class FrameProcessor:
    """
    Process frames from multiple cameras with face detection and recognition
    
    Supports two modes:
    - InsightFace mode (default): Uses RetinaFace + ArcFace + FAISS
    - Legacy mode: Uses Haar Cascade + MediaPipe + LBPH
    """
    
    def __init__(
        self, 
        num_workers=4,
        use_insightface: bool = True,
        det_threshold: float = 0.5,
        recognition_threshold: float = 0.6,
        frame_skip: int = 1
    ):
        """
        Initialize frame processor.
        
        Args:
            num_workers: Number of worker threads
            use_insightface: Use InsightFace pipeline (recommended)
            det_threshold: Face detection confidence threshold
            recognition_threshold: Face recognition similarity threshold
            frame_skip: Process every Nth frame (for performance)
        """
        self.num_workers = num_workers
        # C-ML-001 FIX: Use BoundedThreadPoolExecutor with limited queue
        self.executor = BoundedThreadPoolExecutor(
            max_workers=num_workers,
            max_queue_size=100,  # Limit pending tasks to prevent memory overflow
            thread_name_prefix='frame_processor'
        )
        
        # Use InsightFace or legacy
        self.use_insightface = use_insightface and INSIGHTFACE_AVAILABLE
        
        # Configuration
        self.det_threshold = det_threshold
        self.recognition_threshold = recognition_threshold
        self.frame_skip = frame_skip
        self.frame_count_lock = threading.Lock()
        self.frame_counts = defaultdict(int)
        # Backward-compatible aggregate counter.
        self.frame_count = 0
        
        # InsightFace pipeline (singleton)
        self.pipeline = None
        
        # Legacy detectors
        self.face_cascade = None
        self.mp_face_detection = None
        self.face_recognizer = None
        self.model_path = None
        
        # Processing configuration
        self.detection_confidence = 0.5
        self.recognition_confidence_threshold = 70
        
        # Results storage
        self.results = defaultdict(dict)
        self.results_lock = threading.RLock()
        
        # Statistics
        self.stats = defaultdict(lambda: {
            'frames_processed': 0,
            'faces_detected': 0,
            'faces_recognized': 0,
            'processing_time': 0,
            'last_result_time': 0
        })
        
        # Callbacks
        self.detection_callbacks = []
        self.recognition_callbacks = []
        
        # Initialize based on mode
        if self.use_insightface:
            self._initialize_insightface_pipeline()
        else:
            self._initialize_legacy_detectors()
    
    def _initialize_legacy_detectors(self):
        """Initialize face detectors (legacy mode)"""
        try:
            # Try to load Haar Cascade - use absolute path
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cascade_path = os.path.join(base_dir, 'model', 'Haarcascade.xml')
            
            if os.path.exists(cascade_path):
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
                logger.info(f"Haar Cascade face detector loaded from {cascade_path}")
            else:
                # Use default cascade
                self.face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )
                logger.info("Default Haar Cascade loaded")
        except Exception as e:
            logger.error(f"Failed to load face detector: {e}")
        
        # Try to initialize MediaPipe
        try:
            import mediapipe as mp
            self.mp_face_detection = mp.solutions.face_detection
            logger.info("MediaPipe face detector initialized")
        except ImportError:
            logger.warning("MediaPipe not available, using Haar Cascade only")

    # Backward-compatible alias used by older call sites.
    def _initialize_detectors(self):
        self._initialize_legacy_detectors()
    
    def _initialize_insightface_pipeline(self):
        """Initialize InsightFace pipeline (recommended mode)"""
        global _pipeline_instance
        
        with _pipeline_lock:
            if _pipeline_instance is None:
                try:
                    _pipeline_instance = FaceRecognitionPipeline(
                        det_threshold=self.det_threshold,
                        recognition_threshold=self.recognition_threshold,
                        attendance_cooldown=300  # 5 minutes
                    )
                    logger.info("InsightFace pipeline initialized (singleton)")
                except Exception as e:
                    logger.error(f"Failed to initialize InsightFace pipeline: {e}")
                    self.use_insightface = False
                    self._initialize_legacy_detectors()
                    return
            
            self.pipeline = _pipeline_instance
            logger.info(f"Using InsightFace pipeline: {self.pipeline}")
    
    def load_recognition_model(self, model_path):
        """Load face recognition model (legacy mode)"""
        if self.use_insightface:
            logger.info("Using InsightFace pipeline, legacy model not needed")
            return True
        
        try:
            if os.path.exists(model_path):
                self.face_recognizer = cv2.face.LBPHFaceRecognizer_create()
                self.face_recognizer.read(model_path)
                self.model_path = model_path
                logger.info(f"Face recognition model loaded: {model_path}")
                return True
            else:
                logger.warning(f"Recognition model not found: {model_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to load recognition model: {e}")
            return False
    
    def set_detection_threshold(self, threshold: float):
        """Set detection confidence threshold"""
        self.det_threshold = threshold
        if self.pipeline:
            self.pipeline.det_threshold = threshold
        logger.info(f"Detection threshold set to {threshold}")
    
    def set_recognition_threshold(self, threshold: float):
        """Set recognition confidence threshold"""
        self.recognition_threshold = threshold
        if self.pipeline:
            self.pipeline.recognition_threshold = threshold
        logger.info(f"Recognition threshold set to {threshold}")
    
    def set_frame_skip(self, skip: int):
        """Set frame skip interval (process every Nth frame)"""
        self.frame_skip = max(1, skip)
        logger.info(f"Frame skip set to {self.frame_skip}")

    def _next_frame_count(self, camera_id: str) -> int:
        """Increment frame counters atomically and return per-camera counter."""
        with self.frame_count_lock:
            self.frame_counts[camera_id] += 1
            self.frame_count += 1
            return self.frame_counts[camera_id]
    
    def detect_faces(self, frame):
        """
        Detect faces in a frame.
        
        Uses InsightFace if available, otherwise falls back to legacy methods.
        
        Returns:
            list: List of face bounding boxes [(x, y, w, h), ...] or DetectedFace objects
        """
        if frame is None or frame.size == 0:
            return []
        
        # Ensure frame is valid
        if len(frame.shape) < 2:
            return []
        
        # Use InsightFace if available
        if self.use_insightface and self.pipeline:
            try:
                faces = self.pipeline.detector.detect(frame)
                # Convert DetectedFace to tuple format for compatibility
                return [(f.bbox[0], f.bbox[1], f.bbox[2]-f.bbox[0], f.bbox[3]-f.bbox[1]) for f in faces]
            except Exception as e:
                logger.error(f"InsightFace detection error: {e}")
        
        # Legacy detection methods
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        faces = []
        
        # Method 1: Haar Cascade
        if self.face_cascade is not None:
            detections = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            if detections is not None:
                faces.extend([tuple(d) for d in detections])
        
        # Method 2: MediaPipe (if available)
        if self.mp_face_detection is not None:
            try:
                with self.mp_face_detection.FaceDetection(
                    model_selection=1,
                    min_detection_confidence=self.detection_confidence
                ) as detector:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = detector.process(rgb)
                    
                    if results.detections:
                        h, w, _ = frame.shape
                        for detection in results.detections:
                            bbox = detection.location_data.relative_bounding_box
                            x = int(bbox.xmin * w)
                            y = int(bbox.ymin * h)
                            width = int(bbox.width * w)
                            height = int(bbox.height * h)
                            faces.append((x, y, width, height))
            except Exception as e:
                logger.error(f"MediaPipe detection error: {e}")
        
        return faces
    
    def recognize_faces(self, frame, faces):
        """
        Recognize faces in a frame.
        
        Args:
            frame: Input frame
            faces: List of face bounding boxes
        
        Returns:
            list: List of recognition results
        """
        if not faces:
            return []
        
        # Use InsightFace pipeline if available
        if self.use_insightface and self.pipeline:
            try:
                results = self.pipeline.process_frame(frame, track_attendance=False)
                return [
                    {
                        'bbox': (int(r.bbox[0]), int(r.bbox[1]), 
                                int(r.bbox[2]-r.bbox[0]), int(r.bbox[3]-r.bbox[1])),
                        'person_id': r.staff_id,
                        'confidence': float(r.confidence)
                    }
                    for r in results if r.is_recognized
                ]
            except Exception as e:
                logger.error(f"InsightFace recognition error: {e}")
        
        # Legacy recognition
        if self.face_recognizer is None:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        results = []
        for x, y, w, h in faces:
            # Extract face ROI
            face_roi = gray[y:y+h, x:x+w]
            
            try:
                # Recognize face
                label, confidence = self.face_recognizer.predict(face_roi)
                
                # Check confidence threshold
                if confidence < self.recognition_threshold:
                    results.append({
                        'bbox': (x, y, w, h),
                        'person_id': str(label),
                        'confidence': float(confidence)
                    })
            except Exception as e:
                logger.error(f"Recognition error: {e}")
        
        return results
    
    def process_frame(self, camera_id, frame):
        """
        Process a single frame from a camera.
        
        Supports frame skipping for performance optimization.
        
        Args:
            camera_id: Camera identifier
            frame: Input frame
        
        Returns:
            dict: Processing results (None if frame skipped)
        """
        # Frame skipping for performance (per camera to avoid cross-camera interference).
        camera_frame_count = self._next_frame_count(camera_id)
        if self.frame_skip > 1 and (camera_frame_count % self.frame_skip) != 0:
            return None
        
        start_time = time.time()
        
        # Use InsightFace pipeline for both detection and recognition
        if self.use_insightface and self.pipeline:
            try:
                results = self.pipeline.process_frame(frame, camera_id=camera_id, track_attendance=False)
                
                recognized = [
                    {
                        'bbox': (int(r.bbox[0]), int(r.bbox[1]), 
                                int(r.bbox[2]-r.bbox[0]), int(r.bbox[3]-r.bbox[1])),
                        'person_id': r.staff_id,
                        'confidence': float(r.confidence)
                    }
                    for r in results if r.is_recognized
                ]
                
                faces = [
                    (int(r.bbox[0]), int(r.bbox[1]), 
                     int(r.bbox[2]-r.bbox[0]), int(r.bbox[3]-r.bbox[1]))
                    for r in results
                ]
                
                process_time = time.time() - start_time
                
                # Update statistics
                stats = self.stats[camera_id]
                stats['frames_processed'] += 1
                stats['faces_detected'] += len(faces)
                stats['faces_recognized'] += len(recognized)
                stats['processing_time'] += process_time
                stats['last_result_time'] = time.time()
                
                # Store results
                result = {
                    'camera_id': camera_id,
                    'timestamp': time.time(),
                    'faces_detected': len(faces),
                    'faces': faces,
                    'recognized': recognized,
                    'processing_time': process_time,
                    'frame_shape': frame.shape,
                    'mode': 'insightface'
                }
                
                with self.results_lock:
                    self.results[camera_id] = result
                
                # Call detection callbacks
                for callback in self.detection_callbacks:
                    try:
                        callback(camera_id, result)
                    except Exception as e:
                        logger.error(f"Detection callback error: {e}")
                
                # Call recognition callbacks
                for callback in self.recognition_callbacks:
                    try:
                        if recognized:
                            callback(camera_id, recognized)
                    except Exception as e:
                        logger.error(f"Recognition callback error: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"InsightFace processing error: {e}")
        
        # Legacy processing
        # Detect faces
        faces = self.detect_faces(frame)
        
        # Recognize faces
        recognized = self.recognize_faces(frame, faces)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Update statistics
        stats = self.stats[camera_id]
        stats['frames_processed'] += 1
        stats['faces_detected'] += len(faces)
        stats['faces_recognized'] += len(recognized)
        stats['processing_time'] += process_time
        stats['last_result_time'] = time.time()
        
        # Store results
        result = {
            'camera_id': camera_id,
            'timestamp': time.time(),
            'faces_detected': len(faces),
            'faces': faces,
            'recognized': recognized,
            'processing_time': process_time,
            'frame_shape': frame.shape,
            'mode': 'legacy'
        }
        
        with self.results_lock:
            self.results[camera_id] = result
        
        # Call detection callbacks
        for callback in self.detection_callbacks:
            try:
                callback(camera_id, result)
            except Exception as e:
                logger.error(f"Detection callback error: {e}")
        
        # Call recognition callbacks
        for callback in self.recognition_callbacks:
            try:
                if recognized:
                    callback(camera_id, recognized)
            except Exception as e:
                logger.error(f"Recognition callback error: {e}")
        
        return result
    
    def process_frame_async(self, camera_id, frame):
        """
        Process frame asynchronously with backpressure.
        
        C-ML-001 FIX: Returns None if queue is full (backpressure).
        
        Args:
            camera_id: Camera identifier
            frame: Input frame
        
        Returns:
            Future: Async result, or None if queue is full (frame dropped)
        """
        future = self.executor.submit(self.process_frame, camera_id, frame)
        if future is None:
            # Queue is full - frame will be dropped
            logger.debug(f"Frame dropped for {camera_id} due to backpressure")
        return future
    
    def get_latest_result(self, camera_id):
        """Get the latest processing result for a camera"""
        with self.results_lock:
            return self.results.get(camera_id)
    
    def get_results(self, camera_id):
        """Get all results for a camera"""
        with self.results_lock:
            return self.results.get(camera_id, {})
    
    def register_detection_callback(self, callback):
        """Register callback for detection events"""
        self.detection_callbacks.append(callback)
    
    def register_recognition_callback(self, callback):
        """Register callback for recognition events"""
        self.recognition_callbacks.append(callback)
    
    def get_stats(self, camera_id=None):
        """Get processing statistics"""
        if camera_id:
            return dict(self.stats.get(camera_id, {}))
        
        return {
            camera_id: dict(stats)
            for camera_id, stats in self.stats.items()
        }
    
    def get_config(self):
        """Get current configuration"""
        with self.frame_count_lock:
            frame_counts = dict(self.frame_counts)
            frame_count = self.frame_count

        config = {
            'use_insightface': self.use_insightface,
            'insightface_available': INSIGHTFACE_AVAILABLE,
            'det_threshold': self.det_threshold,
            'recognition_threshold': self.recognition_threshold,
            'frame_skip': self.frame_skip,
            'frame_count': frame_count,
            'frame_counts': frame_counts,
        }
        
        if self.use_insightface and self.pipeline:
            config['pipeline'] = {
                'detector': str(self.pipeline.detector),
                'embedder': str(self.pipeline.embedder),
                'vector_store_size': len(self.pipeline.vector_store),
                'attendance_cooldown': self.pipeline.attendance_cooldown
            }
        
        return config
    
    def shutdown(self):
        """Shutdown the processor"""
        self.executor.shutdown(wait=True)
        logger.info("Frame processor shutdown")


class AdaptiveFrameProcessor(FrameProcessor):
    """
    Adaptive frame processor that adjusts processing based on load.
    
    Automatically adjusts frame skipping based on processing time
    to maintain target FPS.
    """
    
    def __init__(self, num_workers=4, target_fps=10, use_insightface=True):
        super().__init__(num_workers, use_insightface=use_insightface)
        self.target_fps = target_fps
        self.frame_skip = 1
        self.frame_count = 0
        
        # Performance monitoring
        self.frame_times = []
        self.max_frame_times = 30
    
    def should_process(self):
        """Determine if frame should be processed based on load"""
        self.frame_count += 1
        
        # Skip frames based on current load
        if self.frame_skip > 1:
            return (self.frame_count % self.frame_skip) == 0
        
        # Check if we need to skip frames
        if len(self.frame_times) >= self.max_frame_times:
            avg_time = sum(self.frame_times) / len(self.frame_times)
            target_time = 1.0 / self.target_fps
            
            if avg_time > target_time:
                # Processing is too slow, skip more frames
                self.frame_skip = min(self.frame_skip + 1, 5)
                logger.info(f"Adaptive: Increased frame_skip to {self.frame_skip} (avg: {avg_time:.3f}s, target: {target_time:.3f}s)")
            elif self.frame_skip > 1:
                # Processing is fast, skip fewer frames
                self.frame_skip = max(self.frame_skip - 1, 1)
                logger.info(f"Adaptive: Decreased frame_skip to {self.frame_skip}")
            
            self.frame_times = []
        
        return True
    
    def process_frame(self, camera_id, frame):
        """Process frame with adaptive skipping"""
        if not self.should_process():
            return None
        
        start_time = time.time()
        result = super().process_frame(camera_id, frame)
        
        # Track processing time
        if result:
            self.frame_times.append(time.time() - start_time)
        
        return result


# Singleton instance
_frame_processor = None
_processor_lock = threading.Lock()


def get_frame_processor(
    num_workers=4, 
    use_insightface: bool = True,
    det_threshold: float = 0.5,
    recognition_threshold: float = 0.6
):
    """
    Get the global frame processor instance.
    
    Args:
        num_workers: Number of worker threads
        use_insightface: Use InsightFace pipeline (recommended)
        det_threshold: Detection confidence threshold
        recognition_threshold: Recognition similarity threshold
    
    Returns:
        FrameProcessor: Configured frame processor
    """
    global _frame_processor
    
    # Double-checked locking for thread safety
    if _frame_processor is None:
        with _processor_lock:
            if _frame_processor is None:
                _frame_processor = FrameProcessor(
                    num_workers=num_workers,
                    use_insightface=use_insightface,
                    det_threshold=det_threshold,
                    recognition_threshold=recognition_threshold
                )
    return _frame_processor


def reset_frame_processor():
    """Reset the global frame processor (useful for testing)"""
    global _frame_processor, _pipeline_instance
    if _frame_processor:
        _frame_processor.shutdown()
    _frame_processor = None
    _pipeline_instance = None
    logger.info("Frame processor reset")
