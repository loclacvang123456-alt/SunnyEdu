"""Class, school, membership, and student CSV/XLSX import services."""
import csv
import hashlib
import io
import re
import secrets
import zipfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import AuditEvent, StudentProfile
from apps.accounts.services import ALPHABET, create_student
from apps.content.models import ImportBatch

from .models import EnglishClass, EnglishMembership, School, SchoolClass, SchoolMembership

STUDENT_FIELDS = ("student_ref", "display_name", "school_code", "school_year", "grade", "school_class_name")
YEAR_RE = re.compile(r"^(\d{4})-(\d{4})$")


def validate_school_year(value):
    """Validate YYYY-YYYY+1 school year format."""
    text = (value or "").strip()
    m = YEAR_RE.match(text)
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise ValidationError("Năm học phải có dạng YYYY-YYYY+1 (ví dụ 2026-2027).")
    return text


def generate_english_code():
    """Generate a unique ENG-XXXXXX class code."""
    for _ in range(20):
        code = "ENG-" + "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not EnglishClass.objects.filter(code=code).exists():
            return code
    raise ValidationError("Không tạo được mã lớp duy nhất.")


def generate_school_code(name=""):
    """Tạo mã trường duy nhất từ tên trường (VD: THCS Lê Quý Đôn -> TLQD hoặc SCH-...)"""
    import unicodedata
    clean_name = (name or "").strip()
    nfkd = unicodedata.normalize("NFKD", clean_name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    words = re.findall(r"[A-Za-z0-9]+", ascii_str)
    if words:
        prefix = "".join(w[0] for w in words).upper()[:8]
        if len(prefix) < 3:
            prefix = "".join(words).upper()[:8]
    else:
        prefix = "SCH"

    if not School.objects.filter(code=prefix).exists():
        return prefix
    for i in range(1, 100):
        candidate = f"{prefix}-{i}"[:32]
        if not School.objects.filter(code=candidate).exists():
            return candidate
    for _ in range(30):
        candidate = f"{prefix}-{''.join(secrets.choice(ALPHABET) for _ in range(4))}"[:32]
        if not School.objects.filter(code=candidate).exists():
            return candidate
    raise ValidationError("Không tạo được mã trường duy nhất.")


def create_school(code, name, actor=None):
    c = (code or "").strip()
    n = (name or "").strip()
    if not 1 <= len(c) <= 32 or not 1 <= len(n) <= 160:
        raise ValidationError("Mã trường (1..32) và tên trường (1..160) là bắt buộc.")
    try:
        school = School.objects.create(code=c, name=n)
    except IntegrityError as exc:
        raise ValidationError("Mã trường đã tồn tại.") from exc
    AuditEvent.objects.create(actor=actor, action="school.create", target_type="school", target_id=school.id)
    return school


def archive_school(school_id, actor=None):
    school = School.objects.get(pk=school_id)
    if not school.archived_at:
        school.archived_at = timezone.now()
        school.save(update_fields=["archived_at", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="school.archive", target_type="school", target_id=school.id)
    return school


def create_school_class(school_id, school_year, grade, name, actor=None):
    school = School.objects.get(pk=school_id, archived_at__isnull=True)
    year = validate_school_year(school_year)
    try:
        grade_int = int(grade)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Khối lớp phải từ 1 đến 12.") from exc
    if not 1 <= grade_int <= 12:
        raise ValidationError("Khối lớp phải từ 1 đến 12.")
    clean_name = (name or "").strip()
    if not 1 <= len(clean_name) <= 40:
        raise ValidationError("Tên lớp trường phải có từ 1 đến 40 ký tự.")
    try:
        sc = SchoolClass.objects.create(school=school, school_year=year, grade=grade_int, name=clean_name)
    except IntegrityError as exc:
        raise ValidationError("Lớp trường này đã tồn tại trong năm học.") from exc
    AuditEvent.objects.create(actor=actor, action="school_class.create", target_type="school_class", target_id=sc.id)
    return sc


def archive_school_class(class_id, actor=None):
    sc = SchoolClass.objects.get(pk=class_id)
    if not sc.archived_at:
        sc.archived_at = timezone.now()
        sc.save(update_fields=["archived_at", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="school_class.archive", target_type="school_class", target_id=sc.id)
    return sc


def create_english_class(name, school_year, actor=None):
    clean_name = (name or "").strip()
    if not 1 <= len(clean_name) <= 120:
        raise ValidationError("Tên lớp tiếng Anh phải có từ 1 đến 120 ký tự.")
    year = validate_school_year(school_year)
    ec = EnglishClass.objects.create(code=generate_english_code(), name=clean_name, school_year=year)
    AuditEvent.objects.create(actor=actor, action="english_class.create", target_type="english_class", target_id=ec.id)
    return ec


def archive_english_class(class_id, actor=None):
    ec = EnglishClass.objects.get(pk=class_id)
    if not ec.archived_at:
        ec.archived_at = timezone.now()
        ec.save(update_fields=["archived_at", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="english_class.archive", target_type="english_class", target_id=ec.id)
    return ec


@transaction.atomic
def transfer_school(student, school_class, effective_at, actor=None):
    student = get_user_model().objects.select_for_update().get(pk=student.pk)
    if student.role != "STUDENT" or effective_at > timezone.now():
        raise ValidationError("Học sinh hoặc ngày chuyển lớp không hợp lệ.")
    if school_class.archived_at:
        raise ValidationError("Lớp trường đã lưu trữ.")
    active = SchoolMembership.objects.select_for_update().filter(student=student, start_at__lte=effective_at).filter(end_at__isnull=True).first()
    if active:
        if active.start_at >= effective_at:
            raise ValidationError("Ngày chuyển lớp phải sau ngày bắt đầu lớp hiện tại.")
        active.end_at = effective_at
        active.save(update_fields=["end_at"])
    membership = SchoolMembership.objects.create(student=student, school_class=school_class, start_at=effective_at)
    AuditEvent.objects.create(actor=actor, action="student.school_transfer", target_type="user", target_id=student.pk)
    return membership


@transaction.atomic
def add_english_member(student, english_class, start_at, actor=None):
    student = get_user_model().objects.select_for_update().get(pk=student.pk)
    if student.role != "STUDENT" or student.status != "ACTIVE" or english_class.archived_at or start_at > timezone.now():
        raise ValidationError("Thành viên hoặc ngày tham gia không hợp lệ.")
    try:
        membership = EnglishMembership.objects.create(student=student, english_class=english_class, start_at=start_at)
    except IntegrityError as exc:
        raise ValidationError("Khoảng thời gian tham gia lớp bị chồng lấn.") from exc
    AuditEvent.objects.create(actor=actor, action="english_class.member.add", target_type="english_class", target_id=english_class.id)
    return membership


@transaction.atomic
def leave_english_class(student, english_class, end_at, actor=None):
    get_user_model().objects.select_for_update().get(pk=student.pk)
    member = EnglishMembership.objects.select_for_update().get(student=student, english_class=english_class, end_at__isnull=True)
    if end_at > timezone.now() or end_at <= member.start_at:
        raise ValidationError("Ngày rời lớp không hợp lệ.")
    member.end_at = end_at
    member.save(update_fields=["end_at"])
    AuditEvent.objects.create(actor=actor, action="english_class.member.leave", target_type="english_class", target_id=english_class.id)
    return member


def generate_student_import_template(fmt="csv"):
    """Tạo tệp mẫu CSV hoặc XLSX chuẩn cho việc nhập danh sách học sinh."""
    from django.conf import settings
    if fmt == "xlsx":
        xlsx_file = settings.BASE_DIR / "docs/examples/students.xlsx"
        if xlsx_file.exists():
            return xlsx_file.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "mau_nhap_hoc_sinh.xlsx"

        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        wb = Workbook()
        ws = wb.active
        ws.title = "students"
        ws.views.sheetView[0].showGridLines = True

        headers = list(STUDENT_FIELDS)
        sample_data = [
            ["HS2026-0001", "Nguyễn Văn An", "THCS-LQD", "2026-2027", "6", "6A1"],
            ["HS2026-0002", "Trần Thị Mai", "", "", "", ""],
            ["HS2026-0003", "Lê Hoàng Nam", "THCS-LQD", "2026-2027", "6", "6A1"],
        ]
        ws.append(headers)
        for row in sample_data:
            ws.append(row)
        for _ in range(6):
            ws.append(["", "", "", "", "", ""])

        thin = Side(border_style="thin", color="000000")
        cell_border = Border(top=thin, left=thin, right=thin, bottom=thin)
        header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True)

        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=len(headers)):
            for cell in row:
                cell.border = cell_border

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 4, 16)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "mau_nhap_hoc_sinh.xlsx"

    csv_file = settings.BASE_DIR / "docs/examples/students.csv"
    if csv_file.exists():
        return csv_file.read_bytes(), "text/csv; charset=utf-8", "mau_nhap_hoc_sinh.csv"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(STUDENT_FIELDS))
    sample_data = [
        ["HS2026-0001", "Nguyễn Văn An", "THCS-LQD", "2026-2027", "6", "6A1"],
        ["HS2026-0002", "Trần Thị Mai", "", "", "", ""],
        ["HS2026-0003", "Lê Hoàng Nam", "THCS-LQD", "2026-2027", "6", "6A1"],
    ]
    for row in sample_data:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "mau_nhap_hoc_sinh.csv"


