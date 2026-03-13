"""
Camera Factory and Connection Classes
Supports multiple camera protocols: RTSP, ONVIF, HTTP, USB
"""
import cv2
import numpy as np
import logging
import threading
import time
import urllib.request
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseCamera(ABC):
    """Abstract base class for all camera types"""
    
    def __init__(self, camera_id, config):
        self.camera_id = camera_id
        self.config = config
        self.is_connected = False
        self.last_frame_time = 0
        self.frame_count = 0
        self.error_count = 0
        
    @abstractmethod
    def connect(self):
        """Establish connection to camera"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Close connection to camera"""
        pass
    
    @abstractmethod
    def read(self):
        """Read frame from camera. Returns (success, frame)"""
        pass
    
    def get_info(self):
        """Get camera information"""
        return {
            'camera_id': self.camera_id,
            'type': self.__class__.__name__,
            'connected': self.is_connected,
            'frame_count': self.frame_count,
            'error_count': self.error_count
        }


class USBCamera(BaseCamera):
    """USB/Webcam camera connector"""
    
    @staticmethod
    def find_available_camera(max_index=10):
        """
        Find an available camera device.
        Returns device index or None if no camera found.
        """
        import os
        
        # Check for /dev/video* on Linux
        if os.path.exists('/dev'):
            video_devices = []
            try:
                for dev in os.listdir('/dev'):
                    if dev.startswith('video'):
                        video_devices.append(int(dev.replace('video', '')))
            except Exception:
                pass
            
            if video_devices:
                logger.info(f"Found video devices: {video_devices}")
                return min(video_devices)
        
        # Try OpenCV indices
        for idx in range(max_index):
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    # Test if we can actually read a frame
                    ret, frame = cap.read()
                    cap.release()
                    if ret and frame is not None:
                        logger.info(f"Found working camera at index {idx}")
                        return idx
                else:
                    cap.release()
            except Exception:
                pass
        
        return None
    
    def __init__(self, camera_id, config):
        super().__init__(camera_id, config)
        self.device_index = config.get('device_index', 0)
        self.cap = None
        self._auto_detect_attempted = False
        
    def connect(self):
        """Connect to USB camera with auto-detection"""
        try:
            # First try the configured device index
            self.cap = cv2.VideoCapture(self.device_index)
            
            if not self.cap.isOpened():
                # Release the failed capture
                if self.cap:
                    self.cap.release()
                    self.cap = None
                
                # Try to auto-detect available camera
                if not self._auto_detect_attempted:
                    logger.warning(f"Camera index {self.device_index} not available, trying auto-detect...")
                    self._auto_detect_attempted = True
                    
                    detected_index = self.find_available_camera()
                    if detected_index is not None:
                        self.device_index = detected_index
                        self.cap = cv2.VideoCapture(self.device_index)
                    else:
                        logger.error("No available camera found. Will retry on next connect attempt.")
                        return False
                else:
                    # Already tried auto-detect, try all indices
                    for idx in range(10):
                        if idx == self.device_index:
                            continue
                        new_cap = cv2.VideoCapture(idx)
                        if new_cap.isOpened():
                            # Test read
                            ret, frame = new_cap.read()
                            if ret and frame is not None:
                                if self.cap:
                                    self.cap.release()
                                self.cap = new_cap
                                self.device_index = idx
                                logger.info(f"Found working camera at index {idx}")
                                break
                            new_cap.release()
            
            if self.cap and self.cap.isOpened():
                # Set camera properties
                width = self.config.get('width', 640)
                height = self.config.get('height', 480)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                
                # Set buffer to 1 for low latency
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                self.is_connected = True
                logger.info(f"USB Camera {self.camera_id} connected at index {self.device_index}")
                return True
            else:
                logger.error(f"Failed to open USB camera {self.camera_id} - no camera available")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to USB camera {self.camera_id}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from USB camera"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info(f"USB Camera {self.camera_id} disconnected")
    
    def read(self):
        """Read frame from USB camera"""
        if not self.is_connected or self.cap is None:
            return False, None
        
        try:
            ret, frame = self.cap.read()
            if ret:
                self.frame_count += 1
                self.last_frame_time = time.time()
            else:
                self.error_count += 1
            return ret, frame
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error reading from USB camera {self.camera_id}: {e}")
            return False, None


