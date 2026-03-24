# Research Agent з RAG-системою

Дослідницький агент з **гібридним пошуком по локальній базі знань** (semantic + BM25 + reranking),
який комбінує результати з інтернету та інгестованих документів для створення
комплексних відповідей.

Еволюція [homework-lesson-3](../homework-lesson-3/) — додано RAG-інструмент `knowledge_search`
з повним ingestion pipeline, hybrid retrieval та cross-encoder reranking через
self-hosted інфраструктуру (без зовнішніх API).

## Demo

![Research Agent with RAG Demo](demo.gif)

---

## Що змінилось: Lesson-3 → Lesson-5

| Аспект | Lesson-3 (було) | Lesson-5 (стало) |
|--------|------------------|-------------------|
| **Tools** | `web_search`, `read_url`, `write_report` | + новий `knowledge_search` (RAG) |
| **Джерела інформації** | Тільки інтернет | Інтернет + локальна база знань |
| **Embeddings** | — | Qwen3-Embedding-8B (4096 dims) через TEI |
| **Vector DB** | — | FAISS (локальний, зберігається на диск) |
| **Lexical search** | — | BM25 через `rank_bm25` |
| **Reranking** | — | BAAI/bge-reranker-v2-m3 через Infinity API |
| **Ingestion** | — | PDF → chunks → FAISS index + BM25 JSON |
| **System prompt** | Базовий (web-only) | Розширений (knowledge base first strategy) |

### Що додано

1. **Knowledge Ingestion Pipeline** (`ingest.py`) — завантажує PDF з `data/`, розбиває на
   чанки через `RecursiveCharacterTextSplitter`, генерує embeddings через TEI,
   зберігає FAISS індекс + BM25 чанки на диск.

2. **Hybrid Retriever** (`retriever.py`) — об'єднує semantic search (FAISS cosine similarity)
   з lexical search (BM25 keyword matching), дедуплікує результати, потім reranks
   через Infinity API (cross-encoder).

3. **RAG Tool** (`knowledge_search`) — агент сам вирішує, коли шукати в базі знань,
   а коли в інтернеті. Стратегія: knowledge base first для domain topics.

---

## Архітектура

```
┌──────────────────────────────────────────────────────────────────────┐
│                          main.py (REPL)                              │
│   input() → agent.stream() → print() (streaming output)             │
│   Команди: exit, quit, new (reset session)                           │
└────────────────┬─────────────────────────────────────────────────────┘
                 │ stream()
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                agent.py (LangGraph ReAct Agent)                      │
│                                                                      │
│  ┌──────────────────┐ ┌────────────┐ ┌─────────────────────────────┐ │
│  │    ChatOpenAI     │ │ MemorySaver│ │  create_react_agent()       │ │
│  │ (Qwen3.5 SGLang) │ │ (memory)   │ │  ReAct loop                 │ │
│  └────────┬─────────┘ └────────────┘ └─────────────────────────────┘ │
│           │                                                          │
│  ┌────────▼──────────────────────────────────────────────────────┐   │
│  │           tool_parser.py (Qwen3ChatWrapper)                   │   │
│  │  Intercepts XML tool calls → converts to LangChain format     │   │
│  └───────────────────────────────────────────────────────────────┘   │
└────────────────┬─────────────────────────────────────────────────────┘
                 │ tool calls
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     tools.py (4 інструменти)                         │
│                                                                      │
│  knowledge_search()     web_search()    read_url()   write_report()  │
│  HybridRetriever        DDGS search     trafilatura   File I/O       │
│  → ranked passages      → snippets      → full text   → .md file    │
│  (≤6000 chars)          (≤4000 chars)   (≤8000 chars)                │
└────────┬─────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│               retriever.py (HybridRetriever)                         │
│                                                                      │
│   ┌────────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│   │  FAISS Vector  │  │ BM25 Lexical │  │  InfinityReranker      │   │
│   │  (semantic)    │  │ (keywords)   │  │  (cross-encoder HTTP)  │   │
│   └───────┬────────┘  └──────┬───────┘  └───────────┬────────────┘   │
│           │                  │                      │                │
│           └──── merge + dedup ──────────────────────┘                │
│                        │                                             │
│              top_k → rerank → top_n                                  │
└──────────────────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
┌─────────────────────┐        ┌───────────────────────────────────────┐
│  FAISS Index (disk)  │        │  K3s Cluster Services                 │
│  index/index.faiss   │        │                                       │
│  index/index.pkl     │        │  TEI (Qwen3-Embedding-8B) :7998       │
│  index/bm25_chunks.  │        │  Infinity (bge-reranker-v2-m3) :7997  │
│       json           │        │  SGLang (Qwen3.5-35B-A3B) :8000       │
└─────────────────────┘        └───────────────────────────────────────┘
```

