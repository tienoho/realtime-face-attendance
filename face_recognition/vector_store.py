"""
Vector Store Module
==================

FAISS-based vector storage for fast face embedding lookup.
"""

import os
import logging
import pickle
import numpy as np
import threading
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FaceRecord:
    """Record for a face in the database."""
    student_id: str
    name: str
    embedding: np.ndarray
    created_at: str = ""


class VectorStore:
    """
    FAISS-based vector store for face embeddings.
    
    Features:
    - Fast similarity search (O(log n) with IVF)
    - Persistent storage
    - Add, update, delete operations
    
    Note: Embedding dimension should match the face embedder output.
    InsightFace buffalo_s/buffalo_l models output 512-dimensional embeddings.
    """
    
    # Embedding dimension for InsightFace models (buffalo_s, buffalo_l)
    # This should match the output dimension of the embedder
    EMBEDDING_DIM = 512
    
    def __init__(
        self,
        index_path: str = "models/faiss_index.bin",
        use_gpu: bool = False,
        nlist: int = 100,  # Number of clusters for IVF
        nprobe: int = 10   # Number of clusters to search
    ):
        """
        Initialize the vector store.
        
        Args:
            index_path: Path to save/load FAISS index
            use_gpu: Use GPU for search (if available)
            nlist: Number of clusters for IVF index
            nprobe: Number of clusters to search
        """
        self.index_path = index_path
        self.use_gpu = use_gpu
        self.nlist = nlist
        self.nprobe = nprobe
        
        # Thread safety
        self._lock = threading.Lock()
        
        self._index = None
        self._student_ids: List[str] = []
        self._student_names: Dict[str, str] = {}
        self._embeddings: List[np.ndarray] = []
        
        self._load_index()
    
    def _create_index(self):
        """Create a new FAISS index."""
        try:
            import faiss
            
            # Use Inner Product (cosine similarity) with normalized vectors
            # Flat index - simple but accurate
            # For large datasets, use IVF index
            self._index = faiss.IndexFlatIP(self.EMBEDDING_DIM)
            
            # Enable GPU if requested and available
            if self.use_gpu:
                try:
                    res = faiss.StandardGpuResources()
                    self._index = faiss.index_cpu_to_gpu(res, 0, self._index)
                    logger.info("FAISS index moved to GPU")
                except Exception as e:
                    logger.warning(f"GPU not available, using CPU: {e}")
            
            logger.info(f"Created new FAISS index (dimension={self.EMBEDDING_DIM})")
            
        except ImportError:
            logger.error("faiss not installed. Run: pip install faiss-cpu")
            raise
    
    def _load_index(self):
        """Load existing index from disk."""
        if os.path.exists(self.index_path):
            try:
                import faiss
                
                # Load index
                self._index = faiss.read_index(self.index_path)
                
                # Load metadata
                meta_path = self.index_path + ".meta"
                if os.path.exists(meta_path):
                    with open(meta_path, 'rb') as f:
                        data = pickle.load(f)
                        self._student_ids = data.get('student_ids', [])
                        self._student_names = data.get('student_names', {})
                
                logger.info(
                    f"Loaded FAISS index with {self._index.ntotal} vectors"
                )
            except Exception as e:
                logger.warning(f"Failed to load index: {e}. Creating new.")
                self._create_index()
        else:
            self._create_index()
    
    def _save_index(self):
        """Save index and metadata to disk."""
        try:
            index_dir = os.path.dirname(self.index_path)
            if index_dir:
                os.makedirs(index_dir, exist_ok=True)
            
            import faiss
            faiss.write_index(self._index, self.index_path)
            
            # Save metadata
            meta_path = self.index_path + ".meta"
            with open(meta_path, 'wb') as f:
                pickle.dump({
                    'student_ids': self._student_ids,
                    'student_names': self._student_names
                }, f)
            
            logger.info(f"Saved FAISS index to {self.index_path}")
            
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def add(self, student_id: str, name: str, embedding: np.ndarray) -> bool:
        """
        Add a face embedding to the store.
        Thread-safe operation.
        """
        with self._lock:
            if embedding.shape[0] != self.EMBEDDING_DIM:
                logger.error(f"Invalid embedding dimension: {embedding.shape[0]}")
                return False
            
            # Normalize embedding
            emb = embedding / np.linalg.norm(embedding)
            
            # Check if student_id already exists
            if student_id in self._student_ids:
                logger.warning(f"Student {student_id} already exists. Updating.")
                return self.update(student_id, name, embedding)
            
            try:
                # Add to FAISS index
                self._index.add(emb.reshape(1, -1).astype('float32'))
                
                # Store metadata
                self._student_ids.append(student_id)
                self._student_names[student_id] = name
                self._embeddings.append(emb)
                
                # Save to disk
                self._save_index()
                
                logger.info(f"Added student {student_id} ({name}) to index")
                return True
                
            except Exception as e:
                logger.error(f"Failed to add embedding: {e}")
                return False
    
    def update(self, student_id: str, name: str, embedding: np.ndarray) -> bool:
        """
        Update an existing face embedding.
        Thread-safe operation.
        """
        with self._lock:
            if student_id not in self._student_ids:
                return self.add(student_id, name, embedding)
            
            # For now, just update metadata
            self._student_names[student_id] = name
            
            idx = self._student_ids.index(student_id)
            emb = embedding / np.linalg.norm(embedding)
            self._embeddings[idx] = emb
            
            # Replace in index (FAISS workaround)
            self._index.reset()
            for e in self._embeddings:
                self._index.add(e.reshape(1, -1).astype('float32'))
            
            self._save_index()
            logger.info(f"Updated student {student_id}")
            return True
    
    def delete(self, student_id: str) -> bool:
        """
        Delete a face embedding from the store.
        Thread-safe operation.
        """
        with self._lock:
            if student_id not in self._student_ids:
                logger.warning(f"Student {student_id} not found")
                return False
            
            idx = self._student_ids.index(student_id)
            
            # Remove from lists
            self._student_ids.pop(idx)
            self._student_names.pop(student_id)
            self._embeddings.pop(idx)
            
            # Rebuild index
            self._index.reset()
            for e in self._embeddings:
                self._index.add(e.reshape(1, -1).astype('float32'))
            
            self._save_index()
            logger.info(f"Deleted student {student_id}")
            return True
    
    def search(
        self, 
        embedding: np.ndarray, 
        k: int = 1,
        threshold: float = 0.5
    ) -> List[Tuple[str, str, float]]:
        """
        Search for similar faces.
        Thread-safe operation.
        
        Args:
            embedding: Query embedding
            k: Number of results to return
            threshold: Minimum similarity threshold (0-1)
            
        Returns:
            List of (student_id, name, similarity) tuples
        """
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                logger.warning("Index is empty")
                return []
            
            # Normalize query
            query = embedding / np.linalg.norm(embedding)
            
            try:
                # Search
                distances, indices = self._index.search(
                    query.reshape(1, -1).astype('float32'),
                    min(k, self._index.ntotal)
                )
                
                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx < 0:  # Invalid index
                        continue
                    
                    student_id = self._student_ids[idx]
                    name = self._student_names[student_id]
                    
                    # Apply threshold (dist is cosine similarity, already in -1 to 1)
                    if dist >= threshold:
                        results.append((student_id, name, float(dist)))
                    else:
                        break  # Results are sorted by distance
                
                return results
                
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the index."""
        return {
            "total_faces": len(self._student_ids),
            "embedding_dim": self.EMBEDDING_DIM,
            "index_type": type(self._index).__name__,
            "use_gpu": self.use_gpu
        }
    
    def clear(self) -> bool:
        """Clear all embeddings."""
        self._index.reset()
        self._student_ids = []
        self._student_names = {}
        self._embeddings = []
        self._save_index()
        logger.info("Cleared FAISS index")
        return True
    
    def __len__(self) -> int:
        return len(self._student_ids)
    
    def __repr__(self) -> str:
        return f"VectorStore(faces={len(self._student_ids)}, dim={self.EMBEDDING_DIM})"


def test_vector_store():
    """Quick test function."""
    print("Testing VectorStore...")
    
    store = VectorStore(index_path="test_faiss.bin")
    
    # Add test embeddings
    test_emb = np.random.randn(512)
    store.add("test001", "Test User", test_emb)
    
    # Search
    results = store.search(test_emb, k=1)
    
    print(f"✓ VectorStore initialized")
    print(f"✓ Added 1 face, found {len(results)} match")
    
    # Clean up
    store.clear()
    if os.path.exists("test_faiss.bin"):
        os.remove("test_faiss.bin")
    if os.path.exists("test_faiss.bin.meta"):
        os.remove("test_faiss.bin.meta")
    
    return True


if __name__ == "__main__":
    test_vector_store()
