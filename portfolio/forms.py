from django import forms
from research.models import Dataset, StrategyVersion
from strategies.catalog import METHODS, COVARIANCES


class ExperimentForm(forms.Form):
    dataset = forms.ModelChoiceField(queryset=Dataset.objects.all(), widget=forms.Select(attrs={"data-live-options": ""}))
    method = forms.ChoiceField(choices=[(name, name) for name in METHODS])
    strategy = forms.ModelChoiceField(queryset=StrategyVersion.objects.all(), required=False, widget=forms.Select(attrs={"data-live-options": ""}), help_text="Optional saved Python or recipe version; overrides the method selection.")
    covariance = forms.ChoiceField(choices=[(name, name) for name in COVARIANCES], initial="ledoit_wolf")
    lookback = forms.IntegerField(min_value=10, max_value=2520, initial=126)
    cap = forms.FloatField(min_value=.01, max_value=1, initial=.2)
    cost_bps = forms.FloatField(min_value=0, max_value=1000, initial=10)
    risk_aversion = forms.FloatField(min_value=0, initial=10)
    rebalance = forms.ChoiceField(choices=[("monthly", "Monthly"), ("weekly", "Weekly"), ("daily", "Daily")])
    views = forms.JSONField(required=False, initial={}, help_text='Absolute daily views: {"SPY": 0.0003}')
    seed = forms.IntegerField(initial=42)
    hypothesis = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    window = forms.ChoiceField(choices=[("validation", "Validation"), ("holdout", "Final holdout")], help_text="Repeated holdout use weakens its value as independent evidence.")
    advanced = forms.JSONField(required=False, initial={}, help_text="Additional parameters, e.g. fixed_weights, turnover_limit, ewma_decay, allow_short, gross_limit, short_cap, borrow_rate.")
    allow_short = forms.BooleanField(required=False, help_text="Backtests only; not supported for account execution.")
    net_exposure = forms.FloatField(initial=1, min_value=0)
    gross_limit = forms.FloatField(initial=1.5, min_value=0)
    short_cap = forms.FloatField(initial=.2, min_value=0, max_value=1)
    borrow_rate = forms.FloatField(initial=.03, min_value=0, help_text="Annual rate as a decimal, e.g. .03 = 3%; accrues actual days / 360 on shorts.")
    fixed_weights = forms.JSONField(required=False, initial={}, help_text='For fixed_weights method: {"AAPL": 0.5, "MSFT": 0.5}. Remaining long-only allocation is cash.')

    def clean_advanced(self):
        value = self.cleaned_data.get("advanced") or {}
        if not isinstance(value, dict): raise forms.ValidationError("Additional parameters must be an object")
        return value

    def config(self):
        data = self.cleaned_data
        result = {"dataset": data["dataset"].pk, "method": data["method"], "seed": data["seed"], "window": data["window"], "hypothesis": data["hypothesis"], "parameters": {key: data[key] for key in ("covariance", "lookback", "cap", "cost_bps", "risk_aversion", "rebalance")} | {"views": data.get("views") or {}} | (data.get("advanced") or {})}
        if data.get("strategy"):
            result["strategy"] = data["strategy"].digest
        result["parameters"].update({key: data[key] for key in ("allow_short", "net_exposure", "gross_limit", "short_cap", "borrow_rate")})
        if data.get("fixed_weights"): result["parameters"]["fixed_weights"] = data["fixed_weights"]
        return result


class DatasetForm(forms.Form):
    name = forms.CharField(max_length=120)
    tickers = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), help_text="Paste actual ticker symbols, e.g. AAPL, MSFT, NVDA. Descriptions such as 'top 100 Nasdaq by market cap' are not a ticker list.")
    start = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}), help_text="Use at least a year of prices; saving requires 250 common trading sessions.")
    end = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}), help_text="Today is allowed; incomplete current-day bars are excluded automatically.")
    feed = forms.ChoiceField(choices=[("iex", "IEX — free account default"), ("sip", "SIP — requires entitlement")])
    benchmark = forms.CharField(required=False, initial="SPY")

    def clean_tickers(self):
        from research.datasets import symbols
        try: return symbols(self.cleaned_data["tickers"])
        except ValueError as exc: raise forms.ValidationError(str(exc)) from None

    def clean_benchmark(self):
        from research.datasets import symbols
        value = self.cleaned_data["benchmark"]
        try: return symbols([value])[0] if value else ""
        except ValueError as exc: raise forms.ValidationError(str(exc)) from None


class RecipeForm(forms.Form):
    from strategies.recipes import SIGNALS, ALLOCATORS
    name = forms.CharField(max_length=120)
    signal = forms.ChoiceField(choices=[(v, v) for v in SIGNALS])
    allocator = forms.ChoiceField(choices=[(v, v) for v in ALLOCATORS])
    overlay = forms.ChoiceField(choices=[("none", "None"), ("volatility_target", "Volatility target")])
    parameters = forms.JSONField(initial={"lookback": 126, "cap": .2, "covariance": "ledoit_wolf", "rebalance": "weekly"})
