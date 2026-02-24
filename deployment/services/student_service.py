"""Student and registration service layer."""

import os
import threading

import psycopg2
import pymysql

try:
    from deployment.services.dto_service import error_response, success_response
except ImportError:
    from services.dto_service import error_response, success_response


def register_student(rt, current_user):
    del current_user  # reserved for audit/authorization extensions

    try:
        if "file" not in rt.request.files:
            return error_response("MISSING_FILE", "No file provided", 400)

        student_id = rt.request.form.get("student_id", "").strip()
        name = rt.request.form.get("name", "").strip()
        subject = rt.request.form.get("subject", "General").strip()
        del subject  # currently unused in persistence model

        valid, error = rt.validate_student_id(student_id)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        valid, error = rt.validate_name(name)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        file = rt.request.files["file"]
        if not rt.allowed_file(file.filename):
            return error_response("INVALID_FILE_TYPE", "Invalid file type. Allowed: png, jpg, jpeg", 400)

        img_bytes = file.read()
        nparr = rt.np.frombuffer(img_bytes, rt.np.uint8)
        img = rt.cv2.imdecode(nparr, rt.cv2.IMREAD_COLOR)

        if img is None:
            return error_response("INVALID_IMAGE", "Invalid image file", 400)

        face_boxes = rt.detect_faces_mediapipe(img)
        if not face_boxes:
            return error_response("NO_FACE_DETECTED", "No face detected in image", 400)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM students WHERE student_id = %s", (student_id,))
            if cursor.fetchone():
                return error_response("DUPLICATE_STUDENT_ID", f"Student ID {student_id} already exists", 409)

            cursor.execute(
                "INSERT INTO students (student_id, name) VALUES (%s, %s)",
                (student_id, name),
            )

            student_folder = os.path.join(rt.app.config["UPLOAD_FOLDER"], student_id)
            os.makedirs(student_folder, exist_ok=True)

            saved_count = 0
            for x, y, w, h in face_boxes[:1]:
                pad = 20
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(img.shape[1], x + w + pad)
                y2 = min(img.shape[0], y + h + pad)

                face_img = img[y1:y2, x1:x2]
                gray_face = rt.cv2.cvtColor(face_img, rt.cv2.COLOR_BGR2GRAY)

                img_filename = f"{student_id}_{rt.datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                img_path = os.path.join(student_folder, img_filename)
                rt.cv2.imwrite(img_path, gray_face)

                cursor.execute(
                    "INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)",
                    (student_id, img_path),
                )
                saved_count += 1

            rt.logger.info(f"Student {student_id} ({name}) registered with {saved_count} images")

        rt.logger.info("Starting auto-training after student registration...")
        training_result = rt.train_face_recognition_model()

        if training_result["status"] == "success":
            rt.logger.info(f"Auto-training completed: {training_result['images_trained']} images")
        else:
            rt.logger.warning(f"Auto-training failed: {training_result['message']}")

        return success_response(
            {
                "student_id": student_id,
                "name": name,
                "images_saved": saved_count,
                "model_trained": training_result["status"] == "success",
                "training_details": training_result,
            },
            message="Student registered successfully",
            status=201,
        )

    except (pymysql.Error, psycopg2.Error) as e:
        rt.logger.error(f"Database error during registration: {e}")
        return error_response("DATABASE_ERROR", "Database error", 500)
    except Exception as e:
        rt.logger.error(f"Registration error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)


def register_student_multi(rt, current_user):
    del current_user

    try:
        files = rt.request.files.getlist("images")
        if not files or len(files) == 0:
            return error_response("MISSING_IMAGES", "No images provided", 400)

        if len(files) > 20:
            return error_response("TOO_MANY_IMAGES", "Maximum 20 images allowed", 400)

        if len(files) < 3:
            rt.logger.warning(f"Only {len(files)} images provided, recommend at least 5-10")

        student_id = rt.request.form.get("student_id", "").strip()
        name = rt.request.form.get("name", "").strip()
        apply_augmentation = rt.request.form.get("apply_augmentation", "true").lower() == "true"

        valid, error = rt.validate_student_id(student_id)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        valid, error = rt.validate_name(name)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM students WHERE student_id = %s", (student_id,))
            if cursor.fetchone():
                return error_response("DUPLICATE_STUDENT_ID", f"Student ID {student_id} already exists", 409)

        valid_images = []
        face_detector = rt.get_face_detector()
        if face_detector is None:
            rt.logger.warning("InsightFace not available, using MediaPipe fallback")

        for i, file in enumerate(files):
            if not rt.allowed_file(file.filename):
                continue

            try:
                img_bytes = file.read()
                nparr = rt.np.frombuffer(img_bytes, rt.np.uint8)
                img = rt.cv2.imdecode(nparr, rt.cv2.IMREAD_COLOR)

                if img is None:
                    rt.logger.warning(f"Invalid image {i}: could not decode")
                    continue

                if face_detector:
                    faces = face_detector.detect(img)
                    if faces:
                        face = max(faces, key=lambda f: f.confidence)
                        face_crop = face_detector.get_face_crop(img, face.bbox, padding=20)
                        if face_crop is not None and face_crop.size > 0:
                            valid_images.append(face_crop)
                            rt.logger.debug(f"Image {i}: face detected, crop size: {face_crop.shape}")
                else:
                    face_boxes = rt.detect_faces_mediapipe(img)
                    if face_boxes:
                        x, y, w, h = face_boxes[0]
                        pad = 20
                        x1 = max(0, x - pad)
                        y1 = max(0, y - pad)
                        x2 = min(img.shape[1], x + w + pad)
                        y2 = min(img.shape[0], y + h + pad)
                        face_crop = img[y1:y2, x1:x2]
                        if face_crop.size > 0:
                            valid_images.append(face_crop)
                            rt.logger.debug(
                                f"Image {i}: face detected (MediaPipe), crop size: {face_crop.shape}"
                            )

            except Exception as img_err:
                rt.logger.warning(f"Error processing image {i}: {img_err}")

        if len(valid_images) < 1:
            return error_response("NO_FACE_DETECTED", "No valid faces detected in any image", 400)

        rt.logger.info(f"Detected {len(valid_images)} valid face images from {len(files)} uploaded")

        original_images = list(valid_images)
        original_count = len(original_images)
        if apply_augmentation and rt.augment_face_batch:
            try:
                target = min(15, max(10, original_count * 3))
                valid_images = rt.augment_face_batch(valid_images, target_count=target)
                rt.logger.info(f"Applied augmentation: {original_count} -> {len(valid_images)} images")
            except Exception as aug_err:
                rt.logger.warning(f"Augmentation failed: {aug_err}")

        student_folder = os.path.join(rt.app.config["UPLOAD_FOLDER"], student_id)
        os.makedirs(student_folder, exist_ok=True)

        saved_count = 0
        for i, img in enumerate(valid_images):
            try:
                img_filename = f"{student_id}_{i:03d}.jpg"
                img_path = os.path.join(student_folder, img_filename)
                rt.cv2.imwrite(img_path, img)
                saved_count += 1
            except Exception as save_err:
                rt.logger.warning(f"Failed to save image {i}: {save_err}")

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO students (student_id, name) VALUES (%s, %s)",
                (student_id, name),
            )

            for i in range(saved_count):
                img_path = os.path.join(student_folder, f"{student_id}_{i:03d}.jpg")
                cursor.execute(
                    "INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)",
                    (student_id, img_path),
                )

        pipeline_result = {"status": "not_available"}
        pipeline = rt.get_face_pipeline()

        if pipeline:
            try:
                result = pipeline.register_face(student_id, name, original_images)
                pipeline_result = {
                    "status": "success" if result.get("success") else "error",
                    "message": result.get("message", ""),
                    "images_processed": result.get("images_processed", 0),
                }
                rt.logger.info(f"FAISS registration: {pipeline_result}")
            except Exception as pipeline_err:
                rt.logger.error(f"Pipeline registration failed: {pipeline_err}")
                pipeline_result = {"status": "error", "message": str(pipeline_err)}

        def run_training():
            try:
                training_result = rt.train_face_recognition_model()
                if training_result.get("status") == "success":
                    rt.logger.info(
                        f"Background training completed: {training_result.get('images_trained')} images"
                    )
                else:
                    rt.logger.warning(
                        f"Background training failed: {training_result.get('message')}"
                    )
            except Exception as train_err:
                rt.logger.error(f"Background training error: {train_err}")

        threading.Thread(target=run_training, daemon=True).start()

        return success_response(
            {
                "student_id": student_id,
                "name": name,
                "images_uploaded": len(files),
                "faces_detected": original_count,
                "images_saved": saved_count,
                "augmentation_applied": apply_augmentation,
                "faiss_registration": pipeline_result,
                "lbph_training": {"status": "queued", "message": "Training started in background"},
            },
            message="Student registered successfully",
            status=201,
        )

    except (pymysql.Error, psycopg2.Error) as e:
        rt.logger.error(f"Database error during multi-registration: {e}")
        return error_response("DATABASE_ERROR", "Database error", 500)
    except Exception as e:
        rt.logger.error(f"Multi-registration error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)


def register_face_capture(rt, current_user):
    del current_user

    try:
        data = rt.request.get_json(silent=True)
        if not data or not data.get("image_data"):
            return error_response("MISSING_IMAGE_DATA", "No image data provided", 400)

        student_id = data.get("student_id", "").strip()
        name = data.get("name", "").strip()
        image_data = data.get("image_data", "")

        valid, error = rt.validate_student_id(student_id)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        valid, error = rt.validate_name(name)
        if not valid:
            return error_response("VALIDATION_ERROR", error, 400)

        try:
            if "," in image_data:
                image_data = image_data.split(",")[1]
            img_bytes = rt.base64.b64decode(image_data)
            nparr = rt.np.frombuffer(img_bytes, rt.np.uint8)
            img = rt.cv2.imdecode(nparr, rt.cv2.IMREAD_COLOR)
        except Exception as decode_err:
            rt.logger.warning(f"Invalid base64 image payload: {decode_err}")
            return error_response("INVALID_IMAGE_DATA", "Invalid image data", 400)

        if img is None:
            return error_response("INVALID_IMAGE", "Could not decode image", 400)

        face_detector = rt.get_face_detector()
        face_crop = None
        if face_detector:
            faces = face_detector.detect(img)
            if faces:
                face = max(faces, key=lambda f: f.confidence)
                face_crop = face_detector.get_face_crop(img, face.bbox, padding=20)
        else:
            face_boxes = rt.detect_faces_mediapipe(img)
            if face_boxes:
                x, y, w, h = face_boxes[0]
                pad = 20
                x1, y1 = max(0, x - pad), max(0, y - pad)
                x2, y2 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
                face_crop = img[y1:y2, x1:x2]

        if face_crop is None or face_crop.size == 0:
            return error_response("NO_FACE_DETECTED", "No face detected in image", 400)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM students WHERE student_id = %s", (student_id,))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute(
                    "INSERT INTO students (student_id, name) VALUES (%s, %s)",
                    (student_id, name),
                )

        student_folder = os.path.join(rt.app.config["UPLOAD_FOLDER"], student_id)
        os.makedirs(student_folder, exist_ok=True)

        timestamp = rt.datetime.now().strftime("%Y%m%d%H%M%S")
        img_filename = f"{student_id}_{timestamp}.jpg"
        img_path = os.path.join(student_folder, img_filename)
        rt.cv2.imwrite(img_path, face_crop)

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)",
                (student_id, img_path),
            )

        pipeline = rt.get_face_pipeline()
        faiss_result = {"status": "not_available"}
        if pipeline:
            try:
                result = pipeline.register_face(student_id, name, [face_crop])
                faiss_result = {
                    "status": "success" if result.get("success") else "error",
                    "message": result.get("message", ""),
                }
            except Exception as e:
                faiss_result = {"status": "error", "message": str(e)}

        return success_response(
            {
                "student_id": student_id,
                "name": name,
                "image_path": img_path,
                "faiss_registration": faiss_result,
            },
            message="Face captured successfully",
            status=201,
        )

    except Exception as e:
        rt.logger.error(f"Face capture error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)


def register_face(rt, current_user):
    del current_user

    try:
        if "file" not in rt.request.files:
            return error_response("MISSING_FILE", "No file provided", 400)

        student_id = rt.request.form.get("student_id", "").strip()

        file = rt.request.files["file"]
        if not rt.allowed_file(file.filename):
            return error_response("INVALID_FILE_TYPE", "Invalid file type", 400)

        timestamp = rt.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{student_id}_{timestamp}.jpg" if student_id else f"{timestamp}.jpg"
        filename = rt.secure_filename(filename)
        filepath = os.path.join(rt.app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        image = rt.cv2.imread(filepath)
        face_boxes = rt.detect_faces_mediapipe(image)
        if not face_boxes:
            os.remove(filepath)
            return error_response("NO_FACE_DETECTED", "No face detected", 400)

        if student_id:
            try:
                with rt.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM training_images WHERE student_id = %s",
                        (student_id,),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute(
                            "UPDATE training_images SET image_path = %s WHERE student_id = %s",
                            (filepath, student_id),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO training_images (student_id, image_path) VALUES (%s, %s)",
                            (student_id, filepath),
                        )
            except Exception as db_err:
                rt.logger.warning(f"Could not save to database: {db_err}")

        return success_response(
            {
                "filename": filename,
                "faces_detected": len(face_boxes),
            },
            message="Face registered successfully",
            status=201,
        )

    except Exception as e:
        rt.logger.error(f"Face registration error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)


def get_students(rt, current_user):
    del current_user

    try:
        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT student_id, name, is_active, created_at FROM students ORDER BY created_at DESC")
            students = cursor.fetchall()

        return success_response(
            {
                "students": [
                    {
                        "student_id": s[0],
                        "name": s[1],
                        "is_active": bool(s[2]),
                        "created_at": s[3].isoformat() if s[3] else None,
                    }
                    for s in students
                ]
            },
            message="Students fetched successfully",
            status=200,
        )

    except Exception as e:
        rt.logger.error(f"Error fetching students: {e}")
        return error_response("SERVER_ERROR", "Server error", 500)
