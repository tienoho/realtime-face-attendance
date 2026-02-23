"""
Face Recognition Module
======================

Advanced face detection and recognition using InsightFace (RetinaFace + ArcFace).

Usage:
    from face_recognition import FaceRecognizer
    
    recognizer = FaceRecognizer()
    faces = recognizer.detect(image)
    embedding = recognizer.embed(image, face_bbox)
    match = recognizer.identify(embedding)
"""

from .detector import FaceDetector
from .recognizer import FaceEmbedder
from .vector_store import VectorStore
from .pipeline import FaceRecognitionPipeline

__all__ = [
    'FaceDetector',
    'FaceEmbedder', 
    'VectorStore',
    'FaceRecognitionPipeline'
]

__version__ = '2.0.0'
