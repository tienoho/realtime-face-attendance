# 🐘 PostgreSQL Migration - Docker Configuration

**Ngày:** 2026-03-03  
**Status:** Migrated from MySQL to PostgreSQL

---

## 🔧 CHANGES MADE

### 1. docker-compose.yml

#### Database Service
```yaml
# BEFORE - MySQL
db:
  image: mysql:8.0
  environment:
    MYSQL_ROOT_PASSWORD: rootpassword
    MYSQL_DATABASE: face_attendance
    MYSQL_USER: faceuser
    MYSQL_PASSWORD: facepassword
  volumes:
    - mysql_data:/var/lib/mysql
    - ./database/init_db.sql:/docker-entrypoint-initdb.d/init_db.sql
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]

# AFTER - PostgreSQL
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_USER: faceuser
    POSTGRES_PASSWORD: facepassword
    POSTGRES_DB: face_attendance
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./database/postgres_schema.sql:/docker-entrypoint-initdb.d/init.sql
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U faceuser -d face_attendance"]
```

#### Backend Environment
```yaml
# BEFORE
environment:
  - DB_TYPE=mysql

# AFTER
environment:
  - DB_TYPE=postgresql
  - DB_PORT=5432
```

#### Volumes
```yaml
# BEFORE
volumes:
  mysql_data:

# AFTER
volumes:
  postgres_data:
```

---

### 2. Dockerfile

```dockerfile
# BEFORE
libmysqlclient-dev \

# AFTER
libpq-dev \
```

---

## 🚀 DEPLOY WITH POSTGRESQL

### Clean Deploy (fresh start)
```bash
# Remove old MySQL data (WARNING: destructive)
docker-compose down -v

# Start with PostgreSQL
docker-compose up --build
```

### Migration from existing MySQL (if needed)
```bash
# 1. Backup MySQL data
docker exec face-attendance-db mysqldump -u root -p face_attendance > backup.sql

# 2. Convert to PostgreSQL (use pgloader or manual conversion)

# 3. Switch to PostgreSQL
docker-compose down
docker-compose -f docker-compose.yml up --build
```

---

## ✅ VERIFICATION

```bash
# Check PostgreSQL is running
docker-compose ps

# Check logs
docker-compose logs db

# Connect to PostgreSQL
docker exec -it face-attendance-db psql -U faceuser -d face_attendance

# Test backend health
curl http://localhost:5001/api/health
```

---

## 📊 POSTGRESQL ADVANTAGES

| Feature | MySQL | PostgreSQL |
|---------|-------|------------|
| JSON Support | Limited | Native JSONB |
| Concurrency | MVCC | Better MVCC |
| Extensions | Limited | Rich ecosystem |
| Standards | Partial | Full SQL compliance |
| Performance | Good | Better for complex queries |

---

**Migration to PostgreSQL completed! 🐘**
