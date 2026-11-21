# EDUWEB: bản phát triển

Ứng dụng đang được xây theo các tài liệu trong `docs/`. Chỉ dùng dữ liệu giả trên máy local; không đưa lên Internet hay dùng dữ liệu học sinh thật. Ghi âm, giao diện quản lý lớp và bài, MFA giáo viên, xếp hạng và các tiêu chí vận hành còn chưa hoàn tất.

## Chạy thử

Yêu cầu Python 3.13, uv, Docker Desktop và PostgreSQL 17. Trong PowerShell tại thư mục dự án:

```powershell
python -m uv venv --python 3.13 .venv
python -m uv pip install --python .venv/Scripts/python.exe -r requirements.lock
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Mở http://127.0.0.1:8000/ và nhập mã học sinh giả được in bởi `seed_demo`. Chạy lệnh đó lần nữa sẽ đổi mã và thu hồi phiên cũ. Dữ liệu trong Docker volume là dữ liệu phát triển, không phải bản sao lưu production.

Để thêm khóa học và bài tập mẫu, chạy `python manage.py seed_courses` sau khi có tài khoản giáo viên. Lệnh không tự gán lớp hoặc học sinh. Xem [cách quản lý khóa học](docs/khoa-hoc.md).

Kiểm tra trên PostgreSQL:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.accounts apps.classes apps.content apps.assignments apps.grading apps.reporting
```

Không dùng khóa mặc định hoặc cấu hình DEBUG trong production. Yêu cầu và các ca nghiệm thu còn lại ở `docs/05-trien-khai-va-nghiem-thu.md`.
