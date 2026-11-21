"""Teacher course management pages."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from apps.accounts.permissions import owner_ui_required
from apps.assignments.models import Assignment
from apps.assignments.owner_services import assign_targets_with_schedule
from apps.classes.models import EnglishClass
from apps.content.models import Course, CourseExercise, CourseTag
from apps.content.course_services import (
    add_course_exercise, create_and_attach_course_exercise, create_course, create_course_tag, remove_course_exercise,
    set_course_classes, set_course_tags, update_course,
)
from .owner_teaching_views import build_assign_target_rows
from .owner_views import owner_context, parse_local_dt


def _message(exc):
    return '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Dữ liệu không hợp lệ.'


@never_cache
@owner_ui_required
def courses(request):
    if request.method == 'POST':
        try:
            course = create_course(
                request.user, request.POST.get('name'), request.POST.get('description', ''),
                request.POST.get('category'), request.POST.get('difficulty'),
                is_published=request.POST.get('is_published') == 'on',
            )
            messages.success(request, 'Đã tạo khóa học.')
            return redirect('owner_course_detail', course_id=course.id)
        except (ValidationError, ValueError, TypeError) as exc:
            messages.error(request, _message(exc))
    rows = Course.objects.filter(created_by=request.user).annotate(
        exercise_count=Count('exercises', distinct=True), class_count=Count('english_classes', distinct=True),
    ).order_by('name')
    return render(request, 'owner/courses.html', owner_context(
        'courses', courses=rows, categories=Course._meta.get_field('category').choices,
        difficulties=range(1, 6),
    ))


@never_cache
@owner_ui_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, pk=course_id, created_by=request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'update':
                update_course(request.user, course.id, request.POST.get('name'),
                              request.POST.get('description', ''), request.POST.get('category'),
                              request.POST.get('difficulty'), request.POST.get('is_published') == 'on')
                messages.success(request, 'Đã lưu khóa học.')
            elif action == 'classes':
                set_course_classes(request.user, course.id, request.POST.getlist('class_ids'))
                messages.success(request, 'Đã cập nhật lớp học.')
            elif action == 'course_tags':
                set_course_tags(request.user, course.id, request.POST.getlist('tag_ids'))
                messages.success(request, 'Đã cập nhật chủ đề khóa học.')
            elif action == 'create_new_exercise':
                _ex, exam, version = create_and_attach_course_exercise(
                    request.user, course.id, request.POST.get('title'),
                    request.POST.get('difficulty', '1'), request.POST.getlist('tag_ids'),
                )
                messages.success(request, f'Đã tạo bài tập "{exam.title}". Hãy thêm câu hỏi bên dưới.')
                return redirect(f"{reverse('owner_version_editor', args=[exam.id, version.id])}?course_id={course.id}&new_q=1")
            elif action == 'add_exercise':
                add_course_exercise(request.user, course.id, request.POST.get('assignment_id'),
                                    request.POST.get('difficulty'), request.POST.getlist('tag_ids'))
                messages.success(request, 'Đã thêm bài tập.')
            elif action == 'remove_exercise':
                remove_course_exercise(request.user, course.id, request.POST.get('exercise_id'))
                messages.success(request, 'Đã gỡ bài khỏi khóa học.')
            elif action == 'assign_exercises':
                due_at = parse_local_dt(request.POST.get('due_at'))
                max_attempts = request.POST.get('max_attempts', '1')
                mode = request.POST.get('mode') or None
                assigned = assign_targets_with_schedule(
                    request.user,
                    request.POST.getlist('assignment_ids'),
                    request.POST.getlist('class_ids'),
                    request.POST.getlist('student_ids'),
                    due_at,
                    max_attempts=max_attempts,
                    mode=mode,
                )
                messages.success(request, f'Đã giao {len(assigned)} bài tập theo thời hạn và số lần làm đã chọn.')
            elif action == 'create_tag':
                create_course_tag(request.user, request.POST.get('tag_name'), request.POST.get('tag_kind'))
                messages.success(request, 'Đã tạo chủ đề.')
            else:
                raise ValidationError('Thao tác không hợp lệ.')
        except (ValidationError, ValueError, TypeError, CourseExercise.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        return redirect('owner_course_detail', course_id=course.id)
    classes = EnglishClass.objects.filter(archived_at__isnull=True).order_by('-school_year', 'name')
    selected_classes = set(course.english_classes.values_list('id', flat=True))
    rows = [{'classroom': classroom, 'selected': classroom.id in selected_classes} for classroom in classes]
    tags = list(CourseTag.objects.order_by('kind', 'name'))
    selected_tags = set(course.tags.values_list('id', flat=True))
    exercises = course.exercises.select_related('assignment__version__exam').annotate(
        question_count=Count('assignment__version__questions', distinct=True),
        recipient_count=Count('assignment__recipients', filter=Q(assignment__recipients__state='ASSIGNED'), distinct=True),
        assigned_class_count=Count('assignment__classes', distinct=True),
    ).prefetch_related('tags').order_by('assignment__title')
    assignments = Assignment.objects.filter(version__exam__created_by=request.user).exclude(
        status='CANCELLED',
    ).exclude(pk__in=course.exercises.values('assignment_id')).order_by('-created_at')
    target_data = build_assign_target_rows(course=course)
    return render(request, 'owner/course_detail.html', owner_context(
        'courses', course=course, classes=rows, exercises=exercises, assignments=assignments,
        class_rows=target_data['class_rows'], student_rows=target_data['student_rows'], default_due=target_data['default_due'],
        tags=tags, course_tags=[{'tag': tag, 'selected': tag.id in selected_tags} for tag in tags],
        categories=Course._meta.get_field('category').choices,
        tag_kinds=CourseTag._meta.get_field('kind').choices, difficulties=range(1, 6),
    ))
