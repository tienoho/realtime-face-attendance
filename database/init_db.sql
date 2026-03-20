-- ============================================================
-- Face Attendance System - Database Schema
-- Fixed version with consistent database name and all required tables
-- ============================================================

-- Create database with consistent name
CREATE DATABASE IF NOT EXISTS face_attendance;
USE face_attendance;

-- ============================================================
-- Users table for authentication
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Staffs table for face registration (replaces students)
-- ============================================================
CREATE TABLE IF NOT EXISTS staffs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    staff_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    face_image_path VARCHAR(255),
    department VARCHAR(100),
    position VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_staff_id (staff_id),
    INDEX idx_is_active (is_active),
    INDEX idx_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Students table (deprecated - kept for backward compatibility)
-- ============================================================
CREATE TABLE IF NOT EXISTS students (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    face_image_path VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student_id (student_id),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Attendance table (now uses staff_id)
-- ============================================================
CREATE TABLE IF NOT EXISTS Attendance (
    id INT PRIMARY KEY AUTO_INCREMENT,
    staff_id VARCHAR(50) NOT NULL,
    enrollment VARCHAR(100),
    name VARCHAR(50),
    date VARCHAR(20) NOT NULL,
    time VARCHAR(20) NOT NULL,
    subject VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'Present',
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staffs(staff_id),
    INDEX idx_date (date),
    INDEX idx_staff_date (staff_id, date),
    INDEX idx_subject (subject)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Insert default admin user (password: admin123)
-- Default password hash for 'admin123'
-- Note: In production, use proper password hashing
-- ============================================================
INSERT INTO users (username, password_hash) 
SELECT 'admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqKx8pKv6u' 
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

-- ============================================================
-- Create training images table (now uses staff_id)
-- ============================================================
CREATE TABLE IF NOT EXISTS training_images (
    id INT PRIMARY KEY AUTO_INCREMENT,
    staff_id VARCHAR(50) NOT NULL,
    image_path VARCHAR(255) NOT NULL,
    is_used_for_training BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES staffs(staff_id),
    INDEX idx_staff (staff_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
