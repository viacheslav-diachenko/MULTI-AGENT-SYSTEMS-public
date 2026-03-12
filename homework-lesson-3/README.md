# Research Agent

Інтерактивний дослідницький агент, який отримує питання від користувача, самостійно
шукає інформацію в інтернеті, аналізує знайдені джерела та генерує структурований
Markdown-звіт.

## Демо

![Research Agent Demo](demo.gif)

## Архітектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py (REPL)                          │
│   Інтерактивний цикл: введення → агент → вивід відповіді        │
└─────────────┬───────────────────────────────────────────────────┘
              │ stream()
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   agent.py (LangGraph ReAct Agent)              │
│                                                                 │
│  ┌─────────────────┐ ┌────────────┐ ┌────────────────────────┐  │
│  │   ChatOpenAI    │ │ MemorySaver│ │ create_react_agent()   │  │
│  │(Qwen3.5 SGLang)│  │ (memory)   │ │ ReAct loop             │  │
│  └────────┬────────┘ └────────────┘ └────────────────────────┘  │
│          │                                                      │
│  ┌───────▼────────────────────────────────────────────────────┐ │
│  │            tool_parser.py (Qwen3ChatWrapper)               │ │
│  │  Intercepts XML tool calls → converts to LangChain format  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────┬───────────────────────────────────────────────────┘
              │ tool calls
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       tools.py (3 tools)                        │
│                                                                 │
│  web_search()          read_url()          write_report()       │
│  DuckDuckGo search     trafilatura          File I/O            │
│  → snippets + URLs     → full text          → Markdown file     │
│                        (truncated)                              │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    config.py (Settings)                         │
│  Pydantic Settings ← .env file                                  │
│  SYSTEM_PROMPT — роль агента, стратегія, формат звіту           │
└─────────────────────────────────────────────────────────────────┘
```

### Ключові рішення

- **LangGraph `create_react_agent`** — сучасний спосіб побудови ReAct-агентів
  з LangChain, замість застарілого `AgentExecutor`.
- **`MemorySaver` checkpointer** — зберігає історію діалогу між повідомленнями
  в межах сесії через `thread_id`.
- **Context engineering** — результати `read_url` обрізаються до 8000 символів,
  щоб не забити контекстне вікно LLM.
- **Pydantic Settings** — всі налаштування завантажуються з `.env` файлу,
  жодних хардкоджених значень.
- **XML Tool Call Parser** (`tool_parser.py`) — обгортка над ChatOpenAI, яка
  перехоплює XML tool calls від моделей Qwen3.5 (формат `<tool_call><function=...>`)
  і конвертує їх у стандартний LangChain `AIMessage.tool_calls` формат.
  Це дозволяє використовувати `create_react_agent` з бекендами (sglang),
  які не парсять tool calls на рівні API.

## Вимоги

- Python 3.12+
- Доступ до OpenAI-сумісного LLM API (SGLang, vLLM, OpenAI, тощо)

## Швидкий старт

### 1. Клонування та налаштування

```bash
cd homework-lesson-3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Конфігурація

```bash
cp .env.example .env
# Відредагуйте .env — вкажіть ваш API ключ та endpoint
```

Для OpenAI:
```env
API_KEY=sk-your-key-here
API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
```

Для локального SGLang/vLLM:
```env
API_KEY=not-needed
API_BASE=http://localhost:8000/v1
MODEL_NAME=qwen3.5-35b-a3b
```

### 3. Запуск

```bash
python main.py
```

### Приклад сесії

```
==================================================
  Research Agent
  Type your question and press Enter.
  Commands: 'exit' / 'quit' to leave,
            'new' to start a fresh conversation.
==================================================

You: Порівняй три підходи до побудови RAG: naive, sentence-window та parent-child retrieval

Agent: [Агент виконує web_search, read_url, аналізує джерела, пише звіт...]

Agent: Я підготував детальний звіт з порівнянням трьох підходів до RAG.
Звіт збережено у файл output/rag_comparison.md

You: А який з них найкращий для production?

Agent: [Пам'ятає попередній контекст, відповідає на основі зібраної інформації...]

You: exit
Goodbye!
```

### Приклади виводу

- [Згенерований звіт про RAG підходи](example_output/report.md) — повний Markdown-звіт, створений агентом
- [Транскрипт демо-сесії](example_output/demo_session.md) — повний вивід демо-сесії з tool calls та відповідями

## Структура проєкту

```
homework-lesson-3/
├── main.py              # Entry point — інтерактивний REPL
├── agent.py             # Збірка агента (LLM + tools + memory)
├── tools.py             # Визначення та реалізація інструментів
├── tool_parser.py       # XML tool call parser для Qwen3.5 моделей
├── config.py            # Pydantic Settings + system prompt
├── requirements.txt     # Залежності з версіями
├── .env.example         # Шаблон змінних середовища
├── .gitignore
├── example_output/
│   ├── report.md        # Приклад згенерованого звіту
│   └── demo_session.md  # Транскрипт демо-сесії
└── README.md
```

## Інструменти агента

| Tool | Опис | Бібліотека |
|------|------|------------|
| `web_search` | Пошук в інтернеті через DuckDuckGo | `ddgs` |
| `read_url` | Витягування тексту зі сторінки | `trafilatura` |
| `write_report` | Збереження Markdown-звіту у файл | `builtins (open)` |

## Залежності

| Пакет | Версія | Призначення |
|-------|--------|-------------|
| `langgraph` | ≥1.1.0 | ReAct agent + checkpointer |
| `langchain-openai` | ≥1.1.10 | ChatOpenAI для OpenAI-compatible API |
| `ddgs` | ≥7.0 | DuckDuckGo search |
| `trafilatura` | ≥2.0.0 | Витягування тексту зі сторінок |
| `pydantic` | ≥2.12.0 | Валідація та серіалізація |
| `pydantic-settings` | ≥2.12.0 | Завантаження config із .env |
