# Changelog

Усі значущі зміни в проєкті документуються в цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/).

## [1.0.0] - 2026-04-23

### Додано

- `langfuse_setup.py` — singleton `langfuse_client`, `langfuse_callback`,
  `get_prompt_text(name, label, **vars)` з `lru_cache`. Автоматичний
  `load_dotenv()` з `PROJECT_ROOT/.env` перед створенням клієнта (SDK
  не читає .env сам, pydantic-settings вантажить тільки у `Settings`).
- `scripts/seed_prompts.py` — one-off push 4 MAS system prompts у
  Langfuse Prompt Management з label `production`. Idempotent —
  повторний запуск публікує нову версію й перепромотить `production`.
- K8s інфраструктура (`k8s/`):
  - `langfuse-values.yaml` — helm chart `langfuse/langfuse` v1.5.27,
    bundled stack (Postgres + ClickHouse + Redis/Valkey + MinIO),
    `signUpDisabled: true`, `telemetryEnabled: false`, headless init
    через `LANGFUSE_INIT_*` env vars.
  - `langfuse-ingress.yaml` — Traefik `IngressRoute` UI-only на
    `https://ualangfuse.elkogroup.com` з middleware chain
    `langfuse-authelia-forward-auth, kube-system-security-headers,
     kube-system-rate-limit, kube-system-compression`. MAS трафік
    бʼється в ClusterIP `http://langfuse-web.langfuse.svc:3000` без
    Authelia — SDK автентифікується через `pk-lf`/`sk-lf`, не browser
    cookies.
- `.env.example` доповнено секцією `LANGFUSE_*` (public key, secret key,
  host, user_id).
- `requirements.txt` — `langfuse>=3,<4`, `python-dotenv>=1.0`,
  RAG-залежності з hw10 (`ddgs`, `trafilatura`, `faiss-cpu`,
  `rank-bm25`, `pypdf`). Пін `langgraph==1.1.6` / `langchain==1.2.13`
  синхронізовано з робочим `.venv` hw10 — інакше ловиться
  `ImportError: ServerInfo from langgraph.runtime`.

### Змінено

- `config.py` — 4 функції `get_{supervisor,planner,researcher,critic}_prompt()`
  більше не містять тіла промпта. Вони викликають
  `get_prompt_text("hw12/<role>_system", ...)`, а runtime-значення
  (`current_datetime`, `current_date`, `max_revision_rounds`)
  передаються як `{{template}}` змінні — тіло у Langfuse стабільне
  між викликами (урок hw10 v1.0.4 про prompt-hash drift).
- `config.Settings.model_config` — додано `"extra": "ignore"`, щоб
  pydantic-settings не падав на `LANGFUSE_*` env vars (вони для
  SDK, не для Settings).
- `supervisor.py` — у `plan` / `research` / `critique` tool-обгортках
  додано `config=RunnableConfig(callbacks=[langfuse_callback])` у
  `sub_agent.invoke(...)`. Без цього spans суб-агентів потрапляли в
  окремий (unparented) trace, а не під trace REPL-turn-у.
- `main.py` — новий `@observe("hw12-repl-turn")` враппер `_run_turn`:
  відкриває один trace на user-turn, у `propagate_attributes` блоці
  виставляє `session_id` / `user_id` / `tags` / `metadata` на весь
  trace. `_current_config` тепер містить
  `"callbacks": [langfuse_callback]`, тому supervisor stream теж
  трейситься. `_resume_supervisor` (HITL approve/edit/revise/reject)
  наслідує те саме — один trace на весь turn, включно з resume-ами.

### Конфігурація системи

- Project: `homework-12` (org `homework-org`).
- LLM Connection (для evaluator-ів, налаштовується в UI):
  provider `openai`, base URL `http://uaai-vllm19.onyx.svc:8000/v1`,
  model `gemma-4-26b-a4b-it`, api-key будь-який — vLLM не валідує.
