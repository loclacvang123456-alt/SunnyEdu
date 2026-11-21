import json
import re
from decimal import Decimal
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


def _get_student_leaderboards(current_student=None):
    from apps.accounts.models import User
    from apps.assignments.models import Attempt
    from apps.classes.models import EnglishMembership
    from apps.content.models import Course
    from apps.grading.models import GradeRelease

    students = list(User.objects.filter(role=User.Role.STUDENT, status=User.Status.ACTIVE).only('id', 'username', 'display_name'))
    student_ids = [s.id for s in students]
    if not student_ids:
        empty_res = {'top10': [], 'full_list': [], 'total_students': 0, 'my_entry': None, 'is_in_top10': False}
        return {'hours': empty_res, 'score': empty_res, 'courses': empty_res}

    # 1. Study Hours
    student_seconds = {sid: 0 for sid in student_ids}
    attempts = Attempt.objects.filter(recipient__student_id__in=student_ids).values('recipient__student_id', 'started_at', 'submitted_at', 'status')
    for att in attempts:
        sid = att['recipient__student_id']
        s_at = att['started_at']
        sub_at = att['submitted_at']
        status = att['status']
        if sub_at and s_at:
            sec = max(120, min((sub_at - s_at).total_seconds(), 9000))
        elif status == 'IN_PROGRESS':
            sec = 300
        else:
            sec = 180
        student_seconds[sid] = student_seconds.get(sid, 0) + int(sec)

    # Count one latest published result per assigned exercise, even after retakes or republication.
    student_scores = {sid: [] for sid in student_ids}
    releases = GradeRelease.objects.filter(
        attempt__recipient__student_id__in=student_ids,
    ).exclude(attempt__status='VOID').order_by(
        'attempt__recipient_id', '-attempt__attempt_no', '-number',
    ).values('attempt__recipient_id', 'attempt__recipient__student_id', 'total_points', 'max_points')
    seen_recipients = set()
    for release in releases:
        recipient = release['attempt__recipient_id']
        if recipient in seen_recipients:
            continue
        seen_recipients.add(recipient)
        maximum = float(release['max_points'] or 0)
        if maximum > 0:
            student_scores[release['attempt__recipient__student_id']].append(
                float(release['total_points'] or 0) / maximum * 10
            )

    # 3. Courses Count
    memberships = EnglishMembership.objects.filter(student_id__in=student_ids, end_at__isnull=True).values('student_id', 'english_class_id')
    class_students = {}
    for m in memberships:
        class_students.setdefault(m['english_class_id'], set()).add(m['student_id'])

    course_classes = Course.objects.filter(is_published=True).values('id', 'english_classes__id')
    student_courses_set = {sid: set() for sid in student_ids}
    for cc in course_classes:
        cid = cc['id']
        eclass_id = cc['english_classes__id']
        if eclass_id in class_students:
            for sid in class_students[eclass_id]:
                student_courses_set[sid].add(cid)

    direct_course_recipients = Course.objects.filter(is_published=True, exercises__assignment__recipients__student_id__in=student_ids).values('id', 'exercises__assignment__recipients__student_id')
    for dcr in direct_course_recipients:
        cid = dcr['id']
        sid = dcr['exercises__assignment__recipients__student_id']
        if sid in student_courses_set:
            student_courses_set[sid].add(cid)

    def _build_ranking(metric_key, key_fn, format_fn):
        raw = []
        for s in students:
            val = key_fn(s.id)
            if val is None:
                continue
            is_me = bool(current_student and s.id == current_student.id)
            raw.append({
                'student_id': str(s.id),
                'name': s.display_name or s.username,
                'username': s.username,
                'avatar_letter': (s.display_name or s.username or 'H')[:1].upper(),
                'metric_key': metric_key,
                'raw_value': val,
                'display_value': format_fn(val),
                'is_me': is_me,
            })
        raw.sort(key=lambda item: (-item['raw_value'], item['name']))
        for idx, item in enumerate(raw, start=1):
            item['rank'] = idx
            if idx == 1:
                item['medal'] = 'gold'
            elif idx == 2:
                item['medal'] = 'silver'
            elif idx == 3:
                item['medal'] = 'bronze'
            else:
                item['medal'] = ''

        top10 = raw[:10]
        full_list = raw[:50]
        my_entry = next((item for item in raw if item['is_me']), None)
        is_in_top10 = bool(my_entry and my_entry['rank'] <= 10)

        return {
            'top10': top10,
            'full_list': full_list,
            'total_students': len(raw),
            'my_entry': my_entry,
            'is_in_top10': is_in_top10,
        }

    hours_ranking = _build_ranking(
        'hours',
        lambda sid: round(student_seconds.get(sid, 0) / 3600, 1),
        lambda v: f"{v} giờ" if v >= 1 else (f"{round(v * 60)} phút" if v > 0 else "0 giờ")
    )
    score_ranking = _build_ranking(
        'score',
        lambda sid: sum(student_scores[sid]) / len(student_scores[sid]) if len(student_scores[sid]) >= 5 else None,
        lambda v: f"{v:.1f} điểm"
    )
    courses_ranking = _build_ranking(
        'courses',
        lambda sid: len(student_courses_set.get(sid, set())),
        lambda v: f"{v} khóa"
    )

    return {
        'hours': hours_ranking,
        'score': score_ranking,
        'courses': courses_ranking,
    }


