import secrets

from django.conf import settings

from .eventos import usuario_atual


class UsuarioAtualMiddleware:
    """Guarda quem esta logado na requisicao, para o log de seguranca saber o autor de cada alteracao."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = usuario_atual.set(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            usuario_atual.reset(token)


def politica_csp(nonce, relaxada=False):
    cdns = " ".join(settings.CSP_CDNS)
    # Scripts so do proprio site, dos CDNs fixados e os inline que carregam o nonce desta resposta.
    # Na politica relaxada (Swagger) vai 'unsafe-inline' SEM nonce: com nonce o navegador ignora o unsafe-inline.
    scripts = f"'self' {cdns} " + ("'unsafe-inline'" if relaxada else f"'nonce-{nonce}'")
    return "; ".join([
        "default-src 'self'",
        f"script-src {scripts}",
        f"style-src 'self' 'unsafe-inline' {cdns}",       # estilos inline do Bootstrap/htmx/scanner
        f"font-src 'self' data: {cdns}",
        "img-src 'self' data: blob:" + (f" {cdns}" if relaxada else ""),
        "media-src 'self' blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


class CabecalhosSegurancaMiddleware:
    """Content-Security-Policy com nonce por requisicao + Permissions-Policy.

    X-Content-Type-Options, X-Frame-Options, Referrer-Policy e HSTS ja vem do SecurityMiddleware/
    XFrameOptionsMiddleware do Django (configurados em settings).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            # A documentacao Swagger (drf-spectacular) usa script inline proprio: politica relaxada so nela
            relaxada = request.path.startswith(tuple(settings.CSP_CAMINHOS_RELAXADOS))
            response["Content-Security-Policy"] = politica_csp(request.csp_nonce, relaxada)
        response.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
        return response