class RTSPCamera(BaseCamera):
    """RTSP stream camera connector"""
    
    def __init__(self, camera_id, config):
        super().__init__(camera_id, config)
        self.url = config.get('url', '')
        self.username = config.get('username')
        self.password = config.get('password')
        self.cap = None
        self._build_url()
        
    def _build_url(self):
        """Build RTSP URL with credentials if provided"""
        if self.username and self.password:
            if '@' in self.url:
                # Replace existing credentials in URL
                pattern = r'(rtsp://)(.*?)@'
                replacement = f'rtsp://{self.username}:{self.password}@'
                self.url = re.sub(pattern, replacement, self.url)
            elif self.url.startswith('rtsp://'):
                # Inject credentials when URL does not have them
                self.url = self.url.replace('rtsp://', f'rtsp://{self.username}:{self.password}@', 1)

    @staticmethod
    def _safe_url_for_log(url: str) -> str:
        """Redact credentials in RTSP URLs before logging."""
        if not isinstance(url, str):
            return ""
        return re.sub(r'rtsp://[^/@]+@', 'rtsp://***:***@', url)
    
    def connect(self):
        """Connect to RTSP stream"""
        try:
            self.cap = cv2.VideoCapture(self.url)
            
            if self.cap.isOpened():
                # Set buffer size to reduce latency
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Try to read first frame to verify connection
                ret, frame = self.cap.read()
                if ret:
                    self.is_connected = True
                    logger.info(
                        f"RTSP Camera {self.camera_id} connected: {self._safe_url_for_log(self.url)}"
                    )
                    return True
            
            logger.error(f"Failed to open RTSP stream {self.camera_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to RTSP camera {self.camera_id}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from RTSP stream"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info(f"RTSP Camera {self.camera_id} disconnected")
    
    def read(self):
        """Read frame from RTSP stream"""
        if not self.is_connected or self.cap is None:
            return False, None
        
        try:
            ret, frame = self.cap.read()
            if ret:
                self.frame_count += 1
                self.last_frame_time = time.time()
            else:
                self.error_count += 1
            return ret, frame
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error reading from RTSP camera {self.camera_id}: {e}")
            return False, None


class HTTPCamera(BaseCamera):
    """HTTP/MJPEG stream camera connector"""
    
    # H-CAM-002: Connection retry configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds
    MAX_RETRY_DELAY = 30.0  # seconds
    
    def __init__(self, camera_id, config):
        super().__init__(camera_id, config)
        self.url = config.get('url', '')
        self.stream = None
        self.bytes = b''
        self.frame_cache = None
        self._consecutive_errors = 0
        self._last_retry_time = 0
        self._current_retry_delay = self.INITIAL_RETRY_DELAY
        
    def connect(self):
        """Connect to HTTP stream with retry logic"""
        # H-CAM-002: Implement exponential backoff retry
        for attempt in range(self.MAX_RETRIES):
            try:
                # H-CAM-001 FIX: Ensure previous connection is closed
                self._close_stream()
                
                self.stream = urllib.request.urlopen(self.url, timeout=10)
                self.is_connected = True
                self._consecutive_errors = 0
                self._current_retry_delay = self.INITIAL_RETRY_DELAY
                logger.info(f"HTTP Camera {self.camera_id} connected: {self.url}")
                return True
                
            except Exception as e:
                self._consecutive_errors += 1
                wait_time = min(self._current_retry_delay * (2 ** attempt), self.MAX_RETRY_DELAY)
                logger.warning(
                    f"HTTP Camera {self.camera_id} connection attempt {attempt + 1}/{self.MAX_RETRIES} "
                    f"failed: {e}. Retrying in {wait_time:.1f}s..."
                )
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(wait_time)
        
        logger.error(f"Failed to connect HTTP camera {self.camera_id} after {self.MAX_RETRIES} attempts")
        return False
    
    def disconnect(self):
        """Disconnect from HTTP stream"""
        self._close_stream()
        self.is_connected = False
        self.bytes = b''
        logger.info(f"HTTP Camera {self.camera_id} disconnected")
    
    def _close_stream(self):
        """H-CAM-001 FIX: Safely close stream to prevent connection leak"""
        if self.stream:
            try:
                self.stream.close()
            except Exception as e:
                logger.debug(f"Error closing stream for {self.camera_id}: {e}")
            finally:
                self.stream = None
    
    def read(self):
        """Read frame from HTTP stream (MJPEG)"""
        if not self.is_connected or self.stream is None:
            return False, None
        
        try:
            # Read more data from stream
            self.bytes += self.stream.read(4096)
            
            # Find JPEG frame boundaries
            a = self.bytes.find(b'\xff\xd8')
            b = self.bytes.find(b'\xff\xd9')
            
            if a != -1 and b != -1:
                jpg = self.bytes[a:b+2]
                self.bytes = self.bytes[b+2:]
                
                # Decode JPEG to numpy array
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                
                if frame is not None:
                    self.frame_count += 1
                    self.last_frame_time = time.time()
                    return True, frame
            
            return False, None
            
        except Exception as e:
            self.error_count += 1
            if self.error_count % 10 == 0:
                logger.error(f"Error reading from HTTP camera {self.camera_id}: {e}")
            return False, None


class ONVIFCamera(BaseCamera):
    """ONVIF camera connector (basic implementation)"""
    
    def __init__(self, camera_id, config):
        super().__init__(camera_id, config)
        self.ip = config.get('ip', '')
        self.port = config.get('port', 8080)
        self.username = config.get('username')
        self.password = config.get('password')
        self.cap = None
        
    def connect(self):
        """Connect to ONVIF camera via RTSP"""
        try:
            # ONVIF typically uses RTSP for streaming
            # Construct RTSP URL from ONVIF config
            self.url = f"rtsp://{self.ip}:{self.port}/stream1"
            
            if self.username and self.password:
                self.url = f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/stream1"
            
            self.cap = cv2.VideoCapture(self.url)
            
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.is_connected = True
                logger.info(f"ONVIF Camera {self.camera_id} connected")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to ONVIF camera {self.camera_id}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from ONVIF camera"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info(f"ONVIF Camera {self.camera_id} disconnected")
    
    def read(self):
        """Read frame from ONVIF camera"""
        if not self.is_connected or self.cap is None:
            return False, None
        
        try:
            ret, frame = self.cap.read()
            if ret:
                self.frame_count += 1
                self.last_frame_time = time.time()
            else:
                self.error_count += 1
            return ret, frame
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error reading from ONVIF camera {self.camera_id}: {e}")
            return False, None


class CameraFactory:
    """Factory class to create camera instances"""
    
    _camera_types = {
        'usb': USBCamera,
        'rtsp': RTSPCamera,
        'http': HTTPCamera,
        'onvif': ONVIFCamera,
    }
    
    @classmethod
    def create(cls, camera_id, camera_type, config):
        """Create a camera instance based on type"""
        if camera_type not in cls._camera_types:
            raise ValueError(f"Unknown camera type: {camera_type}. Available: {list(cls._camera_types.keys())}")
        
        camera_class = cls._camera_types[camera_type]
        return camera_class(camera_id, config)
    
    @classmethod
    def get_supported_types(cls):
        """Get list of supported camera types"""
        return list(cls._camera_types.keys())


# Example configuration
CAMERA_CONFIG_EXAMPLES = {
    'usb': {
        'type': 'usb',
        'device_index': 0,
        'width': 640,
        'height': 480,
    },
    'rtsp': {
        'type': 'rtsp',
        'url': 'rtsp://192.168.1.100:554/stream1',
        'username': 'admin',
        'password': 'admin123',
    },
    'http': {
        'type': 'http',
        'url': 'http://192.168.1.100:8080/mjpeg',
    },
    'onvif': {
        'type': 'onvif',
        'ip': '192.168.1.100',
        'port': 8080,
        'username': 'admin',
        'password': 'admin123',
    }
}
