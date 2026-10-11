"""Anexos seguros: so tipos permitidos, tamanho maximo, conteudo conferido e download so com login.

Sem isso, um anexo .html/.svg servido pelo proprio site rodaria script com a sessao de quem abrisse (XSS).
"""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse

# extensao -> assinaturas validas do inicio do arquivo ("numero magico"); None = texto puro
TIPOS = {
    "pdf": (b"%PDF",),
    "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
    "docx": (b"PK\x03\x04",), "xlsx": (b"PK\x03\x04",),
    "txt": None, "csv": None,
}
IMAGENS = {"jpg", "jpeg", "png", "webp"}       # abrem no navegador; o resto sempre baixa
AJUDA_ANEXO = f"Fotos (jpg, png, webp), PDF, Word, Excel, txt ou csv, ate {settings.ANEXO_TAMANHO_MAX_MB} MB."


def extensao(nome):
    return Path(nome).suffix.lower().lstrip(".")


def validar_anexo(arquivo):
    ext = extensao(arquivo.name)
    if ext not in TIPOS:
        raise ValidationError(f"Tipo de arquivo nao permitido (.{ext or '?'}). "
                              f"Aceitos: {', '.join(sorted(TIPOS))}.")
    limite = settings.ANEXO_TAMANHO_MAX_MB * 1024 * 1024
    if arquivo.size > limite:
        raise ValidationError(f"Arquivo maior que {settings.ANEXO_TAMANHO_MAX_MB} MB.")
    assinaturas = TIPOS[ext]
    inicio = arquivo.read(16)
    arquivo.seek(0)
    if assinaturas and not inicio.startswith(assinaturas):
        raise ValidationError(f"O conteudo do arquivo nao corresponde a um .{ext}.")
    if ext == "webp" and inicio[8:12] != b"WEBP":
        raise ValidationError("O conteudo do arquivo nao corresponde a um .webp.")


def resposta_download(campo_arquivo):
    """Entrega o arquivo com cabecalhos que impedem o navegador de executa-lo."""
    nome = Path(campo_arquivo.name).name
    ext = extensao(nome)
    resposta = FileResponse(campo_arquivo.open("rb"), as_attachment=ext not in IMAGENS, filename=nome,
                            content_type=mimetypes.guess_type(nome)[0] if ext in IMAGENS else "application/octet-stream")
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
    return resposta
