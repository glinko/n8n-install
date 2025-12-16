# Видение меню телеграм-бота

## Конфигурация .env

**Требование**: Бот должен читать конфигурацию из корневого файла `.env` проекта (`/home/user/n8n-install/.env`), а не из `tg-bot/.env`.

**Текущая проблема**: В `config.py` используется `env_file=".env"`, что ищет файл в текущей рабочей директории. В контейнере это `/app/.env`, что неправильно.

**Решение**: 
- Либо использовать абсолютный путь к корневому `.env`
- Либо монтировать корневой `.env` в контейнер и указать правильный путь в `config.py`

**Примечание**: В `docker-compose.yml` переменные окружения передаются напрямую через секцию `environment:`, но для локальной разработки и явного чтения из файла нужно исправить путь к `.env`.

## Общие принципы

1. **Динамическое меню**: Все кнопки меню создаются динамически на основе данных из базы данных. Без необходимости перезапуска бота или контейнера.

2. **Хранение в БД**: Вся структура меню, метки кнопок, порядок сортировки, права доступа и параметры действий (agentflow ID, тип действия и т.д.) хранятся в базе данных.

3. **Обновление меню**: Меню на клиенте пересобирается по команде `/update` без перезапуска процесса.

4. **Многоуровневое меню**: Поддержка подменю (вложенных уровней меню).

5. **Параметры кнопок в БД**: Все параметры, необходимые для выполнения действия кнопки (agentflow ID, тип действия, дополнительные параметры), сохраняются в базе данных вместе с элементом меню.

## Текущая структура меню

### Верхний уровень (главное меню)

#### 1. Кнопка "ChatGPT"
- **Действие**: Обращается к agentflow в Flowise
- **Agentflow ID**: `8824745a-73a2-4e8d-98c4-c44bca3251e7`
- **Тип**: Прямое обращение к agentflow
- **Описание**: Открывает чат с ChatGPT через Flowise

#### 2. Кнопка "Sysopka"
- **Действие**: Показывает подменю второго уровня
- **Тип**: Подменю
- **Подменю содержит**:
  - **ClaudeCLI**: Интеграция с Claude CLI через Docker контейнер
  - **CursorCLI**: Интеграция с Cursor CLI через Docker контейнер
  - **ProxMox**: Обращается к agentflow `88ee84bd-21d1-412b-bff6-81ae33857c1e` в Flowise
  - **HomeNET**: Обращается к agentflow `88ee84bd-21d1-412b-bff6-81ae33857c1e` в Flowise
  
**Примечание**: В будущем эти три кнопки будут разделены на индивидуальные agentflow. Сейчас все используют один и тот же ID.

#### 3. Кнопка "People" (бывшая "Семейная панель")
- **Переименование**: "Семейная панель" → "People"
- **Действие**: Показывает подменю второго уровня
- **Тип**: Подменю
- **Подменю содержит**:
  - **Profile** (бывший "Мой профиль"): Отображает профиль пользователя
  - *(место для будущих элементов)*

#### 4. Кнопка "Profile" (бывший "Мой профиль")
- **Переименование**: "Мой профиль" → "Profile"
- **Перемещение**: Из верхнего уровня → второй уровень под "People"
- **Действие**: Отображает профиль пользователя

## Структура данных в базе

### Таблица MenuItem должна включать:
- `id`: Уникальный идентификатор
- `key`: Уникальный ключ элемента (например, "CHATGPT", "SYSOPKA", "PEOPLE", "PROFILE")
- `label`: Отображаемый текст кнопки (например, "ChatGPT", "People", "Profile")
- `parent_id`: ID родительского элемента (NULL для элементов верхнего уровня)
- `sort_order`: Порядок сортировки
- `roles`: Роли пользователей, имеющих доступ (например, "user,superadmin" или NULL для всех)
- `is_active`: Флаг активности элемента
- `action_type`: Тип действия (например, "flowise_agentflow", "submenu", "profile", "custom")
- `action_config`: JSON с конфигурацией действия:
  - Для agentflow: `{"agentflow_id": "8824745a-73a2-4e8d-98c4-c44bca3251e7", "flowise_base_url": "...", "flowise_api_key": "..."}`
  - Для подменю: `{"type": "submenu"}`
  - Для профиля: `{"type": "profile"}`
