"""
Swagger/OpenAPI configuration for Face Attendance API
"""

SWAGGER_TEMPLATE = {
    "info": {
        "title": "Face Attendance API",
        "description": "Real-time face attendance system API with face recognition",
        "version": "2.0.0",
        "contact": {
            "name": "API Support",
            "email": "support@faceattendance.local"
        }
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: \"Bearer {token}\""
        }
    },
    "security": [
        {"Bearer": []}
    ],
    "definitions": {
        "LoginRequest": {
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "username": {
                    "type": "string",
                    "description": "User's username"
                },
                "password": {
                    "type": "string",
                    "format": "password",
                    "description": "User's password"
                }
            }
        },
        "LoginResponse": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "JWT authentication token"
                },
                "user_id": {
                    "type": "integer",
                    "description": "User ID"
                },
                "username": {
                    "type": "string",
                    "description": "Username"
                }
            }
        },
        "RegisterStudentRequest": {
            "type": "object",
            "required": ["student_id", "name"],
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Unique student identifier (3-50 chars, alphanumeric)"
                },
                "name": {
                    "type": "string",
                    "description": "Student's full name (2-100 chars, letters only)"
                },
                "subject": {
                    "type": "string",
                    "description": "Optional subject name"
                },
                "file": {
                    "type": "file",
                    "description": "Face image file (jpg, png, jpeg)"
                }
            }
        },
        "AttendanceResponse": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string"
                },
                "status": {
                    "type": "string",
                    "enum": ["success", "unknown", "already_marked", "no_face"]
                },
                "student_id": {
                    "type": "string"
                },
                "name": {
                    "type": "string"
                },
                "subject": {
                    "type": "string"
                },
                "time": {
                    "type": "string"
                },
                "confidence": {
                    "type": "number"
                }
            }
        },
        "Student": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string"
                },
                "name": {
                    "type": "string"
                },
                "is_active": {
                    "type": "boolean"
                },
                "created_at": {
                    "type": "string",
                    "format": "date-time"
                }
            }
        },
        "AttendanceRecord": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string"
                },
                "name": {
                    "type": "string"
                },
                "date": {
                    "type": "string"
                },
                "time": {
                    "type": "string"
                },
                "subject": {
                    "type": "string"
                },
                "status": {
                    "type": "string"
                },
                "confidence": {
                    "type": "number"
                }
            }
        },
        "Error": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Error message"
                }
            }
        }
    }
}

# API Route Documentation
API_DOCS = {
    '/api/login': {
        'post': {
            'tags': ['Authentication'],
            'summary': 'User login',
            'description': 'Authenticate user and get JWT token',
            'parameters': [
                {
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        '$ref': '#/definitions/LoginRequest'
                    }
                }
            ],
            'responses': {
                '200': {
                    'description': 'Login successful',
                    'schema': {
                        '$ref': '#/definitions/LoginResponse'
                    }
                },
                '400': {
                    'description': 'Missing credentials',
                    'schema': {
                        '$ref': '#/definitions/Error'
                    }
                },
                '401': {
                    'description': 'Invalid credentials',
                    'schema': {
                        '$ref': '#/definitions/Error'
                    }
                }
            }
        }
    },
    '/api/health': {
        'get': {
            'tags': ['Health'],
            'summary': 'Health check',
            'description': 'Check API health status and database connection',
            'responses': {
                '200': {
                    'description': 'API is healthy'
                }
            }
        }
    }
}
