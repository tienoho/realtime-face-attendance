"""
Face Recognition Pipeline
=========================

Unified pipeline that combines detection, embedding, and identification.
"""

import os
import logging
import cv2
import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .detector import FaceDetector, DetectedFace
from .recognizer import FaceEmbedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """Result of face recognition on a frame."""
    staff_id: Optional[str]
    name: Optional[str]
    confidence: float
    bbox: Tuple[int, int, int, int]
    is_recognized: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AttendanceRecord:
    """Attendance record for a recognized face."""
    staff_id: str
    name: str
    confidence: float
    camera_id: str
    timestamp: str


class FaceRecognitionPipeline:
    """
    Complete face recognition pipeline for attendance system.
    
    Features:
    - Real-time face detection
    - Embedding extraction
    - Vector-based identification
    - Attendance tracking with deduplication
    
    Note: Uses a single FaceAnalysis instance for both detection
    and recognition to minimize memory usage.
    """
    
    # Default configuration from config
    DEFAULT_DET_THRESHOLD = config.DETECTOR_THRESHOLD
    DEFAULT_RECOGNITION_THRESHOLD = config.RECOGNITION_THRESHOLD
    DEFAULT_ATTENDANCE_COOLDOWN = config.ATTENDANCE_COOLDOWN
    
    def __init__(
        self,
        detector: FaceDetector = None,
        embedder: FaceEmbedder = None,
        vector_store: VectorStore = None,
        det_threshold: float = DEFAULT_DET_THRESHOLD,
        recognition_threshold: float = DEFAULT_RECOGNITION_THRESHOLD,
        attendance_cooldown: int = DEFAULT_ATTENDANCE_COOLDOWN
    ):
        """
        Initialize the pipeline.
        
        Args:
            detector: Face detector (will create if None)
            embedder: Face embedder (will reuse detector's model if None)
            vector_store: Vector store (will create if None)
            det_threshold: Detection confidence threshold
            recognition_threshold: Recognition similarity threshold
            attendance_cooldown: Seconds between attendance records
        """
        # Create detector first (loads model)
        self.detector = detector or FaceDetector()
        
        # Reuse detector's FaceAnalysis instance for embedder
        # This avoids loading the model multiple times
        if embedder is not None:
            self.embedder = embedder
        else:
            self.embedder = FaceEmbedder(app=self.detector._app)
        
        self.vector_store = vector_store or VectorStore()
        
        self.det_threshold = det_threshold
        self.recognition_threshold = recognition_threshold
        self.attendance_cooldown = attendance_cooldown
        
        # Attendance tracking
        self._recent_attendance: Dict[str, float] = {}
        
        logger.info(f"FaceRecognitionPipeline initialized (optimized - single model)")
        logger.info(f"  Detection threshold: {det_threshold}")
        logger.info(f"  Recognition threshold: {recognition_threshold}")
        logger.info(f"  Attendance cooldown: {attendance_cooldown}s")
    
    def process_frame(
        self, 
        frame: np.ndarray,
        camera_id: str = "default",
        track_attendance: bool = True
    ) -> List[RecognitionResult]:
        """
        Process a single frame for face recognition.
        
        Args:
            frame: BGR image frame
            camera_id: Camera identifier
            track_attendance: Whether to record attendance
            
        Returns:
            List of recognition results
        """
        if frame is None or frame.size == 0:
            return []
        
        results = []
        
        # Step 1: Detect faces
        faces = self.detector.detect(frame)
        
        if not faces:
            return []
        
        # Step 2: For each face, extract embedding and identify
        for face in faces:
            # Skip low confidence detections
            if face.confidence < self.det_threshold:
                continue
            
            # Crop face region
            face_crop = self.detector.get_face_crop(frame, face.bbox)
            
            if face_crop is None or face_crop.size == 0:
                continue
            
            # Step 3: Extract embedding
            embedding = self.embedder.embed(face_crop)
            
            if embedding is None:
                continue
            
            # Step 4: Search in vector store
            matches = self.vector_store.search(
                embedding, 
                k=1, 
                threshold=self.recognition_threshold
            )
            
            if matches:
                staff_id, name, confidence = matches[0]
                is_recognized = True
                
                # Track attendance if enabled
                if track_attendance:
                    self._record_attendance(staff_id, name, confidence, camera_id)
            else:
                staff_id = None
                name = None
                confidence = 0.0
                is_recognized = False
            
            results.append(RecognitionResult(
                staff_id=staff_id,
                name=name,
                confidence=confidence,
                bbox=face.bbox,
                is_recognized=is_recognized
            ))
        
        return results
    
    def _record_attendance(
        self,
        student_id: str,
        name: str,
        confidence: float,
        camera_id: str
    ) -> Optional[AttendanceRecord]:
        """Record attendance with cooldown deduplication."""
        current_time = datetime.now().timestamp()
        
        # Check cooldown
        last_time = self._recent_attendance.get(student_id, 0)
        if current_time - last_time < self.attendance_cooldown:
            return None
        
        # Record attendance
        self._recent_attendance[staff_id] = current_time
        
        record = AttendanceRecord(
            staff_id=staff_id,
            name=name,
            confidence=confidence,
            camera_id=camera_id,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(
            f"Attendance recorded: {staff_id} ({name}) "
            f"confidence={confidence:.2f} camera={camera_id}"
        )
        
        return record
    
    def register_face(
        self,
        student_id: str,
        name: str,
        images: List[np.ndarray]
    ) -> Dict[str, Any]:
        """
        Register a new face with multiple images.
        
        Args:
            student_id: Unique student identifier
            name: Student name
            images: List of face images
            
        Returns:
            Registration result
        """
        if not images:
            return {
                'success': False,
                'message': 'No images provided'
            }
        
        embeddings = []
        
        for i, img in enumerate(images):
            # Detect face
            faces = self.detector.detect(img)
            
            if not faces:
                logger.warning(f"No face detected in image {i+1}")
                continue
            
            # Use largest face
            face = max(faces, key=lambda f: f.confidence)
            
            # Crop face
            face_crop = self.detector.get_face_crop(img, face.bbox)
            
            if face_crop is None:
                continue
            
            # Extract embedding
            embedding = self.embedder.embed(face_crop)
            
            if embedding is not None:
                embeddings.append(embedding)
        
        if not embeddings:
            return {
                'success': False,
                'message': 'No valid face embeddings extracted'
            }
        
        # Average embeddings for more robust recognition
        avg_embedding = np.mean(embeddings, axis=0)
        
        # Add to vector store
        success = self.vector_store.add(staff_id, name, avg_embedding)
        
        if success:
            return {
                'success': True,
                'message': f'Registered {staff_id} with {len(embeddings)} images',
                'images_processed': len(embeddings),
                'staff_id': staff_id,
                'name': name
            }
        else:
            return {
                'success': False,
                'message': 'Failed to add to vector store'
            }
    
    def unregister_face(self, staff_id: str) -> bool:
        """Remove a face from the system."""
        return self.vector_store.delete(staff_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            'detector': str(self.detector),
            'embedder': str(self.embedder),
            'vector_store': self.vector_store.get_stats(),
            'config': {
                'det_threshold': self.det_threshold,
                'recognition_threshold': self.recognition_threshold,
                'attendance_cooldown': self.attendance_cooldown
            }
        }
    
    def clear_attendance_history(self):
        """Clear attendance tracking history."""
        self._recent_attendance.clear()
        logger.info("Attendance history cleared")


def test_pipeline():
    """Quick test of the pipeline."""
    print("Testing FaceRecognitionPipeline...")
    
    pipeline = FaceRecognitionPipeline()
    
    # Test with blank image
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = pipeline.process_frame(test_frame)
    
    print(f"✓ Pipeline initialized")
    print(f"✓ Processed test frame: {len(results)} faces")
    print(f"✓ Vector store: {len(pipeline.vector_store)} faces")
    
    return True


if __name__ == "__main__":
    test_pipeline()