- `created_at`, `updated_at`: Временные метки

## Команда /update

При вызове команды `/update`:
1. Система должна перечитать структуру меню из базы данных
2. Пересобрать клавиатуру меню для текущего пользователя с учетом его роли
3. Отправить обновленную клавиатуру пользователю
4. Обновление должно происходить без перезапуска процесса бота

## Начальные данные (seed data)

### Элементы верхнего уровня:
1. **CHATGPT**:
   - label: "ChatGPT"
   - parent_id: NULL
   - sort_order: 10
   - action_type: "flowise_agentflow"
   - action_config: `{"agentflow_id": "8824745a-73a2-4e8d-98c4-c44bca3251e7"}`

2. **SYSOPKA**:
   - label: "Sysopka"
   - parent_id: NULL
   - sort_order: 20
   - action_type: "submenu"

3. **PEOPLE**:
   - label: "People"
   - parent_id: NULL
   - sort_order: 30
   - action_type: "submenu"
   - roles: "superadmin" (или другие роли по необходимости)

### Элементы второго уровня под SYSOPKA:
4. **SYSOPKA_CLAUDECLI**:
   - label: "ClaudeCLI"
   - parent_id: ID элемента SYSOPKA
   - sort_order: 10
   - action_type: "claude_cli_submenu"
   - action_config: None

5. **SYSOPKA_CURSORCLI**:
   - label: "CursorCLI"
   - parent_id: ID элемента SYSOPKA
   - sort_order: 20
   - action_type: "cursor_cli_submenu"
   - action_config: None

6. **SYSOPKA_PROXMOX**:
   - label: "ProxMox"
   - parent_id: ID элемента SYSOPKA
   - sort_order: 30
   - action_type: "flowise_agentflow"
   - action_config: `{"agentflow_id": "88ee84bd-21d1-412b-bff6-81ae33857c1e"}`

7. **SYSOPKA_HOMENET**:
   - label: "HomeNET"
   - parent_id: ID элемента SYSOPKA
   - sort_order: 40
   - action_type: "flowise_agentflow"
   - action_config: `{"agentflow_id": "88ee84bd-21d1-412b-bff6-81ae33857c1e"}`

### Элементы второго уровня под PEOPLE:
7. **PROFILE**:
   - label: "Profile"
   - parent_id: ID элемента PEOPLE
   - sort_order: 10
   - action_type: "profile"

## Требования к реализации

1. **Расширение модели MenuItem**: Добавить поля `action_type` (String) и `action_config` (JSON) для хранения параметров действий.

2. **Динамическая генерация меню**: Функция `build_main_menu` должна полностью генерировать меню из БД, включая все уровни.

3. **Обработка действий**: При нажатии на кнопку система должна:
   - Определить тип действия из `action_type`
   - Извлечь параметры из `action_config`
   - Выполнить соответствующее действие (вызов agentflow, переход в подменю, показ профиля и т.д.)

4. **Команда /update**: Реализовать обработчик команды `/update`, который пересобирает и отправляет меню пользователю.

5. **Конфигурация env**: Бот должен брать настройки из файла `/home/user/n8n-install/.env` (корневой .env проекта), а не из `tg-bot/.env`.

## Миграции и обратная совместимость

- Сохранить поддержку существующих элементов меню
- Мигрировать существующие элементы (PROFILE, FAMILY_PANEL) в новую структуру
- Обеспечить плавный переход без потери данных

---

## Расширение функциональности ClaudeCLI (2025-12-11)

### Требование: Подменю сессий для ClaudeCLI

Кнопка **ClaudeCLI** должна иметь собственное подменю с управлением сессиями.

### Структура подменю ClaudeCLI:

1. **"New Session"** - создание новой сессии
2. **Кнопки существующих сессий** (динамически) - по одной кнопке на каждую сохраненную сессию
3. **"Flags"** - добавление дополнительных флагов к запросу

### Процесс работы:

