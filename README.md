# Rastro

**Rastro** é um ERP web para pequenas empresas de serviços técnicos, com foco em telecomunicações. Ele reúne em um só lugar o atendimento de **manutenções e instalações**, o **controle de SLA**, a execução em campo por **ordens de serviço (OS)** e o **estoque** de materiais e equipamentos, que pode ser rastreado por número de série.

Projeto de Trabalho de Conclusão de Curso. O SAP foi usado como referência conceitual: no módulo SAP PM, a *Nota de manutenção* registra o pedido e a *Ordem de manutenção* registra a execução.

---

## Funcionalidades

### Atividades (chamado + OS)
- Dois tipos de atividade: **Manutenção** (falhas, reparos e rotinas preventivas) e **Instalação** (ativações e execução de serviço).
- **Formulário específico por tipo**: cada tipo coleta só os campos que importam para a triagem.
- **Prioridade calculada automaticamente** pela matriz impacto × urgência (ITIL).
- **SLA** de primeira resposta e de solução, com prazos **por contrato de cliente** e um SLA padrão para os demais.
  - O status *pendente cliente* pausa o relógio do SLA.
  - Cada atividade mostra a situação: no prazo, em risco, estourado, cumprido ou violado.
- **Ordens de serviço dentro da atividade**: técnico, agendamento, mudança de status e lançamento de material na mesma tela.
- **Linha do tempo única**: comentários e histórico de cada campo alterado (quem, quando, valor anterior e novo).
- **Encerramento** exige nota de resolução e categoria, o que alimenta os indicadores.
- Endereço, coordenadas, cliente final, contato e janela de acesso ficam registrados na atividade.

### Painéis
- **Geral**: atividades e OSs por status, SLA estourado e em risco, percentual de SLA cumprido e MTTR (tempo médio de resolução).
- **Triagem**: fila pelo prazo de primeira resposta e tempo médio de resposta.
- **Manutenção**: ativos e locais com mais ocorrências e alerta de risco à segurança.
- **Instalação**: agenda da semana, instalações com pré-requisitos pendentes e instalações ainda sem OS.

### Estoque
- **Kardex**: o saldo é sempre a soma das movimentações, que nunca são editadas nem apagadas. Toda correção é um ajuste justificado.
- **Número de série por unidade**: dá para saber em qual OS e em qual cliente cada equipamento foi instalado.
- Material usado na OS gera baixa automática no estoque. Sem saldo, nada é gravado.
- **Scanner opcional** de código de barras e QR Code, por câmera ou por leitor USB/Bluetooth.

### Cadastros
- Clientes, com validação de CPF/CNPJ e contrato de SLA próprio.
- Catálogo de serviços, gerais ou exclusivos de um cliente.
- Tabela de SLA padrão.

### Segurança
- **Perfis de acesso (RBAC)**: Administrador, Coordenação, Técnico e Estoque.
  - Toda permissão é conferida no servidor.
  - O técnico só opera as OSs atribuídas a ele.
- Login com **bloqueio por tentativas**, senhas com **Argon2** e regras de senha forte.
- Sessão com expiração por inatividade e cookies `HttpOnly` e `SameSite`.
- **Anexos seguros**: tipo, tamanho e conteúdo validados; download só para quem está logado.
- Cabeçalhos de segurança: **Content-Security-Policy** com nonce, Permissions-Policy, nosniff e proteção contra uso em iframe.
- **Log de segurança imutável**: logins, falhas, bloqueios, mudanças de perfil e acessos negados.
- Configuração de produção com **HTTPS** (Caddy + gunicorn).

### API REST
- API completa com documentação **OpenAPI/Swagger**.
- Token com prazo de validade e limite de requisições por minuto.

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12, Django 5, Django REST Framework, drf-spectacular |
| Banco de dados | PostgreSQL 16 |
| Front-end | Templates Django, Bootstrap 5, Bootstrap Icons, HTMX, Chart.js, html5-qrcode |
| Segurança | Argon2 (argon2-cffi), CSP própria, RBAC com grupos e permissões do Django |
| Testes | pytest + pytest-django |
| Infraestrutura | Docker / Docker Compose, gunicorn, Caddy (HTTPS) |

---

## Como rodar (desenvolvimento)

Pré-requisito: [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e em execução.

```bash
git clone https://github.com/SHAMartins/rastro.git
cd rastro
cp .env.example .env
docker compose up --build
```

Em outro terminal, crie o seu usuário administrador:

```bash
docker compose exec web python manage.py createsuperuser
```

Acesse:

| Endereço | O que é |
|---|---|
| http://localhost:8000/entrar/ | Login |
| http://localhost:8000/ | Painel geral |
| http://localhost:8000/api/docs/ | Documentação da API (Swagger) |
| http://localhost:8000/admin/ | Administração do Django (apoio) |

Depois de entrar, cadastre os outros usuários e defina o perfil de cada um em **Segurança → Usuários**.

### Testes

```bash
docker compose exec web pytest
```

### Migrações

O contêiner só aplica as migrações já salvas no repositório. Depois de alterar um model, gere a migração e inclua o arquivo no commit:

```bash
docker compose exec web python manage.py makemigrations
```

---

## Produção (HTTPS)

1. Copie `.env.prod.example` para `.env.prod` e preencha os valores: domínio, uma `SECRET_KEY` gerada e uma senha forte para o banco. Com `DEBUG=False`, o sistema não sobe se a chave for fraca.
2. Suba os serviços:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

O Caddy recebe as conexões nas portas 80 e 443, emite o certificado TLS e repassa as requisições para o gunicorn. Use `CADDY_TLS=internal` em rede interna ou um e-mail para obter um certificado Let's Encrypt em domínio público.

---

## Estrutura do projeto

```
chamados/    Atividades: chamado, SLA, campos por tipo (campos.py), regras (services.py)
ordens/      Ordens de servico: execucao, status, material usado
estoque/     Produtos, movimentacoes (kardex), unidades com numero de serie
clientes/    Clientes, servicos e telas de cadastro (inclui contrato de SLA)
dashboard/   Paineis geral, triagem, manutencao e instalacao
seguranca/   Perfis, login com bloqueio, CSP, anexos seguros, log de seguranca
api/         Endpoints REST
config/      Configuracoes, rotas e menu
templates/   Telas (HTML)
static/      CSS e JavaScript
```

As regras de negócio ficam nos arquivos `services.py` de cada app e são as mesmas para as telas, o admin e a API.

---

## Principais regras de negócio

- **Numeração automática**: atividade `CH-2026-00001` e OS `2026-00001`.
- **Prioridade** = matriz impacto × urgência. Ao reclassificar a atividade, os prazos de SLA são recalculados.
- **SLA**: o contrato do cliente tem preferência sobre o padrão, e o status *pendente cliente* pausa o relógio.
- Uma atividade **só é resolvida** com nota e categoria de encerramento, e com todas as suas OSs fechadas.
- Atividades, OSs e movimentações **nunca são apagadas**: elas são canceladas ou corrigidas por ajuste.
- **Produto e serviço exclusivos de um cliente** só podem ser usados em atividades desse cliente.
- **Equipamento com número de série**: entrada, ajuste e baixa exigem as séries, e o saldo sempre bate com as unidades em estoque.
