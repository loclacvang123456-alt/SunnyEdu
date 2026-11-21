from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from apps.assignments.models import Assignment
from apps.content.models import Course, CourseExercise, CourseTag, Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption


TAGS = [
    ('LISTENING', 'Nghe', 'SKILL'), ('SPEAKING', 'Nói', 'SKILL'),
    ('READING', 'Đọc', 'SKILL'), ('WRITING', 'Viết', 'SKILL'),
    ('TENSES', 'Các thì', 'GRAMMAR'), ('CONDITIONALS', 'Câu điều kiện', 'GRAMMAR'),
    ('PASSIVE', 'Câu bị động', 'GRAMMAR'), ('REPORTED_SPEECH', 'Câu tường thuật', 'GRAMMAR'),
    ('RELATIVE_CLAUSES', 'Mệnh đề quan hệ', 'GRAMMAR'),
    ('WORD_FORM', 'Dạng từ', 'VOCAB'), ('VOCABULARY', 'Từ vựng', 'VOCAB'),
    ('PRONUNCIATION', 'Ngữ âm', 'EXAM'), ('EXAM_PRACTICE', 'Luyện đề', 'EXAM'),
]
COURSES = [
    ('IELTS nền tảng (mẫu)', 'Luyện bốn kỹ năng tiếng Anh.', 'IELTS', 2, ['LISTENING', 'SPEAKING', 'READING', 'WRITING']),
    ('Luyện thi vào 10 (mẫu)', 'Ôn kiến thức và luyện đề.', 'ENTRANCE_10', 3, ['READING', 'WRITING', 'TENSES', 'VOCABULARY', 'PRONUNCIATION']),
    ('Ôn tập cuối kỳ (mẫu)', 'Ôn từ vựng và ngữ pháp.', 'SEMESTER', 1, ['READING', 'WRITING', 'TENSES', 'VOCABULARY']),
]
SAMPLE_EXERCISES = {
    'IELTS nền tảng (mẫu)': [
        ('HW-SMP001', 'Từ vựng học thuật (mẫu)', 'Choose the word closest to “important”.', ['significant', 'silent', 'empty', 'tiny'], 'READING', 2),
        ('HW-SMP004', 'Đọc câu ngắn (mẫu)', 'A library is a place to ___.', ['read books', 'wash cars', 'buy shoes', 'grow trees'], 'READING', 1),
        ('HW-SMP005', 'Từ đồng nghĩa (mẫu)', 'Choose the word closest to “increase”.', ['rise', 'fall', 'stop', 'hide'], 'VOCABULARY', 3),
    ],
    'Luyện thi vào 10 (mẫu)': [
        ('HW-SMP002', 'Câu điều kiện (mẫu)', 'If it rains, we ___ at home.', ['will stay', 'stayed', 'staying', 'stays'], 'CONDITIONALS', 3),
        ('HW-SMP006', 'Câu bị động (mẫu)', 'The book ___ by the teacher.', ['was written', 'write', 'writing', 'wrote'], 'PASSIVE', 2),
    ],
    'Ôn tập cuối kỳ (mẫu)': [
        ('HW-SMP003', 'Thì hiện tại đơn (mẫu)', 'She ___ to school every day.', ['goes', 'go', 'going', 'gone'], 'TENSES', 1),
    ],
}


class Command(BaseCommand):
    help = 'Tạo khóa, nhãn và bài tập mẫu; không gán lớp hoặc học sinh.'

    @transaction.atomic
    def handle(self, *args, **options):
        owner = User.objects.filter(role='OWNER', status='ACTIVE').first()
        if not owner:
            raise CommandError('Cần tài khoản giáo viên đang hoạt động trước khi tạo dữ liệu mẫu.')
        for code, name, kind in TAGS:
            CourseTag.objects.get_or_create(code=code, defaults={'name': name, 'kind': kind})
        created_count = 0
        for name, description, category, difficulty, tag_codes in COURSES:
            course, created = Course.objects.get_or_create(
                created_by=owner, name=name,
                defaults={'description': description, 'category': category, 'difficulty': difficulty,
                          'is_published': True, 'is_sample': True},
            )
            if created:
                course.tags.set(CourseTag.objects.filter(code__in=tag_codes))
                created_count += 1
            if not course.is_sample:
                continue
            for code, title, prompt, options, tag_code, stars in SAMPLE_EXERCISES[name]:
                assignment = Assignment.objects.filter(code=code).first()
                if not assignment:
                    exam = Exam.objects.create(title=title, created_by=owner)
                    version = ExamVersion.objects.create(exam=exam, number=1)
                    question = Question.objects.create(version=version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt=prompt, max_points='1.00')
                    for index, content in enumerate(options):
                        option = QuestionOption.objects.create(question=question, key=chr(65 + index), position=index + 1, content=content)
                        if index == 0:
                            AnswerKeyOption.objects.create(question=question, option=option)
                    now = timezone.now()
                    version.status, version.published_at = 'PUBLISHED', now
                    version.save(update_fields=['status', 'published_at', 'updated_at'])
                    assignment = Assignment.objects.create(version=version, title=title, code=code, status='PUBLISHED', mode='PRACTICE', opens_at=now-timedelta(days=1), due_at=now+timedelta(days=365), late_until=now+timedelta(days=372), published_at=now)
                    item = CourseExercise.objects.create(course=course, assignment=assignment, difficulty=stars)
                    item.tags.add(CourseTag.objects.get(code=tag_code))
        self.stdout.write(f'Created {created_count} sample courses. No classes or students assigned.')
