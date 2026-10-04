"""Original text reports. User-authored Markdown is rendered through a sanitizer."""
import bleach
import markdown


def safe_markdown(text):
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return bleach.clean(html, tags=["p", "br", "pre", "code", "strong", "em", "h1", "h2", "h3", "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "th", "td"], attributes={}, strip=True)


def report(run):
    lines = ["# Portfolio Lab experiment", f"\nRun: `{run.pk}`", f"\nStatus: {run.status}", f"\nMethod: {run.config.get('method')}", f"\nDataset SHA-256: `{run.dataset.digest}`", f"\nStrategy SHA-256: `{run.strategy.digest if run.strategy else run.provenance.get('source_digest')}`", f"\nWindow: {run.config.get('window')}", "\n## Hypothesis", run.hypothesis, "\n## Metrics", "\n| Metric | Value |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in run.results.get("metrics", {}).items())
    lines.extend(["\n## Interpretation", "Daily stock/ETF close simulation with one-session execution delay, cash, and proportional costs. Signed research charges configured borrow and financing rates. Caps constrain targets; weights drift between rebalances. Annualization uses 252 sessions. Sharpe uses zero risk-free rate. Bootstrap intervals describe this sample and do not correct selection across repeated trials.", "\nNo result here establishes future profitability. Physical-measure simulations are descriptive, not an alpha model. Venue bars and adjusted closes do not represent executable quotes.", "\n## Reproducibility", "```json\n" + __import__("json").dumps({"config": run.config, "provenance": run.provenance}, indent=2) + "\n```"])
    return "\n".join(lines)
