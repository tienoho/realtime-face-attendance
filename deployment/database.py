"""
Database connection pool manager for Face Attendance API
Provides efficient database connection handling with pooling
"""
import os
import logging
from contextlib import contextmanager
import pymysql
from dbutils.pooled_db import PooledDB

logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'db': os.getenv('DB_NAME', 'face_attendance'),
    'charset': 'utf8mb4',
    'autocommit': True,
}

# Pool configuration
POOL_CONFIG = {
    'creator': pymysql,
    'maxconnections': 10,       # Max connections in pool
    'mincached': 2,              # Min idle connections
    'maxcached': 5,              # Max idle connections
    'maxshared': 3,             # Max shared connections
    'blocking': True,            # Block when pool is full
    'maxusage': None,           # Max reuses per connection
    'setsession': [],           # Session commands
    'ping': 1,                  # Check connection alive
    **DB_CONFIG
}

# Global connection pool
_db_pool = None


def init_db_pool():
    """Initialize the database connection pool"""
    global _db_pool
    
    if _db_pool is not None:
        logger.warning("Database pool already initialized")
        return
    
    try:
        _db_pool = PooledDB(**POOL_CONFIG)
        logger.info("Database connection pool initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


def get_db_pool():
    """Get the database connection pool"""
    global _db_pool
    
    if _db_pool is None:
        init_db_pool()
    
    return _db_pool


@contextmanager
def get_db_connection():
    """
    Get a database connection from the pool.
    This is a context manager that automatically returns the connection to the pool.
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            ...
    """
    pool = get_db_pool()
    conn = pool.connection()
    
    try:
        yield conn
    except pymysql.Error as e:
        logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
    finally:
        conn.close()  # Returns connection to pool


def close_db_pool():
    """Close all connections in the pool"""
    global _db_pool
    
    if _db_pool is not None:
        _db_pool.close()
        _db_pool = None
        logger.info("Database connection pool closed")


# Decorator for functions that need database connection
def with_db_connection(func):
    """
    Decorator to automatically provide database connection to a function.
    
    Usage:
        @with_db_connection
        def query_users(cursor):
            cursor.execute("SELECT * FROM users")
            return cursor.fetchall()
    """
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            result = func(cursor, *args, **kwargs)
            return result
    
    return wrapper


# Health check for database
def check_db_health():
    """Check if database connection is healthy"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            return True, "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False, str(e)


if __name__ == '__main__':
    # Test the connection pool
    init_db_pool()
    
    try:
        # Test getting a connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT VERSION()')
            version = cursor.fetchone()
            print(f"MySQL version: {version[0]}")
            
            # List tables
            cursor.execute('SHOW TABLES')
            tables = cursor.fetchall()
            print(f"Tables: {[t[0] for t in tables]}")
    finally:
        close_db_pool()
