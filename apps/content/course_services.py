"""Course administration. Assignment access still uses its recipient list."""
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import AuditEvent
from apps.assignments.models import Assignment
from apps.classes.models import EnglishClass
from .models import Course, CourseExercise, CourseTag


def _owner(actor):
    if not actor or not actor.is_authenticated or actor.role != 'OWNER' or actor.status != 'ACTIVE':
        raise PermissionDenied


def _values(name, description, category, difficulty, is_published):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise ValidationError('Tên khóa học phải có từ 1 đến 200 ký tự.')
    if not isinstance(description, str) or len(description.strip()) > 300:
        raise ValidationError('Mô tả khóa học tối đa 300 ký tự.')
    if category not in Course.Category.values:
        raise ValidationError('Loại khóa học không hợp lệ.')
    if isinstance(difficulty, bool) or str(difficulty) not in ('1', '2', '3', '4', '5'):
        raise ValidationError('Độ khó phải từ 1 đến 5 sao.')
    if type(is_published) is not bool:
        raise ValidationError('Trạng thái hiển thị không hợp lệ.')
    return name.strip(), description.strip(), category, int(difficulty), is_published


def _ids(values):
    if not isinstance(values, (list, tuple)):
        raise ValidationError('Danh sách không hợp lệ.')
    try:
        return {uuid.UUID(str(value)) for value in values}
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError('Mã trong danh sách không hợp lệ.') from exc


@transaction.atomic
def create_course(actor, name, description, category, difficulty, is_published=False):
    _owner(actor)
    name, description, category, difficulty, is_published = _values(name, description, category, difficulty, is_published)
    if Course.objects.filter(created_by=actor, name=name).exists():
        raise ValidationError('Tên khóa học đã tồn tại.')
    try:
        with transaction.atomic():
            course = Course.objects.create(created_by=actor, name=name, description=description, category=category, difficulty=difficulty, is_published=is_published)
    except IntegrityError as exc:
        raise ValidationError('Tên khóa học đã tồn tại.') from exc
    AuditEvent.objects.create(actor=actor, action='course.create', target_type='course', target_id=course.id)
    return course


@transaction.atomic
def update_course(actor, course_id, name, description, category, difficulty, is_published):
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    name, description, category, difficulty, is_published = _values(name, description, category, difficulty, is_published)
    if Course.objects.filter(created_by=actor, name=name).exclude(pk=course.pk).exists():
        raise ValidationError('Tên khóa học đã tồn tại.')
    course.name, course.description, course.category, course.difficulty, course.is_published = name, description, category, difficulty, is_published
    try:
        with transaction.atomic():
            course.save()
    except IntegrityError as exc:
        raise ValidationError('Tên khóa học đã tồn tại.') from exc
    AuditEvent.objects.create(actor=actor, action='course.update', target_type='course', target_id=course.id)
    return course


@transaction.atomic
def set_course_classes(actor, course_id, class_ids):
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    ids = _ids(class_ids)
    classes = list(EnglishClass.objects.filter(pk__in=ids, archived_at__isnull=True))
    if len(classes) != len(ids):
        raise ValidationError('Có lớp không tồn tại hoặc đã lưu trữ.')
    course.english_classes.set(classes)
    for ce in course.exercises.select_related('assignment').all():
        _sync_assignment_to_classes(ce.assignment, classes)
    AuditEvent.objects.create(actor=actor, action='course.classes', target_type='course', target_id=course.id, metadata={'count': len(classes)})
    return course


def _sync_assignment_to_classes(assignment, classes):
    if not classes or assignment.status != 'PUBLISHED':
        return
    from django.contrib.auth import get_user_model
    from apps.assignments.models import AssignmentClass, AssignmentRecipient, RecipientEnglishClass
    from apps.assignments.owner_services import _snapshot_membership
    from apps.classes.models import EnglishMembership

    class_ids = [c.id for c in classes]
    for c in classes:
        AssignmentClass.objects.get_or_create(assignment=assignment, english_class=c)
    student_ids = list(
        EnglishMembership.objects.filter(
            english_class_id__in=class_ids,
            end_at__isnull=True,
            student__role='STUDENT',
            student__status='ACTIVE',
        ).values_list('student_id', flat=True).distinct()
    )
    if not student_ids:
        return
    User = get_user_model()
    for student in User.objects.filter(pk__in=student_ids).order_by('id'):
        school_data, english_classes = _snapshot_membership(student, target_classes=class_ids)
        recipient, _ = AssignmentRecipient.objects.get_or_create(
            assignment=assignment, student=student, defaults=school_data,
        )
        for ec in english_classes:
            RecipientEnglishClass.objects.get_or_create(
                recipient=recipient,
                english_class=ec,
                defaults={'class_name_snapshot': ec.name, 'school_year_snapshot': ec.school_year},
            )


