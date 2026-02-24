"""Attendance service layer."""

import psycopg2
import pymysql

try:
    from deployment.services.dto_service import error_response, success_response
except ImportError:
    from services.dto_service import error_response, success_response


def _to_string(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def mark_attendance(rt, current_user):
    del current_user

    try:
        if "file" not in rt.request.files:
            return error_response("MISSING_FILE", "No file provided", 400)

        subject = rt.request.form.get("subject", "General").strip()

        valid, error = rt.validate_subject(subject)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        file = rt.request.files["file"]
        if not rt.allowed_file(file.filename):
            return error_response("INVALID_FILE_TYPE", "Invalid file type", 400)

        img_bytes = file.read()
        nparr = rt.np.frombuffer(img_bytes, rt.np.uint8)
        img = rt.cv2.imdecode(nparr, rt.cv2.IMREAD_COLOR)
        if img is None:
            return error_response("INVALID_IMAGE", "Invalid image file", 400)

        gray = rt.cv2.cvtColor(img, rt.cv2.COLOR_BGR2GRAY)
        face_boxes = rt.detect_faces_haar(gray)

        if not face_boxes:
            payload = {"status": "no_face"}
            return success_response(payload, message="No face detected", status=200)

        x, y, w, h = face_boxes[0]
        face_roi = gray[y : y + h, x : x + w]

        student_id, confidence = rt.recognize_face(face_roi)
        if student_id is None or confidence >= 70:
            payload = {
                "status": "unknown",
                "confidence": float(confidence) if confidence else None,
            }
            return success_response(payload, message="Face not recognized", status=200)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT student_id, name FROM students WHERE student_id = %s AND is_active = TRUE",
                (student_id,),
            )
            student = cursor.fetchone()
            if not student:
                payload = {"status": "not_found"}
                return success_response(payload, message="Student not found or inactive", status=200)

            today = rt.datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "SELECT id FROM attendance WHERE student_id = %s AND date = %s AND subject = %s",
                (student_id, today, subject),
            )
            if cursor.fetchone():
                payload = {
                    "status": "already_marked",
                    "student_id": student[0],
                    "name": student[1],
                }
                return success_response(payload, message="Already marked attendance today", status=200)

            now = rt.datetime.now()
            cursor.execute(
                """INSERT INTO attendance
                   (student_id, enrollment, name, date, time, subject, status, confidence_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    student_id,
                    student_id,
                    student[1],
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%H:%M:%S"),
                    subject,
                    "Present",
                    float(confidence),
                ),
            )

            rt.logger.info(f"Attendance marked: {student[1]} ({student_id}) for {subject}")

        payload = {
            "status": "success",
            "student_id": student[0],
            "name": student[1],
            "subject": subject,
            "time": now.strftime("%H:%M:%S"),
            "confidence": float(confidence),
        }
        return success_response(payload, message="Attendance marked successfully", status=200)

    except (pymysql.Error, psycopg2.Error) as e:
        rt.logger.error(f"Database error during attendance: {e}")
        return error_response("DATABASE_ERROR", "Database error", 500)
    except Exception as e:
        rt.logger.error(f"Attendance error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)


def get_attendance_report(rt, current_user):
    del current_user

    try:
        date = rt.request.args.get("date", rt.datetime.now().strftime("%Y-%m-%d"))
        subject = rt.request.args.get("subject", None)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            if subject:
                cursor.execute(
                    """SELECT a.student_id, a.name, a.date, a.time, a.subject, a.status, a.confidence_score
                       FROM attendance a WHERE a.date = %s AND a.subject = %s ORDER BY a.time""",
                    (date, subject),
                )
            else:
                cursor.execute(
                    """SELECT student_id, name, date, time, subject, status, confidence_score
                       FROM attendance WHERE date = %s ORDER BY time""",
                    (date,),
                )

            records = cursor.fetchall()

        return success_response(
            {
                "date": date,
                "subject": subject,
                "count": len(records),
                "records": [
                    {
                        "student_id": r[0],
                        "name": r[1],
                        "date": _to_string(r[2]),
                        "time": _to_string(r[3]),
                        "subject": r[4],
                        "status": r[5],
                        "confidence": float(r[6]) if r[6] else None,
                    }
                    for r in records
                ],
            },
            message="Attendance report fetched successfully",
            status=200,
        )

    except Exception as e:
        rt.logger.error(f"Error fetching report: {e}")
        return error_response("SERVER_ERROR", "Server error", 500)


def get_recent_attendance(rt, current_user):
    del current_user
    return success_response(
        {"records": [], "count": 0},
        message="Recent attendance fetched successfully",
        status=200,
    )
