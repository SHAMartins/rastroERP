from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SegurancaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "seguranca"
    verbose_name = "Seguranca"

    def ready(self):
        from . import sinais  # noqa: F401  (registra os receptores de login/perfil)
        from .perfis import sincronizar_perfis
        # Depois que todas as permissoes existem, aplica a matriz de perfis aos grupos
        post_migrate.connect(sincronizar_perfis, sender=self, dispatch_uid="seguranca_sincronizar_perfis")
