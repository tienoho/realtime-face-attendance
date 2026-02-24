"""
Camera Manager - Multi-camera management with threading
Manages multiple camera connections, frame capture, and processing
"""
import threading
import queue
import logging
import time
import re
from collections import defaultdict
from .camera_factory import CameraFactory

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Manages multiple cameras with thread-based frame capture
    """
    
    def __init__(self, max_cameras=16, frame_queue_size=5):
        self.max_cameras = max_cameras
        self.frame_queue_size = frame_queue_size
        
        # Camera storage
        self.cameras = {}  # camera_id -> Camera object
        self.camera_configs = {}  # camera_id -> config
        self.frame_queues = {}  # camera_id -> Queue
        self.capture_threads = {}  # camera_id -> Thread
        self.stop_flags = {}  # camera_id -> Event for stopping
        
        # State
        self.running = False
        self.lock = threading.RLock()
        
        # Callbacks
        self.frame_callbacks = []
        self.status_callbacks = []
        
        # Statistics
        self.stats = defaultdict(lambda: {
            'frames_captured': 0,
            'frames_dropped': 0,
            'errors': 0,
            'fps': 0,
            'last_frame_time': 0
        })
    
    def add_camera(self, camera_id, camera_type, config):
        """
        Add a new camera to the manager
        
        Args:
            camera_id: Unique identifier for the camera
            camera_type: Type of camera ('usb', 'rtsp', 'http', 'onvif')
            config: Camera configuration dictionary
        
        Returns:
            bool: True if camera was added successfully
        """
        with self.lock:
            # Check if camera already exists
            if camera_id in self.cameras:
                logger.warning(f"Camera {camera_id} already exists")
                return False
            
            # Check max cameras
            if len(self.cameras) >= self.max_cameras:
                logger.error(f"Maximum number of cameras ({self.max_cameras}) reached")
                return False
            
            # Create camera
            try:
                camera = CameraFactory.create(camera_id, camera_type, config)
            except Exception as e:
                logger.error(f"Failed to create camera {camera_id}: {e}")
                return False
            
            # Create frame queue
            frame_queue = queue.Queue(maxsize=self.frame_queue_size)
            
            # Store camera and queue
            self.cameras[camera_id] = camera
            self.camera_configs[camera_id] = config
            self.frame_queues[camera_id] = frame_queue
            
            logger.info(f"Camera {camera_id} ({camera_type}) added successfully")
            return True
    
    def remove_camera(self, camera_id):
        """
        Remove a camera from the manager
        
        Args:
            camera_id: ID of camera to remove
        
        Returns:
            bool: True if camera was removed
        """
        with self.lock:
            if camera_id not in self.cameras:
                logger.warning(f"Camera {camera_id} not found")
                return False
            
            # Stop capture thread
            self._stop_capture_thread(camera_id)
            
            # Disconnect camera
            try:
                self.cameras[camera_id].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting camera {camera_id}: {e}")
            
            # Remove from storage
            del self.cameras[camera_id]
            del self.frame_queues[camera_id]
            del self.camera_configs[camera_id]
            
            logger.info(f"Camera {camera_id} removed")
            return True
    
    def start_camera(self, camera_id):
        """
        Start capturing from a camera
        
        Args:
            camera_id: ID of camera to start
        """
        with self.lock:
            if camera_id not in self.cameras:
                logger.error(f"Camera {camera_id} not found")
                return False

            # Create stop event for this camera
            stop_event = threading.Event()
            self.stop_flags[camera_id] = stop_event
            
            # Connect to camera
            camera = self.cameras[camera_id]
            if not camera.connect():
                logger.error(f"Failed to connect to camera {camera_id}")
                del self.stop_flags[camera_id]
                return False

            # Ensure capture loop can run when starting individual cameras.
            self.running = True
            
            # Start capture thread
            thread = threading.Thread(
                target=self._capture_loop,
                args=(camera_id, stop_event),
                daemon=True,
                name=f"Camera-{camera_id}"
            )
            thread.start()
            self.capture_threads[camera_id] = thread
            
            logger.info(f"Camera {camera_id} started")
            return True
    
    def stop_camera(self, camera_id):
        """
        Stop capturing from a camera
        """
        self._stop_capture_thread(camera_id)
        
        if camera_id in self.cameras:
            try:
                self.cameras[camera_id].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting camera {camera_id}: {e}")
        
        # Clean up stop flag
        if camera_id in self.stop_flags:
            del self.stop_flags[camera_id]

        # If there are no active capture threads, mark manager as not running.
        if not self.capture_threads:
            self.running = False
        
        logger.info(f"Camera {camera_id} stopped")

    def _stop_capture_thread(self, camera_id):
        """Stop capture thread for a camera"""
        if camera_id in self.stop_flags:
            # Signal thread to stop
            self.stop_flags[camera_id].set()
        
        # Wait for thread to finish (with timeout)
        if camera_id in self.capture_threads:
            thread = self.capture_threads[camera_id]
            thread.join(timeout=2.0)  # Wait up to 2 seconds
            if thread.is_alive():
                logger.warning(f"Capture thread for {camera_id} did not stop gracefully")
            del self.capture_threads[camera_id]
    
    def _capture_loop(self, camera_id, stop_event):
        """
        Continuous capture loop for one camera
        
        This runs in a separate thread for each camera
        """
        camera = self.cameras[camera_id]
        frame_queue = self.frame_queues[camera_id]
        
        while self.running and camera_id in self.cameras and not stop_event.is_set():
            start_time = time.time()
            
            # Read frame
            ret, frame = camera.read()
            
            if ret and frame is not None:
                # Put frame in queue
                try:
                    # Try non-blocking put
                    frame_queue.put_nowait((frame, time.time()))
                    self.stats[camera_id]['frames_captured'] += 1
                    self.stats[camera_id]['last_frame_time'] = time.time()
                    
                    # Calculate FPS
                    elapsed = time.time() - start_time
                    if elapsed > 0:
                        self.stats[camera_id]['fps'] = 1.0 / elapsed
                    
                    # Call frame callbacks
                    for callback in self.frame_callbacks:
                        try:
                            callback(camera_id, frame)
                        except Exception as e:
                            logger.error(f"Frame callback error: {e}")
                            
                except queue.Full:
                    # Queue is full, drop frame
                    try:
                        frame_queue.get_nowait()  # Remove old frame
                        frame_queue.put_nowait((frame, time.time()))
                        self.stats[camera_id]['frames_dropped'] += 1
                    except queue.Empty:
                        pass
                    except Exception as e:
                        logger.error(f"Error handling queue overflow: {e}")
            else:
                # Read failed
                self.stats[camera_id]['errors'] += 1
                
                # Try to reconnect
                self._handle_camera_error(camera_id)
                
                # Small delay before retry
                time.sleep(1)
    
    def _handle_camera_error(self, camera_id):
        """Handle camera read error"""
        camera = self.cameras[camera_id]
        
        # Check if camera is still connected
        if not camera.is_connected:
            # Try to reconnect
            logger.warning(f"Camera {camera_id} disconnected, attempting reconnect...")
            for attempt in range(3):
                if camera.connect():
                    logger.info(f"Camera {camera_id} reconnected")
                    return
                time.sleep(2)
            
            logger.error(f"Failed to reconnect camera {camera_id}")
    
    def start_all(self):
        """Start all registered cameras"""
        self.running = True
        
        for camera_id in list(self.cameras.keys()):
            self.start_camera(camera_id)
        
        logger.info(f"Started {len(self.cameras)} cameras")
    
    def stop_all(self):
        """Stop all cameras"""
        self.running = False
        
        for camera_id in list(self.cameras.keys()):
            self.stop_camera(camera_id)
        
        logger.info("All cameras stopped")
    
    def get_frame(self, camera_id, timeout=1):
        """
        Get a frame from a camera's queue
        
        Args:
            camera_id: Camera ID
            timeout: Timeout in seconds
        
        Returns:
            tuple: (frame, timestamp) or (None, None) if timeout
        """
        if camera_id not in self.frame_queues:
            return None, None
        
        try:
            frame, timestamp = self.frame_queues[camera_id].get(timeout=timeout)
            return frame, timestamp
        except queue.Empty:
            return None, None
    
    def get_latest_frame(self, camera_id):
        """
        Get the latest frame, discarding older ones
        
        Args:
            camera_id: Camera ID
        
        Returns:
            tuple: (frame, timestamp) or (None, None) if no frames
        """
        if camera_id not in self.frame_queues:
            return None, None
        
        frame, timestamp = None, None
        queue = self.frame_queues[camera_id]
        
        # Get latest frame
        while not queue.empty():
            try:
                frame, timestamp = queue.get_nowait()
            except queue.Empty:
                break
        
        return frame, timestamp
    
    def register_frame_callback(self, callback):
        """Register a callback for each frame"""
        self.frame_callbacks.append(callback)

    @staticmethod
    def _sanitize_config(config):
        """Redact sensitive fields before returning camera config to clients."""
        if not isinstance(config, dict):
            return {}

        redacted = dict(config)
        sensitive_keys = {'password', 'passwd', 'secret', 'token', 'api_key', 'access_key'}
        for key in list(redacted.keys()):
            key_lower = str(key).lower()
            if key_lower in sensitive_keys:
                redacted[key] = '***'
                continue

            # Also redact credentials embedded in stream URLs.
            if key_lower in {'url', 'stream_url', 'rtsp_url'} and isinstance(redacted[key], str):
                redacted[key] = re.sub(r'://[^/@]+@', '://***:***@', redacted[key])
        return redacted
    
    def get_camera_info(self, camera_id):
        """Get information about a camera"""
        if camera_id not in self.cameras:
            return None
        
        camera = self.cameras[camera_id]
        stats = self.stats[camera_id]
        
        return {
            'camera_id': camera_id,
            'type': camera.__class__.__name__,
            'connected': camera.is_connected,
            'config': self._sanitize_config(self.camera_configs[camera_id]),
            'stats': stats
        }
    
    def get_all_cameras(self):
        """Get information about all cameras"""
        return {
            camera_id: self.get_camera_info(camera_id)
            for camera_id in self.cameras.keys()
        }
    
    def get_status(self):
        """Get overall status of camera manager"""
        return {
            'running': self.running,
            'total_cameras': len(self.cameras),
            'cameras': self.get_all_cameras()
        }


# Singleton instance
_camera_manager = None


def get_camera_manager():
    """Get the global camera manager instance"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
