"""Escaped, readable tables for nested numerical results."""
import json
from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def pretty(value):
    if isinstance(value, dict):
        rows = "".join(str(format_html("<tr><th>{}</th><td>{}</td></tr>", str(key).replace("_", " "), pretty(item))) for key, item in value.items())
        return mark_safe(f"<table>{rows}</table>")
    if isinstance(value, (list, tuple)):
        return mark_safe("<ul>" + "".join(str(format_html("<li>{}</li>", pretty(item))) for item in value) + "</ul>")
    if isinstance(value, float):
        return escape(f"{value:.6g}")
    return escape("—" if value is None else str(value))


@register.filter
def json_text(value):
    return json.dumps(value, indent=2, default=str)
