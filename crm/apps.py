from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crm'

    def ready(self):
        from .signals import init_default_data
        post_migrate.connect(init_default_data, sender=self)
