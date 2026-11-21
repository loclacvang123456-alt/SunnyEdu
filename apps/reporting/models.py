import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F

class RankingPeriod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    school_year = models.CharField(max_length=9)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    scope = models.CharField(max_length=16, choices=[(x,x) for x in ('ENGLISH_CLASS','SCHOOL_CLASS','SCHOOL_GRADE','SCHOOL')])
    scope_target = models.JSONField()
    status = models.CharField(max_length=10, default='DRAFT', choices=[(x,x) for x in ('DRAFT','ACTIVE','FINAL','STALE','INVALID')])
    show_peers = models.BooleanField(default=False)
    current_snapshot = models.ForeignKey('RankingSnapshot', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    revision = models.PositiveIntegerField(default=0)
    invalid_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end_at__gt=F('start_at')), name='ranking_valid_dates'), models.CheckConstraint(condition=Q(show_peers=False)|Q(scope='ENGLISH_CLASS'), name='ranking_peer_scope')]

class RankingAssignment(models.Model):
    period = models.ForeignKey(RankingPeriod, on_delete=models.PROTECT, related_name='assignment_links')
    assignment = models.ForeignKey('assignments.Assignment', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['period','assignment'], name='ranking_unique_assignment')]

class RankingMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(RankingPeriod, on_delete=models.PROTECT, related_name='members')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    alias = models.CharField(max_length=24)
    cohort_snapshot = models.JSONField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['period','student'], name='ranking_unique_student'), models.UniqueConstraint(fields=['period','alias'], name='ranking_unique_alias')]

class RankingSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey(RankingPeriod, on_delete=models.PROTECT, related_name='snapshots')
    number = models.PositiveIntegerField()
    published_at = models.DateTimeField()
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['period','number'], name='ranking_unique_snapshot')]

class RankingEntry(models.Model):
    snapshot = models.ForeignKey(RankingSnapshot, on_delete=models.PROTECT, related_name='entries')
    member = models.ForeignKey(RankingMember, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=[('RANKED','RANKED'),('INCOMPLETE','INCOMPLETE')])
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    source_release_ids = models.JSONField(default=list)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['snapshot','member'], name='ranking_unique_entry'), models.CheckConstraint(condition=(Q(status='INCOMPLETE',score__isnull=True,rank__isnull=True)|Q(status='RANKED',score__gte=0,score__lte=100,rank__gte=1,score__isnull=False,rank__isnull=False)), name='ranking_valid_entry')]
