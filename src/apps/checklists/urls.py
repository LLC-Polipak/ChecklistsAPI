from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.checklists.views import ChecklistResultViewSet, TemplateViewSet

router = DefaultRouter()
router.register(r'templates', TemplateViewSet, basename='template')
router.register(r'results', ChecklistResultViewSet, basename='result')

urlpatterns = [
    path('', include(router.urls)),
]
