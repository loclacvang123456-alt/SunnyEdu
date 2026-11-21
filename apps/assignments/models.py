import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Assignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey('content.ExamVersion', on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=9, unique=True)
    mode = models.CharField(max_length=8, choices=[('PRACTICE', 'Luyện tập'), ('EXAM', 'Bài kiểm tra')], default='PRACTICE')
    game_feedback_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default='DRAFT')
    opens_at = models.DateTimeField()
    due_at = models.DateTimeField()
    late_until = models.DateTimeField()
    late_policy = models.CharField(max_length=5, default='ALLOW')
    revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    answers_released_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)
    classes = models.ManyToManyField('classes.EnglishClass', through='AssignmentClass')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(opens_at__lt=models.F('due_at')) & Q(due_at__lte=models.F('late_until')), name='assignment_valid_dates'), models.CheckConstraint(condition=Q(mode__in=['PRACTICE', 'EXAM']), name='assignment_mode_valid'), models.CheckConstraint(condition=Q(game_feedback_enabled=False) | Q(mode='PRACTICE'), name='game_feedback_practice_only')]


class AssignmentClass(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT)
    english_class = models.ForeignKey('classes.EnglishClass', on_delete=models.PROTECT)
    due_at = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    assigned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment', 'english_class'], name='unique_assignment_class')]


class AssignmentRecipient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name='recipients')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    state = models.CharField(max_length=10, default='ASSIGNED')
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_at_override = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    exempt_reason = models.TextField(blank=True)
    school_class = models.ForeignKey('classes.SchoolClass', null=True, blank=True, on_delete=models.PROTECT)
    school = models.ForeignKey('classes.School', null=True, blank=True, on_delete=models.PROTECT)
    grade = models.PositiveSmallIntegerField(null=True, blank=True)
    school_year = models.CharField(max_length=9, blank=True)
    school_name_snapshot = models.CharField(max_length=160, blank=True)
    school_class_name_snapshot = models.CharField(max_length=40, blank=True)
    current_attempt = models.ForeignKey('Attempt', null=True, blank=True, on_delete=models.PROTECT, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment', 'student'], name='unique_assignment_recipient')]


class RecipientEnglishClass(models.Model):
    recipient = models.ForeignKey(AssignmentRecipient, on_delete=models.PROTECT)
    english_class = models.ForeignKey('classes.EnglishClass', on_delete=models.PROTECT)
    class_name_snapshot = models.CharField(max_length=120)
    school_year_snapshot = models.CharField(max_length=9)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['recipient', 'english_class'], name='unique_recipient_class')]


class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(AssignmentRecipient, on_delete=models.PROTECT, related_name='attempts')
    attempt_no = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, default='IN_PROGRESS')
    revision = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    due_at_at_submit = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    graded_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    replacement_reason = models.TextField(blank=True)
    visibility_reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['recipient', 'attempt_no'], name='unique_attempt_number'), models.UniqueConstraint(fields=['recipient'], condition=Q(status='IN_PROGRESS'), name='unique_active_attempt'), models.CheckConstraint(condition=Q(attempt_no__gte=1, attempt_no__lte=5), name='attempt_number_range')]


class AttemptVisibilityEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='visibility_events')
    duration_ms = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    @property
    def duration_seconds(self):
        return round(self.duration_ms / 1000, 1)


class Response(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT, related_name='responses')
    question = models.ForeignKey('content.Question', on_delete=models.PROTECT)
    text_answer = models.TextField(blank=True)
    ordered_option_ids = models.JSONField(default=list, blank=True)
    match_pairs = models.JSONField(default=list, blank=True)
    audio_asset = models.ForeignKey('content.Asset', null=True, blank=True, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=0)
    options = models.ManyToManyField('content.QuestionOption', through='ResponseOption')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'question'], name='unique_response_question')]


class ResponseOption(models.Model):
    response = models.ForeignKey(Response, on_delete=models.PROTECT)
    option = models.ForeignKey('content.QuestionOption', on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['response', 'option'], name='unique_response_option')]


class PracticeShot(models.Model):
    response = models.OneToOneField(Response, on_delete=models.PROTECT, related_name='practice_shot')
    option = models.ForeignKey('content.QuestionOption', on_delete=models.PROTECT)
    idempotency_key = models.UUIDField(unique=True)
    expected_revision = models.PositiveIntegerField()
    response_revision = models.PositiveIntegerField()
    attempt_revision = models.PositiveIntegerField()
    correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)


class SubmissionRequest(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT)
    idempotency_key = models.UUIDField()
    payload_digest = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'idempotency_key'], name='unique_submission_key')]
