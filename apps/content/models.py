import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Exam(Entity):
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ExamVersion(Entity):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        PUBLISHED = "PUBLISHED"
        ARCHIVED = "ARCHIVED"

    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "number"], name="content_version_number_unique")]


class Asset(Entity):
    class Purpose(models.TextChoices):
        PROMPT_AUDIO = "PROMPT_AUDIO"
        RESPONSE_AUDIO = "RESPONSE_AUDIO"
        PROMPT_IMAGE = "PROMPT_IMAGE"

    class Status(models.TextChoices):
        UPLOADING = "UPLOADING"
        READY = "READY"
        REJECTED = "REJECTED"
        DELETING = "DELETING"
        DELETED = "DELETED"

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    object_key = models.CharField(max_length=512, unique=True)
    original_name = models.CharField(max_length=255, blank=True, default="")
    detected_mime = models.CharField(max_length=80, null=True, blank=True)
    bytes = models.PositiveBigIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADING)
    expires_at = models.DateTimeField(null=True, blank=True)


class Passage(Entity):
    version = models.ForeignKey(ExamVersion, on_delete=models.CASCADE, related_name="passages")
    ref = models.CharField(max_length=40)
    text_body = models.TextField(blank=True, default="")
    audio_asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True)
    transcript = models.TextField(blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "ref"], name="content_passage_ref_unique")]


class Question(Entity):
    class Type(models.TextChoices):
        SINGLE_CHOICE = "SINGLE_CHOICE"
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
        WORD_ORDER = "WORD_ORDER"
        STRESS_CHOICE = "STRESS_CHOICE"
        MATCH_IMAGE = "MATCH_IMAGE"
        SENTENCE_TRANSFORM = "SENTENCE_TRANSFORM"
        TEXT = "TEXT"
        AUDIO = "AUDIO"

    class Skill(models.TextChoices):
        READING = "READING"
        LISTENING = "LISTENING"
        WRITING = "WRITING"
        SPEAKING = "SPEAKING"

    class Difficulty(models.TextChoices):
        FOUNDATION = "FOUNDATION"
        STANDARD = "STANDARD"
        CHALLENGE = "CHALLENGE"

    version = models.ForeignKey(ExamVersion, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField()
    type = models.CharField(max_length=20, choices=Type.choices)
    skill = models.CharField(max_length=12, choices=Skill.choices)
    difficulty = models.CharField(max_length=12, choices=Difficulty.choices)
    prompt = models.TextField()
    max_points = models.DecimalField(max_digits=8, decimal_places=2)
    passage = models.ForeignKey(Passage, on_delete=models.PROTECT, null=True, blank=True, related_name="questions")
    explanation = models.TextField(blank=True, default="")
    pirate_game = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["version", "position"], name="content_question_position_unique"),
            models.CheckConstraint(condition=Q(position__gte=1, position__lte=100), name="content_question_position_range"),
            models.CheckConstraint(condition=Q(max_points__gte=Decimal("0.01"), max_points__lte=Decimal("100")), name="content_question_points_range"),
            models.CheckConstraint(condition=(Q(type__in=["SINGLE_CHOICE", "MULTIPLE_CHOICE", "STRESS_CHOICE", "MATCH_IMAGE"], skill__in=["READING", "LISTENING"]) | Q(type__in=["WORD_ORDER", "SENTENCE_TRANSFORM"], skill__in=["READING", "WRITING"]) | Q(type="TEXT", skill="WRITING") | Q(type="AUDIO", skill="SPEAKING")), name="content_question_type_skill"),
        ]


class MatchImage(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="match_images")
    image_asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["question", "position"], name="match_image_position_unique"), models.UniqueConstraint(fields=["question", "image_asset"], name="match_image_asset_unique")]


class MatchWord(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="match_words")
    text = models.CharField(max_length=200)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["question", "position"], name="match_word_position_unique")]


class MatchKey(Entity):
    image = models.OneToOneField(MatchImage, on_delete=models.CASCADE, related_name="answer_key")
    word = models.OneToOneField(MatchWord, on_delete=models.CASCADE, related_name="answer_key")


class QuestionOption(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    key = models.CharField(max_length=1)
    position = models.PositiveSmallIntegerField()
    content = models.TextField()

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["question", "key"], name="content_option_key_unique"), models.UniqueConstraint(fields=["question", "position"], name="content_option_position_unique")]


