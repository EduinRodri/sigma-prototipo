from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nucleo"
    verbose_name = "SIGMA"

    def ready(self):
        # Después de cada migración, los tres roles quedan creados con sus permisos.
        from .roles import asegurar_grupos

        post_migrate.connect(asegurar_grupos, sender=self)
