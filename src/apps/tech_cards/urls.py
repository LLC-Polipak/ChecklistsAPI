from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tech_cards.views import TechCardViewSet

router = DefaultRouter()
router.register(r'tech-cards', TechCardViewSet, basename='tech-card')

urlpatterns = [
    path('', include(router.urls)),
]
