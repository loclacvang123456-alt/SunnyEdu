from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.assignments.models import AssignmentRecipient
from apps.classes.models import EnglishMembership
from apps.content.models import Course, CourseExercise, CourseTag, Question

EXERCISE_TYPES = (
    ('SINGLE_CHOICE', 'Trắc nghiệm một đáp án'), ('MULTIPLE_CHOICE', 'Trắc nghiệm nhiều đáp án'),
    ('WORD_ORDER', 'Sắp xếp từ'), ('MATCH_IMAGE', 'Nối tranh với từ'),
    ('SENTENCE_TRANSFORM', 'Biến đổi câu'),
    ('STRESS_CHOICE', 'Chọn trọng âm'), ('TEXT', 'Tự luận'), ('AUDIO', 'Ghi âm'),
)


def _published_courses():
    return Course.objects.filter(is_published=True).annotate(
        exercise_count=Count('exercises', filter=Q(exercises__assignment__status='PUBLISHED'), distinct=True)
    )


def _stars(item):
    item.stars = '★' * item.difficulty + '☆' * (5 - item.difficulty)
    return item


@never_cache
def catalog(request):
    query = request.GET.get('q', '').strip()[:100]
    category = request.GET.get('category', '').strip()
    skill = request.GET.get('skill', '')
    tag = request.GET.get('tag', '')[:100]
    exercise_type = request.GET.get('type', '')
    order = request.GET.get('sort', '')
    courses = _published_courses()
    if query:
        courses = courses.filter(name__icontains=query)
    if category in Course.Category.values:
        courses = courses.filter(category=category)
    else:
        category = ''
    if skill in ('LISTENING', 'SPEAKING', 'READING', 'WRITING'):
        published = CourseExercise.objects.filter(assignment__status='PUBLISHED', tags__code=skill).values('course_id')
        courses = courses.filter(Q(tags__code=skill) | Q(pk__in=published))
    else:
        skill = ''
    if tag:
        published = CourseExercise.objects.filter(assignment__status='PUBLISHED', tags__code=tag).values('course_id')
        courses = courses.filter(Q(tags__code=tag) | Q(pk__in=published))
    if exercise_type in Question.Type.values:
        courses = courses.filter(exercises__assignment__status='PUBLISHED', exercises__assignment__version__questions__type=exercise_type)
    else:
        exercise_type = ''
    if order == 'most':
        courses = courses.order_by('-exercise_count', 'name', 'id')
    elif order == 'least':
        courses = courses.order_by('exercise_count', 'name', 'id')
    else:
        order = ''
        courses = courses.order_by('name', 'id')
    paginator = Paginator(courses.distinct().prefetch_related('tags'), 9)
    page_obj = paginator.get_page(request.GET.get('page'))
    for course in page_obj.object_list:
        _stars(course)
    params = request.GET.copy()
    params.pop('page', None)
    page_query = f'&{params.urlencode()}' if params else ''
    public_tags = CourseExercise.objects.filter(course__is_published=True, assignment__status='PUBLISHED').values('tags__pk')
    tags = CourseTag.objects.filter(Q(courses__is_published=True) | Q(pk__in=public_tags)).exclude(kind='SKILL').distinct().order_by('name')
    return render(request, 'catalog/list.html', {
        'courses': page_obj, 'page_obj': page_obj, 'total_courses': paginator.count, 'page_query': page_query,
        'q': query, 'category': category, 'categories': Course.Category.choices,
        'skill': skill, 'tag': tag, 'tags': tags,
        'type': exercise_type, 'types': EXERCISE_TYPES, 'sort': order,
        'active': 'courses',
    })


@never_cache
def detail(request, course_id):
    course = _stars(get_object_or_404(_published_courses(), pk=course_id))
    now = timezone.now()
    student = request.user if request.user.is_authenticated and request.user.role == 'STUDENT' and request.user.status == 'ACTIVE' else None
    unlocked = bool(student and EnglishMembership.objects.filter(
        student=student, english_class__in=course.english_classes.filter(archived_at__isnull=True), start_at__lte=now, end_at__isnull=True,
    ).exists())
    exercises = []
    if unlocked:
        recipients = AssignmentRecipient.objects.filter(
            student=student, state='ASSIGNED', assignment__status='PUBLISHED',
            assignment_id__in=course.exercises.values('assignment_id'),
        ).select_related('assignment', 'current_attempt').distinct()
        recipients_by_assignment = {r.assignment_id: r for r in recipients}
        for item in course.exercises.filter(assignment_id__in=recipients_by_assignment).select_related('assignment').prefetch_related('tags').order_by('assignment__due_at', 'id'):
            item.recipient = recipients_by_assignment[item.assignment_id]
            item.can_start = item.assignment.opens_at <= now and (item.assignment.late_until is None or now < item.assignment.late_until)
            _stars(item)
            exercises.append(item)
    return render(request, 'catalog/detail.html', {'course': course, 'unlocked': unlocked, 'exercises': exercises, 'student': student, 'active': 'courses'})
