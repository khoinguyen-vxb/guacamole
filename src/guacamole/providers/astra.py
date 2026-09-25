"""GPT-6 Astra via Responses; no implicit tools, sessions, files, or credentials in prompts.

https://developers.openai.com/api/docs/guides/token-counting
https://developers.openai.com/api/docs/models/gpt-6-astra
"""

import asyncio
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

from ..contracts import JSON, AgentTurn, ContextPacket
from ..tools.registry import encode


class _Text(BaseModel):
    model_config = ConfigDict(strict=True)
    type: str
    text: str = ""


class _Output(BaseModel):
    model_config = ConfigDict(strict=True)
    type: str
    content: list[_Text] = []
    summary: list[_Text] = []


class _Response(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    status: str
    output: list[_Output]


class AstraReasoning:
    name = "openai-responses"
    model = "gpt-6-astra"
    context_capacity_tokens = 1_050_000

    def __init__(
        self, *, api_key_env: str = "OPENAI_API_KEY", timeout_s: float = 120.0
    ) -> None:
        self._api_key_env = api_key_env
        self.timeout_s = timeout_s

    def _post(self, path: str, data: JSON) -> JSON:
        key = os.environ.get(self._api_key_env)
        if not key:
            raise RuntimeError(f"Set {self._api_key_env} to use GPT-6 Astra")
        request = Request(
            f"https://api.openai.com/v1/responses{path}",
            data=encode(data).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                return json.load(response)
        except HTTPError as exc:
            # Do not persist server echoes of prompts or authentication headers.
            raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}") from None

    async def count_tokens(self, prompt: str) -> int:
        response = await asyncio.to_thread(
            self._post, "/input_tokens", {"model": self.model, "input": prompt}
        )
        count = response.get("input_tokens")
        if type(count) is not int or count < 0:
            raise ValueError("OpenAI did not return a valid input token count")
        return count

    async def respond(self, packet: ContextPacket) -> AgentTurn:
        if packet.model != self.model or packet.provider != self.name:
            raise ValueError("Context packet targets another provider")
        if (
            packet.input_tokens + packet.reserved_output_tokens
            > self.context_capacity_tokens
        ):
            raise ValueError("Context packet exceeds model capacity")
        if packet.reserved_output_tokens > 128_000:
            raise ValueError("Requested output exceeds GPT-6 Astra's output limit")
        raw = await asyncio.to_thread(
            self._post,
            "",
            {
                "model": self.model,
                "input": packet.prompt,
                "store": False,
                "max_output_tokens": packet.reserved_output_tokens,
            },
        )
        response = _Response.model_validate(raw)
        if response.status != "completed":
            raise RuntimeError(
                "OpenAI returned an incomplete response; no action executed"
            )
        texts, summaries = [], []
        for item in response.output:
            if item.type == "message":
                texts.extend(
                    content.text
                    for content in item.content
                    if content.type == "output_text"
                )
            elif item.type == "reasoning":
                summaries.extend(
                    s.text for s in item.summary if s.type == "summary_text"
                )
        turn = AgentTurn.model_validate_json("".join(texts))
        return turn.model_copy(
            update={
                "provider_request_id": response.id,
                "provider_summary": "\n".join(summaries) or None,
            }
        )