@never_cache
def home(request):
    if request.user.is_authenticated and request.user.role == 'STUDENT':
        return redirect('student_dashboard')
    from apps.accounts.models import User
    from apps.assignments.models import Assignment
    from apps.content.models import Course
    from django.db.models import Count, Q
    student_count = User.objects.filter(role=User.Role.STUDENT, status=User.Status.ACTIVE).count()
    course_count = Course.objects.filter(is_published=True).count()
    exercise_count = Assignment.objects.filter(status='PUBLISHED').values('version_id').distinct().count()
    featured_courses = list(Course.objects.filter(is_published=True).annotate(
        exercise_count=Count('exercises', filter=Q(exercises__assignment__status='PUBLISHED'), distinct=True)
    ).order_by('name')[:8])
    for course in featured_courses:
        course.stars = '★' * course.difficulty + '☆' * (5 - course.difficulty)
    leaderboards = _get_student_leaderboards()
    podiums = []
    for key, title in [('hours', 'Giờ học'), ('score', 'Điểm trung bình'), ('courses', 'Khóa học')]:
        entries = [entry for entry in leaderboards[key]['top10'] if key == 'score' or entry['raw_value'] > 0][:3]
        podiums.append({'key': key, 'title': title, 'places': [
            {'rank': rank, 'entry': entries[rank - 1] if len(entries) >= rank else None}
            for rank in (2, 1, 3)
        ]})
    return render(request, 'landing.html', {
        'student_count': student_count,
        'course_count': course_count,
        'exercise_count': exercise_count,
        'featured_courses': featured_courses,
        'podiums': podiums,
    })


