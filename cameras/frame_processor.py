"""
Frame Processor - Multi-camera video processing pipeline
Handles face detection and recognition for multiple camera streams
"""
import cv2
import numpy as np
import logging
import threading
import time
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future

logger = logging.getLogger(__name__)


class FrameProcessor:
    """
    Process frames from multiple cameras with face detection and recognition
    """
    
    def __init__(self, num_workers=4):
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        
        # Face detection
        self.face_cascade = None
        self.mp_face_detection = None
        
        # Face recognition
        self.face_recognizer = None
        self.model_path = None
        
        # Processing configuration
        self.detection_confidence = 0.5
        self.recognition_threshold = 70
        self.frame_skip = 1
        
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
        
        # Initialize detectors
        self._initialize_detectors()
    
    def _initialize_detectors(self):
        """Initialize face detectors"""
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
    
    def load_recognition_model(self, model_path):
        """Load face recognition model"""
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
    
    def set_recognition_threshold(self, threshold):
        """Set recognition confidence threshold"""
        self.recognition_threshold = threshold
    
    def detect_faces(self, frame):
        """
        Detect faces in a frame using both methods
        
        Returns:
            list: List of face bounding boxes [(x, y, w, h), ...]
        """
        if frame is None or frame.size == 0:
            return []
        
        # Ensure frame is valid
        if len(frame.shape) < 2:
            return []
        
        # Convert to grayscale
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
        Recognize faces in a frame
        
        Args:
            frame: Input frame
            faces: List of face bounding boxes
        
        Returns:
            list: List of recognition results
        """
        if not faces or self.face_recognizer is None:
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
        Process a single frame from a camera
        
        Args:
            camera_id: Camera identifier
            frame: Input frame
        
        Returns:
            dict: Processing results
        """
        start_time = time.time()
        
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
            'frame_shape': frame.shape
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
        Process frame asynchronously
        
        Args:
            camera_id: Camera identifier
            frame: Input frame
        
        Returns:
            Future: Async result
        """
        return self.executor.submit(self.process_frame, camera_id, frame)
    
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
    
    def shutdown(self):
        """Shutdown the processor"""
        self.executor.shutdown(wait=True)
        logger.info("Frame processor shutdown")


class AdaptiveFrameProcessor(FrameProcessor):
    """
    Adaptive frame processor that adjusts processing based on load
    """
    
    def __init__(self, num_workers=4, target_fps=10):
        super().__init__(num_workers)
        self.target_fps = target_fps
        self.frame_skip = 1
        self.frame_count = 0
        
        # Performance monitoring
        self.frame_times = []
        self.max_frame_times = 30
    
    def should_process(self):
        """Determine if frame should be processed"""
        self.frame_count += 1
        
        # Skip frames based on current load
        if self.frame_skip > 1:
            return (self.frame_count % self.frame_skip) == 0
        
        # Check if we need to skip frames
        if len(self.frame_times) >= self.max_frame_times:
            avg_time = sum(self.frame_times) / len(self.frame_times)
            if avg_time > (1.0 / self.target_fps):
                # Processing is too slow, skip more frames
                self.frame_skip = min(self.frame_skip + 1, 5)
            elif self.frame_skip > 1:
                # Processing is fast, skip fewer frames
                self.frame_skip = max(self.frame_skip - 1, 1)
            
            self.frame_times = []
        
        return True
    
    def process_frame(self, camera_id, frame):
        """Process frame with adaptive skipping"""
        if not self.should_process():
            return None
        
        start_time = time.time()
        result = super().process_frame(camera_id, frame)
        
        # Track processing time
        self.frame_times.append(time.time() - start_time)
        
        return result


# Singleton instance
_frame_processor = None


def get_frame_processor(num_workers=4):
    """Get the global frame processor instance"""
    global _frame_processor
    if _frame_processor is None:
        _frame_processor = FrameProcessor(num_workers)
    return _frame_processor
