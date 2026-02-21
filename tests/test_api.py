"""
Unit tests for Face Attendance API endpoints
"""
import pytest
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHealthEndpoint:
    """Tests for /api/health endpoint"""
    
    def test_health_check_returns_200(self, client):
        """Health check should return 200 status"""
        response = client.get('/api/health')
        assert response.status_code == 200
    
    def test_health_check_returns_json(self, client):
        """Health check should return JSON"""
        response = client.get('/api/health')
        assert response.content_type == 'application/json'
    
    def test_health_check_has_status(self, client):
        """Health check should have status field"""
        response = client.get('/api/health')
        data = json.loads(response.data)
        assert 'status' in data
        assert 'timestamp' in data


class TestLoginEndpoint:
    """Tests for /api/login endpoint"""
    
    def test_login_missing_credentials(self, client):
        """Login should return 400 when credentials are missing"""
        response = client.post('/api/login',
                               json={},
                               content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'credentials' in data['message'].lower()
    
    def test_login_missing_username(self, client):
        """Login should return 400 when username is missing"""
        response = client.post('/api/login',
                               json={'password': 'test'},
                               content_type='application/json')
        assert response.status_code == 400
    
    def test_login_missing_password(self, client):
        """Login should return 400 when password is missing"""
        response = client.post('/api/login',
                               json={'username': 'test'},
                               content_type='application/json')
        assert response.status_code == 400
    
    def test_login_invalid_credentials(self, client):
        """Login should return 401 for invalid credentials"""
        response = client.post('/api/login',
                               json={'username': 'invalid', 'password': 'invalid'},
                               content_type='application/json')
        assert response.status_code == 401


class TestValidationHelpers:
    """Tests for validation helper functions"""
    
    def test_validate_student_id_valid(self):
        """Test valid student IDs"""
        from deployment.api import validate_student_id
        
        valid_ids = ['12345', 'student_001', 'STU-2024-001']
        for student_id in valid_ids:
            result, _ = validate_student_id(student_id)
            assert result is True
    
    def test_validate_student_id_too_short(self, app):
        """Test student ID too short"""
        with app.app_context():
            from deployment.api import validate_student_id
            result, error = validate_student_id('ab')
            assert result is False
            assert '3-50' in error
    
    def test_validate_student_id_invalid_chars(self, app):
        """Test student ID with invalid characters"""
        with app.app_context():
            from deployment.api import validate_student_id
            result, error = validate_student_id('student@123')
            assert result is False
            assert 'alphanumeric' in error.lower()
    
    def test_validate_name_valid(self, app):
        """Test valid names"""
        with app.app_context():
            from deployment.api import validate_name
            
            valid_names = ['John Doe', 'Nguyen Van A', 'Maria Garcia']
            for name in valid_names:
                result, _ = validate_name(name)
                assert result is True
    
    def test_validate_name_too_short(self, app):
        """Test name too short"""
        with app.app_context():
            from deployment.api import validate_name
            result, error = validate_name('A')
            assert result is False
    
    def test_validate_name_invalid_chars(self, app):
        """Test name with invalid characters"""
        with app.app_context():
            from deployment.api import validate_name
            result, error = validate_name('John123')
            assert result is False


class TestFileValidation:
    """Tests for file validation helpers"""
    
    def test_allowed_file_valid_extensions(self, app):
        """Test valid file extensions"""
        with app.app_context():
            from deployment.api import allowed_file
            
            assert allowed_file('image.jpg') is True
            assert allowed_file('image.jpeg') is True
            assert allowed_file('image.png') is True
    
    def test_allowed_file_invalid_extension(self, app):
        """Test invalid file extension"""
        with app.app_context():
            from deployment.api import allowed_file
            
            assert allowed_file('document.pdf') is False
            assert allowed_file('video.mp4') is False
            assert allowed_file('archive.zip') is False
    
    def test_allowed_file_no_extension(self, app):
        """Test file with no extension"""
        with app.app_context():
            from deployment.api import allowed_file
            
            assert allowed_file('filename') is False


class TestAttendanceEndpoint:
    """Tests for /api/attendance endpoint"""
    
    def test_attendance_requires_auth(self, client):
        """Attendance should require authentication"""
        response = client.post('/api/attendance')
        assert response.status_code == 401
    
    def test_attendance_requires_file(self, client, auth_headers):
        """Attendance should require file in request"""
        response = client.post('/api/attendance',
                              headers=auth_headers)
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'file' in data['message'].lower()
    
    def test_attendance_invalid_file_type(self, client, auth_headers):
        """Attendance should reject invalid file types"""
        response = client.post('/api/attendance',
                              headers=auth_headers,
                              data={'file': (b'fake', 'test.pdf')})
        assert response.status_code == 400


class TestRegisterEndpoint:
    """Tests for /api/register-face endpoint"""
    
    def test_register_requires_auth(self, client):
        """Register should require authentication"""
        response = client.post('/api/register-face')
        assert response.status_code == 401
    
    def test_register_requires_file(self, client, auth_headers):
        """Register should require file in request"""
        response = client.post('/api/register-face',
                              headers=auth_headers)
        assert response.status_code == 400


class TestStudentsEndpoint:
    """Tests for /api/students endpoint"""
    
    def test_students_requires_auth(self, client):
        """Students list should require authentication"""
        response = client.get('/api/students')
        assert response.status_code == 401


class TestAttendanceReportEndpoint:
    """Tests for /api/attendance/report endpoint"""
    
    def test_report_requires_auth(self, client):
        """Report should require authentication"""
        response = client.get('/api/attendance/report')
        assert response.status_code == 401


class TestErrorHandlers:
    """Tests for error handlers"""
    
    def test_404_error(self, client):
        """Test 404 error handler"""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['message'].lower()


# Run tests with: pytest tests/ -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
