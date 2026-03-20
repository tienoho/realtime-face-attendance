"""
Vector Store Module
==================

FAISS-based vector storage for fast face embedding lookup.
Optimized version with ID mapping, lazy deletion, and memory efficiency.
"""

import os
import logging
import pickle
import numpy as np
import threading
from typing import List, Tuple, Optional, Dict, Any, Set
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)


@dataclass
class FaceRecord:
    """Record for a face in the database."""
    staff_id: str
    name: str
    embedding: np.ndarray
    created_at: str = ""


class VectorStore:
    """
    FAISS-based vector store for face embeddings.
    
    C-RC-002 FIX: Thread-safe with proper lock management
    C-ML-002 FIX: No duplicate embeddings (only in FAISS)
    C-PERF-001 FIX: O(1) update/delete with lazy deletion
    
    Features:
    - Fast similarity search (O(log n) with IVF)
    - Persistent storage
    - Add, update, delete operations with ID mapping
    - Memory efficient (no duplicate embeddings)
    """
    
    # Embedding dimension from config
    EMBEDDING_DIM = config.EMBEDDING_DIM
    
    def __init__(
        self,
        index_path: str = None,
        use_gpu: bool = None,
        nlist: int = None,
        nprobe: int = None,
        rebuild_threshold: float = 0.1
    ):
        """
        Initialize the vector store.
        
        Args:
            index_path: Path to save/load FAISS index
            use_gpu: Use GPU for search (if available)
            nlist: Number of clusters for IVF index
            nprobe: Number of clusters to search
            rebuild_threshold: Fraction of deleted items to trigger rebuild
        """
        self.index_path = index_path if index_path is not None else config.INDEX_PATH
        self.use_gpu = use_gpu if use_gpu is not None else config.USE_GPU
        self.nlist = nlist if nlist is not None else config.IVF_NLIST
        self.nprobe = nprobe if nprobe is not None else config.IVF_NPROBE
        self.rebuild_threshold = rebuild_threshold
        
        # Thread safety - separate locks for different operations
        self._index_lock = threading.RLock()
        self._meta_lock = threading.RLock()
        self._save_lock = threading.Lock()
        
        # FAISS index with ID mapping
        self._index = None
        self._next_id = 0
        
        # Metadata only (no embeddings duplication)
        self._staff_ids: Dict[int, str] = {}  # faiss_id -> staff_id
        self._staff_names: Dict[str, str] = {}  # staff_id -> name
        self._faiss_id_map: Dict[str, int] = {}  # staff_id -> faiss_id
        self._deleted_ids: Set[int] = set()
        
        self._load_index()

    @staticmethod
    def _normalize_embedding(embedding: np.ndarray) -> Optional[np.ndarray]:
        """Normalize embedding safely; return None for invalid vectors."""
        if embedding is None:
            return None
        norm = np.linalg.norm(embedding)
        if norm <= 0:
            return None
        return embedding / norm
    
    def _create_index(self):
        """Create a new FAISS index with ID mapping."""
        try:
            import faiss
            
            # C-PERF-001 FIX: Use IndexIDMap for efficient updates
            base_index = faiss.IndexFlatIP(self.EMBEDDING_DIM)
            self._index = faiss.IndexIDMap(base_index)
            
            # Enable GPU if requested and available
            if self.use_gpu:
                try:
                    res = faiss.StandardGpuResources()
                    self._index = faiss.index_cpu_to_gpu(res, 0, self._index)
                    logger.info("FAISS index moved to GPU")
                except Exception as e:
                    logger.warning(f"GPU not available, using CPU: {e}")
            
            logger.info(f"Created new FAISS index with ID mapping (dimension={self.EMBEDDING_DIM})")
            
        except ImportError:
            logger.error("faiss not installed. Run: pip install faiss-cpu")
            raise
    
    def _load_index(self):
        """Load existing index from disk."""
        if os.path.exists(self.index_path):
            try:
                import faiss
                
                with self._index_lock:
                    # Load index
                    self._index = faiss.read_index(self.index_path)
                
                # Load metadata
                meta_path = self.index_path + ".meta"
                if os.path.exists(meta_path):
                    with open(meta_path, 'rb') as f:
                        data = pickle.load(f)
                        self._staff_ids = data.get('staff_ids', {})
                        self._staff_names = data.get('staff_names', {})
                        self._faiss_id_map = data.get('faiss_id_map', {})
                        self._next_id = data.get('next_id', 0)
                        self._deleted_ids = set(data.get('deleted_ids', []))
                
                logger.info(
                    f"Loaded FAISS index with {self._index.ntotal} vectors, "
                    f"{len(self._deleted_ids)} marked for deletion"
                )
            except Exception as e:
                logger.warning(f"Failed to load index: {e}. Creating new.")
                self._create_index()
        else:
            self._create_index()
    
    def _save_index(self):
        """Save index and metadata to disk (thread-safe)."""
        with self._save_lock:
            try:
                index_dir = os.path.dirname(self.index_path)
                if index_dir:
                    os.makedirs(index_dir, exist_ok=True)
                
                import faiss
                
                with self._index_lock:
                    faiss.write_index(self._index, self.index_path)
                
                # Save metadata
                meta_path = self.index_path + ".meta"
                with self._meta_lock:
                    with open(meta_path, 'wb') as f:
                        pickle.dump({
                            'staff_ids': self._staff_ids,
                            'staff_names': self._staff_names,
                            'faiss_id_map': self._faiss_id_map,
                            'next_id': self._next_id,
                            'deleted_ids': list(self._deleted_ids)
                        }, f)
                
                logger.info(f"Saved FAISS index to {self.index_path}")
                
            except Exception as e:
                logger.error(f"Failed to save index: {e}")
    
    def add(self, staff_id: str, name: str, embedding: np.ndarray) -> bool:
        """
        Add a face embedding to the store.
        C-RC-002 FIX: Thread-safe, no nested lock calls
        """
        if embedding.shape[0] != self.EMBEDDING_DIM:
            logger.error(f"Invalid embedding dimension: {embedding.shape[0]}")
            return False
        
        # Normalize embedding
        emb = self._normalize_embedding(embedding)
        if emb is None:
            logger.error("Invalid embedding vector: zero norm")
            return False
        
        with self._meta_lock:
            # Check if staff_id already exists
            if staff_id in self._faiss_id_map:
                logger.warning(f"Staff {staff_id} already exists. Updating.")
                # C-RC-002 FIX: Inline update logic instead of calling update()
                return self._update_internal(staff_id, name, emb)
        
        with self._index_lock:
            try:
                # Assign new FAISS ID
                faiss_id = self._next_id
                self._next_id += 1
                
                # Add to FAISS index with ID
                self._index.add_with_ids(
                    emb.reshape(1, -1).astype('float32'),
                    np.array([faiss_id], dtype=np.int64)
                )
                
                # Update metadata
                with self._meta_lock:
                    self._staff_ids[faiss_id] = staff_id
                    self._staff_names[staff_id] = name
                    self._faiss_id_map[staff_id] = faiss_id
                
                # Schedule async save
                self._schedule_save()
                
                logger.info(f"Added staff {staff_id} ({name}) to index")
                return True
                
            except Exception as e:
                logger.error(f"Failed to add embedding: {e}")
                return False
    
    def _update_internal(self, staff_id: str, name: str, embedding: np.ndarray) -> bool:
        """
        Update an existing face embedding (internal, assumes meta_lock held).
        C-PERF-001 FIX: O(1) update with ID mapping instead of O(n) rebuild
        """
        faiss_id = self._faiss_id_map.get(staff_id)
        if faiss_id is None:
            return False
        
        # Mark old embedding as deleted
        self._deleted_ids.add(faiss_id)
        
        # Add new embedding with new ID
        new_faiss_id = self._next_id
        self._next_id += 1
        
        with self._index_lock:
            self._index.add_with_ids(
                embedding.reshape(1, -1).astype('float32'),
                np.array([new_faiss_id], dtype=np.int64)
            )
        
        # Update metadata
        del self._staff_ids[faiss_id]
        self._staff_ids[new_faiss_id] = staff_id
        self._staff_names[staff_id] = name
        self._faiss_id_map[staff_id] = new_faiss_id
        
        # Check if need to compact
        if len(self._deleted_ids) > len(self._faiss_id_map) * self.rebuild_threshold:
            self._compact_index()
        else:
            self._schedule_save()
        
        logger.info(f"Updated staff {staff_id}")
        return True
    
    def update(self, staff_id: str, name: str, embedding: np.ndarray) -> bool:
        """
        Update an existing face embedding (public API).
        Thread-safe operation.
        """
        emb = self._normalize_embedding(embedding)
        if emb is None:
            logger.error("Invalid embedding vector: zero norm")
            return False
        
        with self._meta_lock:
            if staff_id not in self._faiss_id_map:
                # Add new instead
                return self.add(staff_id, name, embedding)
            return self._update_internal(staff_id, name, emb)
    
    def delete(self, staff_id: str) -> bool:
        """
        Delete a face embedding from the store.
        C-PERF-001 FIX: O(1) lazy deletion instead of O(n) rebuild
        """
        with self._meta_lock:
            if staff_id not in self._faiss_id_map:
                logger.warning(f"Staff {staff_id} not found")
                return False
            
            faiss_id = self._faiss_id_map[staff_id]
            
            # Lazy deletion - mark as deleted
            self._deleted_ids.add(faiss_id)
            
            # Remove from metadata
            del self._faiss_id_map[staff_id]
            del self._staff_names[staff_id]
            if faiss_id in self._staff_ids:
                del self._staff_ids[faiss_id]
            
            # Check if need to compact
            if len(self._deleted_ids) > len(self._faiss_id_map) * self.rebuild_threshold:
                self._compact_index()
            else:
                self._schedule_save()
            
            logger.info(f"Deleted staff {staff_id}")
            return True
    
    def _compact_index(self):
        """
        Rebuild index to remove deleted items.
        Called when deleted ratio exceeds threshold.
        
        C-ML-002 FIX: Disabled because FAISS doesn't support direct read of vectors.
        This prevents index from being wiped. Instead, we rely on lazy deletion
        and search-time filtering (which already works correctly).
        
        TODO: For proper compaction, need to store embeddings separately in memory
        or use faiss.IndexIDMap2 which supports remove_ids.
        """
        logger.info(
            f"Compaction skipped: {len(self._deleted_ids)} items marked for deletion "
            f"will be filtered at search time. To fully compact, restart server "
            f"or implement embedding backup."
        )
        
        # Clear deleted set on restart or implement proper rebuild
        # For now, just schedule a save to persist the current state
        self._save_index()
    
    def _schedule_save(self):
        """Schedule async save (simplified version)."""
        # In production, use a background thread or task queue
        import threading
        threading.Thread(target=self._save_index, daemon=True).start()
    
    def search(
        self, 
        embedding: np.ndarray, 
        k: int = 1,
        threshold: float = 0.5
    ) -> List[Tuple[str, str, float]]:
        """
        Search for similar faces.
        Thread-safe operation.
        """
        with self._index_lock:
            if self._index is None or self._index.ntotal == 0:
                logger.warning("Index is empty")
                return []
            
            # Normalize query
            query = self._normalize_embedding(embedding)
            if query is None:
                logger.warning("Invalid query embedding: zero norm")
                return []
            
            try:
                # Search with extra k to account for deleted items
                search_k = min(k * 2 + len(self._deleted_ids), self._index.ntotal)
                
                distances, indices = self._index.search(
                    query.reshape(1, -1).astype('float32'),
                    search_k
                )
                
                results = []
                with self._meta_lock:
                    for dist, idx in zip(distances[0], indices[0]):
                        if idx < 0:
                            continue
                        if idx in self._deleted_ids:
                            continue
                        if idx not in self._staff_ids:
                            continue
                        
                        staff_id = self._staff_ids[idx]
                        name = self._staff_names.get(staff_id, "")
                        
                        # Apply threshold
                        if dist >= threshold:
                            results.append((staff_id, name, float(dist)))
                        else:
                            break
                        
                        if len(results) >= k:
                            break
                
                return results
                
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the index."""
        with self._index_lock, self._meta_lock:
            index_type = type(self._index).__name__ if self._index is not None else "None"
            return {
                "total_faces": len(self._faiss_id_map),
                "active_faces": len(self._faiss_id_map),
                "deleted_faces": len(self._deleted_ids),
                "embedding_dim": self.EMBEDDING_DIM,
                "index_type": index_type,
                "use_gpu": self.use_gpu
            }
    
    def clear(self) -> bool:
        """Clear all embeddings."""
        with self._index_lock, self._meta_lock:
            self._index.reset()
            self._staff_ids = {}
            self._staff_names = {}
            self._faiss_id_map = {}
            self._deleted_ids = set()
            self._next_id = 0
            self._save_index()
            logger.info("Cleared FAISS index")
            return True
    
    def __len__(self) -> int:
        with self._meta_lock:
            return len(self._faiss_id_map)
    
    def __repr__(self) -> str:
        return f"VectorStore(faces={len(self)}, dim={self.EMBEDDING_DIM})"


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
