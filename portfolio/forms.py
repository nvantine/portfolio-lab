from django import forms
from research.models import Dataset
from strategies.catalog import METHODS, COVARIANCES


class ExperimentForm(forms.Form):
    dataset = forms.ModelChoiceField(queryset=Dataset.objects.all())
    method = forms.ChoiceField(choices=[(name, name) for name in METHODS])
    covariance = forms.ChoiceField(choices=[(name, name) for name in COVARIANCES], initial="ledoit_wolf")
    lookback = forms.IntegerField(min_value=10, max_value=2520, initial=126)
    cap = forms.FloatField(min_value=.01, max_value=1, initial=.2)
    cost_bps = forms.FloatField(min_value=0, max_value=1000, initial=10)
    risk_aversion = forms.FloatField(min_value=0, initial=10)
    rebalance = forms.ChoiceField(choices=[("monthly", "Monthly"), ("weekly", "Weekly"), ("daily", "Daily")])
    views = forms.JSONField(required=False, initial={}, help_text='Absolute daily views: {"SPY": 0.0003}')
    seed = forms.IntegerField(initial=42)
    hypothesis = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def config(self):
        data = self.cleaned_data
        return {"dataset": data["dataset"].pk, "method": data["method"], "seed": data["seed"], "hypothesis": data["hypothesis"], "parameters": {key: data[key] for key in ("covariance", "lookback", "cap", "cost_bps", "risk_aversion", "rebalance")} | {"views": data.get("views") or {}}}
