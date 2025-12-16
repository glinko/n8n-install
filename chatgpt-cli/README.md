# ChatGPT CLI with Tool Support

AI-powered command-line assistant with **real access** to shell commands and filesystem.

## Features

🤖 **Tool Support (Agents)**:
- `shell` - Execute any shell command
- `read_file` - Read files from filesystem
- `write_file` - Write/create files

🔧 **Auto Model Detection**:
- Automatically selects the latest GPT model (gpt-5.2, gpt-4o, etc.)
- Manual override via `--model` flag or `CHATGPT_MODEL` env var

## Usage

### Interactive Chat (with tools enabled by default)

```bash
docker exec chatgpt-cli chatgpt
```

### Single Query

```bash
docker exec chatgpt-cli chatgpt "What is the current disk usage?"
```

### Examples with Tools

**List files:**
```bash
docker exec chatgpt-cli chatgpt "List all Python files in the workspace"
```

**Check system info:**
```bash
docker exec chatgpt-cli chatgpt "Show memory usage and uptime"
```

**Create a file:**
```bash
docker exec chatgpt-cli chatgpt "Create /tmp/hello.txt with 'Hello World'"
```

**Read and analyze:**
```bash
docker exec chatgpt-cli chatgpt "Read docker-compose.yml and list all services"
```

**Complex tasks:**
```bash
docker exec chatgpt-cli chatgpt "Check disk space, find large files over 100MB, and create a report"
```

### Disable Tools

For simple chat without tool access:

```bash
docker exec chatgpt-cli chatgpt --no-tools "Just a simple question"
```

## How It Works

1. **User prompt** → ChatGPT model
2. **Model decides** if it needs to use tools
3. **Tools execute** (shell, read_file, write_file)
4. **Results return** to model
5. **Final answer** presented to user

Example flow:
```
You: "List files and create a report"
  ↓
Model: calls shell("ls -la")
  ↓
Tool: executes, returns output
  ↓
Model: calls write_file("/tmp/report.txt", "...")
  ↓
Tool: writes file
  ↓
Model: "Done! Created report at /tmp/report.txt"
```

## Environment Variables

- `OPENAI_API_KEY` - Required: Your OpenAI API key
- `CHATGPT_MODEL` - Optional: Override default model (e.g., "gpt-4o-mini")

## Security Notes

⚠️ **Important**: This container has:
- Full shell access to the container filesystem
- Ability to read/write files
- Execute any command within the container

Use only in trusted environments. Do not expose to untrusted users.

## Building

```bash
docker build -t chatgpt-cli-chatgpt-cli:latest ./chatgpt-cli
```

## Starting

```bash
docker compose --profile chatgpt up -d chatgpt-cli
```

## Examples Output

```
$ docker exec chatgpt-cli chatgpt "Check disk space"

Detected GPT model: gpt-5.2
🤖 Tool call: shell
🔧 Executing shell: df -h

Answer:
Current disk usage shows 157GB total, 57GB used, 93GB available (38% used).
Main filesystem: /dev/sda2
```

## Model Priority

Auto-detection tries in order:
1. gpt-5.2
2. gpt-5.1
3. gpt-5
4. gpt-4o
5. gpt-4o-mini
6. gpt-4-turbo
7. gpt-4
8. gpt-3.5-turbo

Fallback: gpt-4o-mini
