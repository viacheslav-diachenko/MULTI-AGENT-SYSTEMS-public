# Домашнє завдання: Langfuse observability

Підключіть Langfuse до вашої мультиагентної системи з останньої домашньої роботи, налаштуйте tracing та online evaluation через LLM-as-a-Judge.

---

### Що змінюється порівняно з попередніми homework

| Було | Стає |
|---|---|
| Немає observability — система працює як чорна скринька | Кожен запуск трейситься в Langfuse з повним деревом викликів |
| DeepEval тести запускаються локально вручну (hw10) | Langfuse автоматично оцінює нові трейси через LLM-as-a-Judge |
| Промпти захардкоджені в коді | Усі system prompts агентів винесено в Langfuse Prompt Management |

---

### Що потрібно зробити

#### 0. Налаштування Langfuse Cloud

1. Зареєструйтесь на [us.cloud.langfuse.com](https://us.cloud.langfuse.com) (free tier, без credit card)
2. Створіть Organization → Project (наприклад, `homework-12`)
3. **Settings → API Keys → + Create new API keys** — скопіюйте `Public Key` (`pk-lf-...`) та `Secret Key` (`sk-lf-...`)
4. Збережіть ключі у `.env` файл:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

---

#### 1. Підключення tracing до мультиагентної системи

Інтегруйте Langfuse так, щоб **кожен запуск вашої MAS** створював **trace** у Langfuse з повним деревом (усі LLM-виклики, tool calls, суб-агенти — вкладені під один батьківський trace).

Зверніть увагу на:
- `@observe` декоратор та `CallbackHandler` для LangChain/LangGraph — див. [документацію інтеграції](https://langfuse.com/docs/integrations/langchain)
- `propagate_attributes` для прокидання `session_id`, `user_id`, `tags` на весь trace

**Критерій:** зробіть 3-5 запусків з різними запитами. У Langfuse UI → **Tracing → Traces** має бути 3-5 рядків, кожен розгортається у повне дерево з суб-агентами та tool calls.

---

#### 2. Session та User tracking

Переконайтесь, що ваші traces згруповані у **session** і мають `user_id`:

- Після 3-5 запусків перевірте Langfuse UI:
  - **Sessions** tab — має з'явитися ваша сесія з кількома трейсами всередині
  - **Users** tab — має з'явитися ваш user

---

#### 3. Prompt Management

Винесіть **усі system prompts ваших агентів** з коду в Langfuse Prompt Management. Після цього жоден промпт не повинен бути захардкоджений у Python-файлах — код лише завантажує промпти з Langfuse за іменем та label.

##### 3.1. Створіть промпти у Langfuse UI

Для кожного агента у вашій системі:

1. **Prompts → + New prompt**
2. Задайте ім'я, що відповідає ролі агента
3. Вставте текст промпту. Використовуйте template variables (`{{...}}`) де промпт параметризований
4. Додайте label `production`

##### 3.2. Завантажте промпти з коду

Використовуйте `get_prompt(name, label=...)` з Langfuse Python SDK для завантаження промптів, та `.compile(**variables)` для підстановки template variables. Див. [документацію Prompt Management](https://langfuse.com/docs/prompts).

**Критерій:**
- У коді **жодних захардкоджених system prompts** — усі завантажуються з Langfuse
- У Langfuse UI → **Prompts** — видно промпт для кожного агента

---

#### 4. LLM-as-a-Judge: online evaluation у Langfuse

Налаштуйте **автоматичну оцінку** нових трейсів через Langfuse Evaluators.

##### 4.1. Створіть evaluator'и у Langfuse UI

1. Перейдіть: **LLM-as-a-Judge → Evaluators → + Set up evaluator**
2. Створіть **мінімум 2 evaluator'и** з різними score type (numeric, boolean, або categorical)
3. Самостійно продумайте, які аспекти якості найважливіші для вашої конкретної системи — наприклад: relevance відповіді, groundedness фактів, повнота дослідження, структурованість output'у, тощо
4. Напишіть evaluation prompts, використовуючи template variables `{{input}}`, `{{output}}`

Див. [документацію LLM-as-a-Judge](https://langfuse.com/docs/scores/model-based-evals) для доступних score types, template variables та прикладів.

##### 4.2. Запустіть і перевірте

1. Зробіть 3-5 нових запусків вашої системи
2. Зачекайте 1-2 хвилини — Langfuse виконає evaluation асинхронно
3. Перевірте результати:
   - **Tracing → Traces** → відкрийте trace → вкладка **Scores** — має бути автоматично проставлений score від evaluator'а
   - **LLM-as-a-Judge → Evaluators** → статус evaluator'а показує кількість оброблених трейсів

---

### Вимоги

1. **Tracing працює:** кожен запуск MAS → trace з повним деревом суб-агентів і tool calls
2. **Session/User:** traces згруповані в session, мають user_id
3. **Prompt Management:** усі system prompts агентів завантажуються з Langfuse (жодних захардкоджених)
4. **LLM-as-a-Judge:** мінімум 2 evaluator'и налаштовані, автоматично оцінюють нові traces
5. **Скріншоти:** 4 скріншоти з Langfuse UI (trace tree, session, evaluator scores, prompt management)

---

### Що здавати
- Папка `screenshots/` з 4 скріншотами з Langfuse UI

---
---

# Імплементація

Мультиагентна дослідницька система з **Langfuse self-hosted** як шаром
observability: кожен запуск створює trace з повним деревом sub-agent-ів,
4 system prompts живуть у Prompt Management, 2 LLM-as-a-Judge
evaluator-и автоматично скорять нові traces.

**Версія:** 1.0.0

## Що додано в 1.0.0

- Langfuse self-hosted (ns `langfuse`, helm chart `langfuse/langfuse`
  v1.5.27) з повним стеком Postgres + ClickHouse + Redis/Valkey + MinIO.
- `langfuse_setup.py` — singleton-клієнт, `CallbackHandler`, кешований
  `get_prompt_text(name, label, **vars)`.
- `CallbackHandler` + `@observe` інструментація: кожен REPL turn = один
  trace (`hw12-repl-turn`) з `session_id` / `user_id` / `tags`,
  під яким вкладені suq-agent spans (Planner / Researcher / Critic) з
  усіма LLM-викликами й tool calls.
- Всі 4 system prompts вивантажено у Langfuse Prompt Management
  (`hw12/{supervisor,planner,researcher,critic}_system`, label
  `production`). Жодних захардкоджених промптів у runtime-коді —
  перевірка `grep -r "You are " --include="*.py"` повертає лише
  `scripts/seed_prompts.py` (публікатор).
- 2 LLM-as-a-Judge evaluator-и — `answer_relevance` (numeric 0..1) та
  `citation_presence` (boolean). Judge-модель — **self-hosted
  Gemma 4** (`gemma-4-26b-a4b-it` на `uaai-vllm19.onyx.svc:8000`),
  та сама інстанція, що Onyx використовує як secondary LLM.
  Evaluators фільтрують по `tag:hw12` і scorять 100% нових traces
  з 30-секундним delay.
- `scripts/seed_prompts.py` — one-off push промптів; ідемпотентний
  (повторний запуск = нова version + repromotion `production`).
- `scripts/seed_evaluators.py` — one-off налаштування LLM Connection
  + 2 evaluator templates + 2 job configurations. Автентифікується
  як headless-init-admin через NextAuth credentials (cookie jar),
  тоді викликає tRPC mutations (`llmApiKey.create`,
  `evals.createTemplate`, `evals.createJob`).
- `k8s/` — infra-as-code: helm values + Traefik `IngressRoute` +
  Authelia forward-auth middleware.

## Що змінилось порівняно з hw10

| Було (hw10 — offline eval) | Стає (hw12 — online observability) |
|---|---|
| Якість ловиться локально через `deepeval test run` | Якість ловиться в продакшн-трафіку через Langfuse online evaluators |
| Промпти = source code (hashed через `inspect.getsource`) | Промпти = артефакти в Langfuse Prompt Management, fetch за `label=production` |
| Timestamps у тілі промпта → окрема logic для hash-stability | Timestamps як `{{template}}` змінні, тіло у Langfuse стабільне |
| Нема observability у runtime | Повний trace tree + session + cost/latency per span у Langfuse UI |
| Evaluator runs локально на snapshot-fixtures | Evaluator runs серверно у Langfuse на live traces |
| `hw8 runtime` імпортується / копіюється | Те саме — hw12 це hw10 runtime + Langfuse шар |

## Архітектура

```text
REPL (main.py)
  │  @observe("hw12-repl-turn")
  │  + propagate_attributes(session_id, user_id, tags, metadata)
  ▼
Supervisor (create_agent + HITL middleware + InMemorySaver)
  │  config={"callbacks": [langfuse_callback], "configurable": {"thread_id"}}
  │
  ├── plan       → Planner      → tool calls (web_search / knowledge_search)
  ├── research   → Researcher   → tool calls (web_search / read_url / knowledge_search)
  ├── critique   → Critic       → tool calls (web_search / read_url / knowledge_search)
  └── save_report → HITL gate (approve / edit / revise / reject)
       │
       ▼
   ── HTTPS POST traces (OTLP)  ──►  Langfuse web (ns: langfuse)
      http://langfuse-web.langfuse.svc:3000                │
                                                           ├─ ClickHouse (traces, spans, scores)
                                                           ├─ Postgres (users, projects, prompts)
                                                           ├─ Redis (queue)
                                                           └─ MinIO (trace blobs, exports)
                                                           │
                                                           ▼ filter tag:hw12, sampling 100%
                                                       Evaluators job runner
                                                           │
                                                           ▼
                                         LLM Connection: OpenAI-compatible
                                         http://uaai-vllm19.onyx.svc:8000/v1
                                         model: gemma-4-26b-a4b-it
                                                           │
                                                           ▼
                                         Scores attached to trace:
                                           • answer_relevance (numeric 0..1)
                                           • citation_presence (boolean)
```

### Ключові патерни з Лекції 12

- **Trace / Span / Session** (§2.1) — `@observe("hw12-repl-turn")`
  навколо `_run_turn(user_input, thread_id)` у `main.py` відкриває
  один trace per REPL turn. `CallbackHandler` переданий у
  `RunnableConfig.callbacks` у supervisor.stream → всі вкладені
  sub-agent LLM-виклики й tool calls потрапляють у те саме дерево.
- **Propagate attributes** — `propagate_attributes(session_id,
  user_id, tags, metadata)` всередині `@observe`-блоку ставить ці
  поля на trace + усі spans під ним. Session = один REPL-процес,
  user = env var `LANGFUSE_USER_ID`.
- **Prompt Registry як конфігурація, не код** (§3) — всі 4 системні
  промпти керуються через Langfuse UI (label `production`) без
  redeploy коду. Timestamps передаються як template variables
  (`{{current_datetime}}`, `{{current_date}}`), щоб тіло у Langfuse
  не змінювалось між викликами (урок hw10 v1.0.4 про prompt-hash
  drift).
- **LLM-as-a-Judge online** (§2.2) — judge запускається серверно в
  Langfuse на нових traces. Sampling 100% для homework; у проді
  знижуємо для економії вартості.
- **Self-hosted judge, а не OpenAI** — Gemma 4 на власному vLLM поруч
  з MAS-ом. Дає: (1) нуль-cost evals, (2) жодні дані не виходять
  за периметр кластера, (3) та сама модель слугує Onyx — one spend,
  multi-tenant.

## Компоненти

### `langfuse_setup.py`
- Singleton `langfuse_client = get_client()` + `langfuse_callback =
  CallbackHandler()` при імпорті.
- `get_prompt_text(name, *, label="production", **variables)` —
  memoized-per-process fetch + `.compile(**vars)`. Restart REPL після
  promotion нової версії (lru_cache).
- `load_dotenv(PROJECT_ROOT/.env)` ВИКЛИКАЄТЬСЯ перед
  `get_client()` — Langfuse SDK читає `LANGFUSE_*` з `os.environ`,
  а pydantic-settings вантажить лише у `Settings` (не в env).

### `config.py`
- `Settings` (pydantic) — незмінна з hw10, окрім `"extra":"ignore"`
  для толерантності до `LANGFUSE_*` env vars.
- 4 `get_*_prompt()` функції тепер повертають
  `get_prompt_text("hw12/<role>_system", ...)`.

### `supervisor.py`
- Новий helper `_sub_agent_config()` → `RunnableConfig(callbacks=
  [langfuse_callback])` переданий у `sub_agent.invoke(...)` у кожному
  з 3 tool-обгорток `plan`/`research`/`critique`. Без цього sub-agent
  spans жили б в окремому (unparented) trace.

### `main.py`
- `_SESSION_ID = f"hw12-repl-{uuid[:8]}"` — per-process, всі turn-и
  одного REPL потрапляють в один session.
- `_run_turn(user_input, thread_id)` обгорнутий у `@observe(name=
  "hw12-repl-turn")`; тіло у `with propagate_attributes(...)` блоці
  викликає `supervisor.stream(...)`.
- `_current_config["callbacks"] = [langfuse_callback]` — LangChain
  callback активний і в `stream(...)`, і в `_resume_supervisor(...)`
  (HITL approve/edit/revise/reject).

### `scripts/seed_prompts.py` (one-off)
- `langfuse_client.create_prompt(name, prompt, labels=["production"])`
  для 4 промптів. Ідемпотентний.

### `scripts/seed_evaluators.py` (one-off)
- NextAuth credentials login → cookie jar → tRPC mutations для
  `llmApiKey.create`, `evals.createTemplate`, `evals.createJob`.
- Створює LLM Connection (`provider=gemma-vllm`, base URL
  `uaai-vllm19.onyx.svc:8000/v1`, model `gemma-4-26b-a4b-it`)
  + 2 templates + 2 jobs (фільтр `tag:hw12`, sampling 100%).

## Встановлення та запуск

### Передумови

- k8s cluster з:
  - **vLLM Qwen3.6-35B** на `uaai-llm.onyx.svc:8000` (target модель MAS)
  - **vLLM Gemma 4** на `uaai-vllm19.onyx.svc:8000` з
    `--enable-auto-tool-choice --tool-call-parser gemma4` (judge)
  - **TEI embeddings** на `uaai-embed.onyx.svc:7998`
  - **Infinity reranker** на `uaai-reranker.onyx.svc:7997`
  - cluster-wide Authelia forward-auth middleware (`onyx/auth-server`)
- Python 3.10+
- kubectl + helm 3

### Інфра (one-off)

```bash
cd homework-lesson-12

# 1. Секрети Langfuse (salt, nextauth.secret, encryptionKey, DB паролі)
#    генеруються локально й потрапляють у K8s Secret — values.yaml
#    посилається на них через secretKeyRef (Rule 11.2).
# Приклади в k8s/langfuse-secrets-template.yaml (значення blank).

# 2. Helm-install Langfuse
kubectl create ns langfuse
helm repo add langfuse https://langfuse.github.io/langfuse-k8s
helm install langfuse langfuse/langfuse --version 1.5.27 \
    -n langfuse -f k8s/langfuse-values.yaml

# 3. Ingress + Authelia middleware
kubectl apply -f k8s/langfuse-ingress.yaml

# 4. (Один раз) Seed Prompt Management
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # заповніть LANGFUSE_{PUBLIC,SECRET}_KEY з init-secret
.venv/bin/python scripts/seed_prompts.py

# 5. (Один раз) Seed LLM Connection + evaluators
.venv/bin/python scripts/seed_evaluators.py \
    --base-url http://127.0.0.1:3001 --project homework-12
```

### Щоденний запуск

```bash
# Один REPL процес = один Langfuse session
.venv/bin/python main.py

> LangChain vs LangGraph — key diff?
> new     # починає новий session
> exit
```

## Mapping README-brief → артефакти

| # | Вимога | Файл / UI-артефакт |
|---|---|---|
| 1 | Tracing кожного запуску | `langfuse_setup.langfuse_callback` + `main.py::_run_turn` з `@observe` |
| 2 | Session + user_id | `main.py::propagate_attributes(session_id=_SESSION_ID, user_id=_USER_ID)` |
| 3 | Prompt Management (0 hardcoded) | `hw12/*_system` у Langfuse UI + `config.py` через `get_prompt_text` |
| 4 | ≥2 evaluators | Langfuse UI → LLM-as-a-Judge → `answer_relevance`, `citation_presence` |
| 5 | 4 скріншоти | `screenshots/01-04-*.png` |

## Конфігурація

| Env var | Default | Опис |
|---|---|---|
| `API_BASE` | — | vLLM endpoint для MAS (Qwen3.6) |
| `MODEL_NAME` | `qwen3.6-35b-a3b` | назва моделі MAS |
| `LANGFUSE_PUBLIC_KEY` | — | `pk-lf-...` з Langfuse UI |
| `LANGFUSE_SECRET_KEY` | — | `sk-lf-...` з Langfuse UI |
| `LANGFUSE_HOST` | `http://langfuse-web.langfuse.svc:3000` | self-hosted endpoint для SDK |
| `LANGFUSE_USER_ID` | `student_demo` | label для Users tab (не ставте персональний email) |

## Структура проєкту

```text
homework-lesson-12/
├── README.md                   # цей файл (brief + ця секція)
├── CHANGELOG.md                # Keep-a-Changelog UA
├── requirements.txt            # hw10 deps + langfuse>=3,<4 + python-dotenv
├── .env.example                # + LANGFUSE_* vars
├── .gitignore
│
├── langfuse_setup.py           # singleton client + callback + get_prompt_text
├── config.py                   # prompt helpers → Langfuse registry
├── supervisor.py               # sub-agent invocations → langfuse_callback
├── main.py                     # @observe + propagate_attributes
│
├── agents/{planner,research,critic}.py   # з hw10, untouched
├── schemas.py, tools.py, tool_parser.py, retriever.py, ingest.py  # з hw10
├── data/, index/               # PDFs + FAISS (з hw10)
│
├── scripts/
│   ├── seed_prompts.py          # push 4 prompts → Prompt Management
│   └── seed_evaluators.py       # LLM Connection + 2 evaluators
│
├── k8s/
│   ├── langfuse-values.yaml     # helm values (no secrets)
│   └── langfuse-ingress.yaml    # Traefik Ingress + Authelia middleware
│
└── screenshots/                 # 4 скріншоти Langfuse UI (redacted)
    ├── 01-trace-tree.png
    ├── 02-session.png
    ├── 03-evaluator-scores.png
    └── 04-prompt-management.png
```

## Обмеження поточного релізу

- **Prompt label promotion → restart REPL.** `lru_cache` кешує
  prompt-body on import. Після зміни `production`-тегу у Langfuse
  UI необхідно перезапустити python-процес, щоб підхопилась нова
  версія. Follow-up: `/reload-prompts` REPL-команда, яка чистить
  `_fetch_prompt.cache_clear()`.
- **Cost tracking показує $0** для Qwen / Gemma — моделі не у
  Langfuse pricing-таблиці. Tokens + latency коректні; вартість —
  informational-only.
- **Evaluators з UI працюють лише для traces-фільтрованих тегом.**
  Наш filter `tag:hw12` — інші трейсити (якщо з'являться) не
  скоряться; це by design для homework-scope.
- **HITL `save_report` в batch-режимі auto-reject-иться на EOF.**
  Для screenshot-runs це OK (output trace вже заповнений), але
  для реальних прогонів потрібен інтерактивний stdin.
- **Seed-скрипти мають port-forward залежність.** Локальний запуск
  використовує `kubectl port-forward svc/langfuse-web 3001:3000`.
  Production SDK ходить напряму через ClusterIP
  `http://langfuse-web.langfuse.svc:3000` — no port-forward.

## Відомі кроки ручного налаштування

- `LANGFUSE_INIT_*` env vars у helm values запускають headless-admin
  першого user-а. Після першого boot — `kubectl -n langfuse exec
  langfuse-postgresql-0 -- psql -c "INSERT INTO project_memberships
  ..."` — bootstrap admin-у потрібне явне членство у project (не
  лише org-level OWNER), щоб викликати `evals.createTemplate`.
  Без цього — `UNAUTHORIZED`. Патерн задокументовано у seed скрипті,
  але сам INSERT робимо вручну 1 раз.
- MinIO bucket creds. `s3.auth.rootPassword` у chart повинен
  *мапитись на той самий secret key, що `s3.secretAccessKey`* —
  інакше Langfuse web повертає `SignatureDoesNotMatch` на кожен
  upload trace-blob. Fix у `k8s/langfuse-values.yaml`
  (`rootPasswordSecretKey: secretAccessKey`).