@never_cache
def student_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.role != 'STUDENT':
        return HttpResponseForbidden()

    from datetime import timedelta
    from django.db.models import Q
    from apps.assignments.models import AssignmentRecipient, Attempt
    from apps.classes.models import EnglishClass
    from apps.content.models import Course

    now = timezone.now()
    today = timezone.localtime(now).date()
    start_date = today - timedelta(days=29)

    recipients = AssignmentRecipient.objects.filter(
        student=request.user,
        state='ASSIGNED',
        assignment__status='PUBLISHED'
    ).filter(
        Q(assignment__course_exercises__isnull=True) | Q(
            assignment__course_exercises__course__is_published=True,
            assignment__course_exercises__course__english_classes__archived_at__isnull=True,
            assignment__course_exercises__course__english_classes__memberships__student=request.user,
            assignment__course_exercises__course__english_classes__memberships__start_at__lte=now,
            assignment__course_exercises__course__english_classes__memberships__end_at__isnull=True,
        )
    ).select_related('assignment', 'current_attempt').prefetch_related(
        'assignment__classes',
        'assignment__course_exercises__course',
    ).distinct().order_by('assignment__due_at')

    assignments = []
    for r in recipients:
        a = r.assignment
        if r.current_attempt and r.current_attempt.status in ('SUBMITTED', 'GRADED'):
            status_code = 'completed'
            status_label = 'Đã nộp'
            pill_class = 'pill-success'
            action_label = 'Xem kết quả'
            url = reverse('student_assignment_result', args=[a.id])
        elif r.current_attempt and r.current_attempt.status == 'IN_PROGRESS':
            status_code = 'in_progress'
            status_label = 'Đang làm'
            pill_class = 'pill-warning'
            action_label = 'Làm tiếp'
            url = reverse('student_assignment', args=[a.id])
        else:
            status_code = 'unattempted'
            status_label = 'Chưa làm'
            pill_class = ''
            action_label = 'Bắt đầu làm bài'
            url = reverse('student_assignment', args=[a.id])

        class_objs = list(a.classes.all())
        class_ids = ','.join(str(c.id) for c in class_objs)
        class_names = [c.name for c in class_objs]

        course_objs = [ce.course for ce in a.course_exercises.all() if ce.course and ce.course.is_published]
        course_ids = ','.join(str(c.id) for c in course_objs)
        course_names = [c.name for c in course_objs]

        created_ts = a.opens_at.timestamp() if a.opens_at else (a.created_at.timestamp() if a.created_at else 0)
        due_ts = a.due_at.timestamp() if a.due_at else 0
        is_due_soon = bool(a.due_at and (a.due_at - now) <= timedelta(days=1))

        assignments.append({
            'id': str(a.id),
            'title': a.title,
            'status_code': status_code,
            'status_label': status_label,
            'pill_class': pill_class,
            'action_label': action_label,
            'due_at': a.due_at,
            'due_timestamp': due_ts,
            'created_timestamp': created_ts,
            'late_until': a.late_until,
            'is_late': bool(a.due_at and now > a.due_at),
            'is_due_soon': is_due_soon,
            'url': url,
            'class_ids': class_ids,
            'class_names': class_names,
            'course_ids': course_ids,
            'course_names': course_names,
        })

    # Available classes and courses for filters
    student_classes = list(EnglishClass.objects.filter(
        memberships__student=request.user,
        memberships__end_at__isnull=True,
    ).distinct().order_by('name'))

    assigned_ids = [r.assignment_id for r in recipients]
    student_courses = list(Course.objects.filter(
        is_published=True,
        exercises__assignment__in=assigned_ids,
    ).distinct().order_by('name'))

    # Study Stats & 30-day heatmap
    attempts = Attempt.objects.filter(
        recipient__student=request.user,
        started_at__date__gte=start_date - timedelta(days=2),
    ).prefetch_related('responses')

    daily_seconds = {start_date + timedelta(days=i): 0 for i in range(30)}
    daily_count = {start_date + timedelta(days=i): 0 for i in range(30)}

    for att in attempts:
        t_start = timezone.localtime(att.started_at)
        att_date = t_start.date()
        if att_date not in daily_seconds:
            continue
        daily_count[att_date] += 1
        if att.submitted_at:
            t_sub = timezone.localtime(att.submitted_at)
            sec = max(120, min((t_sub - t_start).total_seconds(), 9000))
        elif att.status == 'IN_PROGRESS':
            responses = list(att.responses.all())
            if responses:
                latest = max(timezone.localtime(resp.updated_at) for resp in responses)
                sec = max(180, min((latest - t_start).total_seconds(), 5400))
            else:
                sec = 300
        else:
            sec = 300
        daily_seconds[att_date] += int(sec)

    heatmap_days = []
    total_seconds = sum(daily_seconds.values())
    active_days_count = 0
    weekday_vn = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']

    for d in sorted(daily_seconds.keys()):
        sec = daily_seconds[d]
        hours = round(sec / 3600, 1)
        mins = round(sec / 60)
        cnt = daily_count[d]
        if sec > 0:
            active_days_count += 1

        if sec == 0:
            level = 0
        elif sec < 1800:
            level = 1
        elif sec < 3600:
            level = 2
        elif sec < 7200:
            level = 3
        else:
            level = 4

        w_name = weekday_vn[d.weekday()]
        if sec > 0:
            if mins >= 60:
                time_str = f"{hours} giờ ({mins} phút)"
            else:
                time_str = f"{mins} phút"
            tooltip = f"{w_name}, {d.strftime('%d/%m/%Y')}: {time_str} làm bài ({cnt} bài)"
        else:
            tooltip = f"{w_name}, {d.strftime('%d/%m/%Y')}: Chưa làm bài"

        heatmap_days.append({
            'date': d.isoformat(),
            'day_number': d.day,
            'date_str': d.strftime('%d/%m'),
            'weekday': d.weekday(),
            'hours': hours,
            'minutes': mins,
            'level': level,
            'tooltip': tooltip,
            'attempts_count': cnt,
            'is_today': (d == today),
        })

    # Group into weeks for calendar grid (Monday to Sunday)
    calendar_weeks = []
    first_weekday = heatmap_days[0]['weekday'] # 0: Mon, 6: Sun
    current_week = [None] * first_weekday

    for day in heatmap_days:
        current_week.append(day)
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []
    if current_week:
        while len(current_week) < 7:
            current_week.append(None)
        calendar_weeks.append(current_week)

    total_hours = round(total_seconds / 3600, 1)
    avg_hours_per_day = round(total_hours / 30, 2)
    completed_count = sum(1 for item in assignments if item['status_code'] == 'completed')

    study_stats = {
        'total_hours': total_hours,
        'avg_hours_per_day': avg_hours_per_day,
        'active_days_count': active_days_count,
        'completed_count': completed_count,
        'calendar_weeks': calendar_weeks,
        'start_date_str': start_date.strftime('%d/%m/%Y'),
        'today_str': today.strftime('%d/%m/%Y'),
    }

    leaderboards = _get_student_leaderboards(request.user)
    leaderboards_json = json.dumps({
        'hours': leaderboards['hours']['full_list'],
        'score': leaderboards['score']['full_list'],
        'courses': leaderboards['courses']['full_list'],
    })

    return render(request, 'student/dashboard.html', {
        'assignments': assignments,
        'student_classes': student_classes,
        'student_courses': student_courses,
        'study_stats': study_stats,
        'leaderboards': leaderboards,
        'leaderboards_json': leaderboards_json,
        'active': 'home',
    })


