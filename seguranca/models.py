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
        USUARIO_CRIADO = "USUARIO_CRIADO", "Usuário criado"
        TOKEN_EMITIDO = "TOKEN_EMITIDO", "Token de API emitido"
        ACESSO_NEGADO = "ACESSO_NEGADO", "Acesso negado"

    tipo = models.CharField(max_length=16, choices=Tipo.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Usuário",
                                related_name="eventos_seguranca", help_text="Quem sofreu/fez a ação")
    nome_usuario = models.CharField("Usuário informado", max_length=150, blank=True)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+", help_text="Quem fez a alteração (quando diferente)")
    ip = models.GenericIPAddressField(null=True, blank=True)
    detalhe = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "evento de segurança"
        verbose_name_plural = "eventos de segurança"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nome_usuario or self.usuario}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("O log de segurança é imutável.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("O log de segurança não pode ser apagado.")
