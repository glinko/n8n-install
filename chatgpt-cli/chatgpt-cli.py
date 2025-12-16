#!/usr/bin/env python
import os
import sys
import json
import argparse
import subprocess
from typing import List, Dict, Any

from openai import OpenAI
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]ERROR:[/red] OPENAI_API_KEY is not set")
        sys.exit(1)
    return OpenAI(api_key=api_key)


def auto_detect_model(client: OpenAI) -> str:
    """
    Автоматически выбираем последнюю доступную gpt-модель для чата.
    Используем приоритетный список известных рабочих моделей.
    """
    try:
        model_list = client.models.list()
        available_models = {m.id for m in model_list.data}

        # Приоритетный список известных chat-моделей (от новых к старым)
        priority_models = [
            "gpt-5.2",
            "gpt-5.2-pro",
            "gpt-5.2-chat-latest",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
        ]

        # Ищем первую доступную модель из приоритетного списка
        for model in priority_models:
            if model in available_models:
                console.print(f"[green]Detected GPT model:[/green] {model}", style="dim")
                return model

        # Если ничего из приоритета не найдено, ищем любую gpt-модель
        # исключая специальные (realtime, image, audio)
        excluded_keywords = ("realtime", "image", "audio", "codex", "vision", "chat-latest")
        gpt_models = [
            m.id for m in model_list.data
            if (m.id.startswith("gpt-") and
                not any(keyword in m.id.lower() for keyword in excluded_keywords) and
                not m.id.startswith("o1") and
                not m.id.startswith("ft:gpt"))
        ]

        if gpt_models:
            # Сортируем и берем первую
            gpt_models.sort()
            selected = gpt_models[-1]  # Последняя в алфавитном порядке обычно новее
            console.print(f"[green]Detected GPT model:[/green] {selected}", style="dim")
            return selected

        # Fallback
        console.print(
            "[yellow]Warning:[/yellow] No suitable chat gpt-* models found, using fallback gpt-4o-mini"
        )
        return "gpt-4o-mini"

    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not fetch model list: {e}", style="dim")
        console.print("[yellow]Using fallback model: gpt-4o-mini[/yellow]", style="dim")
        return "gpt-4o-mini"


def resolve_model(client: OpenAI, override: str | None) -> str:
    """
    Порядок приоритета:
    1) флаг --model
    2) переменная окружения CHATGPT_MODEL
    3) авто-детект по списку моделей
    """
    if override:
        console.print(f"[green]Using model from CLI:[/green] {override}", style="dim")
        return override

    env_model = os.environ.get("CHATGPT_MODEL")
    if env_model:
        console.print(f"[green]Using model from CHATGPT_MODEL:[/green] {env_model}", style="dim")
        return env_model

    return auto_detect_model(client)


# ============= TOOLS ============= #

def tool_shell(command: str) -> str:
    """Execute a shell command in the container"""
    try:
        console.print(f"[yellow]🔧 Executing shell:[/yellow] {command}", style="dim")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + result.stderr
        console.print(f"[dim]Shell output:[/dim]\n{output[:500]}", style="dim")
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Shell tool error: {e}"


def tool_read_file(path: str) -> str:
    """Read a file from container filesystem"""
    try:
        console.print(f"[yellow]📖 Reading file:[/yellow] {path}", style="dim")
        with open(path, "r") as f:
            content = f.read()
        console.print(f"[dim]File size: {len(content)} bytes[/dim]", style="dim")
        return content
    except Exception as e:
        return f"File read error: {e}"


def tool_write_file(path: str, content: str) -> str:
    """Write content to a file"""
    try:
        console.print(f"[yellow]✍️  Writing file:[/yellow] {path}", style="dim")
        with open(path, "w") as f:
            f.write(content)
        console.print(f"[dim]Wrote {len(content)} bytes to {path}[/dim]", style="dim")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"File write error: {e}"


TOOLS_MAP = {
    "shell": tool_shell,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
}


# Tool definitions for OpenAI API
TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command in the container. Returns stdout and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g., 'ls -la', 'cat file.txt')"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the filesystem",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates or overwrites the file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path where to write the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        }
    }
]


def execute_tool_call(tool_call) -> str:
    """Execute a tool call and return the result"""
    function_name = tool_call.function.name
    function_args = json.loads(tool_call.function.arguments)

    if function_name not in TOOLS_MAP:
        return f"Error: Unknown tool '{function_name}'"

    tool_func = TOOLS_MAP[function_name]
    try:
        result = tool_func(**function_args)
        return result
    except TypeError as e:
        return f"Error calling {function_name}: {e}"


def chat_with_tools(messages: List[Dict[str, Any]], model: str, client: OpenAI, max_iterations: int = 5) -> str:
    """
    Run a chat completion with tool support.
    Handles tool calls iteratively until the model provides a final answer.
    """
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_DEFINITIONS,
            tool_choice="auto",
            temperature=0.3,
        )

        response_message = response.choices[0].message

        # Check if the model wants to call tools
        if response_message.tool_calls:
            # Add the assistant's response to messages
            messages.append(response_message)

            # Execute each tool call
            for tool_call in response_message.tool_calls:
                console.print(f"[cyan]🤖 Tool call:[/cyan] {tool_call.function.name}", style="bold")

                result = execute_tool_call(tool_call)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": result
                })

            # Continue the loop to get the next response
            continue

        # No tool calls, return the final answer
        if response_message.content:
            return response_message.content

        # Shouldn't happen, but just in case
        return "Error: No content and no tool calls in response"

    return f"Error: Maximum iterations ({max_iterations}) reached without final answer"


def single_call(prompt: str, model_override: str | None = None, use_tools: bool = True):
    client = get_client()
    model = resolve_model(client, model_override)

    messages = [{"role": "user", "content": prompt}]

    if use_tools:
        answer = chat_with_tools(messages, model, client)
    else:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
        answer = resp.choices[0].message.content

    console.print(f"\n[bold green]Answer:[/bold green]\n{answer}")


def interactive_chat(model_override: str | None = None, use_tools: bool = True):
    client = get_client()
    model = resolve_model(client, model_override)

    tools_status = "[green]enabled[/green]" if use_tools else "[red]disabled[/red]"
    console.print(f"[bold green]ChatGPT CLI[/bold green] (model: [cyan]{model}[/cyan], tools: {tools_status})")
    console.print("Type 'exit' or 'quit' to leave.\n")

    messages: List[dict] = []

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]you[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[red]Bye[/red]")
            break

        if user_input.strip().lower() in ("exit", "quit"):
            console.print("[red]Bye[/red]")
            break

        messages.append({"role": "user", "content": user_input})

        if use_tools:
            answer = chat_with_tools(messages, model, client)
            messages.append({"role": "assistant", "content": answer})
        else:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
            )
            answer = resp.choices[0].message.content
            messages.append({"role": "assistant", "content": answer})

        console.print(f"[bold magenta]assistant[/bold magenta]: {answer}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="ChatGPT CLI with tool support (shell, file access)"
    )
    parser.add_argument(
        "-m",
        "--model",
        help="Override model name (e.g. gpt-4o-mini, gpt-5.2, etc.)",
        default=None,
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable tool support (shell, file access)",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt text. If empty, starts interactive chat.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    use_tools = not args.no_tools

    if args.prompt:
        prompt = " ".join(args.prompt)
        single_call(prompt, model_override=args.model, use_tools=use_tools)
    else:
        interactive_chat(model_override=args.model, use_tools=use_tools)


if __name__ == "__main__":
    main()
