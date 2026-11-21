import os
import uuid
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentClass, AssignmentRecipient, RecipientEnglishClass
from apps.classes.models import EnglishClass
from apps.content.editor_services import upsert_question
from apps.content.models import Asset, Course, CourseExercise, CourseTag, Exam, ExamVersion
from apps.content.services import publish_version


TAG_DEFINITIONS = [
    # Skills
    ('LISTENING', 'Nghe', 'SKILL'),
    ('SPEAKING', 'Nói', 'SKILL'),
    ('READING', 'Đọc', 'SKILL'),
    ('WRITING', 'Viết', 'SKILL'),
    # Grammar
    ('TENSES', 'Các thì', 'GRAMMAR'),
    ('CONDITIONALS', 'Câu điều kiện', 'GRAMMAR'),
    ('PASSIVE', 'Câu bị động', 'GRAMMAR'),
    ('REPORTED_SPEECH', 'Câu tường thuật', 'GRAMMAR'),
    ('RELATIVE_CLAUSES', 'Mệnh đề quan hệ', 'GRAMMAR'),
    ('GERUND_INFINITIVE', 'Danh động từ & Động từ nguyên mẫu', 'GRAMMAR'),
    ('INVERSION', 'Đảo ngữ', 'GRAMMAR'),
    ('CLEFT_SENTENCE', 'Câu chẻ nhấn mạnh', 'GRAMMAR'),
    # Vocab
    ('VOCABULARY', 'Từ vựng', 'VOCAB'),
    ('WORD_FORM', 'Dạng từ', 'VOCAB'),
    ('PHRASAL_VERBS', 'Cụm động từ', 'VOCAB'),
    ('COLLOCATIONS', 'Cụm từ cố định', 'VOCAB'),
    ('SYNONYMS_ANTONYMS', 'Đồng nghĩa & Trái nghĩa', 'VOCAB'),
    ('IDIOMS', 'Thành ngữ', 'VOCAB'),
    ('BUSINESS_ENGLISH', 'Tiếng Anh thương mại', 'VOCAB'),
    # Exam / Formats
    ('PRONUNCIATION', 'Ngữ âm', 'EXAM'),
    ('STRESS', 'Trọng âm', 'EXAM'),
    ('WORD_ORDER', 'Sắp xếp câu', 'EXAM'),
    ('MATCHING', 'Nối tranh & từ', 'EXAM'),
    ('EXAM_PRACTICE', 'Luyện đề', 'EXAM'),
    ('PRIMARY_TAG', 'Tiểu học (1-5)', 'EXAM'),
    ('SECONDARY_TAG', 'THCS (6-9)', 'EXAM'),
    ('HIGH_SCHOOL_TAG', 'THPT (10-12)', 'EXAM'),
    ('ENTRANCE_10_TAG', 'Vào 10', 'EXAM'),
    ('THPT_QG_TAG', 'THPT Quốc Gia', 'EXAM'),
    ('IELTS_TAG', 'IELTS', 'EXAM'),
    ('TOEIC_TAG', 'TOEIC', 'EXAM'),
    ('TESOL_TAG', 'TESOL', 'EXAM'),
]


