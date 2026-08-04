import pytest
from rest_framework.reverse import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
class BaseAPITest:
    """
    Базовый класс для API-тестов.
    """

    url_name: str | None = None

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = APIClient()

    def get_url(
            self,
            args = None,
            kwargs = None,
    ):
        if not self.url_name:
            raise ValueError(f'{self.__class__.__name__} must define url_name')
        # return reverse(self.url_name, kwargs=kwargs)
        return reverse(self.url_name, args=args, kwargs=kwargs)
