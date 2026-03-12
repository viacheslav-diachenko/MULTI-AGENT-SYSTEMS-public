# Research Agent — Custom ReAct Loop

Дослідницький агент з **власною реалізацією ReAct-циклу** (без фреймворкових абстракцій).
Агент отримує питання від користувача, самостійно шукає інформацію в інтернеті,
аналізує знайдені джерела та генерує вичерпну структуровану відповідь.

Еволюція [homework-lesson-3](../homework-lesson-3/) — замість `create_react_agent` (LangGraph)
використовується повністю прозорий цикл на базі `openai` SDK.

---

## Що змінилось: Lesson-3 → Lesson-4

### Порівняльна таблиця

| Аспект | Lesson-3 (було) | Lesson-4 (стало) |
|--------|------------------|-------------------|
| **Агентний цикл** | `create_react_agent()` з LangGraph | Власний `while`-loop у класі `ResearchAgent` |
| **Оркестрація tool calls** | Фреймворк автоматично парсить і виконує | Ручна перевірка, парсинг і виклик у циклі |
| **Визначення tools** | `@tool` декоратор LangChain | JSON Schema (OpenAI function calling format) |
| **Пам'ять діалогу** | `MemorySaver` checkpointer + `thread_id` | Простий `list[dict]` — масив повідомлень |
| **LLM клієнт** | `ChatOpenAI` (langchain-openai) | `openai.OpenAI` (офіційний SDK) |
| **XML парсинг** | `Qwen3ChatWrapper` (клас 80+ рядків, наслідує `BaseChatModel`) | Standalone функція `parse_xml_tool_calls()` (~25 рядків) |
| **Залежності** | `langgraph`, `langchain-openai`, `langchain-core` | `openai` (єдина LLM-залежність) |
| **System prompt** | Базовий (capabilities + rules) | Покращений (роль, ReAct метод, формат, anti-patterns) |
| **Логування tool calls** | Зовнішнє (в REPL через stream parsing) | Вбудоване в ReAct loop (emoji маркери) |
| **Обробка помилок** | На рівні фреймворку | Явна: try/except на кожен tool + iteration limit + graceful fallback |
| **Файлів коду** | 5 (`agent.py`, `tools.py`, `config.py`, `main.py`, `tool_parser.py`) | 4 (`agent.py`, `tools.py`, `config.py`, `main.py`) |

### Що покращилось

1. **Повна прозорість** — кожен крок ReAct-циклу (Think → Act → Observe) видимий у коді.
   Немає "магії" фреймворку — зрозуміло, як саме агент приймає рішення, викликає tools і будує відповідь.

2. **Мінімальні залежності** — видалено `langgraph` і всі пакети `langchain-*`.
   Єдина LLM-залежність — офіційний `openai` SDK. Це зменшує розмір virtual environment,
   спрощує debugging і знімає ризики breaking changes у фреймворку.

3. **Гнучкість tool call parsing** — dual extraction strategy: спочатку перевіряються
   native `tool_calls` з API, потім XML fallback для Qwen3/SGLang. Це робить агента
   сумісним з будь-яким OpenAI-compatible backend.

4. **Явна обробка помилок** — кожен tool виклик обгорнутий у `try/except`, невідомі tools
   повертають зрозуміле повідомлення замість crash. Ліміт ітерацій з graceful fallback:
   якщо агент не завершив за N ітерацій, він отримує nudge і генерує фінальну відповідь.

5. **Покращений system prompt** — структурований за секціями (Role, Tools, Strategy,
   Format, Rules) з явними anti-patterns і обмеженнями поведінки.

---

## Архітектура

### Принципова схема

