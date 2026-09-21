# -----------------------------------------------------------------------------
# Role: Implements the event OR block runtime and UI contract.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-10-31
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
from html import escape
from typing import Any

from bloxsmith_app.block_api import (
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    render_inspector_template,
    render_node_card_template,
    TEXT_PLAIN,
)


# Functional behavior:
# FB1 - Relay the first new non-empty input event to every output port.
# FB2 - Fingerprint relayed events in runtime state so repeated propagation skips duplicates.
# FB3 - Preserve the selected event value and content type instead of merging inputs.
# FB4 - Return skipped status when no new input event is available.
class EventOrBlock(BlockDefinition):
    """Autonomous block implementation for `EventOrBlock`."""
    kind = "event_or"

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the Event OR canvas card body from the block-owned template."""

        input_count = len(node.get("inputs") or [])
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["event-or-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "preview": self.translate(
                    "block.event_or.preview",
                    {"count": input_count},
                    fallback=f"{input_count} incoming event{'s' if input_count > 1 else ''}",
                ),
                # The card text is countable: the count travels next to the marker so the
                # browser also follows a language change without asking the server again.
                "preview_count": input_count,
                "mode": self.translate("block.event_or.mode", fallback="any event"),
            },
        )

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the block-owned inspector panel HTML for the selected node.

        Args:
            node: Serialized graph node handled by the block.
            payload: Optional UI or runtime payload provided by the framework.
        """
        inputs = node.get("inputs") if isinstance(node.get("inputs"), list) else []
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=(
                template
                .replace("{{ source }}", escape(f"{len(inputs)} input(s)"))
                .replace("{{ description }}", escape(self.translate(
                    "block.event_or.behavior_description",
                    fallback="Relays only new incoming messages and ignores duplicates already relayed during the run.",
                )))
            ),
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
        )
        return {"html": html, "context": {"node_id": str(node.get("id") or ""), "input_count": len(inputs), "full_panel": True}}

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Execute the block through the generic runtime context and return runtime outputs.

        Args:
            context: Generic runtime context injected by the execution engine.
        """
        raw_seen = context.previous_result.get("event_or_seen") if isinstance(context.previous_result, dict) else []
        seen = {str(item) for item in raw_seen if str(item or "").strip()} if isinstance(raw_seen, list) else set()
        next_seen = set(seen)
        relayed_events: list[dict[str, object]] = []

        for event in sorted(context.input_events, key=lambda item: (item.input_port_id, item.edge_id)):
            value = str(event.value or "").strip()
            if not value:
                continue
            content_type = str(event.content_type or TEXT_PLAIN)
            fingerprint = self._fingerprint(event.edge_id, event.input_port_id, value, content_type)
            if fingerprint in next_seen:
                continue
            next_seen.add(fingerprint)
            relayed_events.append(
                {
                    "input_port_id": event.input_port_id,
                    "input_port_name": event.input_port_name,
                    "source_node_id": event.source_node_id,
                    "source_port_id": event.source_port_id,
                    "value": value,
                    "content_type": content_type,
                }
            )

        relayed_value = str(relayed_events[-1]["value"] if relayed_events else "")
        output_content_type = str(relayed_events[-1]["content_type"] if relayed_events else TEXT_PLAIN)
        outputs = [
            BlockRuntimeOutput(
                port_id=int(getattr(port, "id", 0) or 0),
                port_name=str(getattr(port, "name", "") or ""),
                value=relayed_value,
                content_type=output_content_type,
            )
            for port in context.output_ports
        ]
        logs = (
            [
                f"[event_or] {context.node_id}.{event['input_port_id']} relaye "
                f"{event['source_node_id']}.{event['source_port_id']}."
                for event in relayed_events
            ]
            if relayed_events
            else [f"[event_or] {context.node_id}: aucun nouvel input a relayer."]
        )
        return BlockRuntimeResult(
            status="success" if relayed_events else "skipped",
            outputs=outputs,
            logs=logs,
            last_message=relayed_value,
            content_type=output_content_type,
            worker_received=relayed_value or "-",
            metadata={"event_or_seen": sorted(next_seen), "relayed_events": relayed_events},
        )

    def _fingerprint(self, edge_id: str, port_id: int, value: str, content_type: str) -> str:
        """Provide internal EventOrBlock behavior for `_fingerprint`.

        Args:
            edge_id: Identifier used to select a graph, port, output, or runtime object.
            port_id: Numeric port identifier.
            value: Value to normalize, render, serialize, or process.
            content_type: Content type value used by this block helper.
        """
        return json.dumps(
            {
                "edge": str(edge_id),
                "port": int(port_id),
                "content_type": str(content_type or TEXT_PLAIN),
                "value": str(value or ""),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
