"""
Face Embedder Module
====================

Uses ArcFace (via InsightFace) for generating 512-dimensional
face embeddings for recognition.
"""

import os
import logging
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)


@dataclass
class FaceMatch:
    """Represents a face match result."""
    student_id: str
    name: str
    confidence: float
    distance: float
    
    def __post_init__(self):
        # Convert cosine similarity to confidence percentage
        # Cosine similarity ranges from -1 to 1, normalize to 0-100
        self.confidence = max(0, min(100, (self.distance + 1) / 2 * 100))


class FaceEmbedder:
    """
    Face embedder using InsightFace's ArcFace model.
    
    Generates 512-dimensional embeddings that can be used
    for face comparison and identification.
    
    Note: Can reuse FaceAnalysis instance from detector to avoid
    loading model multiple times (saves memory).
    """
    
    # Embedding dimension from config
    EMBEDDING_DIM = config.EMBEDDING_DIM
    
    def __init__(
        self,
        app=None,
        model_name: str = None,
        providers: List[str] = None
    ):
        """
        Initialize the face embedder.
        
        Args:
            app: Pre-initialized FaceAnalysis instance (reuses model)
            model_name: InsightFace model name (used if app is None)
            providers: Execution providers
        """
        self.model_name = model_name if model_name is not None else config.DETECTOR_MODEL
        self.providers = providers or ['CPUExecutionProvider']
        
        # Reuse existing app or create new one
        if app is not None:
            self._app = app
            logger.info(f"Reusing FaceAnalysis instance from detector")
        else:
            self._app = None
            self._initialize()
    
    def _initialize(self) -> None:
        """Initialize InsightFace application for embedding extraction."""
        try:
            from insightface.app import FaceAnalysis
            
            # Create application - same app handles both detection and embedding
            self._app = FaceAnalysis(
                name=self.model_name,
                providers=self.providers
            )
            
            # Prepare model
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            
            logger.info(f"FaceEmbedder initialized with model: {self.model_name}")
            
        except ImportError as e:
            logger.error(f"Failed to import insightface: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize FaceEmbedder: {e}")
            raise
    
    def embed(self, image: np.ndarray, face=None) -> Optional[np.ndarray]:
        """
        Extract face embedding from an image.
        
        Args:
            image: BGR image (OpenCV format)
            face: Optional pre-detected face (if None, will detect first)
            
        Returns:
            512-dimensional embedding vector or None
        """
        if image is None or image.size == 0:
            return None
        
        # Convert BGR to RGB
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = image[:, :, ::-1].copy()
        else:
            image_rgb = image
        
        try:
            # Get faces (includes embeddings)
            faces = self._app.get(image_rgb)
            
            if not faces:
                logger.debug("No face found in image")
                return None
            
            # Use the first/largest face
            if face is not None:
                # Match with pre-detected face
                for f in faces:
                    if self._faces_match(face.bbox, f.bbox):
                        return f.embedding
                return faces[0].embedding
            else:
                # Use first detected face
                return faces[0].embedding
                
        except Exception as e:
            logger.error(f"Error extracting embedding: {e}")
            return None
    
    def embed_batch(self, images: List[np.ndarray]) -> List[Optional[np.ndarray]]:
        """
        Extract embeddings from multiple images.
        
        Args:
            images: List of BGR images
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        for image in images:
            emb = self.embed(image)
            embeddings.append(emb)
        return embeddings
    
    def _faces_match(
        self, 
        bbox1: Tuple, 
        bbox2: Tuple, 
        iou_threshold: float = 0.5
    ) -> bool:
        """Check if two face bounding boxes overlap significantly."""
        # Calculate IoU
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i < x1_i or y2_i < y1_i:
            return False
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        iou = intersection / float(area1 + area2 - intersection)
        return iou > iou_threshold
    
    def compare(
        self, 
        embedding1: np.ndarray, 
        embedding2: np.ndarray
    ) -> float:
        """
        Compare two face embeddings using cosine similarity.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (-1 to 1)
        """
        # Normalize embeddings
        emb1 = embedding1 / np.linalg.norm(embedding1)
        emb2 = embedding2 / np.linalg.norm(embedding2)
        
        # Cosine similarity
        similarity = np.dot(emb1, emb2)
        
        return float(similarity)
    
    def __repr__(self) -> str:
        return f"FaceEmbedder(model={self.model_name}, dim={self.EMBEDDING_DIM})"


def test_embedder():
    """Quick test function for the embedder."""
    import cv2
    
    print("Testing FaceEmbedder...")
    
    embedder = FaceEmbedder()
    
    # Create a test image
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Extract embedding
    embedding = embedder.embed(test_image)
    
    if embedding is not None:
        print(f"✓ Embedder initialized successfully")
        print(f"✓ Embedding shape: {embedding.shape}")
        print(f"✓ Embedding dimension: {len(embedding)}")
    else:
        print("⚠ No face detected (expected for blank image)")
        print("✓ Embedder initialized successfully")
    
    return True


if __name__ == "__main__":
    test_embedder()