```
┌──────────────────────────────────────────────────────────────────────┐
│                          main.py (REPL)                              │
│   input() → agent.chat() → print()                                   │
│   Команди: exit, quit, new (reset)                                   │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  agent.py — ResearchAgent                             │
│                                                                      │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │              Custom ReAct Loop (while-цикл)                    │ │
│   │                                                                │ │
│   │   1. Додати user message до self.messages                      │ │
│   │   2. Відправити [system + messages] → LLM API                  │ │
│   │   3. Перевірити відповідь на tool_calls:                       │ │
│   │      ├─ native tool_calls (OpenAI format)?                     │ │
│   │      └─ XML fallback (Qwen3 <tool_call> tags)?                 │ │
│   │   4. Якщо tool calls є:                                        │ │
│   │      ├─ 🔧 Лог: назва + аргументи                              │ │
│   │      ├─ Виконати tool → отримати результат                     │ │
│   │      ├─ 📎 Лог: розмір результату                               │ │
│   │      ├─ Додати результат до messages                           │ │
│   │      └─ Повернутись до кроку 2                                 │ │
│   │   5. Якщо tool calls немає → фінальна відповідь                │ │
│   │   6. Якщо ліміт ітерацій → nudge + останній LLM call           │ │
│   └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│   openai.OpenAI ──────────────→ SGLang / vLLM / OpenAI API          │
│   self.messages: list[dict] ──→ Пам'ять діалогу                      │
│   parse_xml_tool_calls() ─────→ Regex XML парсер                     │
└────────────────┬─────────────────────────────────────────────────────┘
                 │ tool calls
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     tools.py — 3 інструменти                         │
│                                                                      │
│   TOOL_SCHEMAS ─── JSON Schema (OpenAI function calling format)      │
│   TOOL_REGISTRY ── dict: name → callable                             │
│                                                                      │
│   web_search(query)        read_url(url)        write_report(f, c)   │
│   └─ DDGS (DuckDuckGo)    └─ trafilatura        └─ File I/O         │
│      → snippets + URLs       → full text            → .md file       │
│                              (≤8000 chars)                           │
└──────────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     config.py — Settings + Prompt                     │
│                                                                      │
│   Settings (Pydantic BaseSettings) ← .env file                       │
│   SYSTEM_PROMPT — Role / Tools / Strategy / Format / Rules           │
└──────────────────────────────────────────────────────────────────────┘
```

### ReAct Loop — покроковий flow

```
User: "Порівняй naive RAG та sentence-window retrieval"
  │
  ▼
┌─ Ітерація 1 ─────────────────────────────────────────────┐
│ LLM отримує: [system_prompt, user_msg]                    │
│ LLM вирішує: потрібно шукати → tool_call: web_search(…)   │
│ Agent виконує web_search → результат 5 посилань            │
│ Результат додається до messages                           │
└───────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Ітерація 2 ─────────────────────────────────────────────┐
│ LLM отримує: [system, user, assistant+tc, tool_result]    │
│ LLM вирішує: потрібно ще → tool_call: web_search(…)       │
│ Agent виконує web_search → ще 5 посилань                   │
└───────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Ітерація 3 ─────────────────────────────────────────────┐
│ LLM вирішує: прочитати статтю → tool_call: read_url(…)    │
│ Agent виконує read_url → 8000 chars тексту                │
└───────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Ітерація 4 ─────────────────────────────────────────────┐
│ LLM вирішує: достатньо інформації → НЕ викликає tools     │
│ LLM генерує фінальну відповідь (Markdown)                 │
│ Loop завершується, відповідь повертається в REPL           │
└───────────────────────────────────────────────────────────┘
```

---

## Структура проєкту

```
homework-lesson-4/
├── main.py              # Entry point — інтерактивний REPL
├── agent.py             # ResearchAgent — custom ReAct loop + XML parser
├── tools.py             # Tool функції + JSON Schema + TOOL_REGISTRY
├── config.py            # Pydantic Settings + SYSTEM_PROMPT
├── requirements.txt     # Залежності (без langgraph/langchain)
├── .env.example         # Шаблон змінних середовища
├── .gitignore
└── README.md
```

### Опис файлів

| Файл | Рядків | Відповідальність |
|------|--------|------------------|
| `agent.py` | ~260 | Клас `ResearchAgent` з custom ReAct loop. XML парсер для Qwen3. Dual extraction (native + XML). Error handling + iteration limit. |
| `tools.py` | ~200 | Три tool-функції (plain Python, без декораторів). `TOOL_SCHEMAS` — JSON Schema для API. `TOOL_REGISTRY` — маппінг name → callable. |
| `config.py` | ~100 | `Settings` (Pydantic BaseSettings) для завантаження з `.env`. `SYSTEM_PROMPT` зі структурованими секціями prompt engineering. |
| `main.py` | ~70 | REPL: input loop, команди (exit/quit/new), виклик `agent.chat()`, error handling. |

---

## Інструменти агента

| Tool | Призначення | JSON Schema params | Бібліотека |
|------|-------------|-------------------|------------|
| `web_search` | Пошук в інтернеті через DuckDuckGo | `query` (required), `max_results` (optional) | `ddgs` |
| `read_url` | Витягування тексту зі сторінки (≤8000 chars) | `url` (required) | `trafilatura` |
| `write_report` | Збереження Markdown-звіту у файл | `filename` (required), `content` (required) | `builtins` |

Tools визначені як **JSON Schema** у форматі OpenAI function calling API:

