-- ============================================================
-- PostgreSQL Schema for Face Attendance System
-- Migration from MySQL to PostgreSQL
-- ============================================================

-- Drop existing tables (if exists) in correct order
DROP TABLE IF EXISTS training_images CASCADE;
DROP TABLE IF EXISTS attendance CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================================
-- Users table for authentication
-- ============================================================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for users
CREATE INDEX idx_users_username ON users(username);

-- ============================================================
-- Students table for face registration
-- ============================================================
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    face_image_path VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for students
CREATE INDEX idx_students_student_id ON students(student_id);
CREATE INDEX idx_students_is_active ON students(is_active);
CREATE INDEX idx_students_name ON students(name);

-- ============================================================
-- Attendance table (renamed from Attendance to lowercase)
-- ============================================================
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

-- Indexes for attendance
CREATE INDEX idx_attendance_date ON attendance(date);
CREATE INDEX idx_attendance_student_date ON attendance(student_id, date);
CREATE INDEX idx_attendance_subject ON attendance(subject);
CREATE INDEX idx_attendance_student_date_subject ON attendance(student_id, date, subject);

-- ============================================================
-- Training images table
-- ============================================================
CREATE TABLE training_images (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    is_used_for_training BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

-- Indexes for training_images
CREATE INDEX idx_training_images_student_id ON training_images(student_id);

-- ============================================================
-- TRIGGERS FOR updated_at TIMESTAMP
-- ============================================================

-- Function to update timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for users table
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for students table
DROP TRIGGER IF EXISTS update_students_updated_at ON students;
CREATE TRIGGER update_students_updated_at 
    BEFORE UPDATE ON students
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- COMMENTS for documentation
-- ============================================================

COMMENT ON TABLE users IS 'User authentication table';
COMMENT ON TABLE students IS 'Student information and face registration';
COMMENT ON TABLE attendance IS 'Attendance records for students';
COMMENT ON TABLE training_images IS 'Training images for face recognition';

-- ============================================================
-- Insert default admin user (password: admin123)
-- Password hash: bcrypt of 'admin123'
-- WARNING: Change this password immediately after deployment!
-- ============================================================
INSERT INTO users (username, password_hash) 
SELECT 'admin', '$2b$12$eHdR0/jXQEJjGYdkEwSVVOYuGRJIE0VrnkavUoTvjBD2E2Z74rENu' 
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

-- ============================================================
-- NOTES:
-- 1. Run this script AFTER MySQL to PostgreSQL migration
-- 2. Use migrate_mysql_to_postgresql.py to transfer data
-- 3. After migration, run: SELECT setval('table_id_seq', (SELECT MAX(id) FROM table));
--    to reset sequences if needed
-- ============================================================
