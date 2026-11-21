import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    response = models.OneToOneField('assignments.Response', on_delete=models.PROTECT, related_name='grade')
    source = models.CharField(max_length=10, choices=[('AUTO', 'AUTO'), ('TEACHER', 'TEACHER')])
    points = models.DecimalField(max_digits=8, decimal_places=2)
    feedback = models.TextField(blank=True, default='')
    revision = models.PositiveIntegerField(default=1)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    graded_at = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(points__gte=0), name='grade_nonnegative')]


class CriterionScore(models.Model):
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='criterion_scores')
    criterion = models.ForeignKey('content.RubricCriterion', on_delete=models.PROTECT)
    level = models.PositiveSmallIntegerField()
    note = models.TextField(blank=True, default='')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['grade', 'criterion'], name='unique_grade_criterion'), models.CheckConstraint(condition=Q(level__lte=4), name='criterion_level_max')]


class GradeHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='history')
    revision = models.PositiveIntegerField()
    previous = models.JSONField()
    next = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['grade', 'revision'], name='unique_grade_history_revision')]


class ErrorOccurrence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    response = models.ForeignKey('assignments.Response', on_delete=models.PROTECT, related_name='errors')
    tag = models.ForeignKey('content.Tag', on_delete=models.PROTECT)
    source = models.CharField(max_length=10)
    confidence = models.CharField(max_length=10)
    note = models.TextField(blank=True, default='')
    start_char = models.PositiveIntegerField(null=True, blank=True)
    end_char = models.PositiveIntegerField(null=True, blank=True)
    start_ms = models.PositiveIntegerField(null=True, blank=True)
    end_ms = models.PositiveIntegerField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['response', 'tag'], name='unique_response_error')]


class ErrorReview(models.Model):
    occurrence = models.OneToOneField(ErrorOccurrence, on_delete=models.PROTECT, primary_key=True)
    student_reviewed_at = models.DateTimeField(null=True, blank=True)
    teacher_reviewed_at = models.DateTimeField(null=True, blank=True)
    teacher_note = models.TextField(blank=True, default='')


class GradeRelease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey('assignments.Attempt', on_delete=models.PROTECT, related_name='grade_releases')
    number = models.PositiveIntegerField()
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    published_at = models.DateTimeField(auto_now_add=True)
    total_points = models.DecimalField(max_digits=8, decimal_places=2)
    max_points = models.DecimalField(max_digits=8, decimal_places=2)
    snapshot = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'number'], name='unique_release_number')]
