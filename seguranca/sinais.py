"""Sinais do Django que alimentam o log de seguranca. Nunca registra senha (o Django ja a remove)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver

from . import bloqueio
from .eventos import registrar
from .models import EventoSeguranca as E

User = get_user_model()


@receiver(user_logged_in)
def login_ok(sender, request, user, **kwargs):
    bloqueio.limpar(user.get_username())
    registrar(E.Tipo.LOGIN_OK, user, ip=bloqueio.ip_do_request(request))


@receiver(user_logged_out)
def logout(sender, request, user, **kwargs):
    if user:
        registrar(E.Tipo.LOGOUT, user, ip=bloqueio.ip_do_request(request))


@receiver(user_login_failed)
def login_falhou(sender, credentials, request=None, **kwargs):
    nome = credentials.get("username", "")             # credentials ja vem sem a senha
    ip = bloqueio.ip_do_request(request)
    if bloqueio.bloqueado(nome, ip):
        registrar(E.Tipo.BLOQUEIO, nome_usuario=nome, ip=ip, detalhe="Tentativa durante o bloqueio")
        return
    usuario = User.objects.filter(username__iexact=nome).first()
    registrar(E.Tipo.LOGIN_FALHA, usuario, nome_usuario=nome, ip=ip)
    if bloqueio.registrar_falha(nome, ip):
        registrar(E.Tipo.BLOQUEIO, usuario, nome_usuario=nome, ip=ip, detalhe="Limite de tentativas atingido")


@receiver(m2m_changed, sender=User.groups.through)
def perfil_alterado(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear") or not isinstance(instance, User):
        return
    perfis = ", ".join(instance.groups.values_list("name", flat=True)) or "nenhum"
    registrar(E.Tipo.PERFIL_ALTERADO, instance, detalhe=f"Perfis agora: {perfis}")


@receiver(m2m_changed, sender=User.user_permissions.through)
def permissao_alterada(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and isinstance(instance, User):
        registrar(E.Tipo.PERFIL_ALTERADO, instance, detalhe="Permissoes individuais alteradas")


@receiver(pre_save, sender=User)
def flags_alteradas(sender, instance, **kwargs):
    if not instance.pk:
        return
    antes = User.objects.filter(pk=instance.pk).values("is_superuser", "is_staff", "is_active").first()
    if not antes:
        return
    mudancas = [f"{campo}: {antes[campo]} -> {getattr(instance, campo)}" for campo in antes
                if antes[campo] != getattr(instance, campo)]
    if mudancas:
        registrar(E.Tipo.PERFIL_ALTERADO, instance, detalhe="; ".join(mudancas))