def parse_students(data, filename):
    """Parse and validate CSV/XLSX student import rows without modifying the DB."""
    if len(data) > 2 * 1024 * 1024:
        raise ValidationError("Tệp vượt quá 2 MiB.")
    if filename.lower().endswith(".csv"):
        try:
            reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
            if not reader.fieldnames or reader.fieldnames[:len(STUDENT_FIELDS)] != list(STUDENT_FIELDS):
                raise ValidationError("Cột CSV không khớp mẫu students.")
            rows = [r for r in reader if any((r.get(k) or "").strip() for k in STUDENT_FIELDS)]
        except UnicodeDecodeError as exc:
            raise ValidationError("CSV phải dùng UTF-8.") from exc
    elif filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = zf.infolist()
                if len(members) > 100 or sum(m.file_size for m in members) > 10 * 1024 * 1024 or any("vbaProject" in m.filename or "externalLinks/" in m.filename for m in members):
                    raise ValidationError("XLSX không an toàn hoặc quá lớn.")
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
            if wb.sheetnames != ["students"]:
                raise ValidationError("XLSX phải có một sheet students.")
            values = wb["students"].iter_rows()
            first = next(values, None)
            if not first or [c.value for c in first[:len(STUDENT_FIELDS)]] != list(STUDENT_FIELDS):
                raise ValidationError("Cột XLSX không khớp mẫu students.")
            rows = []
            for cells in values:
                cell_list = list(cells)
                if any(getattr(c, "data_type", None) == "f" for c in cell_list):
                    raise ValidationError("Không nhận công thức XLSX.")
                core_cells = (cell_list + [None] * max(0, len(STUDENT_FIELDS) - len(cell_list)))[:len(STUDENT_FIELDS)]
                if all(c is None or c.value is None or str(c.value).strip() == "" for c in core_cells):
                    continue
                rows.append({k: "" if (c is None or c.value is None) else str(c.value) for k, c in zip(STUDENT_FIELDS, core_cells)})
            wb.close()
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise ValidationError("XLSX không hợp lệ.") from exc
    else:
        raise ValidationError("Chỉ nhận CSV hoặc XLSX.")

    if not 1 <= len(rows) <= 1000:
        raise ValidationError("Danh sách cần từ 1 đến 1.000 dòng.")

    existing_refs = set(StudentProfile.objects.values_list("student_ref", flat=True))
    seen = set()
    parsed = []
    for idx, raw in enumerate(rows, start=2):
        row = {k: (raw.get(k) or "").strip() for k in STUDENT_FIELDS}
        row_errors = []
        ref = row["student_ref"]
        name = row["display_name"]
        if not 1 <= len(ref) <= 32:
            row_errors.append("student_ref phải 1..32 ký tự")
        elif ref in seen:
            row_errors.append("student_ref bị trùng trong tệp")
        seen.add(ref)
        if not 1 <= len(name) <= 120:
            row_errors.append("display_name phải 1..120 ký tự")

        school_vals = [row["school_code"], row["school_year"], row["grade"], row["school_class_name"]]
        school_class_id = None
        if any(school_vals):
            if not all(school_vals):
                row_errors.append("Phải điền đủ 4 cột trường/năm/khối/lớp hoặc để trống cả 4")
            else:
                try:
                    year = validate_school_year(row["school_year"])
                    grade_int = int(row["grade"])
                    sc = SchoolClass.objects.filter(
                        school__code=row["school_code"],
                        school__archived_at__isnull=True,
                        school_year=year,
                        grade=grade_int,
                        name=row["school_class_name"],
                        archived_at__isnull=True,
                    ).first()
                    if not sc:
                        row_errors.append("Chưa có trường hoặc lớp trường tương ứng, hãy tạo trước")
                    else:
                        school_class_id = str(sc.id)
                except (ValueError, ValidationError):
                    row_errors.append("Năm học hoặc khối không hợp lệ")

        parsed.append({
            **row,
            "line": idx,
            "exists_in_db": ref in existing_refs,
            "school_class_id": school_class_id,
            "errors": row_errors,
        })
    return parsed


