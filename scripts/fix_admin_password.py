#!/usr/bin/env python3
"""Fix admin password hash in PostgreSQL database."""
import bcrypt
import psycopg2

# Generate new hash for admin123
new_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
print(f"New hash: {new_hash}")

# Update database
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    user='faceuser',
    password='facepassword',
    database='face_attendance'
)
cur = conn.cursor()
cur.execute("UPDATE users SET password_hash = %s WHERE username = 'admin'", (new_hash,))
conn.commit()
print("Password updated successfully!")

# Verify
cur.execute("SELECT username, password_hash FROM users WHERE username = 'admin'")
result = cur.fetchone()
print(f"User: {result[0]}")
print(f"Hash: {result[1]}")

# Test password
test_result = bcrypt.checkpw(b'admin123', result[1].encode())
print(f"Password verification: {test_result}")

conn.close()