class AnswerKeyOption(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answer_keys")
    option = models.ForeignKey(QuestionOption, on_delete=models.CASCADE, related_name="answer_keys")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["question", "option"], name="content_answer_option_unique")]


class RubricCriterion(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="criteria")
    key = models.CharField(max_length=40)
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=120)
    level_descriptions = models.JSONField()

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["question", "key"], name="content_criterion_key_unique"), models.UniqueConstraint(fields=["question", "position"], name="content_criterion_position_unique")]


class Tag(Entity):
    class Kind(models.TextChoices):
        TOPIC = "TOPIC"
        ERROR = "ERROR"

    kind = models.CharField(max_length=5, choices=Kind.choices)
    skill = models.CharField(max_length=12, choices=Question.Skill.choices)
    name = models.CharField(max_length=100)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "skill", "name"], name="content_tag_unique")]


class QuestionTag(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="question_tags")
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT, related_name="question_tags")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["question", "tag"], name="content_question_tag_unique")]


class ImportBatch(Entity):
    class Status(models.TextChoices):
        PREVIEW = "PREVIEW"
        COMMITTED = "COMMITTED"
        EXPIRED = "EXPIRED"

    kind = models.CharField(max_length=12, default="QUESTIONS")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payload_json = models.JSONField()
    source_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVIEW)
    expires_at = models.DateTimeField()
    committed_version = models.ForeignKey(ExamVersion, on_delete=models.PROTECT, null=True, blank=True)
    committed_target_id = models.UUIDField(null=True, blank=True)


class Course(Entity):
    class Category(models.TextChoices):
        PRIMARY = 'PRIMARY', 'Tiểu học (Lớp 1-5)'
        SECONDARY = 'SECONDARY', 'THCS (Lớp 6-9)'
        HIGH_SCHOOL = 'HIGH_SCHOOL', 'THPT (Lớp 10-12)'
        ENTRANCE_10 = 'ENTRANCE_10', 'Luyện thi vào 10'
        NATIONAL_EXAM = 'NATIONAL_EXAM', 'Luyện thi THPT QG'
        IELTS = 'IELTS', 'Luyện thi IELTS'
        TOEIC = 'TOEIC', 'Luyện thi TOEIC'
        TESOL = 'TESOL', 'Chứng chỉ TESOL'
        SEMESTER = 'SEMESTER', 'Ôn tập học kỳ'
        OTHER = 'OTHER', 'Khác'

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    difficulty = models.PositiveSmallIntegerField(default=1)
    is_published = models.BooleanField(default=False)
    is_sample = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='courses')
    english_classes = models.ManyToManyField('classes.EnglishClass', blank=True, related_name='courses')
    tags = models.ManyToManyField('CourseTag', blank=True, related_name='courses')

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            models.CheckConstraint(condition=Q(difficulty__gte=1, difficulty__lte=5), name='course_difficulty_range'),
            models.CheckConstraint(condition=Q(category__in=['PRIMARY', 'SECONDARY', 'HIGH_SCHOOL', 'ENTRANCE_10', 'NATIONAL_EXAM', 'IELTS', 'TOEIC', 'TESOL', 'SEMESTER', 'OTHER']), name='course_category_valid'),
            models.UniqueConstraint(fields=['created_by', 'name'], name='course_owner_name_unique'),
        ]


class CourseTag(Entity):
    class Kind(models.TextChoices):
        SKILL = 'SKILL', 'Kỹ năng'
        GRAMMAR = 'GRAMMAR', 'Ngữ pháp'
        VOCAB = 'VOCAB', 'Từ vựng'
        EXAM = 'EXAM', 'Ôn thi'

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    class Meta:
        ordering = ['kind', 'name']
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=['SKILL', 'GRAMMAR', 'VOCAB', 'EXAM']), name='course_tag_kind_valid'),
            models.UniqueConstraint(fields=['kind', 'name'], name='course_tag_name_kind_unique'),
        ]


class CourseExercise(Entity):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='exercises')
    assignment = models.ForeignKey('assignments.Assignment', on_delete=models.PROTECT, related_name='course_exercises')
    difficulty = models.PositiveSmallIntegerField(default=1)
    tags = models.ManyToManyField(CourseTag, blank=True, related_name='exercises')

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['course', 'assignment'], name='course_exercise_unique'),
            models.CheckConstraint(condition=Q(difficulty__gte=1, difficulty__lte=5), name='course_exercise_difficulty_range'),
        ]
