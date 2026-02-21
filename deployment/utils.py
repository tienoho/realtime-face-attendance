"""
Performance utilities for Face Attendance API
Includes image processing and optimization functions
"""
import cv2
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def compress_image(image, max_width=640, quality=85):
    """
    Compress image to reduce storage size while maintaining quality.
    
    Args:
        image: Input image (numpy array)
        max_width: Maximum width to resize to
        quality: JPEG compression quality (1-100)
    
    Returns:
        Compressed image
    """
    h, w = image.shape[:2]
    
    # Calculate new dimensions
    if w > max_width:
        ratio = max_width / w
        new_w = max_width
        new_h = int(h * ratio)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    return image


def preprocess_face_image(image, target_size=(200, 200)):
    """
    Preprocess face image for recognition.
    
    Args:
        image: Input face image
        target_size: Target size for the face image
    
    Returns:
        Preprocessed grayscale image
    """
    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Resize to standard size
    gray = cv2.resize(gray, target_size)
    
    # Apply histogram equalization for better contrast
    gray = cv2.equalizeHist(gray)
    
    return gray


def detect_faces_fast(gray_image, scale_factor=1.1, min_neighbors=5):
    """
    Optimized face detection with parameters tuned for speed.
    
    Args:
        gray_image: Grayscale image
        scale_factor: Scale factor for detection (higher = faster but less accurate)
        min_neighbors: Min neighbors for detection
    
    Returns:
        List of face rectangles (x, y, w, h)
    """
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    
    faces = cascade.detectMultiScale(
        gray_image,
        scaleFactor=scale_factor,
        minNeighbors=min_neighbors,
        minSize=(30, 30)
    )
    
    return list(faces) if faces is not None else []


def extract_face_roi(image, bbox, padding=0.2):
    """
    Extract face region of interest with padding.
    
    Args:
        image: Input image
        bbox: Bounding box (x, y, w, h)
        padding: Padding ratio around the face
    
    Returns:
        Cropped face image
    """
    x, y, w, h = bbox
    
    # Add padding
    pad_w = int(w * padding)
    pad_h = int(h * padding)
    
    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h)
    x2 = min(image.shape[1], x + w + pad_w)
    y2 = min(image.shape[0], y + h + pad_h)
    
    face_roi = image[y1:y2, x1:x2]
    
    return face_roi


class FrameProcessor:
    """Process video frames with configurable frame skipping"""
    
    def __init__(self, skip_frames=2):
        """
        Initialize frame processor.
        
        Args:
            skip_frames: Number of frames to skip between processing
        """
        self.skip_frames = skip_frames
        self.frame_count = 0
    
    def should_process(self):
        """Check if current frame should be processed"""
        self.frame_count += 1
        return (self.frame_count - 1) % (self.skip_frames + 1) == 0
    
    def reset(self):
        """Reset frame counter"""
        self.frame_count = 0


class ImageCache:
    """Simple LRU cache for processed images"""
    
    def __init__(self, max_size=100):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
    
    def get(self, key):
        if key in self.cache:
            self.access_times[key] = datetime.now()
            return self.cache[key]
        return None
    
    def set(self, key, value):
        # Evict oldest if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times, key=self.access_times.get)
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
        
        self.cache[key] = value
        self.access_times[key] = datetime.now()
    
    def clear(self):
        self.cache.clear()
        self.access_times.clear()


# Performance monitoring
class PerformanceMonitor:
    """Monitor API performance metrics"""
    
    def __init__(self):
        self.request_times = {}
        self.error_counts = {}
    
    def record_request(self, endpoint, duration_ms):
        if endpoint not in self.request_times:
            self.request_times[endpoint] = []
        self.request_times[endpoint].append(duration_ms)
    
    def record_error(self, endpoint):
        if endpoint not in self.error_counts:
            self.error_counts[endpoint] = 0
        self.error_counts[endpoint] += 1
    
    def get_stats(self, endpoint):
        times = self.request_times.get(endpoint, [])
        if not times:
            return {
                'count': 0,
                'avg_ms': 0,
                'min_ms': 0,
                'max_ms': 0,
                'errors': self.error_counts.get(endpoint, 0)
            }
        
        return {
            'count': len(times),
            'avg_ms': sum(times) / len(times),
            'min_ms': min(times),
            'max_ms': max(times),
            'errors': self.error_counts.get(endpoint, 0)
        }
    
    def get_all_stats(self):
        endpoints = set(self.request_times.keys()) | set(self.error_counts.keys())
        return {ep: self.get_stats(ep) for ep in endpoints}


# Global performance monitor
perf_monitor = PerformanceMonitor()


def monitor_performance(endpoint_name):
    """Decorator to monitor endpoint performance"""
    from functools import wraps
    import time
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                perf_monitor.record_request(endpoint_name, duration_ms)
                return result
            except Exception as e:
                perf_monitor.record_error(endpoint_name)
                raise
        
        return wrapper
    
    return decorator
