"""Exportacao de relatorios em planilha CSV (abre direto no Excel/LibreOffice). Usa so a biblioteca padrao.

- separador ";" e BOM UTF-8: o Excel em portugues abre com colunas e acentos certos;
- datas no formato brasileiro e decimais com virgula;
- protecao contra injecao de formula (OWASP "CSV Injection"): texto que comeca com = + - @ ganha um apostrofo,
  para o Excel tratar como texto e nao executar uma formula escrita por um usuario.
"""
import csv
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone

INICIOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


def celula(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, datetime):
        return f"{timezone.localtime(valor) if timezone.is_aware(valor) else valor:%d/%m/%Y %H:%M}"
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    if isinstance(valor, (int, float, Decimal)):
        return str(valor).replace(".", ",")
    texto = str(valor)
    return "'" + texto if texto.startswith(INICIOS_PERIGOSOS) else texto


def resposta_csv(nome, cabecalho, linhas):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}-{timezone.localdate():%Y-%m-%d}.csv"'
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([celula(v) for v in linha])
    return resposta
