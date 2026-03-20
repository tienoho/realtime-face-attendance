-- Create staffs table
CREATE TABLE IF NOT EXISTS staffs (
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

-- Create indexes for staffs
CREATE INDEX IF NOT EXISTS idx_staffs_staff_id ON staffs(staff_id);
CREATE INDEX IF NOT EXISTS idx_staffs_is_active ON staffs(is_active);
CREATE INDEX IF NOT EXISTS idx_staffs_name ON staffs(name);
CREATE INDEX IF NOT EXISTS idx_staffs_department ON staffs(department);

-- Add foreign key to attendance table (will fail if staff_id column doesn't exist)
ALTER TABLE attendance DROP CONSTRAINT IF EXISTS fk_attendance_staff;
ALTER TABLE attendance ADD CONSTRAINT fk_attendance_staff FOREIGN KEY (staff_id) REFERENCES staffs(staff_id) ON DELETE CASCADE;

-- Add foreign key to training_images table
ALTER TABLE training_images DROP CONSTRAINT IF EXISTS fk_training_images_staff;
ALTER TABLE training_images ADD CONSTRAINT fk_training_images_staff FOREIGN KEY (staff_id) REFERENCES staffs(staff_id) ON DELETE CASCADE;
