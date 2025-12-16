# CursorCLI Testing Guide

This document describes how to test all CursorCLI functionalities.

## Prerequisites

1. **Docker container must be running:**
   ```bash
   docker compose -p localai --profile cursor up -d cursor-code-console
   ```

2. **Telegram bot must be running:**
   ```bash
   docker compose -p localai logs -f tg-bot
   ```

3. **Database must be accessible** (PostgreSQL)

## Automated Testing

Run the automated test script:

```bash
cd /home/user/n8n-install/tg-bot
python test_cursor_cli.py
```

This script tests:
- ✅ Docker container availability
- ✅ User creation/retrieval
- ✅ Session creation
- ✅ Getting user sessions
- ✅ Query execution
- ✅ Session switching
- ✅ Flags parsing
- ✅ Host commands
- ✅ Session deletion
- ✅ End session API

## Manual Testing via Telegram Bot

### Test 1: Creating Sessions

1. Open your Telegram bot
2. Send `/start`
3. Navigate to **Sysopka** → **CursorCLI**
4. Click **New Session**
5. Enter a session name (e.g., `test1`)
6. **Expected:** Bot responds with "✅ Сессия 'test1' создана."

**Test Cases:**
- ✅ Valid name: `test1`, `my_session`, `session-123`
- ❌ Invalid names: `test 1` (spaces), `тест` (non-English), `test@1` (special chars)

### Test 2: Executing Queries

1. After creating a session, you should see: "Введите запрос для сессии test1:"
2. Send a query: `What is Python?`
3. **Expected:** Bot executes the query and returns Cursor CLI response

**Test Cases:**
- ✅ Simple query: `Hello`
- ✅ Complex query: `Write a Python function to calculate factorial`
- ✅ Multi-line query (if supported)

### Test 3: Switching Between Sessions

1. Create first session: `test1`
2. Send a query in `test1`: `First session query`
3. Go back to CursorCLI menu (click **◀️ Главное меню** then **CursorCLI** again)
4. Click **New Session**
5. Create second session: `test2`
6. Send a query in `test2`: `Second session query`
7. Click on `test1` button in the menu
8. **Expected:** Bot switches to `test1` and you can continue the conversation

**Test Cases:**
- ✅ Switch from session 1 to session 2
- ✅ Switch back to session 1
- ✅ Verify each session maintains its own context

### Test 4: Deleting Sessions

1. Create a session: `test_delete`
2. Send a few queries to create message history
3. Send `/delete` command
4. **Expected:** 
   - Bot responds: "✅ Сессия 'test_delete' удалена. История сообщений (X сообщений) сохранена."
   - Session button disappears from menu
   - Messages remain in database with `session_id = NULL`

**Test Cases:**
- ✅ Delete session with messages
- ✅ Delete session without messages
- ✅ Verify messages are preserved after deletion

### Test 5: Flags Support

1. Create or select a session
2. Send a query with flags: `List files #flags --all --long`
3. **Expected:** Flags are parsed and passed to Cursor CLI

**Alternative method:**
1. While in a session, click **Flags** button
2. Enter flags: `--verbose --debug`
3. **Expected:** Flags are added to the current query

**Test Cases:**
- ✅ Flags in query: `query #flags --flag1 --flag2`
- ✅ Flags button: Click Flags, then enter flags
- ✅ No flags: Regular query without flags

### Test 6: Host Commands

1. Create or select a session
2. Send a host command: `!host ping -c 4 8.8.8.8`
3. **Expected:** Command executes on host and returns output

**Test Cases:**
- ✅ Network command: `!host ping -c 4 8.8.8.8`
- ✅ System command: `!host df -h`
- ✅ Alternative prefix: `#host uptime`
- ❌ Disallowed command: `!host rm -rf /` (should be blocked)

**Allowed host commands:**
- Network: `ping`, `traceroute`, `mtr`, `curl`, `wget`, `nc`, `nmap`, `dig`, `host`, `nslookup`
- System: `df`, `free`, `top`, `htop`, `ps`, `uptime`, `uname`
- File: `ls`, `cat`, `grep`, `find`, `du`, `stat`

### Test 7: Exit from CursorCLI

1. Create or select a session
2. Send `/exit`
3. **Expected:** 
   - Bot responds: "Режим Cursor CLI завершён. Используйте /start для возврата в меню."
   - Returns to main menu
   - Session is properly closed

### Test 8: Error Handling

**Test Cases:**

1. **Container not running:**
   - Stop container: `docker compose -p localai stop cursor-code-console`
   - Try to create session
   - **Expected:** Error message about container not found

2. **Invalid session name:**
   - Try to create session with invalid name: `test 1` (with space)
   - **Expected:** Error message asking for valid name

3. **Duplicate session name:**
   - Create session: `test1`
   - Try to create another session: `test1`
   - **Expected:** Error message that session already exists

4. **Delete non-existent session:**
   - Send `/delete` when no session is active
   - **Expected:** Error message

## Database Verification

After testing, verify data in database:

```bash
# Connect to PostgreSQL
docker compose -p localai exec postgres psql -U postgres -d postgres

# Check sessions
SELECT id, user_id, session_name, uuid, created_at 
FROM cursor_cli_sessions 
ORDER BY created_at DESC 
LIMIT 10;

# Check messages
SELECT id, session_id, user_id, LEFT(query, 50) as query_preview, 
       LEFT(response, 50) as response_preview, flags_used, created_at 
FROM cursor_cli_messages 
ORDER BY created_at DESC 
LIMIT 10;

# Check messages with NULL session_id (from deleted sessions)
SELECT COUNT(*) FROM cursor_cli_messages WHERE session_id IS NULL;
```

## Expected Behavior Summary

| Feature | Expected Behavior |
|---------|------------------|
| **Create Session** | Creates DB record, initializes Cursor CLI session, returns success message |
| **Execute Query** | Sends query to Cursor CLI, saves to DB, returns response |
| **Switch Sessions** | Changes active session, maintains separate contexts |
| **Delete Session** | Removes session from DB, preserves messages with NULL session_id |
| **Flags** | Parses `#flags` marker, passes flags to Cursor CLI |
| **Host Commands** | Executes on host via Docker, returns output, saves to DB |
| **Exit** | Clears state, returns to main menu, closes session gracefully |

## Troubleshooting

### Container not found
```bash
# Check if container exists
docker ps -a | grep cursor-code-console

# Start container
docker compose -p localai --profile cursor up -d cursor-code-console

# Check logs
docker compose -p localai logs cursor-code-console
```

### Database connection issues
```bash
# Check PostgreSQL is running
docker compose -p localai ps postgres

# Check database connection from bot container
docker compose -p localai exec tg-bot python -c "from app.db import engine; import asyncio; asyncio.run(engine.connect())"
```

### Cursor CLI command errors
```bash
# Test Cursor CLI directly in container
docker compose -p localai exec cursor-code-console cursor-agent --help

# Check Cursor CLI version
docker compose -p localai exec cursor-code-console cursor-agent --version
```

## Test Checklist

- [ ] Docker container `cursor-code-console` is running
- [ ] Telegram bot is running and responsive
- [ ] Can create new session with valid name
- [ ] Can execute queries in session
- [ ] Can switch between multiple sessions
- [ ] Can delete session (preserves messages)
- [ ] Flags are parsed correctly from queries
- [ ] Flags button works correctly
- [ ] Host commands execute successfully
- [ ] `/exit` command works correctly
- [ ] Error handling works for invalid inputs
- [ ] Database records are created correctly
- [ ] Messages are saved to database
- [ ] Session UUID is stored and used for resume
