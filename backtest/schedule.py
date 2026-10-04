"""Shared calendar period identifiers; missing Mondays do not skip a week."""


def period(day, frequency):
    if frequency == "daily":
        return str(day.date() if hasattr(day, "date") else day)
    if frequency == "weekly":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    if frequency == "monthly":
        return f"{day.year}-{day.month:02d}"
    raise ValueError("Rebalance must be daily, weekly, or monthly")
