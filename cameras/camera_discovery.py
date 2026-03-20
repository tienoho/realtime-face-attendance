"""
Camera Discovery - Auto-detect cameras on the network
Supports USB, RTSP, and ONVIF camera discovery
"""
import cv2
import logging
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Maximum number of IPs to scan to prevent timeout
MAX_IPS_TO_SCAN = 30

# Quick port scan timeout (ms)
QUICK_PORT_TIMEOUT = 500


class CameraDiscovery:
    """
    Discover available cameras on the system and network
    """
    
    # Common RTSP ports and paths
    COMMON_RTSP_PORTS = [554, 8554, 8080]
    COMMON_RTSP_PATHS = ['/stream1', '/stream2', '/ch1/main/av_stream', '/live/ch00_0']
    
    # Common HTTP ports for IP cameras
    COMMON_HTTP_PORTS = [80, 8080, 8443, 8000]
    
    @staticmethod
    def discover_usb_cameras(max_index=10):
        """
        Discover USB cameras on the system
        
        Returns:
            list: List of discovered USB cameras
        """
        discovered = []
        
        for idx in range(max_index):
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    # Test if we can actually read a frame
                    ret, frame = cap.read()
                    cap.release()
                    if ret and frame is not None:
                        discovered.append({
                            'type': 'usb',
                            'device_index': idx,
                            'name': f'USB Camera {idx}',
                            'url': f'/dev/video{idx}' if hasattr(cv2, 'CAP_V4L') else f'USB{idx}',
                            'protocol': 'usb'
                        })
                        logger.info(f"Found USB camera at index {idx}")
            except Exception as e:
                logger.debug(f"Error checking camera index {idx}: {e}")
        
        return discovered
    
    @staticmethod
    def _quick_port_test(ip, port, timeout_ms=500):
        """Quickly test if a port is open using socket"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_ms / 1000.0)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    @staticmethod
    def _test_rtsp_stream(ip, port, path, username=None, password=None):
        """Test if an RTSP stream is accessible"""
        # Quick port check first
        if not CameraDiscovery._quick_port_test(ip, port, QUICK_PORT_TIMEOUT):
            return False, None
        
        try:
            # Build RTSP URL
            if username and password:
                url = f'rtsp://{username}:{password}@{ip}:{port}{path}'
            else:
                url = f'rtsp://{ip}:{port}{path}'
            
            # Try to open the stream with timeout
            cap = cv2.VideoCapture(url)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500)  # 1.5 second timeout
            if cap.isOpened():
                # Try to read a frame
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    return True, url
            else:
                cap.release()
        except Exception as e:
            logger.debug(f"RTSP test failed for {ip}:{port}{path}: {e}")
        
        return False, None
    
    @classmethod
    def discover_ip_cameras(cls, ip_range=None, timeout=3):
        """
        Discover IP cameras on the network
        
        Args:
            ip_range: IP range to scan (e.g., '192.168.1.1-254' or '192.168.1.0/24')
            timeout: Timeout for each connection attempt
        
        Returns:
            list: List of discovered IP cameras
        """
        discovered = []
        
        # If no range specified, use common private IP ranges
        if not ip_range:
            # Try to get local network range
            local_ip = cls._get_local_ip()
            if local_ip:
                # Extract network from local IP (assume /24)
                parts = local_ip.split('.')
                if len(parts) == 4:
                    base_ip = f"{parts[0]}.{parts[1]}.{parts[2]}"
                    ip_range = f"{base_ip}.1-50"  # Limit to first 50 IPs
            else:
                # Use common ranges
                ip_range = '192.168.1.1-50'
        
        # Parse IP range
        ip_list = cls._parse_ip_range(ip_range)
        
        # Limit number of IPs to scan to prevent timeout
        if len(ip_list) > MAX_IPS_TO_SCAN:
            logger.info(f"Limiting scan to first {MAX_IPS_TO_SCAN} IPs (from {len(ip_list)} total)")
            ip_list = ip_list[:MAX_IPS_TO_SCAN]
        
        logger.info(f"Scanning {len(ip_list)} IP addresses for cameras...")
        
        # Scan IPs in parallel with more workers for faster scanning
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {}
            
            for ip in ip_list:
                # Test common RTSP ports and paths
                for port in cls.COMMON_RTSP_PORTS:
                    for path in cls.COMMON_RTSP_PATHS:
                        future = executor.submit(cls._test_rtsp_stream, ip, port, path)
                        futures[future] = (ip, port, path)
                
                # Test common HTTP ports
                for port in cls.COMMON_HTTP_PORTS:
                    future = executor.submit(cls._test_http_stream, ip, port)
                    futures[future] = (ip, port)
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result[0]:  # Camera found
                        ip, port = futures[future][:2]
                        discovered.append({
                            'type': 'rtsp',
                            'ip': ip,
                            'port': port,
                            'name': f'IP Camera {ip}',
                            'url': result[1] if len(result) > 1 else f'rtsp://{ip}:{port}/stream1',
                            'protocol': 'rtsp'
                        })
                        logger.info(f"Found IP camera at {ip}:{port}")
                except Exception as e:
                    logger.debug(f"Error scanning IP: {e}")
        
        return discovered
    
    @staticmethod
    def _test_http_stream(ip, port):
        """Test if HTTP stream is accessible"""
        # Quick port check first
        if not CameraDiscovery._quick_port_test(ip, port, QUICK_PORT_TIMEOUT):
            return False, None
        
        import urllib.request
        
        try:
            url = f'http://{ip}:{port}'
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'Camera-Discovery/1.0')
            
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'multipart' in content_type or 'image' in content_type:
                        return True, url
        except Exception as e:
            logger.debug(f"HTTP test failed for {ip}:{port}: {e}")
        
        return False, None
    
    @staticmethod
    def _get_local_ip():
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return None
    
    @staticmethod
    def _parse_ip_range(ip_range):
        """Parse IP range string to list of IPs"""
        ips = []
        
        # Handle CIDR notation (e.g., 192.168.1.0/24)
        if '/' in ip_range:
            try:
                import ipaddress
                network = ipaddress.ip_network(ip_range, strict=False)
                ips = [str(ip) for ip in network.hosts()]
            except Exception as e:
                logger.error(f"Invalid CIDR notation: {e}")
                return ips
        # Handle range (e.g., 192.168.1.1-254)
        elif '-' in ip_range:
            try:
                base, end = ip_range.split('-')
                parts = base.split('.')
                if len(parts) == 4:
                    prefix = '.'.join(parts[:3])
                    start = int(parts[3])
                    end = int(end)
                    for i in range(start, min(end + 1, 256)):
                        ips.append(f"{prefix}.{i}")
            except Exception as e:
                logger.error(f"Invalid IP range: {e}")
        else:
            # Single IP
            ips = [ip_range]
        
        return ips
    
    @classmethod
    def discover_all(cls, ip_range=None, scan_network=True):
        """
        Discover all available cameras
        
        Args:
            ip_range: IP range to scan for IP cameras
            scan_network: Whether to scan for IP cameras
        
        Returns:
            dict: Dictionary with 'usb' and 'ip' camera lists
        """
        results = {
            'usb': [],
            'ip': [],
            'total': 0
        }
        
        # Discover USB cameras first (usually faster)
        logger.info("Scanning for USB cameras...")
        results['usb'] = cls.discover_usb_cameras()
        
        # Discover IP cameras if requested
        if scan_network:
            logger.info("Scanning for IP cameras...")
            results['ip'] = cls.discover_ip_cameras(ip_range)
        
        results['total'] = len(results['usb']) + len(results['ip'])
        
        logger.info(f"Discovery complete: {results['total']} cameras found "
                   f"({len(results['usb'])} USB, {len(results['ip'])} IP)")
        
        return results


# Singleton instance
_discovery_instance = None
_discovery_lock = threading.Lock()


def get_discovery():
    """Get the camera discovery instance"""
    global _discovery_instance
    with _discovery_lock:
        if _discovery_instance is None:
            _discovery_instance = CameraDiscovery()
    return _discovery_instance


def discover_cameras(ip_range=None, scan_network=True):
    """
    Convenience function to discover cameras
    
    Args:
        ip_range: IP range to scan
        scan_network: Whether to scan network
    
    Returns:
        dict: Discovery results
    """
    return CameraDiscovery.discover_all(ip_range, scan_network)
