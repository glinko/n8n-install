from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..config import settings

logger = logging.getLogger(__name__)

class FlowiseClientError(RuntimeError):
    """Raised when Flowise returns an error response."""

@dataclass
class FlowiseResponse:
    message: str
    raw: dict[str, Any]

async def run_agentflow(
    question: str, 
    agentflow_id: str,
    session_id: str | None = None,
    flowise_base_url: str | None = None,
    flowise_api_key: str | None = None
) -> FlowiseResponse:
    """Run any Flowise agentflow by ID."""
    base_url = flowise_base_url or settings.flowise_base
    api_key = flowise_api_key or settings.flowise_api_key
    
    if not api_key or not agentflow_id:
        raise FlowiseClientError("Flowise agentflow is not configured (missing API key or agentflow ID)")

    session_id = session_id or f"agentflow-{uuid.uuid4()}"

    url = f"{base_url}/api/v1/prediction/{agentflow_id}"
    payload = {
        "question": question,
        "overrideConfig": {
            "sessionId": session_id,
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = ClientTimeout(total=90)
    async with ClientSession(timeout=timeout) as client:
        async with client.post(url, headers=headers, json=payload) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.error("Flowise error %s: %s", resp.status, text)
                raise FlowiseClientError(
                    f"Flowise error {resp.status}: {text[:256]}"
                )
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                logger.exception("Failed to decode Flowise response: %s", text)
                raise FlowiseClientError("Invalid JSON from Flowise") from exc

    message = _extract_response_text(data)
    return FlowiseResponse(message=message, raw=data)

async def run_testchat_flow(question: str, session_id: str | None = None) -> FlowiseResponse:
    """Legacy function for backward compatibility."""
    if not settings.has_flowise_testchat:
        raise FlowiseClientError("Flowise TestChat is not configured")
    return await run_agentflow(question, settings.testchat_chatflow_id, session_id)

async def run_sysopka_agentflow(question: str, session_id: str | None = None, sysopka_type: str = "chatbot") -> FlowiseResponse:
    """Run Sysopka agentflow for specific specialty type"""
    agentflow_id = settings.get_sysopka_id(sysopka_type)

    if not agentflow_id or not settings.flowise_api_key:
        raise FlowiseClientError(f"Sysopka {sysopka_type} agentflow is not configured")

    session_id = session_id or f"sysopka-{sysopka_type}-{uuid.uuid4()}"

    url = f"{settings.flowise_base}/api/v1/prediction/{agentflow_id}"
    payload = {
        "question": question,
        "overrideConfig": {
            "sessionId": session_id,
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.flowise_api_key}",
        "Content-Type": "application/json",
    }

    timeout = ClientTimeout(total=90)
    async with ClientSession(timeout=timeout) as client:
        async with client.post(url, headers=headers, json=payload) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.error("Flowise error %s: %s", resp.status, text)
                raise FlowiseClientError(
                    f"Flowise error {resp.status}: {text[:256]}"
                )
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                logger.exception("Failed to decode Flowise response: %s", text)
                raise FlowiseClientError("Invalid JSON from Flowise") from exc

    message = _extract_response_text(data)
    return FlowiseResponse(message=message, raw=data)

def _extract_response_text(data: dict[str, Any]) -> str:
    candidates = [
        data.get("text"),
        data.get("response"),
        data.get("result"),
        data.get("message"),
        data.get("output"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    # Some Flowise templates store message under data -> answer
    if isinstance(data.get("data"), dict):
        inner = data["data"]
        for key in ("text", "response", "result", "answer"):
            value = inner.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    # Fallback to stringified JSON
    return json.dumps(data)
