import pytest
from django.urls import reverse


@pytest.mark.parametrize("page", ["home", "results"])
@pytest.mark.django_db
def test_placeholder_pages_render(client, page, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="operator", is_staff=True))
    response = client.get(reverse(page))
    assert response.status_code == 200
    assert b"Portfolio Lab" in response.content
