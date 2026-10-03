from django.conf import settings
from django.db import models

from research.models import Experiment


class PaperSession(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)
    fingerprint = models.CharField(max_length=64)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=10000)
    active = models.BooleanField(default=True)
    revoked = models.BooleanField(default=False)
    observations = models.JSONField(default=list)
    slot = models.PositiveSmallIntegerField(default=1, editable=False)
    target_month = models.CharField(max_length=7, blank=True)
    targets = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["slot"], condition=models.Q(revoked=False), name="one_unrevoked_paper_session")]


class PaperDecision(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(PaperSession, on_delete=models.PROTECT)
    trading_date = models.DateField()
    digest = models.CharField(max_length=64, unique=True)
    inputs = models.JSONField()
    targets = models.JSONField()


class PaperOrder(models.Model):
    session = models.ForeignKey(PaperSession, on_delete=models.PROTECT)
    decision = models.ForeignKey(PaperDecision, null=True, on_delete=models.PROTECT)
    client_order_id = models.CharField(max_length=48, unique=True)
    trading_date = models.DateField()
    symbol = models.CharField(max_length=12)
    side = models.CharField(max_length=4)
    qty = models.PositiveIntegerField()
    limit_price = models.DecimalField(max_digits=12, decimal_places=2)
    broker_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default="intent")
    filled_qty = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    filled_price = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    error = models.TextField(blank=True)
