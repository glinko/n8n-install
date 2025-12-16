"""
Service for executing commands on the Docker host.

This module provides functionality to execute commands on the host system
rather than inside containers, using Docker API with host network access.
"""
from __future__ import annotations

import logging
import asyncio
from typing import Sequence
import docker
import shlex

logger = logging.getLogger(__name__)

# Whitelist of allowed commands for security
ALLOWED_HOST_COMMANDS = {
    'ping', 'traceroute', 'mtr', 'netstat', 'ss', 'ip', 
    'curl', 'wget', 'nc', 'nmap', 'dig', 'host', 'nslookup',
    'df', 'free', 'top', 'htop', 'ps', 'uptime', 'uname',
    'ls', 'cat', 'grep', 'find', 'du', 'stat'
}

# Commands that require network access
NETWORK_COMMANDS = {'ping', 'traceroute', 'mtr', 'curl', 'wget', 'nc', 'nmap', 'dig', 'host', 'nslookup'}


async def execute_host_command(
    command: str, 
    args: Sequence[str] | None = None,
    use_host_network: bool = True,
    timeout: int = 30
) -> tuple[str, bool]:
    """
    Execute command on Docker host using temporary container.
    
    Args:
        command: Command to execute (e.g., 'ping', 'traceroute')
        args: Command arguments (e.g., ['-c', '4', '8.8.8.8'])
        use_host_network: If True, use --network host for network commands
        timeout: Maximum execution time in seconds
    
    Returns:
        Tuple of (output, success)
    """
    try:
        # Validate command
        if command not in ALLOWED_HOST_COMMANDS:
            return (f"Error: Command '{command}' is not allowed. Allowed commands: {', '.join(sorted(ALLOWED_HOST_COMMANDS))}", False)
        
        # Build full command
        cmd_parts = [command]
        if args:
            cmd_parts.extend(args)
        
        # Determine if we need host network
        needs_host_network = use_host_network and command in NETWORK_COMMANDS
        
        # Choose base image based on command
        # Alpine has most network tools, but some may need different images
        if command in {'ping', 'traceroute', 'mtr'}:
            # Use image with network tools
            image = 'alpine:latest'
            # Install tools if needed (ping, traceroute are in iputils-alpine)
            if command == 'ping':
                cmd_parts = ['sh', '-c', f'apk add --no-cache iputils >/dev/null 2>&1 && ping {" ".join(shlex.quote(str(a)) for a in (args or []))}']
            elif command == 'traceroute':
                cmd_parts = ['sh', '-c', f'apk add --no-cache traceroute >/dev/null 2>&1 && traceroute {" ".join(shlex.quote(str(a)) for a in (args or []))}']
            elif command == 'mtr':
                cmd_parts = ['sh', '-c', f'apk add --no-cache mtr >/dev/null 2>&1 && mtr {" ".join(shlex.quote(str(a)) for a in (args or []))}']
        else:
            image = 'alpine:latest'
            cmd_parts = [command] + (list(args) if args else [])
        
        logger.info(f"Executing host command: {' '.join(cmd_parts)} (network: {'host' if needs_host_network else 'bridge'})")
        
        # Execute in temporary container
        client = docker.from_env()
        loop = asyncio.get_event_loop()
        
        def run_container():
            # containers.run() doesn't support timeout parameter
            # Use asyncio.wait_for for timeout instead
            # containers.run() returns bytes output when detach=False
            output_bytes = client.containers.run(
                image=image,
                command=cmd_parts,
                network_mode='host' if needs_host_network else 'bridge',
                privileged=needs_host_network,  # Network commands may need privileged mode
                remove=True,  # Auto-remove after execution
                detach=False,
                stdout=True,
                stderr=True
            )
            return output_bytes
        
        # Run in executor to avoid blocking, with timeout
        output_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, run_container),
            timeout=timeout + 5  # Add buffer for container startup
        )
        
        output = output_bytes.decode('utf-8', errors='replace')
        logger.info(f"Host command completed successfully, output length: {len(output)} chars")
        return (output, True)
        
    except asyncio.TimeoutError:
        return (f"Error: Command timed out after {timeout} seconds", False)
    except docker.errors.ContainerError as e:
        error_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        logger.error(f"Container error executing '{command}': {error_output}")
        return (f"Error executing command: {error_output}", False)
    except docker.errors.ImageNotFound:
        return (f"Error: Docker image not found. Please ensure Docker images are available.", False)
    except Exception as e:
        logger.error(f"Error executing host command '{command}': {e}", exc_info=True)
        return (f"Error: {str(e)}", False)


async def execute_host_command_simple(command_line: str) -> tuple[str, bool]:
    """
    Execute command on host by parsing command line string.
    
    Args:
        command_line: Full command line (e.g., "ping -c 4 8.8.8.8")
    
    Returns:
        Tuple of (output, success)
    """
    try:
        parts = shlex.split(command_line)
        if not parts:
            return ("Error: Empty command", False)
        
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else None
        
        return await execute_host_command(command, args)
    except Exception as e:
        logger.error(f"Error parsing command line '{command_line}': {e}", exc_info=True)
        return (f"Error parsing command: {str(e)}", False)
