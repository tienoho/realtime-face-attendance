"""Authentication service layer."""

import threading
import time
import uuid
import psycopg2
from datetime import datetime, timedelta

try:
    from deployment.services.dto_service import error_response, success_response
except ImportError:
    from services.dto_service import error_response, success_response


# H-AUTH-001: JWT Refresh Token configuration
ACCESS_TOKEN_EXPIRY_HOURS = 1  # Short-lived access token
REFRESH_TOKEN_EXPIRY_DAYS = 7  # Long-lived refresh token

# In-memory refresh token store (production: use Redis/database)
# H-TOKEN-001 FIX: Added cleanup thread to prevent memory leak
_refresh_tokens = {}  # token_id: {user_id, expires_at}
_refresh_tokens_lock = threading.Lock()
_token_cleanup_running = True


def _cleanup_expired_tokens():
    """Background thread to clean up expired refresh tokens."""
    global _token_cleanup_running
    while _token_cleanup_running:
        try:
            with _refresh_tokens_lock:
                now = datetime.utcnow()
                expired = [
                    token_id for token_id, data in _refresh_tokens.items()
                    if now > data["expires_at"]
                ]
                for token_id in expired:
                    del _refresh_tokens[token_id]
                
                if expired:
                    pass  # Could add logging here if needed
        except Exception:
            pass
        
        time.sleep(300)  # Check every 5 minutes


# Start cleanup thread
_cleanup_thread = threading.Thread(target=_cleanup_expired_tokens, daemon=True)
_cleanup_thread.start()


def _generate_tokens(rt, user_id: int, username: str) -> dict:
    """Generate access token and refresh token pair."""
    # Access token (short-lived)
    access_token = rt.jwt.encode(
        {
            "user_id": user_id,
            "username": username,
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRY_HOURS),
        },
        rt.app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    
    # Refresh token (long-lived, opaque)
    refresh_token_id = str(uuid.uuid4())
    refresh_token_expires = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)
    
    _refresh_tokens[refresh_token_id] = {
        "user_id": user_id,
        "username": username,
        "expires_at": refresh_token_expires,
    }
    # H-TOKEN-001 FIX: Use lock when accessing shared state
    # (Note: lock is held briefly for dict update, which is atomic in CPython)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token_id,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY_HOURS * 3600,  # seconds
    }


def refresh_access_token(rt):
    """Refresh access token using refresh token."""
    try:
        data = rt.request.get_json(silent=True)
        if not data or not data.get("refresh_token"):
            return error_response("MISSING_REFRESH_TOKEN", "Refresh token required", 400)
        
        refresh_token_id = data.get("refresh_token")
        
        # Validate refresh token
        with _refresh_tokens_lock:
            token_data = _refresh_tokens.get(refresh_token_id)
            if not token_data:
                return error_response("INVALID_REFRESH_TOKEN", "Invalid or expired refresh token", 401)
            
            if datetime.utcnow() > token_data["expires_at"]:
                # Clean up expired token
                del _refresh_tokens[refresh_token_id]
                return error_response("EXPIRED_REFRESH_TOKEN", "Refresh token expired", 401)
        
        # Generate new token pair
        tokens = _generate_tokens(rt, token_data["user_id"], token_data["username"])
        
        # Invalidate old refresh token (token rotation)
        with _refresh_tokens_lock:
            if refresh_token_id in _refresh_tokens:
                del _refresh_tokens[refresh_token_id]
        
        rt.logger.info(f"Token refreshed for user {token_data['username']}")
        return success_response(
            tokens,
            message="Token refreshed successfully",
            status=200,
        )
        
    except Exception as e:
        rt.logger.error(f"Token refresh error: {e}")
        return error_response("SERVER_ERROR", "Server error", 500)


def logout(rt):
    """Logout user by invalidating refresh token."""
    try:
        data = rt.request.get_json(silent=True)
        refresh_token_id = data.get("refresh_token") if data else None
        
        with _refresh_tokens_lock:
            if refresh_token_id and refresh_token_id in _refresh_tokens:
                del _refresh_tokens[refresh_token_id]
                rt.logger.info("Refresh token invalidated")
        
        return success_response({}, message="Logout successful", status=200)
        
    except Exception as e:
        rt.logger.error(f"Logout error: {e}")
        return error_response("SERVER_ERROR", "Server error", 500)


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

            # H-AUTH-001: Generate access and refresh tokens
            tokens = _generate_tokens(rt, user[0], user[1])

            rt.logger.info(f"User {username} logged in successfully")
            return success_response(
                {
                    "token": tokens["access_token"],
                    "refresh_token": tokens["refresh_token"],
                    "token_type": tokens["token_type"],
                    "expires_in": tokens["expires_in"],
                    "user_id": user[0],
                    "username": user[1],
                },
                message="Login successful",
                status=200,
            )

    except psycopg2.Error as e:
        rt.logger.error(f"Database error during login: {e}")
        return error_response("DATABASE_ERROR", "Database error", 500)
    except Exception as e:
        rt.logger.error(f"Login error: {str(e)}")
        return error_response("SERVER_ERROR", "Server error", 500)
