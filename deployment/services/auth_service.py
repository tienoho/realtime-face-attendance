"""Authentication service layer."""

import psycopg2
import pymysql

try:
    from deployment.services.dto_service import error_response, success_response
except ImportError:
    from services.dto_service import error_response, success_response


def _verify_password(rt, stored_hash, password):
    """
    Verify password against stored hash.

    Supports:
    - bcrypt hashes ($2a/$2b/$2y)
    - Werkzeug hashes (scrypt/pbkdf2)
    """
    if not isinstance(stored_hash, str) or not stored_hash:
        return False

    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
        except ImportError:
            rt.logger.error("bcrypt is required to verify bcrypt password hashes")
            return False

        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except Exception as bcrypt_err:
            rt.logger.warning(f"bcrypt verification failed: {bcrypt_err}")
            return False

    # Fallback for Werkzeug-managed hashes.
    try:
        return rt.check_password_hash(stored_hash, password)
    except Exception as hash_err:
        rt.logger.warning(f"Password hash verification failed: {hash_err}")
        return False


def login(rt):
    try:
        auth = rt.request.get_json(silent=True)
        if not auth or not auth.get("username") or not auth.get("password"):
            return error_response("MISSING_CREDENTIALS", "Missing credentials", 400)

        username = auth.get("username")
        password = auth.get("password")

        with rt.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            user = cursor.fetchone()

            if not user:
                return error_response("INVALID_CREDENTIALS", "Invalid credentials", 401)

            stored_hash = user[2]
            if not _verify_password(rt, stored_hash, password):
                return error_response("INVALID_CREDENTIALS", "Invalid credentials", 401)

            token = rt.jwt.encode(
                {
                    "user_id": user[0],
                    "username": user[1],
                    "exp": rt.datetime.utcnow() + rt.timedelta(hours=24),
                },
                rt.app.config["SECRET_KEY"],
                algorithm="HS256",
            )

            rt.logger.info(f"User {username} logged in successfully")
            return success_response(
                {
                    "token": token,
                    "user_id": user[0],
                    "username": user[1],
                },
                message="Login successful",
                status=200,
            )

    except (pymysql.Error, psycopg2.Error) as e:
        rt.logger.error(f"Database error during login: {e}")
        return error_response("DATABASE_ERROR", "Database error", 500)
    except Exception as e:
        rt.logger.error(f"Login error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)
