from optimizer import min_variance, sample_covariance, volatility


def test_optimizer_exports_are_importable():
    assert callable(min_variance)
    assert callable(sample_covariance)
    assert callable(volatility)
