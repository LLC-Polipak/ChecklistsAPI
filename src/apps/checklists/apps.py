from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.checklists'

    def ready(self):
        from apps.core.service_locator import container
        from apps.checklists.services import TemplateService, \
            ChecklistResultService

        container.register(TemplateService, lambda: TemplateService())
        container.register(ChecklistResultService,
                           lambda: ChecklistResultService())