#### Создание новой сессии:
1. Пользователь нажимает "ClaudeCLI" → открывается подменю
2. Пользователь нажимает "New Session"
3. Бот запрашивает: "Название новой сессии (на английском без пробелов)"
4. Пользователь вводит название (например, "Flowise")
5. Бот сохраняет сессию и добавляет кнопку с названием в подменю
6. Бот предлагает: "Введите запрос для сессии"

#### Работа с существующей сессией:
1. Пользователь нажимает кнопку с названием сессии (например, "Flowise")
2. Бот предлагает: "Введите запрос для сессии Flowise"
3. Пользователь вводит запрос (может использовать кнопку "Flags" для добавления флагов)

#### Добавление флагов:
1. Пользователь может нажать кнопку "Flags" в любой момент ввода запроса
2. В текст запроса добавляется маркер "#flags" (только для удобства пользователя)
3. Пользователь может дописать флаги после "#flags", например: `--max-turns 3`
4. При отправке команды "#flags" удаляется, остаются только флаги после неё

### Формат команды на сервере:

```bash
docker exec claude-code-console claude chat --session название_сессии "текст запроса" [флаги]
```

**Пример:**
- Пользователь вводит: `выведи все agentflow из flowise #Flags --max-turns 3`
- Выполняемая команда: `docker exec claude-code-console claude chat --session Flowise "выведи все agentflow из flowise" --max-turns 3`

### Технические требования:

1. **Модель данных**:
   - Создать модель `ClaudeCLISession` для хранения сессий:
     - `id`, `user_id`, `session_name` (уникальное название), `created_at`, `updated_at`
   - Создать модель `ClaudeCLIMessage` для истории запросов (опционально):
     - `id`, `session_id`, `user_id`, `query`, `response`, `flags_used`, `created_at`

2. **FSM состояния**:
   - `ClaudeCLIState.waiting_for_session_name` - ожидание названия новой сессии
   - `ClaudeCLIState.waiting_for_query` - ожидание запроса (с сохраненным session_name)
   - `ClaudeCLIState.adding_flags` - режим добавления флагов

3. **Обработка кнопки ClaudeCLI**:
   - Изменить `action_type` с "flowise_agentflow" на "claude_cli_submenu"
   - При нажатии показывать подменю с сессиями пользователя
   - Подменю генерируется динамически на основе сохраненных сессий пользователя

4. **Выполнение команды**:
   - Использовать `subprocess` или `asyncio.create_subprocess_exec` для выполнения docker команды
   - Обработать вывод команды и отправить пользователю
   - Обработать ошибки выполнения

5. **Обработка флагов**:
   - При обнаружении "#flags" или "#Flags" в тексте:
     - Удалить маркер из команды
     - Извлечь всё после маркера как флаги
     - Добавить флаги в конец команды docker exec

### Структура БД для сессий:

```sql
CREATE TABLE claude_cli_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    session_name VARCHAR(128) NOT NULL,
    UNIQUE(user_id, session_name),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE claude_cli_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES claude_cli_sessions(id),
    user_id INTEGER REFERENCES users(id),
    query TEXT NOT NULL,
    response TEXT,
    flags_used TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Примеры использования:

**Сценарий 1: Создание и использование новой сессии**
1. Пользователь: `/start` → "Sysopka" → "ClaudeCLI"
2. Бот показывает подменю: [New Session] [Flags]
3. Пользователь: "New Session"
4. Бот: "Название новой сессии (на английском без пробелов)"
5. Пользователь: "Flowise"
6. Бот: "Сессия Flowise создана. Введите запрос:"
7. Пользователь: "выведи все agentflow"
8. Бот выполняет: `docker exec claude-code-console claude chat --session Flowise "выведи все agentflow"`

**Сценарий 2: Использование существующей сессии с флагами**
1. Пользователь: "ClaudeCLI" → "Flowise"
2. Бот: "Введите запрос для сессии Flowise:"
3. Пользователь: "выведи все agentflow из flowise"
4. Пользователь: нажимает "Flags"
5. Текст обновляется: "выведи все agentflow из flowise #Flags"
6. Пользователь дописывает: "выведи все agentflow из flowise #Flags --max-turns 3"
7. Бот выполняет: `docker exec claude-code-console claude chat --session Flowise "выведи все agentflow из flowise" --max-turns 3`
