from django.urls import path

from .views import TemplateCreateAPIView

urlpatterns = [
    path('templates/', TemplateCreateAPIView.as_view(), name='template-create')
]
