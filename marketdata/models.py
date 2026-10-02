"""ETF identifiers and adjusted daily closing prices."""

from django.db import models


class Asset(models.Model):
    ticker = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=120, blank=True)

    def __str__(self) -> str:
        return self.ticker


class PricePoint(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    adjusted_close = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["asset", "date"], name="unique_asset_date")]

    def __str__(self) -> str:
        return f"{self.asset.ticker} {self.date}"
