import pytest
from django.urls import reverse


@pytest.mark.parametrize("page", ["home", "results"])
def test_placeholder_pages_render(client, page):
    response = client.get(reverse(page))
    assert response.status_code == 200
    assert b"Portfolio Lab" in response.content
