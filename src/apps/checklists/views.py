from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Template
from .serializers import TemplateSerializer


class TemplateCreateAPIView(generics.CreateAPIView):
    """
    Эндпоинт для создания нового шаблона чек-листа
    """

    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]
