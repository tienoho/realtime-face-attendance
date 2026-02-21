"""
Health Monitor - Camera health monitoring and auto-reconnection
Monitors camera health, detects failures, and handles reconnection
"""
import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class CameraHealthMonitor:
    """
    Monitor camera health and handle failures
    """
    
    def __init__(self, camera_manager, check_interval=10):
        self.camera_manager = camera_manager
        self.check_interval = check_interval
        
        # Health history
        self.health_history = defaultdict(lambda: deque(maxlen=100))
        
        # Health thresholds
        self.error_rate_threshold = 0.1  # 10% errors
        self.fps_threshold = 5  # Minimum FPS
        self.timeout_threshold = 30  # Seconds without frame
        
        # Monitoring state
        self.running = False
        self.monitor_thread = None
        
        # Callbacks
        self.on_health_change = []
        self.on_camera_down = []
        self.on_camera_up = []
    
    def start(self):
        """Start health monitoring"""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Health monitoring started")
    
    def stop(self):
        """Stop health monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Health monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._check_all_cameras()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            
            time.sleep(self.check_interval)
    
    def _check_all_cameras(self):
        """Check health of all cameras"""
        for camera_id in list(self.camera_manager.cameras.keys()):
            self._check_camera(camera_id)
    
    def _check_camera(self, camera_id):
        """Check health of a single camera"""
        # Get camera info
        info = self.camera_manager.get_camera_info(camera_id)
        if not info:
            return
        
        stats = info.get('stats', {})
        
        # Calculate health metrics
        total_frames = stats.get('frames_captured', 0)
        errors = stats.get('errors', 0)
        fps = stats.get('fps', 0)
        
        # Calculate error rate
        error_rate = errors / max(total_frames + errors, 1)
        
        # Check for timeout
        last_frame_time = stats.get('last_frame_time', 0)
        time_since_frame = time.time() - last_frame_time if last_frame_time else 0
        is_timeout = time_since_frame > self.timeout_threshold
        
        # Determine health status
        if not info.get('connected') or is_timeout:
            status = 'down'
        elif error_rate > self.error_rate_threshold:
            status = 'degraded'
        elif fps < self.fps_threshold:
            status = 'degraded'
        else:
            status = 'healthy'
        
        # Get previous status
        prev_status = self._get_latest_status(camera_id)
        
        # Record health
        health_record = {
            'timestamp': time.time(),
            'status': status,
            'error_rate': error_rate,
            'fps': fps,
            'total_frames': total_frames,
            'errors': errors,
            'time_since_frame': time_since_frame
        }
        
        self.health_history[camera_id].append(health_record)
        
        # Check for status changes
        if status != prev_status:
            self._handle_status_change(camera_id, prev_status, status)
        
        # Notify callbacks
        for callback in self.on_health_change:
            try:
                callback(camera_id, status, health_record)
            except Exception as e:
                logger.error(f"Health callback error: {e}")
    
    def _get_latest_status(self, camera_id):
        """Get the latest health status for a camera"""
        history = self.health_history.get(camera_id)
        if history and len(history) > 0:
            return history[-1].get('status')
        return 'unknown'
    
    def _handle_status_change(self, camera_id, old_status, new_status):
        """Handle camera status change"""
        logger.warning(f"Camera {camera_id} status changed: {old_status} -> {new_status}")
        
        if new_status == 'down':
            # Camera went down
            for callback in self.on_camera_down:
                try:
                    callback(camera_id)
                except Exception as e:
                    logger.error(f"Camera down callback error: {e}")
            
            # Try to restart camera
            self._restart_camera(camera_id)
        
        elif new_status == 'healthy' and old_status != 'healthy':
            # Camera came back up
            for callback in self.on_camera_up:
                try:
                    callback(camera_id)
                except Exception as e:
                    logger.error(f"Camera up callback error: {e}")
    
    def _restart_camera(self, camera_id):
        """Attempt to restart a camera"""
        logger.info(f"Attempting to restart camera {camera_id}")
        
        try:
            # Stop camera
            self.camera_manager.stop_camera(camera_id)
            
            # Wait a bit
            time.sleep(2)
            
            # Start camera
            self.camera_manager.start_camera(camera_id)
            
            logger.info(f"Restarted camera {camera_id}")
            
        except Exception as e:
            logger.error(f"Failed to restart camera {camera_id}: {e}")
    
    def get_health(self, camera_id):
        """Get current health status for a camera"""
        history = self.health_history.get(camera_id)
        if history and len(history) > 0:
            return dict(history[-1])
        return {'status': 'unknown'}
    
    def get_all_health(self):
        """Get health status for all cameras"""
        return {
            camera_id: self.get_health(camera_id)
            for camera_id in self.camera_manager.cameras.keys()
        }
    
    def get_history(self, camera_id, limit=100):
        """Get health history for a camera"""
        history = self.health_history.get(camera_id, [])
        return list(history)[-limit:]


class AutoReconnectManager:
    """
    Automatic reconnection manager for cameras
    """
    
    def __init__(self, camera_manager):
        self.camera_manager = camera_manager
        
        # Reconnection settings
        self.max_retries = 5
        self.base_delay = 1
        self.max_delay = 60
        
        # Track retry counts
        self.retry_counts = defaultdict(int)
        
        # Active timers
        self.retry_timers = {}
    
    def schedule_reconnect(self, camera_id, delay=None):
        """Schedule a reconnection attempt"""
        if camera_id in self.retry_timers:
            # Already scheduled
            return
        
        retry_count = self.retry_counts[camera_id]
        
        if retry_count >= self.max_retries:
            logger.error(f"Max retries reached for camera {camera_id}")
            return
        
        # Calculate delay with exponential backoff
        if delay is None:
            delay = min(self.base_delay * (2 ** retry_count), self.max_delay)
        
        logger.info(f"Scheduling reconnect for camera {camera_id} in {delay}s")
        
        # Schedule timer
        timer = threading.Timer(delay, self._attempt_reconnect, args=(camera_id,))
        timer.daemon = True
        timer.start()
        self.retry_timers[camera_id] = timer
    
    def _attempt_reconnect(self, camera_id):
        """Attempt to reconnect a camera"""
        # Remove timer reference
        if camera_id in self.retry_timers:
            del self.retry_timers[camera_id]
        
        # Check if camera exists
        if camera_id not in self.camera_manager.cameras:
            return
        
        try:
            # Try to reconnect
            camera = self.camera_manager.cameras[camera_id]
            
            if camera.connect():
                logger.info(f"Successfully reconnected camera {camera_id}")
                self.retry_counts[camera_id] = 0
            else:
                # Failed, schedule another attempt
                self.retry_counts[camera_id] += 1
                logger.warning(f"Reconnect failed for {camera_id}, retry {self.retry_counts[camera_id]}")
                self.schedule_reconnect(camera_id)
                
        except Exception as e:
            logger.error(f"Reconnect error for {camera_id}: {e}")
            self.schedule_reconnect(camera_id)
    
    def cancel_reconnect(self, camera_id):
        """Cancel pending reconnection"""
        if camera_id in self.retry_timers:
            self.retry_timers[camera_id].cancel()
            del self.retry_timers[camera_id]
    
    def reset_retry_count(self, camera_id):
        """Reset retry count for a camera"""
        self.retry_counts[camera_id] = 0


class MetricsCollector:
    """
    Collect and aggregate system metrics
    """
    
    def __init__(self):
        self.metrics = defaultdict(lambda: deque(maxlen=1000))
        self.lock = threading.Lock()
    
    def record(self, metric_name, value, tags=None):
        """Record a metric value"""
        with self.lock:
            record = {
                'timestamp': time.time(),
                'value': value,
                'tags': tags or {}
            }
            self.metrics[metric_name].append(record)
    
    def get(self, metric_name, limit=100):
        """Get metric values"""
        with self.lock:
            return list(self.metrics.get(metric_name, []))[-limit:]
    
    def get_stats(self, metric_name):
        """Get statistics for a metric"""
        values = [r['value'] for r in self.metrics.get(metric_name, [])]
        
        if not values:
            return {'count': 0}
        
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values)
        }
    
    def get_all_stats(self):
        """Get statistics for all metrics"""
        return {
            name: self.get_stats(name)
            for name in self.metrics.keys()
        }


# Global instances
health_monitor = None
reconnect_manager = None
metrics_collector = None


def initialize_health_monitor(camera_manager):
    """Initialize health monitoring"""
    global health_monitor, reconnect_manager, metrics_collector
    
    health_monitor = CameraHealthMonitor(camera_manager)
    reconnect_manager = AutoReconnectManager(camera_manager)
    metrics_collector = MetricsCollector()
    
    # Set up callbacks
    health_monitor.on_camera_down.append(
        lambda cid: reconnect_manager.schedule_reconnect(cid)
    )
    
    health_monitor.start()
    
    return health_monitor