### RAG Pipeline — покроковий flow

```
python ingest.py (офлайн, одноразово)
  │
  ▼
┌─ Ingestion ──────────────────────────────────────────────────┐
│ 1. PyPDFLoader → завантажує 3 PDF (52 сторінки)               │
│ 2. RecursiveCharacterTextSplitter → 462 чанки (500 chars)     │
│ 3. OpenAIEmbeddings (TEI) → embeddings (4096 dims)            │
│ 4. FAISS.from_documents() → vector index                      │
│ 5. Зберігає: index.faiss + index.pkl + bm25_chunks.json       │
└──────────────────────────────────────────────────────────────┘

python main.py (онлайн, інтерактивно)
  │
  ▼
User: "Що таке RAG і які є підходи до retrieval?"
  │
  ▼
┌─ Ітерація 1 ─────────────────────────────────────────────────┐
│ Agent вирішує: domain topic → knowledge_search                │
│ HybridRetriever:                                              │
│   FAISS → 10 semantic matches                                 │
│   BM25  → 10 keyword matches                                  │
│   Merge → ~15 unique docs                                     │
│   Infinity reranker → top 3 (з scores)                        │
│ Agent отримує 3 найрелевантніші пасажі з source metadata      │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Ітерація 2 ─────────────────────────────────────────────────┐
│ Agent вирішує: потрібно ще → web_search("RAG techniques 2026") │
│ DuckDuckGo → 5 результатів з URLs                             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Ітерація 3 ─────────────────────────────────────────────────┐
│ Agent вирішує: достатньо інформації → синтезує відповідь       │
│ Комбінує knowledge base + web results → Markdown               │
└──────────────────────────────────────────────────────────────┘
```

---

### Приклади виводу

- [Згенерований звіт про RAG підходи](example_output/report.md) — повний Markdown-звіт, створений агентом
- [Транскрипт демо-сесії](example_output/demo_session.md) — повний вивід демо-сесії з tool calls та відповідями

---

## Структура проєкту

```
homework-lesson-5/
├── main.py              # Entry point — інтерактивний REPL зі streaming
├── agent.py             # LangGraph ReAct agent (4 tools + memory)
├── tools.py             # knowledge_search, web_search, read_url, write_report
├── retriever.py         # HybridRetriever: FAISS + BM25 + Infinity reranker
├── ingest.py            # Ingestion pipeline: PDF → chunks → FAISS + BM25 JSON
├── tool_parser.py       # Qwen3ChatWrapper — XML tool call parser
├── test_tool_parser.py  # Unit-тести для XML парсера (15 тестів)
├── config.py            # Pydantic Settings + SYSTEM_PROMPT
├── requirements.txt     # Залежності
├── .env                 # API endpoints (не комітити)
├── .gitignore
├── data/                # PDF документи для ingestion
│   ├── langchain.pdf
│   ├── large-language-model.pdf
│   └── retrieval-augmented-generation.pdf
├── index/               # Згенерований FAISS index + BM25 JSON (gitignored)
├── output/              # Згенеровані звіти агента (gitignored)
├── example_output/
│   ├── report.md        # Приклад згенерованого звіту
│   └── demo_session.md  # Транскрипт демо-сесії
├── CHANGELOG.md
└── README.md
```

### Опис файлів