```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search the internet using DuckDuckGo...",
    "parameters": {
      "type": "object",
      "properties": {
        "query": { "type": "string", "description": "The search query string." },
        "max_results": { "type": "integer", "description": "Number of results (default: 5)." }
      },
      "required": ["query"]
    }
  }
}
```

---

## Швидкий старт

### Вимоги

- Python 3.12+
- Доступ до OpenAI-сумісного LLM API (SGLang, vLLM, OpenAI тощо)

### 1. Клонування та налаштування

```bash
cd homework-lesson-4
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Конфігурація

```bash
cp .env.example .env
# Відредагуйте .env — вкажіть API endpoint
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
  Research Agent (Custom ReAct)
  Type your question and press Enter.
  Commands: 'exit' / 'quit' to leave,
            'new' to start a fresh conversation.
==================================================

You: Порівняй naive RAG та sentence-window retrieval

  🔧 Tool call: web_search(query="naive RAG approach explained")
  📎 Result: 1245 chars

  🔧 Tool call: web_search(query="sentence window retrieval RAG")
  📎 Result: 1389 chars

  🔧 Tool call: read_url(url="https://example.com/rag-comparison")
  📎 Result: 8000 chars

Agent: ## Порівняння Naive RAG та Sentence-Window Retrieval

### 1. Naive RAG
Найпростіший підхід, де документи розбиваються на фіксовані чанки...

### 2. Sentence-Window Retrieval
Покращений підхід, де для пошуку використовується окреме речення...

| Критерій | Naive RAG | Sentence-Window |
|----------|-----------|-----------------|
| Точність | Середня   | Висока          |
| ...      | ...       | ...             |

You: А який краще для production?

  🔧 Tool call: web_search(query="RAG production best practices 2024")
  📎 Result: 1156 chars

Agent: Для production рекомендую Sentence-Window підхід, оскільки...
[Агент пам'ятає контекст попереднього питання]

You: exit
Goodbye!
```

---

## System Prompt Engineering

System prompt структурований за секціями з використанням prompt engineering best practices:

| Секція | Призначення |
|--------|-------------|
| **Role** | Визначає експертну роль агента (Research Agent — expert analyst) |
| **Available Tools** | Перелічує tools з описом (дублює JSON Schema, але допомагає моделі reasoning) |
| **Research Strategy** | ReAct метод: Think → Search → Read → Synthesize |
| **Response Format** | Вимоги до структури відповіді: headings, tables, pros/cons, sources |
| **Rules and Constraints** | Hard constraints: мін. 2 пошуки, ліміт 3-5 tool calls, no repetition, error recovery |

---

## Обробка помилок

| Сценарій | Поведінка |
|----------|-----------|
| Tool кидає exception | `_execute_tool()` перехоплює, повертає `"Error executing {name}: {e}"` — модель бачить помилку і може адаптуватись |
| Невідомий tool name | Повертає список доступних tools — модель може виправити виклик |
| Ліміт ітерацій вичерпано | Вставляє nudge-повідомлення, робить останній LLM call для синтезу зібраної інформації |
| LLM API недоступний | Exception пробивається у REPL → `print(f"Error: {e}")` → користувач може спробувати знову |
| `KeyboardInterrupt` | Перехоплюється в REPL → `"Interrupted"` → можна продовжити |

---

## Залежності

| Пакет | Версія | Призначення |
|-------|--------|-------------|
| `openai` | ≥1.86.0 | OpenAI-compatible API клієнт |
| `ddgs` | ≥7.0 | DuckDuckGo search |
| `trafilatura` | ≥2.0.0 | Витягування тексту зі сторінок |
| `pydantic` | ≥2.12.0 | Валідація і серіалізація |
| `pydantic-settings` | ≥2.12.0 | Завантаження конфігурації з .env |

**Видалені** (порівняно з lesson-3): `langgraph`, `langchain-openai`, `langchain-core`.

---

## Сумісність з LLM бекендами

Агент працює з будь-яким OpenAI-compatible API завдяки dual extraction strategy:

| Backend | Tool call формат | Підтримка |
|---------|-----------------|-----------|
| OpenAI API | Native `tool_calls` | ✅ Через `message.tool_calls` |
| SGLang + Qwen3.5 | XML в `content` | ✅ Через `parse_xml_tool_calls()` |
| vLLM | Native `tool_calls` | ✅ Через `message.tool_calls` |
| Ollama | Native `tool_calls` | ✅ Через `message.tool_calls` |

Порядок перевірки: native `tool_calls` → XML fallback → no tools (фінальна відповідь).
