"""Определение маршрутов API для шаблонов и результатов чек-листов."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.checklists.views import (
    ChecklistAttachmentViewSet,
    ChecklistResultViewSet,
    TemplateViewSet,
)

router = DefaultRouter()
router.register(r'templates', TemplateViewSet, basename='template')
router.register(r'results', ChecklistResultViewSet, basename='result')
router.register(r'attachments', ChecklistAttachmentViewSet, basename='attachment')

urlpatterns = [
    path('', include(router.urls)),
]
