from django.urls import path

from .views import GenerateChecklistAPIView, TemplateCreateAPIView

urlpatterns = [
    path('templates/', TemplateCreateAPIView.as_view(), name='template-create'),
    path('generate/', GenerateChecklistAPIView.as_view(), name='checklist-generate'),
]
