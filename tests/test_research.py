import json
import numpy as np
import pandas as pd
import pytest
from research.models import Dataset, Experiment, Job
from research.services import freeze_frame, materialize, queue_experiment, register_strategy, run_experiment
from research.jobs import work
from portfolio_lab.cli import dispatch


@pytest.fixture
def prices():
    rng = np.random.default_rng(7)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.001, .01, (420, 6)), axis=0)), index=pd.bdate_range("2020-01-01", periods=420), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])


@pytest.mark.django_db
def test_freeze_reproducible_and_tamper_detection(prices):
    dataset = freeze_frame(prices)
    assert freeze_frame(prices).pk == dataset.pk
    pd.testing.assert_frame_equal(materialize(dataset), prices.sort_index(axis=1), check_freq=False)
    dataset.snapshot["prices"][0][0] = 999
    with pytest.raises(ValueError, match="integrity"):
        materialize(dataset)


@pytest.mark.django_db
def test_queue_worker_and_shared_dispatch(prices, settings, tmp_path):
    settings.LAB_DATA_DIR = tmp_path
    dataset = freeze_frame(prices)
    config = {"dataset": dataset.pk, "method": "equal_weight", "parameters": {"lookback": 30, "cap": .2}}
    response = dispatch({"group": "experiments", "action": "run", "config": config})[0]
    done = work(once=True)
    assert done["status"] == "succeeded", done
    run = Experiment.objects.get(pk=response["run_id"])
    assert len(run.results["returns"]) == dataset.manifest["validation_end"] - dataset.manifest["train_end"]
    assert "SPY" in run.results["benchmarks"]
    assert run.provenance["lock_digest"]
    json.dumps(run.results, allow_nan=False)
    result = run_experiment(run)
    assert result["returns"] == run.results["returns"]
    assert result["simulation"] == run.results["simulation"]


@pytest.mark.django_db
def test_failed_job_is_saved(prices, settings, tmp_path):
    settings.LAB_DATA_DIR = tmp_path
    dataset = freeze_frame(prices)
    response = queue_experiment({"dataset": dataset.pk, "parameters": {"lookback": 1000}})
    assert work(once=True)["status"] == "failed"
    assert Experiment.objects.get(pk=response["run_id"]).error


@pytest.mark.django_db
def test_agent_permissions_and_holdout(prices):
    dataset = freeze_frame(prices)
    with pytest.raises(ValueError, match="holdout"):
        dispatch({"group": "experiments", "action": "run", "config": {"dataset": dataset.pk, "window": "holdout"}}, agent=True)
    with pytest.raises(ValueError):
        dispatch({"group": "paper", "action": "tick", "session": 1}, agent=True)
    run = Experiment.objects.create(dataset=dataset, config={"window": "holdout"})
    assert dispatch({"group": "runs", "action": "list"}, agent=True) == []
    with pytest.raises(ValueError):
        dispatch({"group": "runs", "action": "compare", "ids": [str(run.pk)]}, agent=True)


@pytest.mark.django_db
def test_registration_never_executes():
    source = 'raise RuntimeError("must not execute")\ndef target_weights(history, current_weights, parameters):\n    return {}\n'
    first = register_strategy("test", source)
    assert register_strategy("test2", source).digest == first.digest


@pytest.mark.django_db
def test_render_results_and_access(client, django_user_model, prices):
    assert client.get("/").status_code == 302
    assert client.get("/login/").status_code == 200
    user = django_user_model.objects.create_user(username="reviewer", is_staff=True)
    client.force_login(user)
    dataset = freeze_frame(prices)
    run = Experiment.objects.create(dataset=dataset, config={"dataset": dataset.pk, "method": "equal_weight", "window": "validation", "seed": 42, "parameters": {"lookback": 30}}, provenance={})
    run.results = run_experiment(run)
    run.status = "succeeded"
    run.save()
    response = client.get(f"/runs/{run.pk}/")
    assert response.status_code == 200
    assert b"plotly.min.js" in response.content
    assert b"shadow prices" in response.content


def test_markdown_sanitized():
    from research.reporting import safe_markdown
    value = safe_markdown('<img src=x onerror=alert(1)><script>alert(1)</script> **ok**')
    assert "<script" not in value and "onerror" not in value and "<strong>ok</strong>" in value
