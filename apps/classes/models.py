import uuid
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value


def period():
    return Func(F("start_at"), F("end_at"), Value("[)"), function="TSTZRANGE", output_field=DateTimeRangeField())


class School(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SchoolClass(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="classes")
    school_year = models.CharField(max_length=9)
    grade = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=40)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "school_year", "grade", "name"], name="unique_school_class"), models.CheckConstraint(condition=Q(grade__gte=1, grade__lte=12), name="school_class_grade_valid")]


class EnglishClass(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    school_year = models.CharField(max_length=9)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SchoolMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="school_memberships")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="memberships")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end_at__isnull=True) | Q(end_at__gt=F("start_at")), name="school_membership_valid_range"), ExclusionConstraint(name="school_membership_no_overlap", expressions=[("student", RangeOperators.EQUAL), (period(), RangeOperators.OVERLAPS)])]


class EnglishMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="english_memberships")
    english_class = models.ForeignKey(EnglishClass, on_delete=models.PROTECT, related_name="memberships")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end_at__isnull=True) | Q(end_at__gt=F("start_at")), name="english_membership_valid_range"), ExclusionConstraint(name="english_membership_no_overlap", expressions=[("student", RangeOperators.EQUAL), ("english_class", RangeOperators.EQUAL), (period(), RangeOperators.OVERLAPS)])]
