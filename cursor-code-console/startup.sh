#!/usr/bin/env bash
set -euo pipefail

# Startup script for cursor-code-console with logging
LOG_FILE="/home/cursor/cursor-console.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Cursor Code Console Starting ==="
log "Container: cursor-code-console"
log "User: $(whoami)"
log "Working directory: $(pwd)"
log "Node version: $(node --version 2>&1 || echo 'Node not found')"
log "Cursor agent: $(which cursor-agent 2>&1 || echo 'cursor-agent not found')"

# Check if CURSOR_API_KEY is set
if [ -n "${CURSOR_API_KEY:-}" ]; then
    log "CURSOR_API_KEY is set (length: ${#CURSOR_API_KEY})"
else
    log "WARNING: CURSOR_API_KEY is not set"
fi

log "Cursor CLI paths:"
log "  - /usr/local/bin/cursor-agent: $(ls -lh /usr/local/bin/cursor-agent 2>&1 || echo 'not found')"
log "  - /usr/local/lib/cursor-agent: $(ls -lh /usr/local/lib/cursor-agent 2>&1 || echo 'not found')"

log "Workspace contents:"
ls -lh /home/cursor/workspace 2>&1 | head -20 | while read -r line; do log "  $line"; done

log "System info:"
log "  - Hostname: $(hostname)"
log "  - Uptime: $(uptime)"
log "  - Memory: $(free -h | grep Mem | awk '{print "Total: "$2", Used: "$3", Free: "$4}')"

log "=== Cursor Code Console Ready ==="
log "Container will now keep running. Check this log for activity."

# Keep container running and log every hour
while true; do
    sleep 3600
    log "Heartbeat: Container still running. Uptime: $(uptime -p)"
done
