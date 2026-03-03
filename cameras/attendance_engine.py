"""
Attendance Engine - Handle attendance recording and deduplication
Manages attendance records, prevents duplicates, and integrates with database
"""
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# C-SEC-003 FIX: Metadata validation constants
ALLOWED_METADATA_KEYS = {'bbox', 'confidence', 'processing_time', 'face_quality', 'detection_score'}
MAX_METADATA_SIZE = 1024  # 1KB limit

def sanitize_metadata(metadata):
    """
    Sanitize metadata to prevent SQL injection and limit size.
    
    Args:
        metadata: Input metadata dict or any type
        
    Returns:
        dict: Sanitized metadata with only allowed keys
    """
    if not isinstance(metadata, dict):
        return {}
    
    # Filter allowed keys and validate values
    sanitized = {}
    for key, value in metadata.items():
        if key not in ALLOWED_METADATA_KEYS:
            continue
        
        # Validate value type
        if isinstance(value, (int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, str):
            # Limit string length
            sanitized[key] = value[:256] if len(value) > 256 else value
        elif isinstance(value, (list, tuple)) and len(value) <= 4:
            # Allow small lists (e.g., bbox coordinates)
            sanitized[key] = list(value)[:4]
    
    # Check total size
    json_str = json.dumps(sanitized)
    if len(json_str) > MAX_METADATA_SIZE:
        logger.warning(f"Metadata too large ({len(json_str)} bytes), truncating")
        return {}
    
    return sanitized


class AttendanceEngine:
    """
    Engine for managing attendance records
    """
    
    def __init__(self, db_pool=None, dedup_window=300):
        """
        Initialize attendance engine
        
        Args:
            db_pool: Database connection pool (optional)
            dedup_window: Time window in seconds for duplicate detection
        """
        self.db_pool = db_pool
        
        # Deduplication settings
        self.dedup_window = dedup_window
        
        # In-memory cache for deduplication
        # Format: {(person_id, camera_id): last_attendance_time}
        self.recent_attendance = {}
        self.cache_lock = threading.RLock()
        
        # Callbacks
        self.on_attendance_recorded = []
        self.on_duplicate_detected = []
        
        # Statistics
        self.stats = {
            'total_records': 0,
            'duplicates': 0,
            'db_errors': 0
        }
        self.stats_lock = threading.RLock()
        
        # Start cache cleanup thread
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def record_attendance(self, person_id, camera_id, confidence=None, metadata=None):
        """
        Record an attendance event with atomic deduplication.
        
        C-RC-001 FIX: Check and record trong cùng một atomic block
        C-SEC-003 FIX: Sanitize metadata trước khi lưu
        C-ED-002 FIX: Sử dụng UTC timezone
        
        Args:
            person_id: ID of the recognized person
            camera_id: ID of the camera that captured the face
            confidence: Recognition confidence score
            metadata: Additional metadata
        
        Returns:
            bool: True if recorded, False if duplicate
        """
        timestamp = time.time()
        
        # C-RC-001 FIX: Atomic check-and-set operation
        with self.cache_lock:
            key = (person_id, camera_id)
            
            # Check for duplicate
            if key in self.recent_attendance:
                last_time = self.recent_attendance[key]
                if timestamp - last_time < self.dedup_window:
                    # Duplicate detected
                    with self.stats_lock:
                        self.stats['duplicates'] += 1
                    
                    for callback in self.on_duplicate_detected:
                        try:
                            callback(person_id, camera_id, timestamp)
                        except Exception as e:
                            logger.error(f"Duplicate callback error: {e}")
                    
                    return False
            
            # Record in cache immediately (atomic)
            self.recent_attendance[key] = timestamp
            
            # Update stats trong cùng lock
            with self.stats_lock:
                self.stats['total_records'] += 1
        
        # C-SEC-003 FIX: Sanitize metadata
        safe_metadata = sanitize_metadata(metadata)
        
        # C-ED-002 FIX: Use UTC timezone
        now_utc = datetime.now(timezone.utc)
        
        # Record attendance
        attendance_record = {
            'person_id': person_id,
            'camera_id': camera_id,
            'timestamp': timestamp,
            'datetime': now_utc.isoformat(),
            'date': now_utc.strftime('%Y-%m-%d'),
            'time': now_utc.strftime('%H:%M:%S'),
            'confidence': confidence,
            'metadata': safe_metadata
        }
        
        # Save to database (async or sync)
        if self.db_pool:
            try:
                self._save_to_db(attendance_record)
            except Exception as e:
                logger.error(f"Database error: {e}")
                with self.stats_lock:
                    self.stats['db_errors'] += 1
        
        # Notify callbacks
        for callback in self.on_attendance_recorded:
            try:
                callback(attendance_record)
            except Exception as e:
                logger.error(f"Attendance callback error: {e}")
        
        logger.info(f"Attendance recorded: {person_id} at {camera_id}")
        return True
    
    def _is_duplicate(self, person_id, camera_id, timestamp):
        """Check if attendance is duplicate"""
        with self.cache_lock:
            key = (person_id, camera_id)
            
            if key in self.recent_attendance:
                last_time = self.recent_attendance[key]
                if timestamp - last_time < self.dedup_window:
                    return True
            
            return False
    
    def _record_attendance(self, person_id, camera_id, timestamp):
        """Record attendance in cache"""
        with self.cache_lock:
            key = (person_id, camera_id)
            self.recent_attendance[key] = timestamp
    
    def _save_to_db(self, record):
        """
        Save attendance to database với proper error handling.
        
        C-SEC-003 FIX: Use context manager for connection
        """
        if not self.db_pool:
            return
        
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # C-SEC-003 FIX: Use JSON dumps for safe serialization
                    metadata_json = json.dumps(record['metadata'])
                    
                    cursor.execute(
                        """INSERT INTO attendance
                           (person_id, camera_id, date, time, confidence, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            record['person_id'],
                            record['camera_id'],
                            record['date'],
                            record['time'],
                            record['confidence'],
                            metadata_json
                        )
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Database save error: {e}")
            raise
    
    def _cleanup_loop(self):
        """Clean up old cache entries"""
        while self.running:
            try:
                self._cleanup_cache()
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
            
            time.sleep(60)  # Run every minute
    
    def _cleanup_cache(self):
        """Remove old entries from cache"""
        current_time = time.time()
        
        with self.cache_lock:
            keys_to_remove = []
            
            for key, timestamp in self.recent_attendance.items():
                if current_time - timestamp > self.dedup_window * 2:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.recent_attendance[key]
    
    def get_attendance(self, date=None, camera_id=None, person_id=None):
        """
        Get attendance records
        
        Args:
            date: Filter by date (YYYY-MM-DD)
            camera_id: Filter by camera
            person_id: Filter by person
        
        Returns:
            list: List of attendance records
        """
        if not self.db_pool:
            return []
        
        conn = self.db_pool.connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM attendance WHERE 1=1"
        params = []
        
        if date:
            query += " AND date = %s"
            params.append(date)
        
        if camera_id:
            query += " AND camera_id = %s"
            params.append(camera_id)
        
        if person_id:
            query += " AND person_id = %s"
            params.append(person_id)
        
        query += " ORDER BY time DESC"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        conn.close()
        
        return results
    
    def get_stats(self):
        """Get attendance statistics"""
        with self.stats_lock:
            return dict(self.stats)
    
    def set_dedup_window(self, seconds):
        """Set deduplication window"""
        self.dedup_window = seconds
    
    def shutdown(self):
        """Shutdown the engine"""
        self.running = False


class MultiCameraAttendanceManager:
    """
    Manage attendance across multiple cameras
    """
    
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        
        # Create attendance engine
        self.engine = AttendanceEngine(db_pool)
        
        # Track attendance by camera
        self.camera_attendance = defaultdict(list)
        
        # Register callbacks
        self.engine.on_attendance_recorded.append(self._on_attendance_recorded)
    
    def _on_attendance_recorded(self, record):
        """Handle attendance recorded"""
        camera_id = record['camera_id']
        self.camera_attendance[camera_id].append(record)
        
        # Keep only recent records in memory
        if len(self.camera_attendance[camera_id]) > 100:
            self.camera_attendance[camera_id] = self.camera_attendance[camera_id][-100:]
    
    def process_recognition(self, camera_id, recognized_faces):
        """
        Process recognition results from a camera
        
        Args:
            camera_id: Camera identifier
            recognized_faces: List of recognized face dicts
        
        Returns:
            list: List of new attendance records
        """
        new_records = []
        
        for face in recognized_faces:
            person_id = face.get('person_id')
            confidence = face.get('confidence')
            
            if person_id:
                # Record attendance
                recorded = self.engine.record_attendance(
                    person_id=person_id,
                    camera_id=camera_id,
                    confidence=confidence,
                    metadata=face
                )
                
                if recorded:
                    new_records.append({
                        'person_id': person_id,
                        'camera_id': camera_id,
                        'confidence': confidence
                    })
        
        return new_records
    
    def get_camera_attendance(self, camera_id, limit=50):
        """Get recent attendance for a camera"""
        return self.camera_attendance.get(camera_id, [])[-limit:]
    
    def get_all_attendance(self, date=None):
        """Get all attendance for a date"""
        return self.engine.get_attendance(date=date)
    
    def get_summary(self, date=None):
        """Get attendance summary"""
        records = self.engine.get_attendance(date=date)
        
        # Count unique persons
        person_counts = defaultdict(int)
        for record in records:
            person_counts[record[1]] += 1  # person_id is index 1
        
        return {
            'total_records': len(records),
            'unique_persons': len(person_counts),
            'by_person': dict(person_counts)
        }


# Factory function
def create_attendance_manager(db_pool=None):
    """Create attendance manager"""
    return MultiCameraAttendanceManager(db_pool)
