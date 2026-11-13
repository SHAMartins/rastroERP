"""Popula o sistema com dados de demonstracao (empresa de telecom ficticia).

Uso: docker compose exec web python manage.py dados_demo

Serve para apresentar o sistema e para testes de usabilidade: paineis, SLA, OSs e estoque com
historico de varias semanas. Tudo passa pelas regras de negocio (services); depois as datas sao
recuadas para simular o passado. Os usuarios criados ficam SEM senha utilizavel: o administrador
define a senha em Seguranca > Usuarios se quiser entrar com eles.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from chamados import services as chamados
from chamados.models import Chamado, ComentarioChamado, HistoricoChamado
from clientes.models import Cliente, Servico
from estoque import services as estoque
from estoque.models import MovimentacaoEstoque, Produto
from ordens import services as ordens
from ordens.models import HistoricoAlteracao, OrdemServico

User = get_user_model()

CLIENTES = [
    ("Fibra Sul Telecom", "12.345.678/0001-90", "noc@fibrasul.com.br", "(19) 3456-7000"),
    ("Conecta Norte Provedor", "23.456.789/0001-01", "suporte@conectanorte.com.br", "(19) 3222-1100"),
    ("Vale Net Comunicações", "34.567.890/0001-12", "operacao@valenet.com.br", "(11) 4000-2200"),
]
LOCAIS = [
    ("Supermercado Bom Preço - Loja 3", "Av. Brasil, 1500 - Campinas/SP", "-22.9056", "-47.0608"),
    ("Clínica São Lucas", "Rua Barão de Jaguara, 820 - Campinas/SP", "-22.9064", "-47.0581"),
    ("Escola Estadual Prof. Ana Lima", "Rua Coronel Quirino, 300 - Campinas/SP", "-22.8955", "-47.0532"),
    ("Posto Avenida", "Av. John Boyd Dunlop, 2100 - Campinas/SP", "-22.9271", "-47.1011"),
    ("Condomínio Jardim das Palmeiras", "Rua das Palmeiras, 45 - Valinhos/SP", "-22.9706", "-46.9958"),
    ("Farmácia Vida - Centro", "Rua 13 de Maio, 410 - Campinas/SP", "-22.9030", "-47.0600"),
    ("Hotel Central", "Av. Francisco Glicério, 1100 - Campinas/SP", "-22.9037", "-47.0634"),
    ("Indústria Metalvale", "Rod. Anhanguera, km 98 - Sumaré/SP", "-22.8219", "-47.2668"),
]
SINTOMAS = [
    "Link sem sinal (LOS vermelho na ONT)", "Lentidão e perda de pacotes no horário comercial",
    "Quedas intermitentes do link dedicado", "Roteador reiniciando sozinho",
    "Telefonia VoIP sem tom de discagem", "Cabo drop rompido após obra na calçada",
]


class Command(BaseCommand):
    help = "Cria dados de demonstração (clientes, usuários, estoque, atividades e OSs com histórico)."

    def handle(self, *args, **options):
        if Cliente.objects.filter(documento=CLIENTES[0][1]).exists():
            raise CommandError("Os dados de demonstração já foram criados.")
        random.seed(42)                       # mesmo resultado a cada execucao em banco limpo
        with transaction.atomic():
            self.agora = timezone.now()
            self.admin = User.objects.filter(is_superuser=True).first() or self._usuario("admin.demo", "Administrador")
            self.coord = self._usuario("marina.alves", "Coordenação", "Marina", "Alves")
            self.tecnicos = [self._usuario("joao.silva", "Técnico", "João", "Silva"),
                             self._usuario("carla.souza", "Técnico", "Carla", "Souza"),
                             self._usuario("rafael.costa", "Técnico", "Rafael", "Costa")]
            self.estoquista = self._usuario("pedro.lima", "Estoque", "Pedro", "Lima")
            self._clientes()
            self._estoque()
            self._atividades()
        self.stdout.write(self.style.SUCCESS(
            f"Criados: {Cliente.objects.count()} clientes, {Chamado.objects.count()} atividades, "
            f"{OrdemServico.objects.count()} OSs, {Produto.objects.count()} produtos."))

    # ---------- cadastros ----------
    def _usuario(self, login, perfil, nome="", sobrenome=""):
        u, _ = User.objects.get_or_create(username=login, defaults={"first_name": nome, "last_name": sobrenome})
        u.set_unusable_password()
        u.is_staff = perfil == "Administrador"
        u.save()
        u.groups.set([Group.objects.get(name=perfil)])
        return u

    def _clientes(self):
        self.clientes = [Cliente.objects.create(nome=n, documento=d, email=e, telefone=t) for n, d, e, t in CLIENTES]
        Servico.objects.create(nome="Ativação de link dedicado", descricao="Lançamento, instalação e testes")
        Servico.objects.create(nome="Visita técnica corretiva")
        Servico.objects.create(nome="Vistoria de viabilidade", cliente=self.clientes[0])
        # Contrato com SLA mais rigido para o maior cliente
        chamados.salvar_tabela_sla(self.clientes[0], {
            ("MANUTENCAO", "URGENTE"): ("0.5", "3"), ("MANUTENCAO", "ALTA"): ("1", "6")})

    def _estoque(self):
        p = Produto.objects.create
        self.ont = p(codigo="7891000100011", nome="ONT GPON", tipo="ONT", modelo="HG8145V5", controla_serie=True,
                     estoque_minimo=4)
        self.roteador = p(codigo="7891000100028", nome="Roteador Wi-Fi 6", tipo="Roteador", modelo="AX3000",
                          controla_serie=True, estoque_minimo=3)
        self.cabo = p(codigo="CB-DROP-01", nome="Cabo drop 1 fibra", tipo="Cabo", unidade="m", estoque_minimo=300)
        self.conector = p(codigo="CN-SCAPC", nome="Conector SC/APC", tipo="Conector", estoque_minimo=40)
        self.cto = p(codigo="CTO-16", nome="Caixa de emenda CTO 16 portas", tipo="Caixa", estoque_minimo=2)
        e = estoque.registrar_entrada
        e(self.ont, None, self.estoquista, "NF 18.220", "\n".join(f"ONT{n:05d}" for n in range(1, 13)))
        e(self.roteador, None, self.estoquista, "NF 18.221", "\n".join(f"RTX{n:05d}" for n in range(1, 7)))
        e(self.cabo, 1000, self.estoquista, "NF 18.230")
        e(self.conector, 120, self.estoquista, "NF 18.230")
        e(self.cto, 3, self.estoquista, "NF 18.231")
        # As compras aconteceram antes das atividades
        MovimentacaoEstoque.objects.update(criado_em=F("criado_em") - timedelta(days=84))
        self.series = {"ont": [f"ONT{n:05d}" for n in range(1, 13)], "rot": [f"RTX{n:05d}" for n in range(1, 7)]}

    # ---------- atividades ----------
    def _nova(self, tipo, cliente, local, titulo, impacto, urgencia, detalhes, ativo=""):
        nome_local, endereco, lat, lon = local
        return chamados.abrir_chamado(
            self.coord, tipo=tipo, cliente=cliente, titulo=titulo, solicitante_nome=random.choice(
                ["Ana Paula (NOC)", "Bruno Reis", "Daniela Moraes", "Equipe NOC"]),
            solicitante_contato="(19) 99876-5432", cliente_final=nome_local, endereco=endereco,
            latitude=lat, longitude=lon, contato_local="Gerente da unidade", janela_acesso="Seg a sex, 8h as 18h",
            ativo=ativo, impacto=impacto, urgencia=urgencia, detalhes=detalhes)

    def _manutencao(self, cliente, local, impacto, urgencia):
        sintoma = random.choice(SINTOMAS)
        return self._nova("MANUTENCAO", cliente, local, f"Manutenção: {sintoma.split('(')[0].strip().lower()}",
                          impacto, urgencia,
                          {"sintoma": sintoma, "afetados": random.choice(["USUARIO", "SETOR", "UNIDADE"]),
                           "risco": "OPERACIONAL", "local_exato": "Rack do CPD"},
                          ativo=f"CIRC-{random.randint(1000, 9999)}")

    def _instalacao(self, cliente, local, impacto, urgencia, pendente=False):
        return self._nova("INSTALACAO", cliente, local, f"Instalação: link dedicado para {local[0]}", impacto, urgencia,
                          {"servico_contratado": "LINK_DEDICADO", "velocidade": "300 Mbps", "pedido": "PV-2026-0"
                           + str(random.randint(100, 999)), "escopo": "Lançamento de fibra, instalação de ONT e roteador",
                           "prerequisitos": "PENDENTE" if pendente else "OK",
                           "pendencias": "Aguardando autorização do condomínio" if pendente else ""})

    def _executar(self, c, tecnico, material=True, fechar=True):
        o = chamados.gerar_os(c, self.coord, responsavel=tecnico,
                              data_agendada=self.agora + timedelta(hours=random.randint(2, 30)))
        ordens.atualizar_os(o, tecnico, status="EM_ANDAMENTO")
        if material:
            if c.tipo == "INSTALACAO":
                ordens.registrar_material(o, tecnico, self.ont.pk, numeros_serie=self.series["ont"].pop())
                ordens.registrar_material(o, tecnico, self.roteador.pk, numeros_serie=self.series["rot"].pop())
                ordens.registrar_material(o, tecnico, self.cabo.pk, random.randint(60, 140))
            ordens.registrar_material(o, tecnico, self.conector.pk, random.randint(2, 6))
        if fechar:
            ordens.atualizar_os(o, tecnico, status="FECHADA")
        return o

    def _resolver(self, c, categoria="CAMPO"):
        chamados.comentar(c, self.coord, "Cliente confirmou o funcionamento.")
        chamados.atualizar_chamado(c, self.coord, status="RESOLVIDO", categoria_encerramento=categoria,
                                   nota_resolucao="Serviço normalizado e testado com o cliente.",
                                   causa=random.choice(["Conector danificado", "ONT travada", "Rompimento de fibra",
                                                        "Configuração do roteador"]))

    def _recuar(self, c, dias, horas_ate_resolver=None):
        """Leva a atividade (e o que nasceu dela) para o passado, mantendo os intervalos coerentes."""
        c.refresh_from_db()
        novo_inicio = self.agora - timedelta(days=dias, hours=random.randint(0, 8))
        delta = c.aberto_em - novo_inicio
        campos = {"aberto_em": novo_inicio}
        for nome in ("prazo_resposta", "prazo_solucao", "primeira_resposta_em", "pausado_desde"):
            if getattr(c, nome):
                campos[nome] = getattr(c, nome) - delta
        if c.resolvido_em:
            campos["resolvido_em"] = novo_inicio + timedelta(hours=horas_ate_resolver or 5)
        Chamado.objects.filter(pk=c.pk).update(**campos)
        HistoricoChamado.objects.filter(chamado=c).update(alterado_em=F("alterado_em") - delta)
        ComentarioChamado.objects.filter(chamado=c).update(criado_em=F("criado_em") - delta)
        for o in c.ordens.all():
            fim = campos.get("resolvido_em")
            OrdemServico.objects.filter(pk=o.pk).update(
                data_abertura=F("data_abertura") - delta,
                data_agendada=novo_inicio + timedelta(hours=2),
                data_fechamento=(fim - timedelta(minutes=40)) if (fim and o.data_fechamento) else
                (F("data_fechamento") - delta if o.data_fechamento else None))
            HistoricoAlteracao.objects.filter(ordem=o).update(alterado_em=F("alterado_em") - delta)
            MovimentacaoEstoque.objects.filter(ordem=o).update(criado_em=F("criado_em") - delta)

    def _atividades(self):
        cl, lc, tec = self.clientes, LOCAIS, self.tecnicos
        # Historico de 10 semanas: resolvidas dentro e fora do prazo
        for semana in range(10, 0, -1):
            for _ in range(random.randint(1, 3)):
                cliente, local = random.choice(cl), random.choice(lc)
                if random.random() < .7:
                    c = self._manutencao(cliente, local, random.choice(["ALTO", "MEDIO"]), random.choice(["ALTA", "MEDIA"]))
                    horas = random.choice([2, 3, 5, 7, 12, 30])
                else:
                    c = self._instalacao(cliente, local, "MEDIO", "MEDIA")
                    horas = random.choice([48, 96, 150, 260])
                self._executar(c, random.choice(tec), material=random.random() < .8)
                self._resolver(c, "CONCLUIDO" if c.tipo == "INSTALACAO" else "CAMPO")
                self._recuar(c, semana * 7 - random.randint(0, 5), horas)

        # Em aberto agora: uma de cada situacao, para os paineis mostrarem tudo
        estourada = self._manutencao(cl[0], lc[0], "ALTO", "ALTA")
        self._executar(estourada, tec[0], fechar=False)
        self._recuar(estourada, 1)

        em_risco = self._manutencao(cl[1], lc[1], "MEDIO", "MEDIA")
        self._executar(em_risco, tec[1], material=False, fechar=False)
        Chamado.objects.filter(pk=em_risco.pk).update(
            aberto_em=self.agora - timedelta(hours=20), prazo_resposta=self.agora - timedelta(hours=16),
            prazo_solucao=self.agora + timedelta(hours=4), primeira_resposta_em=self.agora - timedelta(hours=19))

        no_prazo = self._instalacao(cl[2], lc[2], "MEDIO", "MEDIA")
        self._executar(no_prazo, tec[2], material=False, fechar=False)

        pendente = self._manutencao(cl[0], lc[3], "MEDIO", "ALTA")
        self._executar(pendente, tec[0], material=False, fechar=False)
        chamados.comentar(pendente, self.coord, "Aguardando o cliente liberar acesso ao rack.")
        chamados.atualizar_chamado(pendente, self.coord, status="PENDENTE_CLIENTE")
        self._recuar(pendente, 1)

        travada = self._instalacao(cl[0], lc[4], "MEDIO", "BAIXA", pendente=True)
        self._recuar(travada, 3)

        # Fila de triagem: duas novas, uma com a resposta ja vencida
        vencida = self._manutencao(cl[1], lc[5], "ALTO", "MEDIA")
        Chamado.objects.filter(pk=vencida.pk).update(aberto_em=self.agora - timedelta(hours=3),
                                                     prazo_resposta=self.agora - timedelta(hours=2),
                                                     prazo_solucao=self.agora + timedelta(hours=5))
        self._manutencao(cl[2], lc[6], "BAIXO", "MEDIA")
        self._instalacao(cl[1], lc[7], "MEDIO", "BAIXA")