| Файл | Відповідальність |
|------|------------------|
| `ingest.py` | Завантажує PDF з `data/`, розбиває на чанки, генерує embeddings через TEI, зберігає FAISS індекс + BM25 JSON на диск. |
| `retriever.py` | `HybridRetriever` — FAISS semantic + BM25 lexical, дедуплікація, reranking через `InfinityReranker` (HTTP client для Infinity API). |
| `tools.py` | 4 tool-функції з `@tool` декоратором LangChain. `knowledge_search` обгортає HybridRetriever. |
| `agent.py` | Збирає LangGraph ReAct agent: ChatOpenAI → Qwen3ChatWrapper → create_react_agent з 4 tools + MemorySaver. |
| `tool_parser.py` | Перехоплює XML tool calls від Qwen3.5 моделей і конвертує в LangChain формат (з hw3). |
| `config.py` | `Settings` (Pydantic BaseSettings) для всіх endpoints + `SYSTEM_PROMPT` зі стратегією "knowledge base first". |
| `main.py` | Інтерактивний REPL: input → agent.stream() → streaming output з emoji маркерами tool calls. |

---

## Інструменти агента

| Tool | Призначення | Бібліотека / Сервіс |
|------|-------------|---------------------|
| `knowledge_search` | Гібридний пошук по локальній базі знань з reranking (≤6000 chars) | FAISS + BM25 + Infinity reranker |
| `web_search` | Пошук в інтернеті через DuckDuckGo (≤4000 chars) | `ddgs` |
| `read_url` | Витягування тексту зі сторінки (≤8000 chars) | `trafilatura` |
| `write_report` | Збереження Markdown-звіту у файл | `builtins (open)` |

---

## Self-Hosted інфраструктура

Всі AI-сервіси розгорнуті локально в K3s кластері — **жодних зовнішніх API або платних сервісів**:

| Сервіс | Модель | Формат API | Призначення |
|--------|--------|------------|-------------|
| **SGLang** | Qwen3.5-35B-A3B-FP8 | OpenAI `/v1/chat/completions` | LLM для agent reasoning |
| **TEI** | Qwen3-Embedding-8B | OpenAI `/v1/embeddings` | Embeddings (4096 dims) |
| **Infinity** | BAAI/bge-reranker-v2-m3 | `POST /rerank` | Cross-encoder reranking |

### Чому не OpenAI API?

- **Безкоштовно** — немає витрат на API calls
- **Приватність** — дані не виходять за межі кластера
- **Потужніші embeddings** — Qwen3-Embedding-8B (4096 dims) vs text-embedding-3-small (1536 dims)
- **Демонструє production підхід** — self-hosted infra замість залежності від зовнішніх сервісів

---

## Тестування

```bash
pip install pytest
python -m pytest test_tool_parser.py -v
```

Тести покривають XML парсер (`parse_xml_tool_calls`):

| Категорія | Що перевіряється |
|---|---|
| Happy path | один/кілька tool calls, один/кілька параметрів |
| Змішаний контент | текст до/після XML-блоків |
| Числовий парсинг | `"10"` → `int`, `"123abc"` → `str` |
| Унікальність ID | кожен tool call має унікальний `call_*` |
| Порожній ввід | `""`, звичайний текст без XML |
| Malformed XML | незакритий тег, без параметрів, зламаний параметр |
| Whitespace | компактний формат, зайві пробіли у значеннях |

---

## Швидкий старт

### Вимоги

- Python 3.12+
- Доступ до OpenAI-сумісного LLM API (SGLang, vLLM, OpenAI тощо)
- Embedding сервіс з OpenAI-compatible API (TEI, OpenAI тощо)
- Reranker сервіс з Infinity API (або локальний cross-encoder)

### 1. Встановлення

```bash
cd homework-lesson-5
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Конфігурація

```bash
cp .env.example .env
# Відредагуйте .env — вкажіть ваші endpoints
```

Для self-hosted (SGLang + TEI + Infinity):
```env
API_KEY=not-needed
API_BASE=http://localhost:8000/v1
MODEL_NAME=qwen3.5-35b-a3b
EMBEDDING_BASE_URL=http://localhost:7998/v1
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
RERANKER_URL=http://localhost:7997/rerank
```

Для OpenAI:
```env
API_KEY=sk-your-key-here
API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
RERANKER_URL=http://localhost:7997/rerank
```

### 3. Ingestion (одноразово)

```bash
python ingest.py
```

Вивід:
```
2026-03-19 21:07:47 [INFO] Loading data/langchain.pdf
2026-03-19 21:07:47 [INFO] Loading data/large-language-model.pdf
2026-03-19 21:07:48 [INFO] Loading data/retrieval-augmented-generation.pdf
2026-03-19 21:07:48 [INFO] Loaded 52 pages from data
2026-03-19 21:07:48 [INFO] Created 462 chunks (size=500, overlap=100)
2026-03-19 21:07:53 [INFO] FAISS index saved to index/
2026-03-19 21:07:53 [INFO] BM25 chunks saved to index/bm25_chunks.json (462 chunks)
2026-03-19 21:07:53 [INFO] Ingestion complete!
```

### 4. Запуск агента

```bash
python main.py
```

### Приклад сесії

```
==================================================
  Research Agent with RAG
  Type your question and press Enter.
  Commands: 'exit' / 'quit' to leave,
            'new' to start a fresh conversation.
