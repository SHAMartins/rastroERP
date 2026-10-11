from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class EventoSeguranca(models.Model):
    """Log de seguranca (imutavel). Nunca guarda senha, token ou outro dado sensivel."""

    class Tipo(models.TextChoices):
        LOGIN_OK = "LOGIN_OK", "Login"
        LOGIN_FALHA = "LOGIN_FALHA", "Login com falha"
        BLOQUEIO = "BLOQUEIO", "Bloqueio por excesso de tentativas"
        LOGOUT = "LOGOUT", "Logout"
        SENHA_ALTERADA = "SENHA_ALTERADA", "Senha alterada"
        PERFIL_ALTERADO = "PERFIL_ALTERADO", "Perfil/permissao alterado"
        USUARIO_CRIADO = "USUARIO_CRIADO", "Usuario criado"
        TOKEN_EMITIDO = "TOKEN_EMITIDO", "Token de API emitido"
        ACESSO_NEGADO = "ACESSO_NEGADO", "Acesso negado"

    tipo = models.CharField(max_length=16, choices=Tipo.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="eventos_seguranca", help_text="Quem sofreu/fez a acao")
    nome_usuario = models.CharField("Usuario informado", max_length=150, blank=True)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+", help_text="Quem fez a alteracao (quando diferente)")
    ip = models.GenericIPAddressField(null=True, blank=True)
    detalhe = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "evento de seguranca"
        verbose_name_plural = "eventos de seguranca"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nome_usuario or self.usuario}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("O log de seguranca e imutavel.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("O log de seguranca nao pode ser apagado.")
