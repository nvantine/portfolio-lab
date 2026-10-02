"""Persist optimization inputs and outputs for reproducibility."""

from django.db import models


class OptimizationRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    parameters = models.JSONField(default=dict)
    input_snapshot = models.JSONField(default=dict)
    results = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Optimization run {self.pk}"
