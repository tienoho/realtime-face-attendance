#!/usr/bin/env python3
"""
Migration Script: MySQL to PostgreSQL
=====================================

Migrate data from MySQL to PostgreSQL for the Face Attendance System.

Prerequisites:
    pip install pymysql psycopg2-binary
    
Usage:
    # Set environment variables
    export SOURCE_DB_HOST=localhost
    export SOURCE_DB_USER=root
    export SOURCE_DB_PASSWORD=your_password
    export SOURCE_DB_NAME=face_attendance
    
    export TARGET_DB_HOST=localhost
    export TARGET_DB_USER=postgres
    export TARGET_DB_PASSWORD=your_password
    export TARGET_DB_NAME=face_attendance
    
    python scripts/migrate_mysql_to_postgresql.py
    
Options:
    --dry-run       Show what would be migrated without actually migrating
    --verify        Verify data after migration
    --skip-schema   Skip schema creation (use existing)
"""

import os
import sys
import argparse
import logging
from datetime import datetime
import pymysql
import psycopg2

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLToPostgreSQLMigrator:
    """Migration từ MySQL sang PostgreSQL"""
    
    def __init__(self, source_config, target_config, dry_run=False):
        self.source_config = source_config
        self.target_config = target_config
        self.dry_run = dry_run
        self.source_conn = None
        self.target_conn = None
        self.stats = {
            'users': 0,
            'students': 0,
            'attendance': 0,
            'training_images': 0,
            'errors': []
        }
    
    def connect_source(self):
        """Kết nối MySQL source"""
        try:
            self.source_conn = pymysql.connect(
                host=self.source_config['host'],
                user=self.source_config['user'],
                password=self.source_config['password'],
                database=self.source_config['database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"Connected to MySQL: {self.source_config['host']}/{self.source_config['database']}")
        except pymysql.Error as e:
            logger.error(f"MySQL connection failed: {e}")
            raise
    
    def connect_target(self):
        """Kết nối PostgreSQL target"""
        try:
            self.target_conn = psycopg2.connect(
                host=self.target_config['host'],
                user=self.target_config['user'],
                password=self.target_config['password'],
                database=self.target_config['database'],
                client_encoding='UTF8'
            )
            self.target_conn.autocommit = False
            logger.info(f"Connected to PostgreSQL: {self.target_config['host']}/{self.target_config['database']}")
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise
    
    def close_connections(self):
        """Đóng tất cả connections"""
        if self.source_conn:
            self.source_conn.close()
            logger.info("MySQL connection closed")
        if self.target_conn:
            self.target_conn.close()
            logger.info("PostgreSQL connection closed")
    
    def create_target_schema(self):
        """Tạo schema trên PostgreSQL"""
        if self.dry_run:
            logger.info("[DRY RUN] Would create PostgreSQL schema")
            return
        
        schema_sql = """
        -- Drop existing tables
        DROP TABLE IF EXISTS training_images CASCADE;
        DROP TABLE IF EXISTS attendance CASCADE;
        DROP TABLE IF EXISTS students CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        
        -- Users table
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Students table
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            face_image_path VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Attendance table
        CREATE TABLE attendance (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR(50) NOT NULL,
            enrollment VARCHAR(100),
            name VARCHAR(50),
            date VARCHAR(20) NOT NULL,
            time VARCHAR(20) NOT NULL,
            subject VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'Present',
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );
        
        -- Training images table
        CREATE TABLE training_images (
            id SERIAL PRIMARY KEY,
            student_id VARCHAR(50) NOT NULL,
            image_path VARCHAR(255) NOT NULL,
            is_used_for_training BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );
        
        -- Indexes
        CREATE INDEX idx_students_student_id ON students(student_id);
        CREATE INDEX idx_students_is_active ON students(is_active);
        CREATE INDEX idx_attendance_date ON attendance(date);
        CREATE INDEX idx_attendance_student_date ON attendance(student_id, date);
        CREATE INDEX idx_attendance_subject ON attendance(subject);
        CREATE INDEX idx_training_images_student_id ON training_images(student_id);
        
        -- Triggers
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        CREATE TRIGGER update_students_updated_at BEFORE UPDATE ON students
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        
        -- Insert default admin
        INSERT INTO users (username, password_hash) 
        SELECT 'admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqKx8pKv6u' 
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');
        """
        
        with self.target_conn.cursor() as cursor:
            cursor.execute(schema_sql)
        self.target_conn.commit()
        logger.info("PostgreSQL schema created")
    
    def migrate_users(self):
        """Migrate users table"""
        logger.info("Migrating users...")
        
        with self.source_conn.cursor() as source_cursor:
            source_cursor.execute("SELECT * FROM users")
            users = source_cursor.fetchall()
        
        if not users:
            logger.info("No users to migrate")
            return
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would migrate {len(users)} users")
            self.stats['users'] = len(users)
            return
        
        with self.target_conn.cursor() as target_cursor:
            for user in users:
                created_at = user.get('created_at')
                updated_at = user.get('updated_at')
                
                target_cursor.execute(
                    """INSERT INTO users (id, username, password_hash, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (
                        user['id'],
                        user['username'],
                        user['password_hash'],
                        created_at.isoformat() if created_at else None,
                        updated_at.isoformat() if updated_at else None
                    )
                )
        
        self.target_conn.commit()
        self.stats['users'] = len(users)
        logger.info(f"Migrated {len(users)} users")
    
    def migrate_students(self):
        """Migrate students table"""
        logger.info("Migrating students...")
        
        with self.source_conn.cursor() as source_cursor:
            source_cursor.execute("SELECT * FROM students")
            students = source_cursor.fetchall()
        
        if not students:
            logger.info("No students to migrate")
            return
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would migrate {len(students)} students")
            self.stats['students'] = len(students)
            return
        
        with self.target_conn.cursor() as target_cursor:
            for student in students:
                created_at = student.get('created_at')
                updated_at = student.get('updated_at')
                
                # Convert MySQL boolean to Python boolean
                is_active = bool(student.get('is_active', 1))
                
                target_cursor.execute(
                    """INSERT INTO students (id, student_id, name, face_image_path, is_active, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (student_id) DO UPDATE SET
                           name = EXCLUDED.name,
                           face_image_path = EXCLUDED.face_image_path,
                           is_active = EXCLUDED.is_active""",
                    (
                        student['id'],
                        student['student_id'],
                        student['name'],
                        student.get('face_image_path'),
                        is_active,
                        created_at.isoformat() if created_at else None,
                        updated_at.isoformat() if updated_at else None
                    )
                )
        
        self.target_conn.commit()
        self.stats['students'] = len(students)
        logger.info(f"Migrated {len(students)} students")
    
    def migrate_attendance(self):
        """Migrate attendance table"""
        logger.info("Migrating attendance...")
        
        with self.source_conn.cursor() as source_cursor:
            source_cursor.execute("SELECT * FROM attendance")
            records = source_cursor.fetchall()
        
        if not records:
            logger.info("No attendance records to migrate")
            return
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would migrate {len(records)} attendance records")
            self.stats['attendance'] = len(records)
            return
        
        with self.target_conn.cursor() as target_cursor:
            for record in records:
                created_at = record.get('created_at')
                
                target_cursor.execute(
                    """INSERT INTO attendance (id, student_id, enrollment, name, date, time, subject, status, confidence_score, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        record['id'],
                        record['student_id'],
                        record.get('enrollment'),
                        record.get('name'),
                        record['date'],
                        record['time'],
                        record['subject'],
                        record.get('status', 'Present'),
                        record.get('confidence_score'),
                        created_at.isoformat() if created_at else None
                    )
                )
        
        self.target_conn.commit()
        self.stats['attendance'] = len(records)
        logger.info(f"Migrated {len(records)} attendance records")
    
    def migrate_training_images(self):
        """Migrate training_images table"""
        logger.info("Migrating training_images...")
        
        with self.source_conn.cursor() as source_cursor:
            source_cursor.execute("SELECT * FROM training_images")
            images = source_cursor.fetchall()
        
        if not images:
            logger.info("No training images to migrate")
            return
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would migrate {len(images)} training images")
            self.stats['training_images'] = len(images)
            return
        
        with self.target_conn.cursor() as target_cursor:
            for image in images:
                created_at = image.get('created_at')
                is_used = bool(image.get('is_used_for_training', 1))
                
                target_cursor.execute(
                    """INSERT INTO training_images (id, student_id, image_path, is_used_for_training, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        image['id'],
                        image['student_id'],
                        image['image_path'],
                        is_used,
                        created_at.isoformat() if created_at else None
                    )
                )
        
        self.target_conn.commit()
        self.stats['training_images'] = len(images)
        logger.info(f"Migrated {len(images)} training images")
    
    def reset_sequences(self):
        """Reset PostgreSQL sequences"""
        if self.dry_run:
            logger.info("[DRY RUN] Would reset sequences")
            return
        
        logger.info("Resetting sequences...")
        
        # Get sequence names dynamically from information_schema
        tables = ['users', 'students', 'attendance', 'training_images']
        
        with self.target_conn.cursor() as cursor:
            for table in tables:
                # Try to find the sequence for this table
                cursor.execute(
                    """
                    SELECT sequence_name 
                    FROM information_schema.sequences 
                    WHERE sequence_name LIKE %s
                    """,
                    (f'%{table}_id_seq%',)
                )
                result = cursor.fetchone()
                
                if result:
                    seq_name = result[0]
                    cursor.execute(f"SELECT setval('{seq_name}', (SELECT MAX(id) FROM {table}))")
                    logger.info(f"  Reset sequence {seq_name} for table {table}")
                else:
                    # Try alternative naming pattern
                    cursor.execute(
                        """
                        SELECT sequence_name 
                        FROM information_schema.sequences 
                        WHERE sequence_name LIKE %s
                        """,
                        (f'%{table}%_id%',)
                    )
                    result = cursor.fetchone()
                    if result:
                        seq_name = result[0]
                        cursor.execute(f"SELECT setval('{seq_name}', (SELECT MAX(id) FROM {table}))")
                        logger.info(f"  Reset sequence {seq_name} for table {table}")
                    else:
                        logger.warning(f"  Could not find sequence for table {table}")
        
        self.target_conn.commit()
        logger.info("Sequences reset complete")
    
    def verify_migration(self):
        """Verify migration results"""
        logger.info("Verifying migration...")
        
        checks = []
        
        with self.target_conn.cursor() as cursor:
            # Check tables exist
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [r[0] for r in cursor.fetchall()]
            expected_tables = ['users', 'students', 'attendance', 'training_images']
            all_exist = all(t in tables for t in expected_tables)
            checks.append(('Tables exist', all_exist))
            logger.info(f"  Tables: {tables}")
            
            # Check record counts
            for table in expected_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                checks.append((f'{table} has data', count > 0))
                logger.info(f"  {table}: {count} records")
        
        all_passed = True
        for check_name, result in checks:
            status = "✓" if result else "✗"
            logger.info(f"{status} {check_name}")
            if not result:
                all_passed = False
        
        return all_passed
    
    def run(self):
        """Chạy migration"""
        logger.info("=" * 60)
        logger.info("Starting MySQL to PostgreSQL Migration")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info("=" * 60)
        start_time = datetime.now()
        
        try:
            # Connect
            self.connect_source()
            self.connect_target()
            
            # Create schema
            self.create_target_schema()
            
            # Migrate data
            self.migrate_users()
            self.migrate_students()
            self.migrate_attendance()
            self.migrate_training_images()
            
            # Reset sequences
            self.reset_sequences()
            
            # Verify
            if not self.dry_run:
                if self.verify_migration():
                    logger.info("✓ Migration completed successfully!")
                else:
                    logger.warning("⚠ Migration completed with verification issues")
            else:
                logger.info("✓ Dry run completed - no data was migrated")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.stats['errors'].append(str(e))
            if self.target_conn:
                self.target_conn.rollback()
            raise
        
        finally:
            self.close_connections()
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Users:        {self.stats['users']}")
        logger.info(f"Students:     {self.stats['students']}")
        logger.info(f"Attendance:   {self.stats['attendance']}")
        logger.info(f"Training Img: {self.stats['training_images']}")
        logger.info(f"Errors:       {len(self.stats['errors'])}")
        logger.info(f"Duration:     {duration}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Migrate MySQL to PostgreSQL')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually migrating'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify data after migration'
    )
    parser.add_argument(
        '--skip-schema',
        action='store_true',
        help='Skip schema creation (use existing)'
    )
    
    # Source database args
    parser.add_argument('--source-host', default=os.getenv('SOURCE_DB_HOST', 'localhost'))
    parser.add_argument('--source-user', default=os.getenv('SOURCE_DB_USER', 'root'))
    parser.add_argument('--source-password', default=os.getenv('SOURCE_DB_PASSWORD', ''))
    parser.add_argument('--source-db', default=os.getenv('SOURCE_DB_NAME', 'face_attendance'))
    
    # Target database args
    parser.add_argument('--target-host', default=os.getenv('TARGET_DB_HOST', 'localhost'))
    parser.add_argument('--target-user', default=os.getenv('TARGET_DB_USER', 'postgres'))
    parser.add_argument('--target-password', default=os.getenv('TARGET_DB_PASSWORD', ''))
    parser.add_argument('--target-db', default=os.getenv('TARGET_DB_NAME', 'face_attendance'))
    
    args = parser.parse_args()
    
    source_config = {
        'host': args.source_host,
        'user': args.source_user,
        'password': args.source_password,
        'database': args.source_db
    }
    
    target_config = {
        'host': args.target_host,
        'user': args.target_user,
        'password': args.target_password,
        'database': args.target_db
    }
    
    migrator = MySQLToPostgreSQLMigrator(
        source_config,
        target_config,
        dry_run=args.dry_run
    )
    
    # Skip schema if requested
    if args.skip_schema:
        migrator.create_target_schema = lambda: logger.info("Skipping schema creation")
    
    migrator.run()


if __name__ == '__main__':
    main()
