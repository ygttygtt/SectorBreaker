"""A2A 1.x client adapter for opaque remote Specialist workers."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, SendMessageRequest

from backend.app.schemas import AgentDeliverable, WorkOrder


class A2AClientTransport:
    """Discover an A2A Agent Card and exchange one structured WorkOrder."""

    def __init__(self, *, connect_timeout_seconds: int = 8) -> None:
        self.connect_timeout_seconds = connect_timeout_seconds
        self._cards: dict[str, object] = {}

    async def discover(self, endpoint: str) -> dict:
        base_url = endpoint.rstrip("/")
        async with httpx.AsyncClient(timeout=self.connect_timeout_seconds) as client:
            card = await A2ACardResolver(client, base_url).get_agent_card()
        if not card.skills:
            raise ValueError("A2A Agent Card declares no skills")
        if not any(interface.protocol_binding == "JSONRPC" for interface in card.supported_interfaces):
            raise ValueError("A2A Agent does not advertise JSONRPC")
        self._cards[base_url] = card
        return MessageToDict(card, preserving_proto_field_name=True)

    async def execute(
        self,
        endpoint: str,
        work_order: WorkOrder,
        *,
        domain: str,
        timeout_seconds: int,
    ) -> AgentDeliverable:
        base_url = endpoint.rstrip("/")
        card = self._cards.get(base_url)
        if card is None:
            await self.discover(base_url)
            card = self._cards[base_url]
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(max(15, timeout_seconds + 5)))
        client = ClientFactory(ClientConfig(
            streaming=True,
            polling=False,
            httpx_client=http_client,
            supported_protocol_bindings=["JSONRPC"],
            accepted_output_modes=["application/json"],
        )).create(card)  # type: ignore[arg-type]
        payload = Value()
        ParseDict({
            "contract": "sectorbreaker.agent-deliverable.v1",
            "domain": domain,
            "work_order": work_order.model_dump(mode="json"),
        }, payload)
        message = Message(
            message_id=f"MSG-{uuid4().hex}",
            role=Role.ROLE_USER,
            parts=[Part(data=payload, media_type="application/json")],
        )
        request = SendMessageRequest(message=message)
        deliverable_payload: dict | None = None

        async def collect() -> None:
            nonlocal deliverable_payload
            async for response in client.send_message(request):
                artifacts = []
                if response.HasField("task"):
                    artifacts.extend(response.task.artifacts)
                if response.HasField("artifact_update"):
                    artifacts.append(response.artifact_update.artifact)
                if response.HasField("message"):
                    for part in response.message.parts:
                        parsed = _part_payload(part)
                        if isinstance(parsed, dict) and parsed.get("contract") == "sectorbreaker.agent-deliverable.v1":
                            deliverable_payload = parsed.get("deliverable")
                for artifact in artifacts:
                    for part in artifact.parts:
                        parsed = _part_payload(part)
                        if isinstance(parsed, dict) and parsed.get("contract") == "sectorbreaker.agent-deliverable.v1":
                            deliverable_payload = parsed.get("deliverable")

        try:
            await asyncio.wait_for(collect(), timeout=max(10, timeout_seconds))
        finally:
            await client.close()
        if not isinstance(deliverable_payload, dict):
            raise ValueError("A2A task completed without a typed AgentDeliverable Artifact")
        deliverable = AgentDeliverable.model_validate(deliverable_payload)
        if deliverable.task_id != work_order.id or deliverable.mission_id != work_order.mission_id:
            raise ValueError("A2A deliverable identity does not match WorkOrder")
        return deliverable


def _part_payload(part: Part):
    if part.HasField("data"):
        return MessageToDict(part.data, preserving_proto_field_name=True)
    if part.text:
        import json

        try:
            return json.loads(part.text)
        except json.JSONDecodeError:
            return None
    return None
