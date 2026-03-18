-- ============================================================
-- Migration Script: Students → Staffs
-- Big Bang Migration
-- ============================================================

-- Step 1: Backup existing data (CREATE BACKUP TABLES)
-- ============================================================
CREATE TABLE IF NOT EXISTS students_backup AS SELECT * FROM students;
CREATE TABLE IF NOT EXISTS attendance_backup AS SELECT * FROM attendance;
CREATE TABLE IF NOT EXISTS training_images_backup AS SELECT * FROM training_images;

-- Step 2: Create new Staffs table
-- ============================================================
CREATE TABLE IF NOT EXISTS staffs (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    position VARCHAR(50),
    face_image_path VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for staffs
CREATE INDEX IF NOT EXISTS idx_staffs_staff_id ON staffs(staff_id);
CREATE INDEX IF NOT EXISTS idx_staffs_is_active ON staffs(is_active);
CREATE INDEX IF NOT EXISTS idx_staffs_name ON staffs(name);
CREATE INDEX IF NOT EXISTS idx_staffs_department ON staffs(department);

-- Trigger for updated_at
DROP TRIGGER IF EXISTS update_staffs_updated_at ON staffs;
CREATE TRIGGER update_staffs_updated_at 
    BEFORE UPDATE ON staffs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Step 3: Migrate data from students to staffs
-- ============================================================
INSERT INTO staffs (staff_id, name, face_image_path, is_active, created_at, updated_at)
SELECT student_id, name, face_image_path, is_active, created_at, updated_at
FROM students;

-- Step 4: Update attendance table references
-- ============================================================
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS staff_id VARCHAR(50);
UPDATE attendance SET staff_id = student_id WHERE staff_id IS NULL;

-- Add foreign key (optional, after verifying data)
-- ALTER TABLE attendance 
--     ADD CONSTRAINT fk_attendance_staff 
--     FOREIGN KEY (staff_id) REFERENCES staffs(staff_id) ON DELETE CASCADE;

-- Step 5: Update training_images table references
-- ============================================================
ALTER TABLE training_images ADD COLUMN IF NOT EXISTS staff_id VARCHAR(50);
UPDATE training_images SET staff_id = student_id WHERE staff_id IS NULL;

-- Step 6: Drop old foreign keys and tables (AFTER ALL UPDATES)
-- ============================================================
-- WARNING: Only execute these after verifying all applications are updated

-- ALTER TABLE attendance DROP CONSTRAINT IF EXISTS attendance_student_id_fkey;
-- ALTER TABLE training_images DROP CONSTRAINT IF EXISTS training_images_student_id_fkey;

-- Step 7: Verify migration
-- ============================================================
SELECT 'staffs count:' AS info, COUNT(*) AS count FROM staffs
UNION ALL
SELECT 'attendance with staff_id:', COUNT(*) FROM attendance WHERE staff_id IS NOT NULL
UNION ALL
SELECT 'training_images with staff_id:', COUNT(*) FROM training_images WHERE staff_id IS NOT NULL;

-- Step 8: Create rollback script (if needed)
-- ============================================================
-- To rollback: Run this only if migration fails
/*
-- Restore from backup
INSERT INTO students (student_id, name, face_image_path, is_active, created_at, updated_at)
SELECT staff_id, name, face_image_path, is_active, created_at, updated_at
FROM staffs;

-- Restore attendance
UPDATE attendance a SET student_id = s.student_id
FROM staffs_backup s WHERE a.staff_id = s.staff_id;

-- Restore training_images  
UPDATE training_images t SET student_id = s.staff_id
FROM staffs_backup s WHERE t.staff_id = s.staff_id;

-- Drop new tables
DROP TABLE IF EXISTS staffs CASCADE;
DROP TABLE IF EXISTS students_backup CASCADE;
DROP TABLE IF EXISTS attendance_backup CASCADE;
DROP TABLE IF EXISTS training_images_backup CASCADE;
*/

-- ============================================================
-- COMMENTS
-- ============================================================
COMMENT ON TABLE staffs IS 'Staff information and face registration';
COMMENT ON TABLE attendance IS 'Attendance records for staff';
