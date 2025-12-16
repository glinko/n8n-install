FROM ubuntu:22.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies including Node.js
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    sudo \
    util-linux \
    bash \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create cursor user with sudo privileges
RUN useradd -m -s /bin/bash cursor && \
    mkdir -p /home/cursor/workspace && \
    chown -R cursor:cursor /home/cursor && \
    echo "cursor ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Install Cursor CLI as root
RUN curl https://cursor.com/install -fsS | bash

# Copy cursor-agent and its dependencies to system-wide location
RUN if [ -f /root/.local/bin/cursor-agent ]; then \
        TARGET_DIR=$(readlink -f /root/.local/bin/cursor-agent 2>/dev/null | xargs dirname 2>/dev/null || echo "") && \
        if [ -n "$TARGET_DIR" ] && [ -d "$TARGET_DIR" ]; then \
            mkdir -p /usr/local/lib/cursor-agent && \
            cp -r "$TARGET_DIR"/* /usr/local/lib/cursor-agent/ && \
            chmod -R +x /usr/local/lib/cursor-agent && \
            chown -R root:root /usr/local/lib/cursor-agent && \
            printf '#!/usr/bin/env bash\nset -euo pipefail\nSCRIPT_DIR="/usr/local/lib/cursor-agent"\nNODE_BIN="$SCRIPT_DIR/node"\nexec "$NODE_BIN" --use-system-ca "$SCRIPT_DIR/index.js" "$@"\n' > /usr/local/bin/cursor-agent && \
            chmod +x /usr/local/bin/cursor-agent; \
        else \
            ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
            chmod -R a+rx /root/.local 2>/dev/null || true; \
        fi; \
    fi

# Copy startup script
COPY startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh && \
    chown cursor:cursor /usr/local/bin/startup.sh

# Set working directory
WORKDIR /home/cursor/workspace

# Switch to cursor user
USER cursor

# Note: CURSOR_API_KEY will be set from docker-compose environment section
# Run startup script with logging
CMD ["/usr/local/bin/startup.sh"]
