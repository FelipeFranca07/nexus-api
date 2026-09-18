# Nexus API

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat&logo=githubactions&logoColor=white)
![Azure Pipelines](https://img.shields.io/badge/Azure%20Pipelines-0078D7?style=flat&logo=azuredevops&logoColor=white)
![GitLab CI](https://img.shields.io/badge/GitLab%20CI-FC6D26?style=flat&logo=gitlab&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

API REST (FastAPI) usada como aplicação de exemplo para demonstrar, de ponta a ponta, o padrão de **CI/CD +
GitOps** que times de plataforma usam hoje: este repositório builda, testa e publica a imagem — o deploy em si
é feito de forma declarativa pelo **ArgoCD**, a partir de um repositório GitOps separado
([`Nexus-GitOps`](https://github.com/FelipeFranca07/Nexus-GitOps)).

> Este repositório documenta um **padrão de arquitetura de referência**, construído do zero para estudo e
> portfólio — não é uma extração de um ambiente de produção real.

![Arquitetura CI/CD + GitOps](https://raw.githubusercontent.com/FelipeFranca07/Nexus-GitOps/main/architecture.svg)

## Índice

- [Por que isso existe](#por-que-isso-existe)
- [A decisão central: CI nunca toca o cluster](#a-decisão-central-ci-nunca-toca-o-cluster)
- [Arquitetura do fluxo](#arquitetura-do-fluxo)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Setup passo a passo (do zero)](#setup-passo-a-passo-do-zero)
- [O pipeline, passo a passo](#o-pipeline-passo-a-passo)
- [Pipelines de referência (Azure DevOps / GitLab CI)](#pipelines-de-referência-azure-devops--gitlab-ci)
- [Rodando localmente](#rodando-localmente)
- [Comandos úteis / como testar](#comandos-úteis--como-testar)
- [Como adaptar para o seu ambiente](#como-adaptar-para-o-seu-ambiente)
- [Boas práticas de segurança](#boas-práticas-de-segurança)
- [Repositório GitOps](#repositório-gitops)

## Por que isso existe

A pergunta que este padrão responde não é "como eu faço deploy de uma API", é **"quem tem permissão para mudar
o que está rodando no cluster, e como isso fica auditável"**. Deploy via `kubectl apply` manual, ou até via CI
rodando `kubectl apply` direto ao final do pipeline, funciona — até o dia em que ninguém consegue dizer com
certeza qual foi o último estado aplicado, por quem, ou por quê. GitOps resolve isso tornando o **Git a única
fonte da verdade** do estado desejado do cluster: se não está commitado no repositório GitOps, não está — e não
deveria estar — rodando.

## A decisão central: CI nunca toca o cluster

A maioria dos pipelines de CI/CD "funcionais" cai numa armadilha sutil: o job de deploy tem credenciais do
cluster e roda `kubectl apply`/`helm upgrade` direto. Funciona, mas mistura duas responsabilidades que deveriam
estar separadas — **construir o artefato** e **decidir o que está rodando em produção**:

| Abordagem | Quem aplica no cluster | Rastreabilidade | Rollback |
|---|---|---|---|
| CI com `kubectl apply` direto | O pipeline, com credenciais do cluster armazenadas como secret de CI | Só o log de execução do pipeline (efêmero, geralmente sem diff) | Manual, refazendo o deploy anterior |
| **GitOps (este padrão)** | Só o ArgoCD, que só lê o repositório GitOps | O histórico de commits do repositório GitOps **é** o histórico de deploys | `git revert` no repositório GitOps — o ArgoCD reconcilia sozinho |

Esse repositório (`Nexus-Api`) nunca tem credenciais do cluster. Ele só sabe fazer duas coisas: publicar uma
imagem no GHCR, e commitar uma mudança de texto (a tag da imagem) em outro repositório Git. Quem efetivamente
decide o que roda no cluster é sempre o [`Nexus-GitOps`](https://github.com/FelipeFranca07/Nexus-GitOps) + ArgoCD.

## Arquitetura do fluxo

```mermaid
flowchart LR
    A[Push no main] --> B[GitHub Actions: lint + test]
    B --> C[Build imagem Docker]
    C --> D[Push para GHCR]
    D --> E["Atualiza tag da imagem\nno repo Nexus-GitOps"]
    E --> F[ArgoCD detecta a mudança]
    F --> G[Sync automático no cluster K8s]
```

1. Push/PR no `main` dispara o pipeline de CI (lint com `ruff`, testes com `pytest`).
2. Em push no `main`, a imagem é construída e publicada no **GHCR**
   (`ghcr.io/felipefranca07/nexus-api`), tagueada com o SHA do commit (`sha-<7 chars>`).
3. O pipeline então clona o [`Nexus-GitOps`](https://github.com/FelipeFranca07/Nexus-GitOps), atualiza a tag da
   imagem no overlay `dev` (via `kustomize edit set image`) e faz commit/push dessa mudança — usando um token
   de escopo restrito, não as credenciais do próprio repositório.
4. O **ArgoCD**, que monitora o repositório GitOps, detecta a mudança e sincroniza automaticamente o cluster —
   sem nenhum `kubectl apply` manual.

Promoção para `staging`/`prod` é manual (ver [Fluxo de promoção](https://github.com/FelipeFranca07/Nexus-GitOps#fluxo-de-promoção)
no repositório GitOps) — só `dev` é atualizado automaticamente a cada push.

## Estrutura do repositório

```
.
├── app/
│   ├── __init__.py
│   └── main.py                  # FastAPI: /health, /ready, /tasks (CRUD em memória)
├── tests/
│   └── test_main.py             # pytest + TestClient
├── Dockerfile                   # multi-stage, usuário não-root, HEALTHCHECK
├── requirements.txt / requirements-dev.txt
├── .github/workflows/ci-cd.yml  # pipeline que efetivamente roda neste repo (GitHub Actions)
├── azure-pipelines.yml          # mesmo fluxo, referência Azure DevOps
└── .gitlab-ci.yml               # mesmo fluxo, referência GitLab CI
```

## Setup passo a passo (do zero)

Tudo o que precisa existir **fora do código** para a esteira funcionar de ponta a ponta, replicando este
padrão no seu próprio GitHub.

### Passo 1 — Criar os dois repositórios

Este padrão depende de **dois** repositórios (ver [A decisão central](#a-decisão-central-ci-nunca-toca-o-cluster)):
um de aplicação (este) e um de GitOps (`Nexus-GitOps`). Crie os dois antes de configurar qualquer secret.

### Passo 2 — Gerar o token que o pipeline usa para escrever no repo GitOps

O `GITHUB_TOKEN` padrão do Actions só tem permissão **dentro do próprio repositório** onde o workflow roda —
não alcança o repositório GitOps. É preciso um token à parte:

1. Acesse `github.com/settings/personal-access-tokens/new` (fine-grained).
2. **Repository access:** `Only select repositories` → selecione só o repositório GitOps.
3. **Permissions → Repository permissions → Contents:** `Read and write`.
4. Gere e copie o token.

> ⚠️ **Pegadinha comum:** se a opção `Public Repositories (read-only)` ficar selecionada em vez de
> `Only select repositories`, o token clona (lê) normalmente mas o `git push` falha com
> `403 Permission denied`, mesmo que "Contents: Read and write" apareça marcado na tela — nesse modo o GitHub
> ignora esse toggle. Se isso acontecer mesmo com a configuração aparentemente correta, teste o token
> isoladamente antes de desconfiar do pipeline:
> ```bash
> curl -X PUT -H "Authorization: Bearer <TOKEN>" \
>   https://api.github.com/repos/<owner>/<repo-gitops>/contents/.test \
>   -d '{"message":"test","content":"dGVzdA=="}'
> ```
> Uma resposta `403 Resource not accessible by personal access token` confirma que é o token, não o workflow.

### Passo 3 — Registrar o token como secret

No repositório da aplicação: `Settings → Secrets and variables → Actions → New repository secret`, nome
`GITOPS_PAT`, valor = o token do passo 2.

### Passo 4 — Habilitar o escopo `workflow` no seu editor local (se usar `gh` CLI)

Publicar/editar arquivos em `.github/workflows/` via `git push` exige o escopo OAuth `workflow` no seu client
Git. Se estiver usando o GitHub CLI: `gh auth refresh -s workflow`.

### Passo 5 — Ajustar os nomes

Troque `felipefranca07`/`Nexus-GitOps` pelos seus, em: `IMAGE_NAME` no topo do `.github/workflows/ci-cd.yml`,
no step `Checkout GitOps repo`, e nos arquivos `azure-pipelines.yml`/`.gitlab-ci.yml` se for usá-los.

### Checklist final

| Item | Onde vive |
|---|---|
| `GITOPS_PAT` (token com Contents: Read/write só no repo GitOps) | Secret do repositório (`Settings → Secrets and variables → Actions`) |
| Repositório GitOps já criado, com `apps/nexus-api/overlays/dev/` existente | GitHub, repositório separado |
| Nomes de imagem/owner ajustados | `ci-cd.yml`, `azure-pipelines.yml`, `.gitlab-ci.yml` |

## O pipeline, passo a passo

O `.github/workflows/ci-cd.yml` tem três jobs, cada um dependendo do anterior:

1. **`test`** — roda em todo push/PR. Lint (`ruff check`) e testes (`python -m pytest`, não `pytest` puro —
   ver nota abaixo). Se falhar, os próximos jobs nem começam.
2. **`build-and-push`** — só em push no `main`. Builda a imagem com Buildx (cache via `type=gha`) e publica no
   GHCR com duas tags: `sha-<commit>` (imutável, usada pelo deploy) e `latest` (conveniência).
3. **`update-gitops`** — clona o repositório GitOps com o `GITOPS_PAT`, roda `kustomize edit set image` no
   overlay `dev`, e commita/push a mudança. Se não houver diferença (`git diff --cached --quiet`), não cria
   commit vazio.

> ℹ️ **Por que `python -m pytest` e não `pytest`?** Sem o `python -m`, o diretório raiz do repositório não
> entra automaticamente no `sys.path`, e `from app.main import app` falha com `ModuleNotFoundError` — mesmo
> que rode perfeitamente na sua máquina (onde o ambiente local costuma já ter isso configurado de outra forma).
> É o tipo de diferença sutil entre "funciona no meu ambiente" e "funciona no runner do CI" que vale documentar.

> ℹ️ **Por que a imagem é sempre minúscula (`ghcr.io/felipefranca07/...`)?** O registry do GHCR (como qualquer
> registry OCI) exige nomes de repositório em minúsculas — `${{ github.repository_owner }}` no GitHub Actions
> preserva a capitalização exata da sua conta (`FelipeFranca07`), então usar essa variável direto no nome da
> imagem quebra o build com `repository name must be lowercase`. A correção é hardcodar (ou normalizar) o nome
> em minúsculas no `IMAGE_NAME`.

## Pipelines de referência (Azure DevOps / GitLab CI)

O CI que efetivamente roda neste repositório é o **GitHub Actions**. Também incluí, como referência funcional
(mesmos estágios, mesma lógica), o mesmo fluxo em:

- `azure-pipelines.yml` — equivalente em Azure DevOps (a plataforma que uso no dia a dia)
- `.gitlab-ci.yml` — equivalente em GitLab CI

para deixar explícito que o padrão GitOps é independente de orquestrador de CI — a única coisa que muda é a
sintaxe do "builda, publica, atualiza o repo GitOps".

## Rodando localmente

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

```bash
docker build -t nexus-api .
docker run -p 8000:8000 nexus-api
```

Endpoints: `GET /health`, `GET /ready`, `GET /tasks`, `POST /tasks`, `GET /tasks/{id}`, `DELETE /tasks/{id}`.

## Comandos úteis / como testar

**Rodar lint e testes como o CI roda:**
```bash
ruff check app tests
python -m pytest -v
```

**Corrigir automaticamente o que o `ruff` conseguir:**
```bash
ruff check --fix app tests
```

**Testar os endpoints manualmente com a API rodando local:**
```bash
curl -X POST localhost:8000/tasks -H "Content-Type: application/json" -d '{"title":"Testar GitOps"}'
curl localhost:8000/tasks
```

**Disparar o pipeline manualmente e acompanhar (via GitHub CLI):**
```bash
gh workflow run ci-cd.yml
gh run watch
```

**Ver se o repositório GitOps recebeu o bump de tag esperado após um push:**
```bash
gh api repos/<owner>/Nexus-GitOps/contents/apps/nexus-api/overlays/dev/kustomization.yaml \
  --jq '.content' | base64 -d | grep newTag
```

## Como adaptar para o seu ambiente

- **Outro registry?** Troque `ghcr.io/...` por `docker.io/...`/ECR/ACR no `IMAGE_NAME` e no step de login —
  o resto do pipeline (lint, test, bump de tag) não muda.
- **Sem GitHub Actions?** Use `azure-pipelines.yml` ou `.gitlab-ci.yml` como ponto de partida — a lógica de
  três estágios (test → build/push → update-gitops) é a mesma.
- **Mais de um ambiente atualizado automaticamente?** Hoje só `dev` é atualizado pelo CI; para automatizar
  `staging` também, repita o step `Bump image tag` apontando para `overlays/staging` (mas veja o trade-off de
  sync automático vs. manual no README do [`Nexus-GitOps`](https://github.com/FelipeFranca07/Nexus-GitOps)).
- **Outro framework além de FastAPI?** Só `app/main.py`, `requirements.txt` e o `Dockerfile` mudam — o
  pipeline não assume nada específico do FastAPI além do `HEALTHCHECK` batendo em `/health`.

## Boas práticas de segurança

- **O `GITOPS_PAT` nunca tem mais acesso do que o necessário.** Fine-grained, restrito a um único repositório,
  só com `Contents: Read and write` — nunca um token clássico com escopo `repo` completo (que alcançaria
  *todos* os seus repositórios) ou pior, com escopos administrativos (`admin:org`, `delete_repo`).
- **Nunca versione tokens/segredos no código.** Todos os exemplos deste README usam `<TOKEN>` como placeholder;
  o valor real vive só em `Settings → Secrets`.
- **A imagem roda como usuário não-root** (`Dockerfile`: `useradd --create-home appuser` + `USER appuser`) —
  reduz o blast radius se algum dia houver uma vulnerabilidade de escape de container.
- **O bot do CI é uma identidade distinta** (`nexus-ci-bot`, e-mail `noreply`) — nunca reusa
  suas credenciais pessoais para os commits automáticos, o que manteria a trilha de auditoria confusa entre
  "eu commitei isso" e "o robô commitou isso".

## Repositório GitOps

Manifests Kubernetes, overlays por ambiente (dev/staging/prod) e Applications do ArgoCD (padrão *App of Apps*)
ficam em [`Nexus-GitOps`](https://github.com/FelipeFranca07/Nexus-GitOps).

---

*Este documento descreve um padrão de arquitetura de referência, construído do zero para estudo e portfólio —
não uma extração de ambiente de produção real.*