==================================================

You: Що таке RAG і які є підходи до retrieval?

  🔧 [knowledge_search] RAG retrieval approaches
  ✅ [knowledge_search] → 1565 chars

  🔧 [knowledge_search] RAG architecture components retrieval generation pipeline
  ✅ [knowledge_search] → 1595 chars

Agent: # What is RAG (Retrieval-Augmented Generation)?

**RAG** stands for **Retrieval-Augmented Generation**, a technique that enhances
large language models (LLMs) by incorporating an information-retrieval mechanism...

## Approaches to Retrieval

### 1. Dense Retrieval (Semantic Search)
Uses bi-encoder embeddings and cosine similarity...

### 2. Sparse Retrieval (BM25)
Traditional keyword-based matching...

### 3. Hybrid Search
Combines dense + sparse for best of both worlds...

You: Порівняй це з останніми тенденціями в інтернеті

  🔧 [web_search] RAG retrieval techniques trends 2026
  ✅ [web_search] → 1245 chars

  🔧 [read_url] https://example.com/advanced-rag-2026
  ✅ [read_url] → 8000 chars

Agent: На основі знайдених джерел, ось порівняння з останніми тенденціями...
[Агент комбінує knowledge base + web results]

You: exit
Goodbye!
```

---

## Hybrid Search — як це працює

```
            Query: "RAG retrieval approaches"
                          │
            ┌─────────────┼─────────────┐
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │ FAISS Vector  │           │  BM25 Lexical  │
    │ (semantic)    │           │  (keywords)    │
    │               │           │               │
    │ cosine sim.   │           │ TF-IDF scoring │
    │ top_k = 10    │           │ top_k = 10    │
    └───────┬───────┘           └───────┬───────┘
            │                           │
            └──────── merge ────────────┘
                       │
                ~15 unique docs
                       │
                       ▼
              ┌────────────────┐
              │   Infinity     │
              │   Reranker     │
              │ (cross-encoder)│
              │ bge-reranker   │
              │   -v2-m3       │
              │               │
              │ top_n = 3      │
              └───────┬────────┘
                      │
               3 most relevant
               passages with
               relevance scores
```

**Навіщо гібридний пошук?**

| Тип пошуку | Сильні сторони | Слабкі сторони |
|-----------|---------------|----------------|
| **Semantic (FAISS)** | Розуміє синоніми, контекст | Може пропустити точні терміни |
| **Lexical (BM25)** | Точні збіги ключових слів, коди помилок | Не розуміє семантику |
| **Hybrid + Reranking** | Найкращий recall + precision | Потребує reranker сервіс |

---

## Залежності

| Пакет | Версія | Призначення |
|-------|--------|-------------|
| `langgraph` | ≥1.1.0 | ReAct agent + checkpointer |
| `langchain` | ≥1.2.0 | Core framework |
| `langchain-openai` | ≥0.4 | ChatOpenAI + OpenAIEmbeddings |
| `langchain-community` | ≥0.4 | FAISS vectorstore, BM25Retriever |
| `faiss-cpu` | latest | Vector similarity search |
| `rank_bm25` | latest | BM25 lexical search |
| `pypdf` | latest | PDF document loader |
| `httpx` | latest | HTTP client для Infinity reranker API |
| `ddgs` | ≥7.0 | DuckDuckGo web search |
| `trafilatura` | ≥2.0.0 | Web page text extraction |
| `pydantic` | ≥2.12.0 | Validation and serialization |
| `pydantic-settings` | ≥2.12.0 | Config from .env |

**Не потрібні** (порівняно з типовим RAG): `sentence-transformers` — reranking виконується
сервером (Infinity API), а не локально.
