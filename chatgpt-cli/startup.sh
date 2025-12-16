#!/usr/bin/env bash
set -euo pipefail

# Startup script for chatgpt-cli with logging
LOG_FILE="/home/chatgpt/chatgpt-cli.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== ChatGPT CLI Starting ==="
log "Container: chatgpt-cli"
log "User: $(whoami)"
log "Working directory: $(pwd)"
log "Python version: $(python --version 2>&1)"

# Check if OPENAI_API_KEY is set
if [ -n "${OPENAI_API_KEY:-}" ]; then
    log "OPENAI_API_KEY is set (length: ${#OPENAI_API_KEY})"
else
    log "WARNING: OPENAI_API_KEY is not set"
fi

# Check chatgpt-cli installation
log "ChatGPT CLI paths:"
log "  - /usr/local/bin/chatgpt-cli.py: $(ls -lh /usr/local/bin/chatgpt-cli.py 2>&1 || echo 'not found')"
log "  - /usr/local/bin/chatgpt: $(ls -lh /usr/local/bin/chatgpt 2>&1 || echo 'not found')"

log "Workspace contents:"
ls -lh /home/chatgpt/workspace 2>&1 | head -20 | while read -r line; do log "  $line"; done

log "System info:"
log "  - Hostname: $(hostname)"
log "  - Uptime: $(uptime)"
log "  - Memory: $(free -h | grep Mem | awk '{print "Total: "$2", Used: "$3", Free: "$4}')"

# Check if tools are available
log "Available tools:"
log "  - bash: $(which bash 2>&1 || echo 'not found')"
log "  - curl: $(which curl 2>&1 || echo 'not found')"
log "  - vim: $(which vim 2>&1 || echo 'not found')"

log "=== ChatGPT CLI Ready ==="
log "Container will now keep running. Check this log for activity."
log ""
log "Usage examples:"
log "  docker exec chatgpt-cli chatgpt 'What is the current time?'"
log "  docker exec -it chatgpt-cli chatgpt"
log "  docker exec chatgpt-cli chatgpt --no-tools 'Hello'"

# Keep container running and log every hour
while true; do
    sleep 3600
    log "Heartbeat: Container still running. Uptime: $(uptime -p)"
done
