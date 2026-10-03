import uuid

from django.db import models


class Dataset(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=120)
    digest = models.CharField(max_length=64, unique=True)
    snapshot = models.JSONField()
    manifest = models.JSONField(default=dict)


class StrategyVersion(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=120)
    digest = models.CharField(max_length=64, unique=True)
    source = models.TextField()


class Experiment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT)
    strategy = models.ForeignKey(StrategyVersion, null=True, blank=True, on_delete=models.PROTECT)
    hypothesis = models.TextField(blank=True)
    config = models.JSONField(default=dict)
    provenance = models.JSONField(default=dict)
    results = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="queued")
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    kind = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="queued")
    experiment = models.OneToOneField(Experiment, null=True, on_delete=models.PROTECT)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)
