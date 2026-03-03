# 🐳 DOCKER DEPLOYMENT FIXES

**Ngày:** 2026-03-03  
**Status:** Ready for Production Deploy

---

## 🔧 CÁC FIXES ĐÃ THỰC HIỆN

### 1. Dockerfile (Backend)

#### ✅ Thêm `face_recognition/` module
**Vấn đề:** Thiếu copy `face_recognition/` module vào container  
**Fix:**
```dockerfile
COPY face_recognition/ ./face_recognition/
COPY tests/ ./tests/  # Optional for verification
```

#### ✅ Thêm Healthcheck
**Vấn đề:** Không có healthcheck để kiểm tra container status  
**Fix:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/api/health')" || exit 1
```

---

### 2. docker-compose.yml

#### ✅ Thêm Environment Variables
**Vấn đề:** Thiếu các biến môi trường quan trọng  
**Fix:**
```yaml
environment:
  - DB_TYPE=mysql
  - LABEL_MAP_PATH=/app/model/label_map.json
  - CORS_ORIGINS=http://localhost,http://localhost:80,http://localhost:3000,http://localhost:5173
  - REDIS_URL=memory://
```

#### ✅ Thêm Volume Mount cho face_recognition
**Vấn đề:** Cần mount thêm `face_recognition/` để development  
**Fix:**
```yaml
volumes:
  - ./TrainingImage:/app/TrainingImage
  - ./model:/app/model
  - ./logs:/app/logs
  - ./face_recognition:/app/face_recognition  # Thêm mới
```

#### ✅ Thêm Healthcheck cho Backend
**Vấn đề:** Không có healthcheck trong docker-compose  
**Fix:**
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:5001/api/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

### 3. frontend/Dockerfile

#### ✅ Sửa npm install
**Vấn đề:** `npm ci --only=production` bỏ qua devDependencies cần thiết để build  
**Fix:**
```dockerfile
# Before
RUN npm ci --only=production

# After  
RUN npm ci  # Install cả devDependencies để build
```

---

## 🚀 DEPLOYMENT INSTRUCTIONS

### Local Development
```bash
# Build và chạy tất cả services
docker-compose up --build

# Chạy detached mode
docker-compose up -d --build

# Xem logs
docker-compose logs -f

# Dừng tất cả
docker-compose down
```

### Production Deploy
```bash
# 1. Set production secret key
export SECRET_KEY=your-secure-secret-key-at-least-32-chars

# 2. Build và deploy
docker-compose -f docker-compose.yml up -d --build

# 3. Kiểm tra health
curl http://localhost:5001/api/health
```

---

## 📋 DEPLOYMENT CHECKLIST

### Pre-deployment
- [ ] Đảm bảo `.env` file có đầy đủ biến môi trường
- [ ] Thay đổi `SECRET_KEY` mặc định
- [ ] Cấu hình `CORS_ORIGINS` cho domain production
- [ ] Backup database (nếu upgrade)

### Build
- [ ] `docker-compose build` thành công
- [ ] Không có lỗi trong build logs
- [ ] Tất cả layers cached đúng

### Runtime
- [ ] Container backend healthy
- [ ] Container frontend chạy được
- [ ] Database khởi động thành công
- [ ] Health check endpoint trả về 200

### Functionality
- [ ] API endpoints hoạt động
- [ ] WebSocket kết nối được
- [ ] Database read/write thành công
- [ ] File uploads hoạt động

---

## 🌐 ENVIRONMENT VARIABLES

### Required
| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (min 32 chars) | `your-secure-key...` |
| `DB_PASSWORD` | Database password | `facepassword` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |

### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `DB_TYPE` | `mysql` | Database type (mysql/postgresql) |
| `PORT` | `5001` | API server port |
| `UPLOAD_FOLDER` | `/app/TrainingImage` | Image upload path |
| `REDIS_URL` | `memory://` | Rate limiting storage |

---

## 🔍 TROUBLESHOOTING

### Issue: Backend không kết nối được database
**Solution:**
```bash
# Kiểm tra database container
docker-compose logs db

# Đảm bảo DB_HOST=db trong docker-compose.yml
# Đảm bảo database đã healthy trước khi backend start
```

### Issue: Frontend không gọi được API
**Solution:**
```bash
# Kiểm tra nginx.conf proxy_pass
docker-compose logs frontend

# Đảm bảo CORS_ORIGINS chứa domain frontend
```

### Issue: WebSocket không kết nối được
**Solution:**
```bash
# Kiểm tra firewall port 5001
# Đảm bảo nginx proxy WebSocket headers đúng
# Kiểm tra token trong WebSocket connection
```

---

## 📊 PRODUCTION OPTIMIZATIONS

### 1. Database
```yaml
# Thêm resource limits
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 512M
```

### 2. Backend
```yaml
# Thêm scaling
deploy:
  replicas: 2
  resources:
    limits:
      memory: 2G
      cpus: '1.0'
```

### 3. Redis (cho production)
```yaml
# Thêm Redis service cho rate limiting
redis:
  image: redis:7-alpine
  restart: always
```

---

## ✅ VERIFICATION

Sau khi deploy, kiểm tra các endpoints:

```bash
# Health check
curl http://localhost:5001/api/health

# API test
curl http://localhost:5001/api/students

# WebSocket test (dùng wscat hoặc browser console)
# wscat -c "ws://localhost:5001?token=YOUR_JWT_TOKEN"

# Frontend
open http://localhost
```

---

**Docker configuration đã sẵn sàng cho production deploy! 🚀**