- MAS LLM залишається Qwen3.6-35B-A3B (`uaai-llm.onyx.svc:8000`).
- Session stride: один процес REPL → один `SESSION_ID`
  (`hw12-repl-<hex>`), `USER_ID` з env (`student_demo` за умовчанням).

### Виправлено (після першого прогону)

- **[P1] Dual-URL NextAuth (public HTTPS + internal HTTP) — фінальна
  конфігурація.** Дві окремі вимоги до session-cookie domain:
  (a) external user → `https://ualangfuse.elkogroup.com` через
  Authelia → cookie повинен мати `Domain=ualangfuse.elkogroup.com` +
  `Secure`, інакше браузер відкине;
  (b) in-cluster automation (Playwright, seed скрипти) ходить на
  `http://langfuse-web.langfuse.svc:3000` без HTTPS — потрібна
  можливість логінитися без `Secure`-cookies і без проходу через
  Authelia.
  Перший підхід тимчасово виставив `nextauth.url=internal` для
  Playwright, але це зламало browser-flow: cookie встановлювався
  на internal host і не зберігався, користувач після Authelia
  повертався на /auth/sign-in.
  Фінальне рішення: `nextauth.url=https://ualangfuse.elkogroup.com`
  (publicly correct cookie domain) + `NEXTAUTH_URL_INTERNAL=
  http://langfuse-web.langfuse.svc:3000` у `additionalEnv`. NextAuth
  публічно знає про HTTPS host (cookie OK для browser), але внутрішні
  callbacks резолвляться на in-cluster URL (Playwright/seed працюють
  через ClusterIP). Шаблон з NextAuth docs про reverse-proxy.
  Задокументовано у `k8s/langfuse-values.yaml`.
- **[P1] MinIO root password мапингу.** `s3.auth.rootPasswordSecretKey`
  спочатку вказував на `rootPassword`, у той час як Langfuse web/worker
  читали `s3.secretAccessKey` — через це `SignatureDoesNotMatch` на
  кожен trace-blob upload. Виправлено: `rootPasswordSecretKey:
  secretAccessKey` (той самий key у тому ж secret).
- **[P1] Bitnami Postgres очікує `postgres-password`, не `password`.**
  Початковий secret мав лише `password` → CreateContainerConfigError.
  Тепер secret містить обидва ключі з тим самим значенням.

### Відкрите

- **OTLP → evaluator pipeline gap.** Langfuse 3.169 обробляє
  OpenTelemetry-ingested traces через окрему ClickHouse-pipeline, яка
  НЕ викликає `trace-upsert` → `create-eval-queue` → evaluator jobs.
  Python Langfuse SDK v3.14 emit-ить OTLP за замовчуванням, тому наші
  traces ніколи не тригерили online-evaluator-ів, навіть коли
  `job_configurations` ACTIVE з `timeScope: [NEW, EXISTING]`. Workaround:
  `scripts/manual_eval.py` читає нові hw12-traces через public API,
  викликає judge-LLM вручну тим самим prompt-ом що й configured
  evaluator, і attach-ить scores через `langfuse_client.create_score()`
  — результат візуально ідентичний в UI (Scores tab на trace). Коли
  Langfuse закриє цей gap (або ми перейдемо на SDK-native ingestion),
  online evaluators підхоплять automatically без змін у MAS-коді.
- **Prompt-label hot-reload без restart REPL** — follow-up (додати
  `/reload-prompts` REPL-команду, яка чистить `_fetch_prompt.cache_clear()`).
- **Cost tracking у Langfuse для Qwen / Gemma показує `$0`** — моделі
  не у pricing-table Langfuse. Tokens + latency коректні; вартість —
  informational-only.
- **HumanInTheLoopMiddleware в batch-mode** — `input()` на closed stdin
  блокувався, а не кидав EOFError. Додано `sys.stdin.isatty()` check
  у `main.py::handle_interrupt`: якщо не tty, автоматично `reject` на
  save_report → trace закривається чисто. Інтерактивний запуск
  повністю зберіг попередню поведінку.