@transaction.atomic
def create_and_attach_course_exercise(actor, course_id, title, difficulty, tag_ids=None):
    """Create a new Exam, published ExamVersion, and PRACTICE Assignment attached to the course."""
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    clean_title = (title or '').strip() if isinstance(title, str) else ''
    if not 1 <= len(clean_title) <= 200:
        raise ValidationError('Tên bài tập phải có từ 1 đến 200 ký tự.')
    if isinstance(difficulty, bool) or str(difficulty) not in ('1', '2', '3', '4', '5'):
        raise ValidationError('Độ khó phải từ 1 đến 5 sao.')
    from datetime import timedelta
    from django.utils import timezone
    from apps.assignments.owner_services import _generate_assignment_code
    from .models import Exam, ExamVersion

    now = timezone.now()
    exam = Exam.objects.create(title=clean_title, created_by=actor)
    version = ExamVersion.objects.create(exam=exam, number=1, status=ExamVersion.Status.DRAFT)
    assignment = Assignment.objects.create(
        version=version,
        title=clean_title,
        code=_generate_assignment_code(),
        status='DRAFT',
        mode='PRACTICE',
        opens_at=now - timedelta(hours=1),
        due_at=now + timedelta(days=365),
        late_until=now + timedelta(days=372),
    )
    classes = list(course.english_classes.filter(archived_at__isnull=True))
    from apps.assignments.models import AssignmentClass
    AssignmentClass.objects.bulk_create([AssignmentClass(assignment=assignment, english_class=c) for c in classes])
    exercise = add_course_exercise(actor, course_id, assignment.id, difficulty, tag_ids or ())
    return exercise, exam, version


@transaction.atomic
def set_course_tags(actor, course_id, tag_ids):
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    ids = _ids(tag_ids)
    tags = list(CourseTag.objects.filter(pk__in=ids))
    if len(tags) != len(ids):
        raise ValidationError('Có nhãn không tồn tại.')
    course.tags.set(tags)
    AuditEvent.objects.create(actor=actor, action='course.tags', target_type='course', target_id=course.id, metadata={'count': len(tags)})
    return course


@transaction.atomic
def create_course_tag(actor, name, kind):
    _owner(actor)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or kind not in CourseTag.Kind.values:
        raise ValidationError('Tên hoặc loại nhãn không hợp lệ.')
    clean = name.strip()
    if CourseTag.objects.filter(kind=kind, name__iexact=clean).exists():
        raise ValidationError('Nhãn này đã tồn tại.')
    tag = CourseTag.objects.create(code='CUSTOM-' + uuid.uuid4().hex, name=clean, kind=kind)
    AuditEvent.objects.create(actor=actor, action='course.tag.create', target_type='course_tag', target_id=tag.id)
    return tag


@transaction.atomic
def add_course_exercise(actor, course_id, assignment_id, difficulty, tag_ids):
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    if isinstance(difficulty, bool) or str(difficulty) not in ('1', '2', '3', '4', '5'):
        raise ValidationError('Độ khó phải từ 1 đến 5 sao.')
    assignment = Assignment.objects.filter(pk=assignment_id, version__exam__created_by=actor, status__in=['DRAFT', 'PUBLISHED']).first()
    if not assignment:
        raise ValidationError('Bài giao không tồn tại hoặc đã hủy.')
    ids = _ids(tag_ids)
    tags = list(CourseTag.objects.filter(pk__in=ids))
    if len(tags) != len(ids):
        raise ValidationError('Có nhãn không tồn tại.')
    exercise, _ = CourseExercise.objects.update_or_create(course=course, assignment=assignment, defaults={'difficulty': int(difficulty)})
    exercise.tags.set(tags)
    AuditEvent.objects.create(actor=actor, action='course.exercise.save', target_type='course', target_id=course.id, metadata={'assignment_id': str(assignment.id)})
    return exercise


@transaction.atomic
def remove_course_exercise(actor, course_id, exercise_id):
    _owner(actor)
    course = Course.objects.select_for_update().get(pk=course_id, created_by=actor)
    exercise = CourseExercise.objects.get(pk=exercise_id, course=course)
    exercise.delete()
    AuditEvent.objects.create(actor=actor, action='course.exercise.remove', target_type='course', target_id=course.id)
    return course
