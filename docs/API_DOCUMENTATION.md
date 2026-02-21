# Face Attendance API Documentation

## Overview
Base URL: `http://localhost:5001`

## Authentication
Most endpoints require JWT authentication. Include the token in the header:
```
Authorization: Bearer <your-token>
```

## Endpoints

### 1. Health Check
**GET** `/api/health`

Check API health status.

**Response:**
```json
{
  "status": "healthy",
  "database": "ok",
  "timestamp": "2026-02-21T12:00:00"
}
```

---

### 2. Login
**POST** `/api/login`

Authenticate and get JWT token.

**Request Body:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response (200):**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user_id": 1,
  "username": "admin"
}
```

**Response (401):**
```json
{
  "message": "Invalid credentials"
}
```

---

### 3. Register Student
**POST** `/api/register-student`

Register a new student with face image.

**Headers:**
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| student_id | string | Yes | Unique student ID (3-50 chars) |
| name | string | Yes | Student name (2-100 chars) |
| subject | string | No | Subject name |
| file | file | Yes | Face image (jpg, png, jpeg) |

**Response (201):**
```json
{
  "message": "Student registered successfully",
  "student_id": "12345",
  "name": "John Doe",
  "images_saved": 1
}
```

---

### 4. Register Face (Legacy)
**POST** `/api/register-face`

Register a face image for attendance.

**Headers:**
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| student_id | string | No | Student ID |
| file | file | Yes | Face image |

**Response (201):**
```json
{
  "message": "Face registered successfully",
  "filename": "12345_20260221120000.jpg",
  "faces_detected": 1
}
```

---

### 5. Mark Attendance
**POST** `/api/attendance`

Mark attendance using face recognition.

**Headers:**
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| subject | string | No | Subject name (default: General) |
| file | file | Yes | Face image |

**Response - Success (200):**
```json
{
  "message": "Attendance marked successfully",
  "status": "success",
  "student_id": "12345",
  "name": "John Doe",
  "subject": "Math",
  "time": "12:00:00",
  "confidence": 45.5
}
```

**Response - Already Marked (200):**
```json
{
  "message": "Already marked attendance today",
  "status": "already_marked",
  "student_id": "12345",
  "name": "John Doe"
}
```

**Response - Unknown Face (200):**
```json
{
  "message": "Face not recognized",
  "status": "unknown",
  "confidence": 85.2
}
```

**Response - No Face (200):**
```json
{
  "message": "No face detected",
  "status": "no_face"
}
```

---

### 6. Get Students
**GET** `/api/students`

Get list of all registered students.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "students": [
    {
      "student_id": "12345",
      "name": "John Doe",
      "is_active": true,
      "created_at": "2026-02-15T10:00:00"
    }
  ]
}
```

---

### 7. Get Attendance Report
**GET** `/api/attendance/report`

Get attendance records.

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date | string | No | Date in YYYY-MM-DD format (default: today) |
| subject | string | No | Filter by subject |

**Response (200):**
```json
{
  "date": "2026-02-21",
  "subject": "Math",
  "count": 2,
  "records": [
    {
      "student_id": "12345",
      "name": "John Doe",
      "date": "2026-02-21",
      "time": "12:00:00",
      "subject": "Math",
      "status": "Present",
      "confidence": 45.5
    }
  ]
}
```

---

## Error Responses

All endpoints may return error responses:

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid or missing token |
| 404 | Endpoint not found |
| 409 | Conflict - Duplicate entry |
| 500 | Internal Server Error |

**Error Response Format:**
```json
{
  "message": "Error description here"
}
```

---

## Testing with cURL

### Login
```bash
curl -X POST http://localhost:5001/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Get Token and Save
```bash
TOKEN=$(curl -s -X POST http://localhost:5001/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | jq -r '.token')
```

### Mark Attendance
```bash
curl -X POST http://localhost:5001/api/attendance \
  -H "Authorization: Bearer $TOKEN" \
  -F "subject=Math" \
  -F "file=@face.jpg"
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| SECRET_KEY | Yes | - | JWT signing key |
| DB_HOST | No | localhost | MySQL host |
| DB_USER | No | root | MySQL username |
| DB_PASSWORD | Yes | - | MySQL password |
| DB_NAME | No | face_attendance | Database name |
| PORT | No | 5001 | Server port |
| UPLOAD_FOLDER | No | TrainingImage | Image upload directory |
| MODEL_PATH | No | TrainingImageLabel/Trainner.yml | Face model path |
