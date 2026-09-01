from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Núcleo"

    def ready(self) -> None:
        from django.db.models.signals import post_delete, post_migrate, post_save, pre_save

        from .models import Feriado
        from .signals import (
            garantir_papeis_e_matriz,
            guardar_ano_do_feriado,
            limpar_cache_de_feriados,
        )

        post_migrate.connect(garantir_papeis_e_matriz, sender=self)
        pre_save.connect(guardar_ano_do_feriado, sender=Feriado)
        post_save.connect(limpar_cache_de_feriados, sender=Feriado)
        post_delete.connect(limpar_cache_de_feriados, sender=Feriado)
