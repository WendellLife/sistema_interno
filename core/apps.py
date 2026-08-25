from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Núcleo"

    def ready(self) -> None:
        from django.db.models.signals import post_migrate

        from .signals import garantir_papeis_e_matriz

        post_migrate.connect(garantir_papeis_e_matriz, sender=self)
