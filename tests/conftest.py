"""
Pytest configuration and fixtures for Face Attendance API tests
"""
import os
import sys
import pytest
import tempfile
from io import BytesIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create and configure a test instance of the Flask app"""
    from deployment.api import app as flask_app
    
    # Configure for testing
    flask_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'DB_NAME': 'test_face_attendance',
    })
    
    yield flask_app


@pytest.fixture
def client(app):
    """Test client for the Flask app"""
    return app.test_client()


@pytest.fixture
def auth_token(app):
    """Generate a test JWT token"""
    import jwt
    from datetime import datetime, timedelta
    
    token = jwt.encode({
        'user_id': 1,
        'username': 'testuser',
        'exp': datetime.utcnow() + timedelta(hours=1)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return token


@pytest.fixture
def auth_headers(auth_token):
    """Generate authorization headers with JWT token"""
    return {'Authorization': f'Bearer {auth_token}'}


@pytest.fixture
def sample_image():
    """Create a sample image file for testing"""
    import numpy as np
    import cv2
    
    # Create a simple 100x100 grayscale image
    img = np.zeros((100, 100), dtype=np.uint8)
    img[25:75, 25:75] = 255  # White square in center
    
    # Convert to JPEG bytes
    _, img_bytes = cv2.imencode('.    return BytesIOjpg', img)
(img_bytes.getvalue())


@pytest.fixture
def sample_color_image():
    """Create a sample color image file for testing"""
    import numpy as np
    import cv2
    
    # Create a simple 100x100 color image
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[25:75, 25:75] = [255, 255, 255]  # White square
    
    # Convert to JPEG bytes
    _, img_bytes = cv2.imencode('.jpg', img)
    return BytesIO(img_bytes.getvalue())


@pytest.fixture
def mock_db(monkeypatch):
    """Mock database connection for testing without actual DB"""
    class MockCursor:
        def __init__(self):
            self.results = []
            self.queries = []
        
        def execute(self, query, params=None):
            self.queries.append((query, params))
            # Return different results based on query
            if 'SELECT' in query and 'users' in query:
                if 'testuser' in str(params):
                    self.results = [(1, 'testuser', 'hashed_password')]
                else:
                    self.results = []
            elif 'SELECT' in query and 'students' in query:
                self.results = []
            elif 'SELECT 1' in query:
                self.results = [(1,)]
            else:
                self.results = []
        
        def fetchone(self):
            return self.results[0] if self.results else None
        
        def fetchall(self):
            return self.results
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
    
    class MockConnection:
        def __init__(self):
            self.cursor_obj = MockCursor()
        
        def cursor(self):
            return self.cursor_obj
        
        def commit(self):
            pass
        
        def close(self):
            pass
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
    
    def mock_get_db_connection():
        return MockConnection()
    
    # Note: In real tests, you'd use monkeypatch to replace get_db_connection
    # This is a placeholder for demonstration
    return mock_get_db_connection