@never_cache
def student_assignment(request, assignment_id):
    from apps.assignments.models import AssignmentRecipient
    from apps.assignments.services import course_access_allowed, start_attempt
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.role != 'STUDENT':
        return HttpResponseForbidden()
    recipient = get_object_or_404(AssignmentRecipient.objects.select_related('assignment', 'current_attempt'), assignment_id=assignment_id, student=request.user, state='ASSIGNED', assignment__status='PUBLISHED')
    if not course_access_allowed(assignment_id, request.user):
        return HttpResponseForbidden('Khóa học chưa được mở cho lớp của em.')
    if request.method == 'POST' and not recipient.current_attempt_id:
        from django.core.exceptions import PermissionDenied
        try:
            start_attempt(recipient.id, request.user)
        except PermissionDenied:
            return HttpResponseForbidden('Bài này chưa mở hoặc đã đóng.')
        return redirect('student_assignment', assignment_id=assignment_id)
    if not recipient.current_attempt_id:
        return render(request, 'student/assignment_start.html', {'assignment': recipient.assignment})
    return render(request, 'student/assignment.html', {'assignment': recipient.assignment, 'attempt': recipient.current_attempt})


@never_cache
def student_assignment_result(request, assignment_id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.role != 'STUDENT':
        return HttpResponseForbidden()

    from apps.assignments.models import AssignmentRecipient
    from apps.assignments.services import course_access_allowed
    from apps.assignments.sentence_transform_service import grade_sentence_transform

    recipient = get_object_or_404(
        AssignmentRecipient.objects.select_related('assignment__version', 'current_attempt'),
        assignment_id=assignment_id,
        student=request.user,
        state='ASSIGNED',
        assignment__status='PUBLISHED'
    )
    if not course_access_allowed(assignment_id, request.user):
        return HttpResponseForbidden('Khóa học chưa được mở cho lớp của em.')

    attempt = recipient.current_attempt
    if not attempt or attempt.status not in ('SUBMITTED', 'GRADED'):
        return redirect('student_assignment', assignment_id=assignment_id)

    assignment = recipient.assignment
    version = assignment.version
    show_answer_details = assignment.mode != 'EXAM' or bool(assignment.answers_released_at)
    questions = list(version.questions.order_by('position', 'id').prefetch_related(
        'options', 'answer_keys', 'match_images__answer_key', 'match_images__image_asset'
    ))
    responses = {
        r.question_id: r
        for r in attempt.responses.select_related('audio_asset', 'grade').prefetch_related('options').all()
    }

    question_results = []
    total_earned = Decimal('0.00')
    total_max = Decimal('0.00')
    correct_count = 0

    for idx, q in enumerate(questions, start=1):
        resp = responses.get(q.id)
        max_pts = q.max_points
        total_max += max_pts
        grade = getattr(resp, 'grade', None) if resp else None
        points = grade.points if grade else Decimal('0.00')
        total_earned += points

        is_correct = bool(points == max_pts and max_pts > 0)
        is_partial = bool(Decimal('0.00') < points < max_pts)
        is_wrong = bool(points == Decimal('0.00'))

        if is_correct:
            correct_count += 1

        q_data = {
            'number': idx,
            'question': q,
            'type': q.type,
            'prompt': re.sub(r'/[^/\r\n]+/', '', q.prompt).strip() if q.type == 'STRESS_CHOICE' else q.prompt,
            'points': points,
            'max_points': max_pts,
            'is_correct': is_correct,
            'is_partial': is_partial,
            'is_wrong': is_wrong,
            'has_response': bool(resp),
            'explanation': q.explanation,
        }

        if q.type == 'SENTENCE_TRANSFORM':
            opts = list(q.options.all())
            standard_answer = opts[0].content if opts else (q.explanation or '')
            student_answer = resp.text_answer if resp else ''
            feedback_data = None
            if grade and grade.feedback:
                try:
                    feedback_data = json.loads(grade.feedback)
                except Exception:
                    feedback_data = None
            if not feedback_data:
                feedback_data = grade_sentence_transform(student_answer, standard_answer, max_pts)

            q_data['student_answer'] = student_answer
            q_data['standard_answer'] = standard_answer
            q_data['diff_tokens'] = feedback_data.get('diff_tokens', [])
            q_data['feedback_message'] = feedback_data.get('feedback', '')
            q_data['minor_errors'] = feedback_data.get('minor_errors', 0)
            q_data['major_errors'] = feedback_data.get('major_errors', 0)

        elif q.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'STRESS_CHOICE'):
            selected_ids = {o.id for o in resp.options.all()} if resp else set()
            correct_ids = {k.option_id for k in q.answer_keys.all()}
            options_info = []
            for opt in q.options.all():
                options_info.append({
                    'content': opt.content,
                    'is_selected': opt.id in selected_ids,
                    'is_correct': opt.id in correct_ids,
                })
            q_data['options_info'] = options_info

        elif q.type == 'WORD_ORDER':
            opts = list(q.options.all())
            by_id = {str(opt.id): opt.content for opt in opts}
            selected_words = [by_id.get(oid, '') for oid in (resp.ordered_option_ids if resp else [])]
            correct_words = [opt.content for opt in opts]
            q_data['student_sentence'] = ' '.join(selected_words)
            q_data['correct_sentence'] = ' '.join(correct_words)

        elif q.type == 'MATCH_IMAGE':
            images = list(q.match_images.select_related('answer_key__word').all())
            image_map = {str(img.id): img for img in images}
            words = {str(w.id): w.text for w in q.match_words.all()}
            pairs = []
            if resp:
                for p in resp.match_pairs:
                    img_id = p.get('image_id')
                    word_id = p.get('word_id')
                    img = image_map.get(img_id)
                    corr_word_id = str(img.answer_key.word_id) if img and hasattr(img, 'answer_key') and img.answer_key else None
                    pairs.append({
                        'image_url': f'/api/v1/attempts/{attempt.id}/images/{img.id}/' if img else '',
                        'selected_word': words.get(word_id, ''),
                        'correct_word': words.get(corr_word_id, ''),
                        'is_correct': word_id == corr_word_id,
                    })
            q_data['match_pairs'] = pairs

        elif q.type == 'TEXT':
            q_data['student_answer'] = resp.text_answer if resp else ''
            q_data['teacher_feedback'] = grade.feedback if grade else ''

        question_results.append(q_data)

    from apps.grading.services import visibility_deduction
    deduction = min(visibility_deduction(attempt), total_earned)
    total_earned -= deduction
    scale_score = round((float(total_earned) / float(total_max) * 10), 1) if total_max > 0 else 0.0

    return render(request, 'student/assignment_result.html', {
        'assignment': assignment,
        'attempt': attempt,
        'question_results': question_results if show_answer_details else [],
        'show_answer_details': show_answer_details,
        'total_earned': total_earned,
        'visibility_deduction': deduction,
        'total_max': total_max,
        'scale_score': scale_score,
        'correct_count': correct_count,
        'total_count': len(questions),
    })


@require_http_methods(['GET', 'POST'])
def sign_out(request):
    logout(request)
    return redirect('/')
