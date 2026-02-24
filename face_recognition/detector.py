"""
Face Detector Module
===================

Uses RetinaFace (via InsightFace) for accurate face detection.
Faster and more accurate than Haar Cascade or MediaPipe alone.
"""

import os
import logging
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    """Represents a detected face with bounding box and landmarks."""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    landmarks: Optional[np.ndarray] = None
    embedding: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bbox': self.bbox,
            'confidence': float(self.confidence),
            'landmarks': self.landmarks.tolist() if self.landmarks is not None else None
        }


class FaceDetector:
    """
    Face detector using InsightFace's RetinaFace.
    
    Features:
    - Multi-face detection
    - Facial landmarks (5 points)
    - High accuracy in various conditions
    - Real-time performance on CPU
    """
    
    # Use config values
    DEFAULT_MODEL = config.DETECTOR_MODEL
    DEFAULT_DET_SIZE = config.DETECTOR_SIZE
    
    def __init__(
        self,
        model_name: str = None,
        providers: List[str] = None,
        det_size: Tuple[int, int] = None,
        det_threshold: float = None
    ):
        """
        Initialize the face detector.
        
        Args:
            model_name: InsightFace model name ('buffalo_l' or 'buffalo_s')
            providers: Execution providers (CPU, CUDA, etc.)
            det_size: Detection input size (width, height) - smaller = faster
            det_threshold: Detection confidence threshold
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.providers = providers or ['CPUExecutionProvider']
        self.det_size = det_size or self.DEFAULT_DET_SIZE
        self.det_threshold = det_threshold if det_threshold is not None else config.DETECTOR_THRESHOLD
        
        self._app = None
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize InsightFace application."""
        try:
            # Set model cache directory
            cache_dir = os.getenv('INSIGHTFACE_CACHE_DIR', './models')
            os.makedirs(cache_dir, exist_ok=True)
            
            from insightface.app import FaceAnalysis
            
            # Create application with specified model
            self._app = FaceAnalysis(
                name=self.model_name,
                providers=self.providers
            )
            
            # Prepare model with specified parameters
            self._app.prepare(
                ctx_id=0,  # CPU
                det_size=self.det_size,
                det_thresh=self.det_threshold
            )
            
            logger.info(f"FaceDetector initialized with model: {self.model_name}")
            logger.info(f"Detection size: {self.det_size}, threshold: {self.det_threshold}")
            
        except ImportError as e:
            logger.error(f"Failed to import insightface: {e}")
            raise ImportError(
                "insightface not installed. Run: pip install insightface"
            )
        except Exception as e:
            logger.error(f"Failed to initialize FaceDetector: {e}")
            raise
    
    def detect(self, image: np.ndarray) -> List[DetectedFace]:
        """
        Detect faces in an image.
        
        Args:
            image: BGR image (OpenCV format) or RGB image
            
        Returns:
            List of DetectedFace objects
        """
        if image is None or image.size == 0:
            logger.warning("Empty image provided to detector")
            return []
        
        # Convert BGR to RGB if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            # Check if it's BGR (OpenCV default)
            if image.dtype == np.uint8:
                # Assume BGR from OpenCV, convert to RGB
                image_rgb = image[:, :, ::-1].copy()
            else:
                image_rgb = image
        else:
            image_rgb = image
        
        try:
            faces = self._app.get(image_rgb)
            
            detected = []
            for face in faces:
                # Get bounding box
                bbox = (
                    int(face.bbox[0]),
                    int(face.bbox[1]),
                    int(face.bbox[2]),
                    int(face.bbox[3])
                )
                
                # Get confidence
                confidence = float(face.det_score) if hasattr(face, 'det_score') else 1.0
                
                # Get landmarks (5 points)
                landmarks = None
                if hasattr(face, 'kps') and face.kps is not None:
                    landmarks = face.kps
                
                detected.append(DetectedFace(
                    bbox=bbox,
                    confidence=confidence,
                    landmarks=landmarks
                ))
            
            logger.debug(f"Detected {len(detected)} faces")
            return detected
            
        except Exception as e:
            logger.error(f"Error during face detection: {e}")
            return []
    
    def detect_batch(self, images: List[np.ndarray]) -> List[List[DetectedFace]]:
        """
        Detect faces in multiple images.
        
        Args:
            images: List of BGR images
            
        Returns:
            List of lists of DetectedFace objects
        """
        results = []
        for image in images:
            results.append(self.detect(image))
        return results
    
    def get_face_crop(self, image: np.ndarray, bbox: Tuple[int, int, int, int], padding: int = 20) -> Optional[np.ndarray]:
        """
        Crop face region from image with optional padding.
        
        Args:
            image: Source image
            bbox: Bounding box (x1, y1, x2, y2)
            padding: Padding around face
            
        Returns:
            Cropped face image or None
        """
        x1, y1, x2, y2 = bbox
        h, w = image.shape[:2]
        
        # Apply padding
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(w, x2 + padding)
        y2 = min(h, y2 + padding)
        
        if x2 <= x1 or y2 <= y1:
            return None
            
        return image[y1:y2, x1:x2]
    
    def __repr__(self) -> str:
        return f"FaceDetector(model={self.model_name}, det_size={self.det_size})"


def test_detector():
    """Quick test function for the detector."""
    import cv2
    
    print("Testing FaceDetector...")
    
    detector = FaceDetector()
    
    # Create a test image (black)
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Detect faces
    faces = detector.detect(test_image)
    
    print(f"✓ Detector initialized successfully")
    print(f"✓ Detected {len(faces)} faces in empty image (expected 0)")
    
    return detector is not None


if __name__ == "__main__":
    test_detector()
