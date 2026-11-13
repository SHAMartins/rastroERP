# Rastro

O Rastro é um ERP web para pequenas empresas de serviços técnicos. Ele junta num lugar só os chamados de manutenção e instalação, o controle de SLA, as ordens de serviço feitas em campo e o estoque de materiais e equipamentos.

É o sistema do nosso Trabalho de Conclusão de Curso. Usei como base a empresa de telecomunicações em que trabalho, onde o dia a dia gira em torno de SLA, manutenção de circuitos e instalação de links. O SAP serviu só como referência: a ideia de separar o pedido da execução veio do SAP PM, que tem a *Nota de manutenção* (o pedido) e a *Ordem de manutenção* (a execução).

## O que o sistema faz

### Atividades

Na tela tudo aparece como uma "atividade", mas no banco são dois registros: o chamado, que é o pedido com o SLA, e as ordens de serviço (OSs), que são a execução. Assim quem atende vê tudo numa página só.

- São dois tipos: **Manutenção** (falha, reparo e preventiva) e **Instalação** (ativação e execução de serviço). Cada tipo tem os seus próprios campos, em vez de um campo de descrição livre.
- A prioridade não é digitada. Ela sai da matriz impacto × urgência do ITIL.
- O SLA tem prazo de primeira resposta e de solução. Cliente com contrato usa os prazos dele; os outros usam o SLA padrão.
- Quando a atividade fica em "pendente cliente", o relógio do SLA para.
- Cada atividade mostra a situação do SLA: no prazo, em risco (80% do prazo já usado), estourado, cumprido ou violado.
- Dentro da atividade dá para gerar a OS, mudar o status, agendar e lançar o material usado.
- Toda alteração vai para uma linha do tempo com quem mudou, quando, o valor antigo e o novo.
- Para encerrar é obrigatório informar a nota de resolução e a categoria, que alimentam os indicadores.

### Painéis

- **Geral**: começa pelo que precisa de ação (SLA estourado, em risco e a fila por prazo) e depois mostra os gráficos de status e a evolução.
- **Triagem**: atividades novas, da que vence primeiro para a última.
- **Manutenção**: ativos e locais que mais dão problema e alerta de risco à segurança das pessoas.
- **Instalação**: agenda da semana, instalações travadas por pré-requisito e instalações ainda sem OS.
- **Evolução das últimas 12 semanas**: abertas, resolvidas, backlog, MTTR (tempo médio de resolução) e % de SLA cumprido.
- **OSs por técnico** (só a Coordenação vê): em aberto, atrasadas, concluídas e tempo médio.

As listas e os indicadores podem ser exportados em planilha (CSV que abre direto no Excel).

### Estoque

- O saldo nunca é digitado: é a soma das movimentações. Movimentação não se edita nem se apaga; se algo estiver errado, entra um ajuste com justificativa.
- Equipamento com número de série é controlado por unidade. Dá para saber em qual OS e em qual cliente cada um foi instalado.
- Material lançado na OS dá baixa no estoque na hora. Se não houver saldo, nada é gravado.
- Quando o saldo chega ao mínimo, o sistema abre uma tarefa de reposição com a quantidade sugerida. A tarefa fecha sozinha quando entra material.
- O leitor de código de barras é opcional: funciona com leitor USB/Bluetooth ou com a câmera do celular.

### Cadastros

Clientes (com CPF/CNPJ validado e contrato de SLA), catálogo de serviços (gerais ou exclusivos de um cliente) e a tabela de SLA padrão.

### Segurança

- Quatro perfis: Administrador, Coordenação, Técnico e Estoque. A permissão é conferida no servidor, não só escondendo botão. O técnico só mexe nas OSs atribuídas a ele.
- O login bloqueia depois de 5 tentativas erradas, e a senha é guardada com Argon2.
- A sessão expira depois de 8 horas sem uso.
- Anexos têm tipo, tamanho e conteúdo verificados, e só quem está logado consegue baixar.
- Cabeçalhos de segurança: CSP com nonce, Permissions-Policy, nosniff e bloqueio de uso em iframe.
- Log de segurança que não pode ser alterado: logins, falhas, bloqueios, mudanças de perfil e acessos negados.

### API

API REST com documentação OpenAPI (Swagger em `/api/docs/`). O token expira e há limite de requisições por minuto.

## Interface

Procurei basear o visual em técnicas de visualização de dados e de usabilidade, e não em gosto pessoal:

- cor só onde existe exceção (SLA estourado ou em risco, saldo zerado), seguindo a ideia de gestão por exceção;
- visão geral primeiro e detalhe depois (Shneiderman, 1996);
- todo indicador com rótulo, valor e contexto (Few, 2006);
- barras em vez de pizza, e linhas retas na evolução, sem curva inventando valores (Cleveland e McGill, 1984; Tufte, 2001);
- status com ponto colorido e texto, para não depender só da cor (WCAG 2.1, critério 1.4.1);
- contraste mínimo de 4,5:1 nos textos (WCAG 2.1, critério 1.4.3).

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12, Django 5.2, Django REST Framework, drf-spectacular |
| Banco de dados | PostgreSQL 16 |
| Front-end | Templates do Django, Bootstrap 5, Bootstrap Icons, HTMX, Chart.js, html5-qrcode |
| Segurança | Argon2 (argon2-cffi), CSP própria, grupos e permissões do Django |
| Testes | pytest e pytest-django |
| Infraestrutura | Docker e Docker Compose, gunicorn, Caddy (HTTPS) |

## Como rodar

Precisa do [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e aberto.

```bash
git clone https://github.com/SHAMartins/rastroERP.git
cd rastroERP
cp .env.example .env
docker compose up --build
```

Em outro terminal, crie o usuário administrador:

```bash
docker compose exec web python manage.py createsuperuser
```

Para ver o sistema com dados de exemplo (clientes, técnicos, estoque e algumas semanas de atividades), rode o comando abaixo uma vez. Os usuários de demonstração são criados sem senha; para entrar com algum deles, defina a senha em **Segurança → Usuários**.

```bash
docker compose exec web python manage.py dados_demo
```

| Endereço | O que é |
|---|---|
| http://localhost:8000/entrar/ | Login |
| http://localhost:8000/ | Painel geral |
| http://localhost:8000/api/docs/ | Documentação da API (Swagger) |
| http://localhost:8000/admin/ | Administração do Django (só apoio) |

### Testes

```bash
docker compose exec web pytest
```

### Migrações

O contêiner só aplica as migrações que já estão no repositório. Depois de mudar um model, gere a migração e inclua o arquivo no commit:

```bash
docker compose exec web python manage.py makemigrations
```

## Produção (HTTPS)

1. Copie `.env.prod.example` para `.env.prod` e preencha o domínio, uma `SECRET_KEY` gerada e uma senha forte para o banco. Com `DEBUG=False` o sistema não sobe se a chave for fraca.
2. Suba os serviços:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

O Caddy recebe as conexões nas portas 80 e 443, emite o certificado TLS e repassa para o gunicorn. Use `CADDY_TLS=internal` numa rede interna, ou um e-mail para ter certificado Let's Encrypt num domínio público.

Em produção, o `collectstatic` grava o CSS e o JavaScript com um código no nome do arquivo. Quando o arquivo muda, o nome muda junto, e o navegador baixa a versão nova sem precisar de Ctrl+F5.

## Estrutura do projeto

```
chamados/    Atividades: chamado, SLA, campos de cada tipo (campos.py) e regras (services.py)
ordens/      Ordens de serviço: execução, status e material usado
estoque/     Produtos, movimentações (kardex), números de série e tarefas de reposição
clientes/    Clientes, serviços e telas de cadastro (inclui o contrato de SLA)
dashboard/   Painéis e indicadores (evolução semanal, desempenho por técnico)
seguranca/   Perfis, login com bloqueio, CSP, anexos e log de segurança
api/         Endpoints REST
config/      Configurações, rotas, menu e exportação de planilhas
templates/   Telas (HTML)
static/      CSS e JavaScript
```

As regras de negócio ficam nos arquivos `services.py` de cada app. As telas, o admin e a API usam as mesmas regras.

## Principais regras de negócio

- Numeração automática: atividade `CH-2026-00001` e OS `2026-00001`.
- Prioridade = matriz impacto × urgência. Ao reclassificar a atividade, os prazos de SLA são recalculados.
- O contrato do cliente tem preferência sobre o SLA padrão, e "pendente cliente" pausa o relógio.
- Uma atividade só é resolvida com nota e categoria de encerramento, e com todas as OSs fechadas.
- Atividades, OSs e movimentações nunca são apagadas: são canceladas ou corrigidas por ajuste.
- Produto e serviço exclusivos de um cliente só podem ser usados nas atividades desse cliente.
- Equipamento com número de série exige as séries na entrada, no ajuste e na baixa, e o saldo sempre bate com as unidades em estoque.

## O que ainda falta

- Estorno: devolver ao estoque o material que saiu para uma OS e não foi usado.
- Cumprimento de SLA por cliente (por contrato).
- SLA contando só o horário comercial. Hoje os prazos contam 24 horas por dia.

Deixei de fora os alertas por e-mail e o escalonamento automático, porque dependeriam de um servidor de e-mail e de tarefas agendadas, o que foge do escopo desta fase.
