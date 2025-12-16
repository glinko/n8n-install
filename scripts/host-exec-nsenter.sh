#!/bin/bash
# Wrapper script to execute commands on Docker host using nsenter
# This script runs inside claude-code-console container and executes commands on the host
#
# Usage: host-exec <command> [args...]
# Example: host-exec ping -c 4 8.8.8.8
#
# Note: This script requires the container to be run with --pid=host and --privileged
# The script will try to use sudo if not running as root

# Check if nsenter is available
if ! command -v nsenter &> /dev/null; then
    echo "Error: nsenter not found. Please install util-linux package." >&2
    exit 1
fi

# Check if we have access to host's PID namespace
if [ ! -d "/proc/1/ns" ]; then
    echo "Error: Cannot access host's PID namespace. Container may need --pid=host flag." >&2
    exit 1
fi

# Check if we have arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <command> [args...]" >&2
    echo "Example: $0 ping -c 4 8.8.8.8" >&2
    exit 1
fi

# Determine if we need sudo (if not running as root)
if [ "$(id -u)" -eq 0 ]; then
    NSENTER_CMD="nsenter"
else
    # Try to use sudo if available
    if command -v sudo &> /dev/null; then
        NSENTER_CMD="sudo nsenter"
    else
        echo "Error: Not running as root and sudo not available. Cannot access host namespaces." >&2
        exit 1
    fi
fi

# Execute command in host's namespaces using nsenter
# -t 1: target PID 1 (host's init process)
# -m: mount namespace (host's filesystem)
# -u: UTS namespace (hostname)
# -n: network namespace (host's network) - most important for network commands
# -p: PID namespace (host's processes)
# --: end of options, start of command

# Try executing with network and PID namespaces (most important for host commands)
if $NSENTER_CMD -t 1 -m -u -n -p -- "$@" 2>/dev/null; then
    exit 0
elif $NSENTER_CMD -t 1 -n -- "$@" 2>/dev/null; then
    # Fallback: only network namespace (for network commands)
    exit 0
else
    # Last resort: try without any namespace restrictions (may not work)
    echo "Warning: Could not enter host namespaces. Command may run in container context." >&2
    exec "$@"
fi
