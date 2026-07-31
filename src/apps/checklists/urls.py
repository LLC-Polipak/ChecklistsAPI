from django.urls import path

from .views import (
    ChecklistResultAPIView,
    GenerateChecklistAPIView,
    TemplateCreateAPIView,
)

urlpatterns = [
    path('templates/', TemplateCreateAPIView.as_view(), name='template-create'),
    path('forms/', GenerateChecklistAPIView.as_view(), name='checklist-form'),
    path('results/', ChecklistResultAPIView.as_view(), name='checklist-results'),
]
