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
-- Staffs table for face registration (replaces students)
-- ============================================================
CREATE TABLE staffs (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    face_image_path VARCHAR(255),
    department VARCHAR(100),
    position VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for staffs
CREATE INDEX idx_staffs_staff_id ON staffs(staff_id);
CREATE INDEX idx_staffs_is_active ON staffs(is_active);
CREATE INDEX idx_staffs_name ON staffs(name);
CREATE INDEX idx_staffs_department ON staffs(department);

-- Keep students table for backward compatibility (deprecated)
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    face_image_path VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for students (deprecated)
CREATE INDEX idx_students_student_id ON students(student_id);
CREATE INDEX idx_students_is_active ON students(is_active);
CREATE INDEX idx_students_name ON students(name);

-- ============================================================
-- Attendance table (renamed from Attendance to lowercase)
-- Now uses staff_id instead of student_id
-- ============================================================
CREATE TABLE attendance (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) NOT NULL,
    enrollment VARCHAR(100),
    name VARCHAR(50),
    date VARCHAR(20) NOT NULL,
    time VARCHAR(20) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'Present',
    confidence_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staffs(staff_id) ON DELETE CASCADE
);

-- Indexes for attendance
CREATE INDEX idx_attendance_date ON attendance(date);
CREATE INDEX idx_attendance_staff_date ON attendance(staff_id, date);
CREATE INDEX idx_attendance_subject ON attendance(subject);
CREATE INDEX idx_attendance_staff_date_subject ON attendance(staff_id, date, subject);

-- Keep old student_id column for backward compatibility (deprecated)
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS student_id VARCHAR(50);
ALTER TABLE attendance ADD CONSTRAINT fk_attendance_student DEPRECATED FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE SET NULL;

-- ============================================================
-- Training images table
-- Now uses staff_id instead of student_id
-- ============================================================
CREATE TABLE training_images (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    is_used_for_training BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staffs(staff_id) ON DELETE CASCADE
);

-- Indexes for training_images
CREATE INDEX idx_training_images_staff_id ON training_images(staff_id);

-- Keep old student_id column for backward compatibility (deprecated)
ALTER TABLE training_images ADD COLUMN IF NOT EXISTS student_id VARCHAR(50);
ALTER TABLE training_images ADD CONSTRAINT fk_training_images_student DEPRECATED FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE SET NULL;

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

-- Trigger for staffs table
DROP TRIGGER IF EXISTS update_staffs_updated_at ON staffs;
CREATE TRIGGER update_staffs_updated_at 
    BEFORE UPDATE ON staffs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for students table (deprecated)
DROP TRIGGER IF EXISTS update_students_updated_at ON students;
CREATE TRIGGER update_students_updated_at 
    BEFORE UPDATE ON students
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- COMMENTS for documentation
-- ============================================================

COMMENT ON TABLE users IS 'User authentication table';
COMMENT ON TABLE staffs IS 'Staff information and face registration (replaces students)';
COMMENT ON TABLE students IS 'DEPRECATED - Student information (use staffs instead)';
COMMENT ON TABLE attendance IS 'Attendance records for staff';
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
