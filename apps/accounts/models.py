import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "OWNER"
        STUDENT = "STUDENT"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        SUSPENDED = "SUSPENDED"
        ARCHIVED = "ARCHIVED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=10, choices=Role.choices)
    display_name = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    auth_epoch = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role"], condition=Q(role="OWNER"), name="one_owner"),
            models.CheckConstraint(condition=Q(role__in=["OWNER", "STUDENT"]), name="accounts_role_valid"),
            models.CheckConstraint(condition=Q(status__in=["ACTIVE", "SUSPENDED", "ARCHIVED"]), name="accounts_status_valid"),
        ]


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, primary_key=True, related_name="student_profile")
    student_ref = models.CharField(max_length=32, unique=True)
    owner_note = models.TextField(blank=True, default="")
    parent_phone = models.CharField(max_length=15, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AccessCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name="access_codes")
    code_digest = models.CharField(max_length=64, unique=True)
    key_version = models.PositiveSmallIntegerField()
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student"], condition=Q(revoked_at__isnull=True), name="one_active_code_per_student")]


class LoginBucket(models.Model):
    bucket_key = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bucket_key", "window_start"], name="unique_login_bucket")]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name="audit_events")
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80)
    target_id = models.UUIDField(null=True)
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict)
    request_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["target_type", "target_id", "created_at"])]


class PrivacyRequest(models.Model):
    class Kind(models.TextChoices):
        EXPORT = "EXPORT"
        ERASE = "ERASE"

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED"
        APPROVED = "APPROVED"
        COMPLETED = "COMPLETED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name="privacy_requests")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="requested_privacy_requests")
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField()
    report = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=["EXPORT", "ERASE"]), name="privacy_kind_valid"),
            models.CheckConstraint(condition=Q(status__in=["REQUESTED", "APPROVED", "COMPLETED"]), name="privacy_status_valid"),
        ]