class Command(BaseCommand):
    help = 'Tạo hệ thống dữ liệu bài tập và khóa học toàn diện: Lớp 1-12, Vào 10, THPT QG, IELTS, TOEIC, TESOL.'

    def handle(self, *args, **options):
        owner = User.objects.filter(role='OWNER', status='ACTIVE').first()
        if not owner:
            raise CommandError('Cần tài khoản giáo viên (OWNER) trước khi tạo dữ liệu.')

        eng_class = EnglishClass.objects.filter(archived_at__isnull=True).first()
        students = list(User.objects.filter(role='STUDENT', status='ACTIVE'))

        self.stdout.write(f'Using Owner: {owner.username}')
        self.stdout.write(f'Using EnglishClass: {eng_class.name if eng_class else "None"}')
        self.stdout.write(f'Assigning to {len(students)} active student(s).')

        # 1. Ensure all CourseTags exist
        for code, name, kind in TAG_DEFINITIONS:
            CourseTag.objects.get_or_create(code=code, defaults={'name': name, 'kind': kind})

        # 2. Check for ready image assets for match image exercises
        prompt_images = list(Asset.objects.filter(purpose='PROMPT_IMAGE', status='READY', uploaded_by=owner))
        if len(prompt_images) < 2:
            prompt_images = list(Asset.objects.filter(purpose='PROMPT_IMAGE', status='READY'))

        # Build curriculum specifications
        courses_spec = self.get_curriculum_spec(prompt_images)

        now = timezone.now()
        total_courses_created = 0
        total_exercises_created = 0

        for c_spec in courses_spec:
            course_name = c_spec['name']
            description = c_spec['description']
            category = c_spec['category']
            difficulty = c_spec['difficulty']
            tag_codes = c_spec['tags']
            exercises = c_spec['exercises']

            course, c_created = Course.objects.get_or_create(
                created_by=owner,
                name=course_name,
                defaults={
                    'description': description,
                    'category': category,
                    'difficulty': difficulty,
                    'is_published': True,
                    'is_sample': False,
                }
            )
            if c_created:
                total_courses_created += 1
                course.tags.set(CourseTag.objects.filter(code__in=tag_codes))
            else:
                course.description = description
                course.category = category
                course.difficulty = difficulty
                course.is_published = True
                course.save()
                course.tags.set(CourseTag.objects.filter(code__in=tag_codes))

            if eng_class:
                course.english_classes.add(eng_class)

            for ex in exercises:
                ex_code = ex['code']
                ex_title = ex['title']
                ex_difficulty = ex.get('difficulty', difficulty)
                ex_tags = ex.get('tags', [])
                questions_data = ex['questions']

                assignment = Assignment.objects.filter(code=ex_code).first()
                if assignment:
                    # Link to course exercise if not already linked
                    ce, _ = CourseExercise.objects.get_or_create(
                        course=course,
                        assignment=assignment,
                        defaults={'difficulty': ex_difficulty}
                    )
                    ce.tags.set(CourseTag.objects.filter(code__in=ex_tags))
                    continue

                # Create exam, draft version, and questions
                with transaction.atomic():
                    exam = Exam.objects.create(title=ex_title, created_by=owner)
                    version = ExamVersion.objects.create(exam=exam, number=1)

                    for pos, q_payload in enumerate(questions_data, start=1):
                        upsert_question(owner, version.id, version.revision, q_payload)
                        version.refresh_from_db()

                    # Publish version
                    version = publish_version(version.id, version.revision)

                    # Create Assignment
                    assignment = Assignment.objects.create(
                        version=version,
                        title=ex_title,
                        code=ex_code,
                        status='PUBLISHED',
                        mode='PRACTICE',
                        opens_at=now - timedelta(days=2),
                        due_at=now + timedelta(days=365),
                        late_until=now + timedelta(days=372),
                        published_at=now,
                    )

                    if eng_class:
                        AssignmentClass.objects.get_or_create(assignment=assignment, english_class=eng_class)
                        for st in students:
                            recipient, _ = AssignmentRecipient.objects.get_or_create(
                                assignment=assignment,
                                student=st,
                                defaults={'state': 'ASSIGNED'}
                            )
                            RecipientEnglishClass.objects.get_or_create(
                                recipient=recipient,
                                english_class=eng_class,
                                defaults={
                                    'class_name_snapshot': eng_class.name,
                                    'school_year_snapshot': eng_class.school_year,
                                }
                            )

                    # Link to CourseExercise
                    ce = CourseExercise.objects.create(
                        course=course,
                        assignment=assignment,
                        difficulty=ex_difficulty
                    )
                    ce.tags.set(CourseTag.objects.filter(code__in=ex_tags))
                    total_exercises_created += 1

            self.stdout.write(f'-> Khóa học: "{course.name}" ({len(exercises)} bài tập)')

        self.stdout.write(self.style.SUCCESS(
            f'Hoàn tất! Đã tổng hợp và cập nhật {len(courses_spec)} khóa học với {total_exercises_created} bài tập mới vào database.'
        ))

    def get_curriculum_spec(self, prompt_images):
        has_images = len(prompt_images) >= 2
        spec = []

        # =====================================================================
        # 1. TIỂU HỌC (LỚP 1 - 2)
        # =====================================================================
        p1_exercises = []
        if has_images:
            p1_exercises.append({
                'code': 'HW-PRI01',
                'title': 'Từ vựng hình ảnh động vật & đồ vật (Lớp 1-2)',
                'difficulty': 1,
                'tags': ['VOCABULARY', 'MATCHING', 'PRIMARY_TAG'],
                'questions': [
                    {
                        'type': 'MATCH_IMAGE',
                        'skill': 'READING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'Em hãy quan sát và nối từng hình ảnh với từ tiếng Anh tương ứng.',
                        'max_points': '2.00',
                        'topic_tags': ['Từ vựng hình ảnh'],
                        'explanation': 'Nối đúng tranh với chữ: Cat (con mèo), Ship/Boat (con tàu).',
                        'match_pairs': [
                            {'image_asset_id': str(prompt_images[0].id), 'word': 'Ship'},
                            {'image_asset_id': str(prompt_images[1].id), 'word': 'Boat'},
                        ],
                    }
                ]
            })

        p1_exercises.extend([
            {
                'code': 'HW-PRI02',
                'title': 'Sắp xếp câu chào hỏi & giới thiệu (Lớp 1-2)',
                'difficulty': 1,
                'tags': ['WORD_ORDER', 'PRIMARY_TAG'],
                'questions': [
                    {
                        'type': 'WORD_ORDER',
                        'skill': 'WRITING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'Kéo hoặc chạm vào các từ để sắp xếp thành câu chào hỏi hoàn chỉnh.',
                        'max_points': '1.00',
                        'topic_tags': ['Chào hỏi'],
                        'explanation': 'Thứ tự đúng: Hello my name is Tony.',
                        'word_tokens': ['Hello', 'my', 'name', 'is', 'Tony'],
                    },
                    {
                        'type': 'WORD_ORDER',
                        'skill': 'WRITING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'Sắp xếp các từ để tạo thành câu hoàn chỉnh chỉ đồ vật.',
                        'max_points': '1.00',
                        'topic_tags': ['Đồ vật'],
                        'explanation': 'Thứ tự đúng: This is a red apple.',
                        'word_tokens': ['This', 'is', 'a', 'red', 'apple'],
                    },
                    {
                        'type': 'WORD_ORDER',
                        'skill': 'WRITING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'Sắp xếp câu hỏi thăm sức khỏe thông dụng.',
                        'max_points': '1.00',
                        'topic_tags': ['Giao tiếp'],
                        'explanation': 'Thứ tự đúng: How are you today?',
                        'word_tokens': ['How', 'are', 'you', 'today'],
                    },
                ]
            },
            {
                'code': 'HW-PRI03',
                'title': 'Từ vựng Màu sắc, Số đếm & Đồ chơi (Lớp 1-2)',
                'difficulty': 1,
                'tags': ['VOCABULARY', 'PRIMARY_TAG'],
                'questions': [
                    {
                        'type': 'SINGLE_CHOICE',
                        'skill': 'READING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'What color is the sky on a sunny day?',
                        'max_points': '1.00',
                        'topic_tags': ['Màu sắc'],
                        'explanation': 'The sky on a sunny day is blue (màu xanh da trời).',
                        'options': [{'key': 'A', 'content': 'Blue'}, {'key': 'B', 'content': 'Red'}, {'key': 'C', 'content': 'Black'}, {'key': 'D', 'content': 'Green'}],
                        'correct_options': ['A'],
                    },
                    {
                        'type': 'SINGLE_CHOICE',
                        'skill': 'READING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'One, two, three, ___, five.',
                        'max_points': '1.00',
                        'topic_tags': ['Số đếm'],
                        'explanation': 'Số còn thiếu giữa three và five là four (số 4).',
                        'options': [{'key': 'A', 'content': 'four'}, {'key': 'B', 'content': 'six'}, {'key': 'C', 'content': 'seven'}, {'key': 'D', 'content': 'ten'}],
                        'correct_options': ['A'],
                    },
                    {
                        'type': 'SINGLE_CHOICE',
                        'skill': 'READING',
                        'difficulty': 'FOUNDATION',
                        'prompt': 'Which animal can fly in the sky?',
                        'max_points': '1.00',
                        'topic_tags': ['Động vật'],
                        'explanation': 'A bird can fly (con chim có thể bay).',
                        'options': [{'key': 'A', 'content': 'A bird'}, {'key': 'B', 'content': 'A fish'}, {'key': 'C', 'content': 'A cat'}, {'key': 'D', 'content': 'A dog'}],
                        'correct_options': ['A'],
                    },
                ]
            },
        ])

        spec.append({
            'name': 'Tiếng Anh Lớp 1 - 2: Khởi động & Từ vựng trực quan',
            'description': 'Làm quen bảng chữ cái, số đếm, màu sắc, con vật và sắp xếp câu giao tiếp đơn giản.',
            'category': 'PRIMARY',
            'difficulty': 1,
            'tags': ['PRIMARY_TAG', 'VOCABULARY', 'WORD_ORDER', 'MATCHING'],
            'exercises': p1_exercises,
        })

        # =====================================================================
        # 2. TIỂU HỌC (LỚP 3 - 5)
        # =====================================================================
        spec.append({
            'name': 'Tiếng Anh Lớp 3 - 5: Giao tiếp & Ngữ pháp Tiểu học',
            'description': 'Nắm vững đại từ, động từ to be, thì hiện tại đơn, trọng âm từ 2 âm tiết và viết câu ngắn.',
            'category': 'PRIMARY',
            'difficulty': 2,
            'tags': ['PRIMARY_TAG', 'GRAMMAR', 'TENSES', 'WORD_ORDER', 'STRESS'],
            'exercises': [
                {
                    'code': 'HW-PRI04',
                    'title': 'Đại từ nhân xưng & Động từ To Be (Lớp 3-5)',
                    'difficulty': 1,
                    'tags': ['GRAMMAR', 'PRIMARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'They ___ my best classmates.',
                            'max_points': '1.00',
                            'topic_tags': ['Động từ To Be'],
                            'explanation': 'Chủ ngữ ngôi thứ ba số nhiều "They" đi với động từ to be "are".',
                            'options': [{'key': 'A', 'content': 'are'}, {'key': 'B', 'content': 'is'}, {'key': 'C', 'content': 'am'}, {'key': 'D', 'content': 'be'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'My father ___ a doctor in a big hospital.',
                            'max_points': '1.00',
                            'topic_tags': ['Động từ To Be'],
                            'explanation': 'Chủ ngữ số ít "My father" đi với "is".',
                            'options': [{'key': 'A', 'content': 'is'}, {'key': 'B', 'content': 'are'}, {'key': 'C', 'content': 'am'}, {'key': 'D', 'content': 'were'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': '___ pen is this? - It is Linda’s.',
                            'max_points': '1.00',
                            'topic_tags': ['Từ để hỏi'],
                            'explanation': 'Hỏi về sở hữu dùng từ để hỏi "Whose" (của ai).',
                            'options': [{'key': 'A', 'content': 'Whose'}, {'key': 'B', 'content': 'Who'}, {'key': 'C', 'content': 'What'}, {'key': 'D', 'content': 'Where'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-PRI05',
                    'title': 'Thì Hiện tại đơn & Thói quen hàng ngày (Lớp 3-5)',
                    'difficulty': 2,
                    'tags': ['TENSES', 'PRIMARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'She usually ___ to school by bike with her brother.',
                            'max_points': '1.00',
                            'topic_tags': ['Hiện tại đơn'],
                            'explanation': 'Chủ ngữ ngôi thứ ba số ít "She" đi với động từ thêm -es: "goes".',
                            'options': [{'key': 'A', 'content': 'goes'}, {'key': 'B', 'content': 'go'}, {'key': 'C', 'content': 'going'}, {'key': 'D', 'content': 'went'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Nam and Minh ___ play football on rainy days.',
                            'max_points': '1.00',
                            'topic_tags': ['Hiện tại đơn'],
                            'explanation': 'Chủ ngữ số nhiều "Nam and Minh" phủ định ở hiện tại đơn dùng trợ động từ "don’t".',
                            'options': [{'key': 'A', 'content': 'don’t'}, {'key': 'B', 'content': 'doesn’t'}, {'key': 'C', 'content': 'isn’t'}, {'key': 'D', 'content': 'aren’t'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-PRI06',
                    'title': 'Sắp xếp câu hỏi & câu trần thuật (Lớp 3-5)',
                    'difficulty': 2,
                    'tags': ['WORD_ORDER', 'PRIMARY_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'Sắp xếp câu hỏi về hoạt động trong thời gian rảnh rỗi.',
                            'max_points': '1.00',
                            'topic_tags': ['Câu hỏi'],
                            'explanation': 'Thứ tự đúng: What do you do in your free time?',
                            'word_tokens': ['What', 'do', 'you', 'do', 'in', 'your', 'free', 'time'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp câu nói về ước mơ nghề nghiệp tương lai.',
                            'max_points': '1.00',
                            'topic_tags': ['Ước mơ'],
                            'explanation': 'Thứ tự đúng: I would like to be an English teacher.',
                            'word_tokens': ['I', 'would', 'like', 'to', 'be', 'an', 'English', 'teacher'],
                        },
                    ]
                },
                {
                    'code': 'HW-PRI07',
                    'title': 'Trọng âm từ 2 âm tiết quen thuộc (Lớp 3-5)',
                    'difficulty': 2,
                    'tags': ['STRESS', 'PRIMARY_TAG'],
                    'questions': [
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'Chạm vào âm tiết mang trọng âm chính của từ: doctor (/ˈdɒk.tər/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ 2 âm tiết'],
                            'explanation': 'Danh từ 2 âm tiết "doctor" có trọng âm rơi vào âm tiết thứ nhất "doc".',
                            'stress_syllables': ['doc', 'tor'],
                            'correct_syllable_index': 1,
                        },
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'FOUNDATION',
                            'prompt': 'Chạm vào âm tiết mang trọng âm chính của từ: monkey (/ˈmʌŋ.ki/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ 2 âm tiết'],
                            'explanation': 'Danh từ "monkey" có trọng âm rơi vào âm tiết đầu "mon".',
                            'stress_syllables': ['mon', 'key'],
                            'correct_syllable_index': 1,
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 3. THCS (LỚP 6 - 7)
        # =====================================================================
        spec.append({
            'name': 'Tiếng Anh Lớp 6 - 7: Nền tảng Ngữ pháp & Kỹ năng Đọc Viết',
            'description': 'Phân biệt hiện tại tiếp diễn, quá khứ đơn, câu so sánh, giới từ chỉ nơi chốn và thời gian.',
            'category': 'SECONDARY',
            'difficulty': 2,
            'tags': ['SECONDARY_TAG', 'TENSES', 'WORD_ORDER', 'STRESS'],
            'exercises': [
                {
                    'code': 'HW-SEC01',
                    'title': 'Hiện tại đơn vs Hiện tại tiếp diễn (Lớp 6-7)',
                    'difficulty': 2,
                    'tags': ['TENSES', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Listen! The birds ___ sweetly in the school garden.',
                            'max_points': '1.00',
                            'topic_tags': ['Hiện tại tiếp diễn'],
                            'explanation': 'Dấu hiệu nhận biết "Listen!" chỉ hành động đang xảy ra: chia "are singing".',
                            'options': [{'key': 'A', 'content': 'are singing'}, {'key': 'B', 'content': 'sing'}, {'key': 'C', 'content': 'sang'}, {'key': 'D', 'content': 'is singing'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'My mother always ___ up early to prepare breakfast for our family.',
                            'max_points': '1.00',
                            'topic_tags': ['Hiện tại đơn'],
                            'explanation': 'Trạng từ tần suất "always" diễn tả thói quen lặp đi lặp lại: chia "gets".',
                            'options': [{'key': 'A', 'content': 'gets'}, {'key': 'B', 'content': 'is getting'}, {'key': 'C', 'content': 'get'}, {'key': 'D', 'content': 'got'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-SEC02',
                    'title': 'Quá khứ đơn & Động từ bất quy tắc (Lớp 6-7)',
                    'difficulty': 2,
                    'tags': ['TENSES', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Last Sunday, we ___ Ha Long Bay and took a lot of photos.',
                            'max_points': '1.00',
                            'topic_tags': ['Quá khứ đơn'],
                            'explanation': 'Dấu hiệu thời gian "Last Sunday" chỉ quá khứ đơn: động từ "visited".',
                            'options': [{'key': 'A', 'content': 'visited'}, {'key': 'B', 'content': 'visit'}, {'key': 'C', 'content': 'are visiting'}, {'key': 'D', 'content': 'have visited'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Shakespeare ___ Romeo and Juliet in the late sixteenth century.',
                            'max_points': '1.00',
                            'topic_tags': ['Động từ bất quy tắc'],
                            'explanation': 'Quá khứ của write là "wrote".',
                            'options': [{'key': 'A', 'content': 'wrote'}, {'key': 'B', 'content': 'written'}, {'key': 'C', 'content': 'writes'}, {'key': 'D', 'content': 'writed'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-SEC03',
                    'title': 'Sắp xếp câu so sánh hơn & so sánh nhất (Lớp 6-7)',
                    'difficulty': 2,
                    'tags': ['WORD_ORDER', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp các từ để hoàn thành câu so sánh hơn giữa hai thành phố.',
                            'max_points': '1.00',
                            'topic_tags': ['So sánh hơn'],
                            'explanation': 'Thứ tự đúng: Da Nang is smaller than Hanoi but cleaner.',
                            'word_tokens': ['Da Nang', 'is', 'smaller', 'than', 'Hanoi', 'but', 'cleaner'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp câu so sánh nhất về ngọn núi cao nhất thế giới.',
                            'max_points': '1.00',
                            'topic_tags': ['So sánh nhất'],
                            'explanation': 'Thứ tự đúng: Mount Everest is the highest mountain in the world.',
                            'word_tokens': ['Mount Everest', 'is', 'the', 'highest', 'mountain', 'in', 'the', 'world'],
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 4. THCS (LỚP 8 - 9)
        # =====================================================================
        spec.append({
            'name': 'Tiếng Anh Lớp 8 - 9: Bứt phá & Ngữ pháp Nâng cao',
            'description': 'Câu điều kiện loại 1 & 2, câu bị động, câu tường thuật gián tiếp và mệnh đề quan hệ.',
            'category': 'SECONDARY',
            'difficulty': 3,
            'tags': ['SECONDARY_TAG', 'CONDITIONALS', 'PASSIVE', 'REPORTED_SPEECH', 'RELATIVE_CLAUSES'],
            'exercises': [
                {
                    'code': 'HW-SEC04',
                    'title': 'Câu điều kiện Loại 1 và Loại 2 (Lớp 8-9)',
                    'difficulty': 3,
                    'tags': ['CONDITIONALS', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'If we protect the environment, wildlife ___ safer in their habitats.',
                            'max_points': '1.00',
                            'topic_tags': ['Điều kiện loại 1'],
                            'explanation': 'Mệnh đề If ở hiện tại đơn (protect), mệnh đề chính dùng "will be".',
                            'options': [{'key': 'A', 'content': 'will be'}, {'key': 'B', 'content': 'would be'}, {'key': 'C', 'content': 'were'}, {'key': 'D', 'content': 'are'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'If I ___ a millionaire, I would build a library for poor children.',
                            'max_points': '1.00',
                            'topic_tags': ['Điều kiện loại 2'],
                            'explanation': 'Điều kiện loại 2 diễn tả giả định trái với thực tế ở hiện tại: dùng "were" cho tất cả các ngôi.',
                            'options': [{'key': 'A', 'content': 'were'}, {'key': 'B', 'content': 'am'}, {'key': 'C', 'content': 'will be'}, {'key': 'D', 'content': 'have been'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-SEC05',
                    'title': 'Câu bị động (Passive Voice) các thì cơ bản (Lớp 8-9)',
                    'difficulty': 3,
                    'tags': ['PASSIVE', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'A new modern bridge ___ across the river last year.',
                            'max_points': '1.00',
                            'topic_tags': ['Bị động quá khứ đơn'],
                            'explanation': 'Chủ ngữ số ít "A new modern bridge" + thời gian "last year": chia bị động "was built".',
                            'options': [{'key': 'A', 'content': 'was built'}, {'key': 'B', 'content': 'is built'}, {'key': 'C', 'content': 'built'}, {'key': 'D', 'content': 'were built'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp các từ để tạo thành câu bị động thì hiện tại hoàn thành.',
                            'max_points': '1.00',
                            'topic_tags': ['Bị động hiện tại hoàn thành'],
                            'explanation': 'Thứ tự đúng: The homework has been completed by all students.',
                            'word_tokens': ['The', 'homework', 'has', 'been', 'completed', 'by', 'all', 'students'],
                        },
                    ]
                },
                {
                    'code': 'HW-SEC06',
                    'title': 'Mệnh đề quan hệ & Câu tường thuật (Lớp 8-9)',
                    'difficulty': 3,
                    'tags': ['RELATIVE_CLAUSES', 'REPORTED_SPEECH', 'SECONDARY_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'The woman ___ designed this eco-friendly building is a talented architect.',
                            'max_points': '1.00',
                            'topic_tags': ['Đại từ quan hệ'],
                            'explanation': 'Thay thế cho danh từ chỉ người làm chủ ngữ dùng đại từ quan hệ "who".',
                            'options': [{'key': 'A', 'content': 'who'}, {'key': 'B', 'content': 'which'}, {'key': 'C', 'content': 'whom'}, {'key': 'D', 'content': 'whose'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp câu tường thuật dạng Yes/No question.',
                            'max_points': '1.00',
                            'topic_tags': ['Câu tường thuật'],
                            'explanation': 'Thứ tự đúng: He asked me if I liked classical music.',
                            'word_tokens': ['He', 'asked', 'me', 'if', 'I', 'liked', 'classical', 'music'],
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 5. ÔN THI VÀO 10 (ENTRANCE_10)
        # =====================================================================
        spec.append({
            'name': 'Luyện thi Tuyển sinh vào lớp 10 THPT: Trọng điểm & Đề thi thử',
            'description': 'Đầy đủ dạng bài thi vào 10: Ngữ âm -ed/-s, trọng âm 2-3 âm tiết, cụm động từ, tìm lỗi sai và viết câu.',
            'category': 'ENTRANCE_10',
            'difficulty': 3,
            'tags': ['ENTRANCE_10_TAG', 'EXAM_PRACTICE', 'PRONUNCIATION', 'STRESS', 'WORD_ORDER', 'PHRASAL_VERBS'],
            'exercises': [
                {
                    'code': 'HW-ENT01',
                    'title': 'Chuyên đề Phát âm đuôi -ed và -s/-es (Đề thi vào 10)',
                    'difficulty': 3,
                    'tags': ['PRONUNCIATION', 'ENTRANCE_10_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Choose the word whose underlined part is pronounced differently: wanted, decided, needed, played.',
                            'max_points': '1.00',
                            'topic_tags': ['Phát âm đuôi -ed'],
                            'explanation': 'played phát âm là /d/, ba từ còn lại tận cùng bằng /t/ và /d/ nên phát âm là /ɪd/.',
                            'options': [{'key': 'A', 'content': 'played'}, {'key': 'B', 'content': 'wanted'}, {'key': 'C', 'content': 'decided'}, {'key': 'D', 'content': 'needed'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Choose the word whose underlined part is pronounced differently: books, cats, maps, dogs.',
                            'max_points': '1.00',
                            'topic_tags': ['Phát âm đuôi -s/-es'],
                            'explanation': 'dogs phát âm là /z/ vì g là âm hữu thanh; books, cats, maps tận cùng bằng âm vô thanh /k, t, p/ nên phát âm là /s/.',
                            'options': [{'key': 'A', 'content': 'dogs'}, {'key': 'B', 'content': 'books'}, {'key': 'C', 'content': 'cats'}, {'key': 'D', 'content': 'maps'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-ENT02',
                    'title': 'Chuyên đề Trọng âm 2 và 3 âm tiết (Đề thi vào 10)',
                    'difficulty': 3,
                    'tags': ['STRESS', 'ENTRANCE_10_TAG'],
                    'questions': [
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Chọn âm tiết mang trọng âm chính của từ: de-ci-sion (/dɪˈsɪʒ.ən/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ có đuôi -ion'],
                            'explanation': 'Từ có đuôi -ion thì trọng âm rơi vào âm tiết liền trước nó: de-CI-sion.',
                            'stress_syllables': ['de', 'ci', 'sion'],
                            'correct_syllable_index': 2,
                        },
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Chọn âm tiết mang trọng âm chính của từ: im-por-tant (/ɪmˈpɔː.tənt/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ 3 âm tiết'],
                            'explanation': 'Tính từ important có trọng âm rơi vào âm tiết thứ hai: im-POR-tant.',
                            'stress_syllables': ['im', 'por', 'tant'],
                            'correct_syllable_index': 2,
                        },
                    ]
                },
                {
                    'code': 'HW-ENT03',
                    'title': 'Cụm động từ (Phrasal Verbs) & Tìm lỗi sai (Vào 10)',
                    'difficulty': 3,
                    'tags': ['PHRASAL_VERBS', 'ENTRANCE_10_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Remember to ___ the lights before leaving the classroom to save energy.',
                            'max_points': '1.00',
                            'topic_tags': ['Cụm động từ'],
                            'explanation': 'turn off = tắt (thiết bị điện), turn on = bật, look after = chăm sóc, give up = từ bỏ.',
                            'options': [{'key': 'A', 'content': 'turn off'}, {'key': 'B', 'content': 'turn on'}, {'key': 'C', 'content': 'look after'}, {'key': 'D', 'content': 'give up'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Find the error: Neither of the students (A) have done (B) their (C) homework yet (D).',
                            'max_points': '1.00',
                            'topic_tags': ['Tìm lỗi sai'],
                            'explanation': 'Cấu trúc "Neither of + plural noun" đi với động từ số ít: sửa "have done" thành "has done".',
                            'options': [{'key': 'A', 'content': 'Neither of'}, {'key': 'B', 'content': 'have done'}, {'key': 'C', 'content': 'their'}, {'key': 'D', 'content': 'yet'}],
                            'correct_options': ['B'],
                        },
                    ]
                },
                {
                    'code': 'HW-ENT04',
                    'title': 'Sắp xếp câu & Viết lại câu không đổi nghĩa (Vào 10)',
                    'difficulty': 3,
                    'tags': ['WORD_ORDER', 'WRITING', 'ENTRANCE_10_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp câu nhượng bộ với liên từ Although trong đề thi vào 10.',
                            'max_points': '1.00',
                            'topic_tags': ['Mệnh đề nhượng bộ'],
                            'explanation': 'Thứ tự đúng: Although it rained heavily they went to school on time.',
                            'word_tokens': ['Although', 'it', 'rained', 'heavily', 'they', 'went', 'to', 'school', 'on', 'time'],
                        },
                        {
                            'type': 'TEXT',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Rewrite the sentence using UNLESS: "If you do not study hard, you will fail the entrance exam."',
                            'max_points': '2.00',
                            'topic_tags': ['Viết lại câu'],
                            'explanation': 'Đáp án mẫu: Unless you study hard, you will fail the entrance exam.',
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 6. THPT (LỚP 10 - 11)
        # =====================================================================
        spec.append({
            'name': 'Tiếng Anh Lớp 10 - 11: Ngữ pháp Nâng cao & Cấu trúc Câu',
            'description': 'Câu chẻ nhấn mạnh (Cleft sentences), Gerund vs Infinitive, trọng âm 3-4 âm tiết và phân từ.',
            'category': 'HIGH_SCHOOL',
            'difficulty': 3,
            'tags': ['HIGH_SCHOOL_TAG', 'GRAMMAR', 'CLEFT_SENTENCE', 'GERUND_INFINITIVE', 'STRESS'],
            'exercises': [
                {
                    'code': 'HW-HSC01',
                    'title': 'Câu chẻ nhấn mạnh (Cleft sentences with It is... that)',
                    'difficulty': 3,
                    'tags': ['CLEFT_SENTENCE', 'HIGH_SCHOOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'It was in 1969 ___ Neil Armstrong set foot on the moon.',
                            'max_points': '1.00',
                            'topic_tags': ['Câu chẻ'],
                            'explanation': 'Cấu trúc câu chẻ nhấn mạnh trạng ngữ thời gian: It was + adverb of time + that...',
                            'options': [{'key': 'A', 'content': 'that'}, {'key': 'B', 'content': 'which'}, {'key': 'C', 'content': 'when'}, {'key': 'D', 'content': 'where'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp các từ để hoàn thiện câu chẻ nhấn mạnh chủ ngữ.',
                            'max_points': '1.00',
                            'topic_tags': ['Câu chẻ chủ ngữ'],
                            'explanation': 'Thứ tự đúng: It is my teacher that inspired me to study abroad.',
                            'word_tokens': ['It', 'is', 'my', 'teacher', 'that', 'inspired', 'me', 'to', 'study', 'abroad'],
                        },
                    ]
                },
                {
                    'code': 'HW-HSC02',
                    'title': 'Gerund & Infinitive sau các động từ đặc biệt',
                    'difficulty': 3,
                    'tags': ['GERUND_INFINITIVE', 'HIGH_SCHOOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'I clearly remember ___ off the gas cooker before leaving home.',
                            'max_points': '1.00',
                            'topic_tags': ['Danh động từ'],
                            'explanation': 'Remember + V-ing diễn tả nhớ đã làm một việc trong quá khứ.',
                            'options': [{'key': 'A', 'content': 'turning'}, {'key': 'B', 'content': 'to turn'}, {'key': 'C', 'content': 'turn'}, {'key': 'D', 'content': 'turned'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'We regret ___ you that your job application has been unsuccessful.',
                            'max_points': '1.00',
                            'topic_tags': ['Động từ nguyên mẫu'],
                            'explanation': 'Regret to inform/tell = lấy làm tiếc khi phải thông báo tin xấu.',
                            'options': [{'key': 'A', 'content': 'to inform'}, {'key': 'B', 'content': 'informing'}, {'key': 'C', 'content': 'inform'}, {'key': 'D', 'content': 'informed'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-HSC03',
                    'title': 'Trọng âm từ 3-4 âm tiết có quy tắc hậu tố',
                    'difficulty': 3,
                    'tags': ['STRESS', 'HIGH_SCHOOL_TAG'],
                    'questions': [
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Chọn trọng âm chính của từ: e-co-no-my (/ɪˈkɒn.ə.mi/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ có đuôi -y'],
                            'explanation': 'Từ tận cùng bằng -y thường có trọng âm rơi vào âm tiết thứ 3 từ dưới lên: e-CO-no-my.',
                            'stress_syllables': ['e', 'co', 'no', 'my'],
                            'correct_syllable_index': 2,
                        },
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Chọn trọng âm chính của từ: com-mu-ni-cate (/kəˈmjuː.nɪ.keɪt/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ có đuôi -ate'],
                            'explanation': 'Động từ tận cùng bằng -ate có từ 3 âm tiết trở lên: trọng âm rơi vào âm tiết thứ 3 từ dưới lên: com-MU-ni-cate.',
                            'stress_syllables': ['com', 'mu', 'ni', 'cate'],
                            'correct_syllable_index': 2,
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 7. THPT (LỚP 12)
        # =====================================================================
        spec.append({
            'name': 'Tiếng Anh Lớp 12: Chương trình Chuẩn & Luyện đề THPT',
            'description': 'Đảo ngữ nâng cao, thể giả định, cấu trúc rút gọn mệnh đề và đọc hiểu các chủ đề xã hội.',
            'category': 'HIGH_SCHOOL',
            'difficulty': 4,
            'tags': ['HIGH_SCHOOL_TAG', 'INVERSION', 'GRAMMAR', 'WORD_ORDER', 'READING'],
            'exercises': [
                {
                    'code': 'HW-HSC04',
                    'title': 'Cấu trúc Đảo ngữ nâng cao với phó từ phủ định (Lớp 12)',
                    'difficulty': 4,
                    'tags': ['INVERSION', 'HIGH_SCHOOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Seldom ___ such an inspiring presentation on renewable energy.',
                            'max_points': '1.00',
                            'topic_tags': ['Đảo ngữ'],
                            'explanation': 'Đầu câu có phó từ phủ định "Seldom", ta thực hiện đảo ngữ đưa trợ động từ lên trước chủ ngữ: have I heard.',
                            'options': [{'key': 'A', 'content': 'have I heard'}, {'key': 'B', 'content': 'I have heard'}, {'key': 'C', 'content': 'did I hear'}, {'key': 'D', 'content': 'I heard'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Sắp xếp câu đảo ngữ với cấu trúc Hardly ... when...',
                            'max_points': '1.00',
                            'topic_tags': ['Đảo ngữ Hardly when'],
                            'explanation': 'Thứ tự đúng: Hardly had the meeting started when the fire alarm rang.',
                            'word_tokens': ['Hardly', 'had', 'the', 'meeting', 'started', 'when', 'the', 'fire', 'alarm', 'rang'],
                        },
                    ]
                },
                {
                    'code': 'HW-HSC05',
                    'title': 'Thể giả định (Subjunctive Mood) & Câu điều ước (Lớp 12)',
                    'difficulty': 4,
                    'tags': ['GRAMMAR', 'HIGH_SCHOOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'The doctor recommended that the patient ___ more fresh vegetables and exercise regularly.',
                            'max_points': '1.00',
                            'topic_tags': ['Thể giả định'],
                            'explanation': 'Cấu trúc giả định thức với động từ recommend that + S + (should) V-nguyên thể: dùng "eat".',
                            'options': [{'key': 'A', 'content': 'eat'}, {'key': 'B', 'content': 'eats'}, {'key': 'C', 'content': 'ate'}, {'key': 'D', 'content': 'is eating'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'I wish I ___ harder for the final semester examination last week.',
                            'max_points': '1.00',
                            'topic_tags': ['Câu điều ước'],
                            'explanation': 'Ước cho một điều trong quá khứ (last week): dùng thì quá khứ hoàn thành "had studied".',
                            'options': [{'key': 'A', 'content': 'had studied'}, {'key': 'B', 'content': 'studied'}, {'key': 'C', 'content': 'would study'}, {'key': 'D', 'content': 'have studied'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 8. ÔN THI THPT QUỐC GIA (NATIONAL_EXAM)
        # =====================================================================
        spec.append({
            'name': 'Luyện thi THPT Quốc Gia: Tổng ôn Cấp tốc & Đề thi Chuẩn',
            'description': 'Bám sát ma trận đề thi Bộ GD&ĐT: Từ đồng nghĩa/trái nghĩa, thành ngữ, giao tiếp, đọc hiểu học thuật và kết hợp câu.',
            'category': 'NATIONAL_EXAM',
            'difficulty': 4,
            'tags': ['THPT_QG_TAG', 'EXAM_PRACTICE', 'SYNONYMS_ANTONYMS', 'IDIOMS', 'READING', 'WORD_ORDER'],
            'exercises': [
                {
                    'code': 'HW-NAT01',
                    'title': 'Từ đồng nghĩa & Trái nghĩa mức độ phân hóa (THPT QG)',
                    'difficulty': 4,
                    'tags': ['SYNONYMS_ANTONYMS', 'THPT_QG_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'CLOSEST in meaning: The new governmental policy aims to ALLEVIATE poverty in remote rural communities.',
                            'max_points': '1.00',
                            'topic_tags': ['Từ đồng nghĩa'],
                            'explanation': 'Alleviate = làm giảm bớt, xoa dịu = ease / reduce.',
                            'options': [{'key': 'A', 'content': 'ease'}, {'key': 'B', 'content': 'worsen'}, {'key': 'C', 'content': 'ignore'}, {'key': 'D', 'content': 'tolerate'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'OPPOSITE in meaning: Many students were SKEPTICAL about the validity of the unverified online rumor.',
                            'max_points': '1.00',
                            'topic_tags': ['Từ trái nghĩa'],
                            'explanation': 'Skeptical = hoài nghi, ngờ vực; trái nghĩa là convinced = tin phục, tin tưởng.',
                            'options': [{'key': 'A', 'content': 'convinced'}, {'key': 'B', 'content': 'doubtful'}, {'key': 'C', 'content': 'suspicious'}, {'key': 'D', 'content': 'curious'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-NAT02',
                    'title': 'Thành ngữ (Idioms) & Chức năng giao tiếp (THPT QG)',
                    'difficulty': 4,
                    'tags': ['IDIOMS', 'THPT_QG_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Whenever exam week comes around, she always burns the ___ oil to revise every lesson.',
                            'max_points': '1.00',
                            'topic_tags': ['Thành ngữ'],
                            'explanation': 'Thành ngữ "burn the midnight oil" nghĩa là thức khuya học bài/làm việc.',
                            'options': [{'key': 'A', 'content': 'midnight'}, {'key': 'B', 'content': 'morning'}, {'key': 'C', 'content': 'evening'}, {'key': 'D', 'content': 'daylight'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Daisy: "Thank you very much for your great assistance!" - Mark: "___"',
                            'max_points': '1.00',
                            'topic_tags': ['Giao tiếp'],
                            'explanation': 'Đáp lại lời cảm ơn trang trọng và lịch sự: "It’s my pleasure" (Rất hân hạnh được giúp bạn).',
                            'options': [{'key': 'A', 'content': 'It’s my pleasure.'}, {'key': 'B', 'content': 'Never mind it.'}, {'key': 'C', 'content': 'You can say that again.'}, {'key': 'D', 'content': 'Not at all true.'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-NAT03',
                    'title': 'Sắp xếp câu đảo ngữ phức & Kết hợp câu (THPT QG)',
                    'difficulty': 4,
                    'tags': ['WORD_ORDER', 'INVERSION', 'THPT_QG_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Sắp xếp cấu trúc đảo ngữ với "Not only... but also..." thường xuất hiện trong đề thi THPT QG.',
                            'max_points': '1.00',
                            'topic_tags': ['Đảo ngữ Not only'],
                            'explanation': 'Thứ tự đúng: Not only did he win the championship but he also broke the world record.',
                            'word_tokens': ['Not only', 'did', 'he', 'win', 'the', 'championship', 'but', 'he', 'also', 'broke', 'the', 'world', 'record'],
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 9. LUYỆN THI IELTS
        # =====================================================================
        spec.append({
            'name': 'IELTS Masterclass: Bứt phá 4 Kỹ năng Band 6.5 - 7.5+',
            'description': 'Luyện từ vựng học thuật AWL, kỹ năng đọc Skimming & Scanning, cấu trúc câu Task 2 và phát triển luận điểm.',
            'category': 'IELTS',
            'difficulty': 4,
            'tags': ['IELTS_TAG', 'READING', 'WRITING', 'VOCABULARY', 'WORD_ORDER'],
            'exercises': [
                {
                    'code': 'HW-IEL01',
                    'title': 'IELTS Academic Vocabulary & Collocations (Band 7.0+)',
                    'difficulty': 4,
                    'tags': ['VOCABULARY', 'IELTS_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'The rapid expansion of urban centers has exerted ___ pressure on local public transport infrastructures.',
                            'max_points': '1.00',
                            'topic_tags': ['Collocations'],
                            'explanation': 'Cụm collocation học thuật: "exert immense / tremendous pressure on" (gây áp lực to lớn lên).',
                            'options': [{'key': 'A', 'content': 'immense'}, {'key': 'B', 'content': 'shallow'}, {'key': 'C', 'content': 'fragile'}, {'key': 'D', 'content': 'trivial'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Researchers need to collect empirical data in order to ___ their scientific hypothesis.',
                            'max_points': '1.00',
                            'topic_tags': ['Từ vựng học thuật'],
                            'explanation': 'Substantiate = chứng minh, làm sáng tỏ bằng bằng chứng thực nghiệm (corroborate/validate).',
                            'options': [{'key': 'A', 'content': 'substantiate'}, {'key': 'B', 'content': 'fabricate'}, {'key': 'C', 'content': 'contradict'}, {'key': 'D', 'content': 'undermine'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-IEL02',
                    'title': 'IELTS Writing Task 2: Câu ghép học thuật & Luận điểm',
                    'difficulty': 4,
                    'tags': ['WRITING', 'WORD_ORDER', 'IELTS_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Sắp xếp câu luận điểm mở bài (Thesis statement) chuẩn phong cách IELTS Writing Task 2.',
                            'max_points': '1.00',
                            'topic_tags': ['Luận điểm học thuật'],
                            'explanation': 'Thứ tự đúng: It is widely acknowledged that continuous education plays a pivotal role in personal development.',
                            'word_tokens': ['It', 'is', 'widely', 'acknowledged', 'that', 'continuous', 'education', 'plays', 'a', 'pivotal', 'role', 'in', 'personal', 'development'],
                        },
                        {
                            'type': 'TEXT',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'IELTS Writing Task 2 Topic: "Some believe that artificial intelligence will replace teachers in the classroom. To what extent do you agree or disagree?" Write your introduction and 1 main body paragraph.',
                            'max_points': '2.00',
                            'topic_tags': ['IELTS Essay'],
                            'explanation': 'Đáp án cần có mở bài nêu rõ quan điểm và thân bài có câu chủ đề (Topic sentence), giải thích (Explanation) và ví dụ (Example).',
                        },
                    ]
                },
                {
                    'code': 'HW-IEL03',
                    'title': 'Trọng âm từ vựng học thuật Academic Word List (AWL)',
                    'difficulty': 4,
                    'tags': ['STRESS', 'IELTS_TAG'],
                    'questions': [
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Chọn trọng âm chính của từ học thuật: a-na-ly-sis (/əˈnæl.ə.sɪs/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ AWL'],
                            'explanation': 'Danh từ analysis có trọng âm rơi vào âm tiết thứ hai: a-NA-ly-sis.',
                            'stress_syllables': ['a', 'na', 'ly', 'sis'],
                            'correct_syllable_index': 2,
                        },
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Chọn trọng âm chính của từ: me-tho-do-lo-gy (/ˌmeθ.əˈdɒl.ə.dʒi/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm từ AWL'],
                            'explanation': 'Từ tận cùng bằng -ology có trọng âm rơi vào âm tiết thứ ba: me-tho-DO-lo-gy.',
                            'stress_syllables': ['me', 'tho', 'do', 'lo', 'gy'],
                            'correct_syllable_index': 3,
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 10. LUYỆN THI TOEIC
        # =====================================================================
        spec.append({
            'name': 'TOEIC Thực chiến 750+: Part 5 & 6 Chuyên sâu',
            'description': 'Luyện từ loại, hậu tố thương mại, liên từ hợp đồng, email công sở và từ vựng tài chính chuẩn format ETS.',
            'category': 'TOEIC',
            'difficulty': 3,
            'tags': ['TOEIC_TAG', 'TOEIC_PART5', 'BUSINESS_ENGLISH', 'GRAMMAR', 'WORD_ORDER'],
            'exercises': [
                {
                    'code': 'HW-TOE01',
                    'title': 'TOEIC Part 5: Từ loại & Hậu tố thương mại (Word Form)',
                    'difficulty': 3,
                    'tags': ['TOEIC_PART5', 'WORD_FORM', 'TOEIC_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'All conference attendees must complete the registration form ___ before accessing the exhibition hall.',
                            'max_points': '1.00',
                            'topic_tags': ['Trạng từ bổ nghĩa'],
                            'explanation': 'Cần một trạng từ bổ nghĩa cho động từ "complete": chọn "promptly" (ngay lập tức).',
                            'options': [{'key': 'A', 'content': 'promptly'}, {'key': 'B', 'content': 'prompt'}, {'key': 'C', 'content': 'promptness'}, {'key': 'D', 'content': 'prompting'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': 'The board of directors expressed their full ___ for the proposed merger plan.',
                            'max_points': '1.00',
                            'topic_tags': ['Danh từ sau tính từ'],
                            'explanation': 'Sau tính từ "full" cần một danh từ: chọn "approval" (sự chấp thuận).',
                            'options': [{'key': 'A', 'content': 'approval'}, {'key': 'B', 'content': 'approve'}, {'key': 'C', 'content': 'approving'}, {'key': 'D', 'content': 'approvingly'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-TOE02',
                    'title': 'TOEIC Part 5: Liên từ & Giới từ trong văn bản hợp đồng',
                    'difficulty': 3,
                    'tags': ['TOEIC_PART5', 'GRAMMAR', 'TOEIC_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'STANDARD',
                            'prompt': '___ severe adverse weather conditions, the international flights have been temporarily delayed.',
                            'max_points': '1.00',
                            'topic_tags': ['Giới từ chỉ nguyên nhân'],
                            'explanation': 'Trước một cụm danh từ "severe adverse weather conditions" dùng giới từ "Due to".',
                            'options': [{'key': 'A', 'content': 'Due to'}, {'key': 'B', 'content': 'Although'}, {'key': 'C', 'content': 'Because'}, {'key': 'D', 'content': 'In spite'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'The warranty covers all repairs, ___ that the customer retained the original receipt.',
                            'max_points': '1.00',
                            'topic_tags': ['Liên từ điều kiện'],
                            'explanation': 'Provided that = với điều kiện là (miễn là) khách hàng giữ lại hóa đơn gốc.',
                            'options': [{'key': 'A', 'content': 'provided'}, {'key': 'B', 'content': 'providingly'}, {'key': 'C', 'content': 'suppose'}, {'key': 'D', 'content': 'as though'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-TOE03',
                    'title': 'Sắp xếp câu thông báo & Email công sở chuẩn ETS',
                    'difficulty': 3,
                    'tags': ['WORD_ORDER', 'BUSINESS_ENGLISH', 'TOEIC_TAG'],
                    'questions': [
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp câu yêu cầu trong email công việc gửi đối tác.',
                            'max_points': '1.00',
                            'topic_tags': ['Email công sở'],
                            'explanation': 'Thứ tự đúng: Please review the attached contract before signing it.',
                            'word_tokens': ['Please', 'review', 'the', 'attached', 'contract', 'before', 'signing', 'it'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'STANDARD',
                            'prompt': 'Sắp xếp thông báo nội bộ công ty về việc nộp báo cáo.',
                            'max_points': '1.00',
                            'topic_tags': ['Thông báo công ty'],
                            'explanation': 'Thứ tự đúng: Employees must submit their monthly expense reports by Friday.',
                            'word_tokens': ['Employees', 'must', 'submit', 'their', 'monthly', 'expense', 'reports', 'by', 'Friday'],
                        },
                    ]
                },
            ]
        })

        # =====================================================================
        # 11. CHỨNG CHỈ TESOL & PHƯƠNG PHÁP GIẢNG DẠY
        # =====================================================================
        spec.append({
            'name': 'TESOL Certificate: Phương pháp Giảng dạy & Quản lý lớp học tiếng Anh',
            'description': 'Lý thuyết thụ đắc ngôn ngữ thứ hai (SLA), mô hình PPP, kỹ thuật đặt câu hỏi CCQs/ICQs và thiết kế bài giảng.',
            'category': 'TESOL',
            'difficulty': 4,
            'tags': ['TESOL_TAG', 'PEDAGOGY', 'CLASSROOM_MANAGEMENT', 'WORD_ORDER', 'STRESS'],
            'exercises': [
                {
                    'code': 'HW-TES01',
                    'title': 'Second Language Acquisition (SLA) & Krashen’s Hypotheses',
                    'difficulty': 4,
                    'tags': ['PEDAGOGY', 'TESOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'According to Stephen Krashen, language acquisition occurs best when learners receive input that is at:',
                            'max_points': '1.00',
                            'topic_tags': ['Lý thuyết SLA'],
                            'explanation': 'Krashen đề xuất giả thuyết "Comprehensible Input" ở mức i + 1 (cao hơn một bậc so với trình độ hiện tại).',
                            'options': [{'key': 'A', 'content': 'i + 1 level'}, {'key': 'B', 'content': 'i - 1 level'}, {'key': 'C', 'content': 'native level'}, {'key': 'D', 'content': 'i + 5 level'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'In TESOL methodology, reducing TTT (Teacher Talking Time) is primarily aimed at:',
                            'max_points': '1.00',
                            'topic_tags': ['Quản lý lớp học'],
                            'explanation': 'Giảm thời gian giáo viên nói (TTT) nhằm tối đa hóa thời gian học sinh luyện tập giao tiếp (STT - Student Talking Time).',
                            'options': [{'key': 'A', 'content': 'increasing Student Talking Time (STT)'}, {'key': 'B', 'content': 'making the teacher less tired'}, {'key': 'C', 'content': 'eliminating student errors completely'}, {'key': 'D', 'content': 'finishing the textbook faster'}],
                            'correct_options': ['A'],
                        },
                    ]
                },
                {
                    'code': 'HW-TES02',
                    'title': 'Kỹ thuật CCQs, ICQs & Mô hình bài giảng PPP',
                    'difficulty': 4,
                    'tags': ['CLASSROOM_MANAGEMENT', 'TESOL_TAG'],
                    'questions': [
                        {
                            'type': 'SINGLE_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'What does CCQ stand for in English language teaching pedagogy?',
                            'max_points': '1.00',
                            'topic_tags': ['Kỹ thuật CCQ'],
                            'explanation': 'CCQ là viết tắt của Concept Checking Question (Câu hỏi kiểm tra khái niệm/độ hiểu nghĩa).',
                            'options': [{'key': 'A', 'content': 'Concept Checking Question'}, {'key': 'B', 'content': 'Classroom Control Quiz'}, {'key': 'C', 'content': 'Core Curriculum Query'}, {'key': 'D', 'content': 'Communicative Competence Questionnaire'}],
                            'correct_options': ['A'],
                        },
                        {
                            'type': 'WORD_ORDER',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Sắp xếp quy trình 5 bước sư phạm khi giáo viên triển khai một hoạt động nhóm giao tiếp.',
                            'max_points': '1.00',
                            'topic_tags': ['Quy trình giảng dạy'],
                            'explanation': 'Thứ tự đúng: Set context, give instructions, model task, monitor groups, give feedback.',
                            'word_tokens': ['Set context', 'give instructions', 'model task', 'monitor groups', 'give feedback'],
                        },
                    ]
                },
                {
                    'code': 'HW-TES03',
                    'title': 'Ngữ âm học & Trọng âm từ trong Sư phạm (TESOL Phonology)',
                    'difficulty': 4,
                    'tags': ['STRESS', 'PEDAGOGY', 'TESOL_TAG'],
                    'questions': [
                        {
                            'type': 'STRESS_CHOICE',
                            'skill': 'READING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Identify the primary stressed syllable for teaching intonation: in-to-na-tion (/ˌɪn.təˈneɪ.ʃən/).',
                            'max_points': '1.00',
                            'topic_tags': ['Trọng âm thuật ngữ sư phạm'],
                            'explanation': 'Hậu tố -tion làm trọng âm rơi vào âm tiết liền kề trước nó: in-to-NA-tion.',
                            'stress_syllables': ['in', 'to', 'na', 'tion'],
                            'correct_syllable_index': 3,
                        },
                        {
                            'type': 'TEXT',
                            'skill': 'WRITING',
                            'difficulty': 'CHALLENGE',
                            'prompt': 'Write 3 Concept Checking Questions (CCQs) for the sentence: "If she had left earlier, she wouldn’t have missed the flight."',
                            'max_points': '2.00',
                            'topic_tags': ['Thiết kế CCQ'],
                            'explanation': 'Ví dụ CCQs: 1) Did she leave early? (No). 2) Did she miss the flight? (Yes). 3) Is this talking about the past or present? (The past).',
                        },
                    ]
                },
            ]
        })

        return spec