def preview_student_import(owner, data, filename):
    rows = parse_students(data, filename)
    return ImportBatch.objects.create(
        kind="STUDENTS",
        owner=owner,
        payload_json=rows,
        source_digest=hashlib.sha256(data).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=24),
    )


@transaction.atomic
def commit_student_import(owner, batch_id, expected_digest, english_class_id=None):
    batch = ImportBatch.objects.select_for_update().get(pk=batch_id, owner=owner, kind="STUDENTS")
    if batch.source_digest != expected_digest:
        raise ValidationError("Nội dung tệp đã thay đổi.")
    if batch.status == ImportBatch.Status.COMMITTED:
        return {"committed": True, "target_id": str(batch.committed_target_id) if batch.committed_target_id else None, "created": 0, "joined": 0}
    if batch.status != ImportBatch.Status.PREVIEW or batch.expires_at <= timezone.now():
        raise ValidationError("Bản xem trước đã hết hạn.")
    if any(r.get("errors") for r in batch.payload_json):
        raise ValidationError("Tệp còn dòng lỗi, không thể nhập.")

    english_class = None
    if english_class_id:
        english_class = EnglishClass.objects.select_for_update().get(pk=english_class_id, archived_at__isnull=True)

    now = timezone.now()
    created, joined = 0, 0
    for row in batch.payload_json:
        profile = StudentProfile.objects.select_related("user").filter(student_ref=row["student_ref"]).first()
        if profile:
            student = profile.user
        else:
            student = create_student(row["display_name"], row["student_ref"], actor=owner)
            created += 1
            if row.get("school_class_id"):
                sc = SchoolClass.objects.get(pk=row["school_class_id"])
                SchoolMembership.objects.create(student=student, school_class=sc, start_at=now)
        if english_class and student.status == "ACTIVE":
            if not EnglishMembership.objects.filter(student=student, english_class=english_class, end_at__isnull=True).exists():
                EnglishMembership.objects.create(student=student, english_class=english_class, start_at=now)
                joined += 1

    batch.status = ImportBatch.Status.COMMITTED
    batch.committed_target_id = english_class.id if english_class else None
    batch.save(update_fields=["status", "committed_target_id", "updated_at"])
    AuditEvent.objects.create(actor=owner, action="students.import.commit", target_type="import_batch", target_id=batch.id, metadata={"created": created, "joined": joined})
    return {"committed": True, "target_id": str(batch.committed_target_id) if batch.committed_target_id else None, "created": created, "joined": joined}
