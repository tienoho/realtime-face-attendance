"""
Background job manager for camera discovery
"""
import threading
import uuid
import time
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoveryJob:
    """Represents a camera discovery job"""
    
    def __init__(self, job_id: str, scan_network: bool = True, ip_range: str = None):
        self.job_id = job_id
        self.scan_network = scan_network
        self.ip_range = ip_range
        self.status = JobStatus.PENDING
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self._result_ready = threading.Event()
    
    def set_running(self):
        self.status = JobStatus.RUNNING
        self.started_at = time.time()
    
    def set_completed(self, result: Dict[str, Any]):
        self.status = JobStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()
        self._result_ready.set()
    
    def set_failed(self, error: str):
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = time.time()
        self._result_ready.set()
    
    def is_complete(self) -> bool:
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED]
    
    def wait(self, timeout: float = None) -> bool:
        return self._result_ready.wait(timeout)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "scan_network": self.scan_network,
            "ip_range": self.ip_range,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error
        }


class DiscoveryJobManager:
    """Manages background discovery jobs"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._jobs: Dict[str, DiscoveryJob] = {}
        self._jobs_lock = threading.Lock()
        self._initialized = True
    
    def create_job(self, scan_network: bool = True, ip_range: str = None) -> DiscoveryJob:
        """Create a new discovery job"""
        job_id = str(uuid.uuid4())[:8]
        job = DiscoveryJob(job_id, scan_network, ip_range)
        with self._jobs_lock:
            self._jobs[job_id] = job
        return job
    
    def get_job(self, job_id: str) -> Optional[DiscoveryJob]:
        """Get a job by ID"""
        with self._jobs_lock:
            return self._jobs.get(job_id)
    
    def remove_completed_jobs(self, max_age_seconds: int = 300):
        """Remove completed jobs older than max_age_seconds"""
        now = time.time()
        with self._jobs_lock:
            to_remove = []
            for job_id, job in self._jobs.items():
                if job.is_complete() and job.completed_at:
                    if now - job.completed_at > max_age_seconds:
                        to_remove.append(job_id)
            for job_id in to_remove:
                del self._jobs[job_id]


# Global instance
_job_manager = None


def get_job_manager() -> DiscoveryJobManager:
    """Get the global job manager instance"""
    global _job_manager
    if _job_manager is None:
        _job_manager = DiscoveryJobManager()
    return _job_manager


def run_discovery_in_background(job: DiscoveryJob, ip_range: str = None, scan_network: bool = True):
    """Run camera discovery in background thread"""
    from cameras.camera_discovery import CameraDiscovery
    
    job.set_running()
    logger.info(f"Starting background discovery job {job.job_id}")
    
    try:
        # Discover USB cameras (fast)
        results = {
            'usb': [],
            'ip': [],
            'total': 0
        }
        
        # Discover USB cameras
        results['usb'] = CameraDiscovery.discover_usb_cameras()
        
        # Discover IP cameras if requested
        if scan_network:
            results['ip'] = CameraDiscovery.discover_ip_cameras(ip_range=ip_range, timeout=1)
        
        results['total'] = len(results['usb']) + len(results['ip'])
        
        job.set_completed(results)
        logger.info(f"Discovery job {job.job_id} completed: {results['total']} cameras found")
        
    except Exception as e:
        logger.error(f"Discovery job {job.job_id} failed: {e}")
        job.set_failed(str(e))
