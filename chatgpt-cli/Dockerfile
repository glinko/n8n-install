FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Install dependencies
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    ca-certificates \
    sudo \
    vim \
    util-linux \
    && rm -rf /var/lib/apt/lists/*

# Create chatgpt user with sudo privileges
RUN useradd -m -s /bin/bash chatgpt && \
    mkdir -p /home/chatgpt/workspace && \
    chown -R chatgpt:chatgpt /home/chatgpt && \
    echo "chatgpt ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Install Python packages
RUN pip install --no-cache-dir "openai>=1.0.0" "rich>=13.0.0"

# Copy CLI script
COPY chatgpt-cli.py /usr/local/bin/chatgpt-cli.py
RUN chmod +x /usr/local/bin/chatgpt-cli.py

# Create wrapper script
RUN printf '#!/usr/bin/env bash\npython /usr/local/bin/chatgpt-cli.py "$@"\n' > /usr/local/bin/chatgpt && \
    chmod +x /usr/local/bin/chatgpt

# Copy startup script
COPY startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh && \
    chown chatgpt:chatgpt /usr/local/bin/startup.sh

# Set working directory
WORKDIR /home/chatgpt/workspace

# Switch to chatgpt user
USER chatgpt

# Note: OPENAI_API_KEY will be set from docker-compose environment section
# Run startup script
CMD ["/usr/local/bin/startup.sh"]
