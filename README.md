# EDUWEB: b?n ph�t tri?n

?ng d?ng dang du?c x�y theo c�c t�i li?u trong `docs/`. Ch? d�ng d? li?u gi? tr�n m�y local; kh�ng dua l�n Internet hay d�ng d? li?u h?c sinh th?t. Ghi �m, giao di?n qu?n ly l?p v� b�i, MFA gi�o vi�n, x?p h?ng v� c�c ti�u ch� v?n h�nh c�n chua ho�n t?t.

## Ch?y th?

Y�u c?u Python 3.13, uv, Docker Desktop v� PostgreSQL 17. Trong PowerShell t?i thu m?c d? �n:

```powershell
python -m uv venv --python 3.13 .venv
python -m uv pip install --python .venv/Scripts/python.exe -r requirements.lock
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

M? http://127.0.0.1:8000/ v� nh?p ma h?c sinh gi? du?c in b?i `seed_demo`. Ch?y l?nh d� l?n n?a s? d?i ma v� thu h?i phi�n cu. D? li?u trong Docker volume l� d? li?u ph�t tri?n, kh�ng ph?i b?n sao luu production.

D? th�m kh�a h?c v� b�i t?p m?u, ch?y `python manage.py seed_courses` sau khi c� t�i kho?n gi�o vi�n. L?nh kh�ng t? g�n l?p ho?c h?c sinh. Xem [c�ch qu?n ly kh�a h?c](docs/khoa-hoc.md).

Ki?m tra tr�n PostgreSQL:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.accounts apps.classes apps.content apps.assignments apps.grading apps.reporting
```

Kh�ng d�ng kh�a m?c d?nh ho?c c?u h�nh DEBUG trong production. Y�u c?u v� c�c ca nghi?m thu c�n l?i ? `docs/05-trien-khai-va-nghiem-thu.md`.

