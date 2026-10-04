from datetime import date
import pytest
from backtest.schedule import period
from research.models import Experiment, Job
from research.services import freeze_frame, queue_experiment, trash_run


def test_week_period_holiday_and_year():
    assert period(date(2024, 1, 2), "weekly") == period(date(2024, 1, 5), "weekly")
    assert period(date(2024, 12, 30), "weekly") == "2025-W01"


@pytest.mark.django_db
def test_trash_cancels_and_restore_preserves(prices):
    dataset = freeze_frame(prices)
    queued = queue_experiment({"dataset": dataset.pk, "method": "equal_weight"})
    trash_run(queued["run_id"])
    assert Job.objects.get(pk=queued["job_id"]).status == "canceled"
    trash_run(queued["run_id"], restore=True)
    assert Experiment.objects.get(pk=queued["run_id"]).trashed_at is None


@pytest.mark.django_db
def test_running_delete_blocked(prices):
    run = Experiment.objects.create(dataset=freeze_frame(prices), status="running")
    with pytest.raises(ValueError, match="running"):
        trash_run(run.pk)
