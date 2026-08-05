
import pytest
from rest_framework.reverse import reverse
from rest_framework.test import APIClient

@pytest.mark.django_db
class TestTemplateViewSet():

    def setup_method(self):
        pass

    def test_200(self, client):
        url = reverse('template-list')
        data = {
          "equipment_uid": "EQ-FORKLIFT-01",
          "checklist_type": "INSPECTION",
          "fields": [
            {
              "name": "Уровень масла",
              "field_type": "CHOICE",
              "order": 1,
              "choices": [
                {"value": "В норме", "order": 1},
                {"value": "Ниже минимума", "order": 2}
              ]
            },
            {
              "name": "Давление в шинах (Атм)",
              "field_type": "INTEGER",
              "order": 2
            },
            {
              "name": "Сигналка работает?",
              "field_type": "CHECKBOX",
              "order": 3
            }
          ]
        }
        response = client.post(url, data)

        assert response.status_code == 200