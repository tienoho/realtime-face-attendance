"""
Database connection pool manager for Face Attendance API
======================================================

Supports both MySQL and PostgreSQL databases.
Set DB_TYPE environment variable to 'mysql' or 'postgresql' (default: mysql).

Usage:
    # For MySQL (default)
    DB_TYPE=mysql python deployment/api.py
    
    # For PostgreSQL
    DB_TYPE=postgresql python deployment/api.py
"""

import os
import logging
from contextlib import contextmanager
import pymysql
from dbutils.pooled_db import PooledDB
import psycopg2
from psycopg2 import pool

logger = logging.getLogger(__name__)

# Database type selection
DB_TYPE = os.getenv('DB_TYPE', 'mysql').lower()

# ============================================================
# MYSQL CONFIGURATION
# ============================================================

MYSQL_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'db': os.getenv('DB_NAME', 'face_attendance'),
    'charset': 'utf8mb4',
    'autocommit': True,
}

MYSQL_POOL_CONFIG = {
    'creator': pymysql,
    'maxconnections': int(os.getenv('DB_POOL_MAX', 10)),
    'mincached': int(os.getenv('DB_POOL_MIN', 2)),
    'maxcached': 5,
    'maxshared': 3,
    'blocking': True,
    'maxusage': None,
    'setsession': [],
    'ping': 1,
    **MYSQL_CONFIG
}

# ============================================================
# POSTGRESQL CONFIGURATION
# ============================================================

POSTGRESQL_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'face_attendance'),
    'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
    'client_encoding': 'UTF8',
}

# ============================================================
# CONNECTION POOL
# ============================================================

_mysql_pool = None
_postgresql_pool = None


def init_db_pool():
    """Initialize the database connection pool based on DB_TYPE"""
    global _mysql_pool, _postgresql_pool
    
    if DB_TYPE == 'postgresql':
        if _postgresql_pool is not None:
            logger.warning("PostgreSQL pool already initialized")
            return
        
        try:
            _postgresql_pool = pool.ThreadedConnectionPool(
                minconn=int(os.getenv('DB_POOL_MIN', 2)),
                maxconn=int(os.getenv('DB_POOL_MAX', 10)),
                **POSTGRESQL_CONFIG
            )
            logger.info("PostgreSQL connection pool initialized")
            logger.info(f"  Host: {POSTGRESQL_CONFIG['host']}:{POSTGRESQL_CONFIG['port']}")
            logger.info(f"  Database: {POSTGRESQL_CONFIG['database']}")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise
    else:
        # MySQL (default)
        if _mysql_pool is not None:
            logger.warning("MySQL pool already initialized")
            return
        
        try:
            _mysql_pool = PooledDB(**MYSQL_POOL_CONFIG)
            logger.info("MySQL connection pool initialized")
            logger.info(f"  Host: {MYSQL_CONFIG['host']}")
            logger.info(f"  Database: {MYSQL_CONFIG['db']}")
        except Exception as e:
            logger.error(f"Failed to initialize MySQL pool: {e}")
            raise


def get_db_pool():
    """Get the database connection pool"""
    global _mysql_pool, _postgresql_pool
    
    if _mysql_pool is None and _postgresql_pool is None:
        init_db_pool()
    
    if DB_TYPE == 'postgresql':
        return _postgresql_pool
    return _mysql_pool


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
    
    if DB_TYPE == 'postgresql':
        conn = None
        try:
            conn = pool.getconn()
            conn.autocommit = True
            yield conn
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
        finally:
            if conn:
                pool.putconn(conn)
    else:
        # MySQL
        conn = pool.connection()
        try:
            yield conn
        except pymysql.Error as e:
            logger.error(f"MySQL error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
        finally:
            conn.close()


def close_db_pool():
    """Close all connections in the pool"""
    global _mysql_pool, _postgresql_pool
    
    if DB_TYPE == 'postgresql':
        if _postgresql_pool is not None:
            _postgresql_pool.closeall()
            _postgresql_pool = None
            logger.info("PostgreSQL connection pool closed")
    else:
        if _mysql_pool is not None:
            _mysql_pool.close()
            _mysql_pool = None
            logger.info("MySQL connection pool closed")


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


# Utility functions
def get_table_list():
    """Get list of tables in the database"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if DB_TYPE == 'postgresql':
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        else:
            cursor.execute('SHOW TABLES')
        tables = cursor.fetchall()
        return [t[0] for t in tables]


def get_db_version():
    """Get database server version"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT VERSION()' if DB_TYPE == 'postgresql' else 'SELECT VERSION()')
        version = cursor.fetchone()
        return version[0] if version else "Unknown"


if __name__ == '__main__':
    print(f"Database type: {DB_TYPE}")
    print("Testing database connection...")
    
    try:
        init_db_pool()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
            print(f"✓ Database connection OK: {result}")
            
            version = get_db_version()
            print(f"✓ Database version: {version}")
            
            tables = get_table_list()
            print(f"✓ Tables: {tables}")
        
        is_healthy, message = check_db_health()
        print(f"✓ Health check: {message}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        
    finally:
        close_db_pool()
