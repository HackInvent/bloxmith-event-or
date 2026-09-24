#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies event or first event behavior for the event OR block.
# File Name: F5.04_event_or_first_event.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-12-07
# -----------------------------------------------------------------------------

"""F5.04 - Event OR relays the first input it receives.

The test wires a text source to the first input of `event_or` and checks that
the message is relayed as is, with no merge behavior.
"""

# Test cases:
# - FB1/FB3 - Connect one text source to EventOr and verify the first non-empty event is relayed unchanged with its content.
# - FB2 - Replay the same event with the persisted fingerprint state and verify it is skipped.
# - FB4 - Verify both an empty activation and a duplicate-only activation return skipped.
# - Runtime modes - Run the graph scenario in centralized and zeromq_active.

from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace

from ui_smoke_common import (
    create_run_api,
    data_edge,
    display_node,
    expect,
    graph_payload,
    isolated_server,
    text_node,
    wait_for_run_terminal,
)
from block_test_packages import install_test_package

from blocs.event_or.block import EventOrBlock
from bloxsmith_app.block_runtime import BlockInputEvent, BlockRuntimeContext


def event_or_node() -> dict:
    return {
        "id": "event-or-1",
        "kind": "event_or",
        "title": "Event OR test",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {"id": 1, "name": "input_1", "title": "In 1", "accepts": ["message/*"], "multiplicity": "many"},
            {"id": 2, "name": "input_2", "title": "In 2", "accepts": ["message/*"], "multiplicity": "many"},
        ],
        "outputs": [
            {"id": 1, "name": "out", "title": "Out", "emits": ["message/*"], "multiplicity": "many"}
        ],
        "config": {},
    }


def _verify_event_or_without_event_is_skipped() -> None:
    """Verify a silent Event OR is not reported as a successful relay."""

    with isolated_server() as server:
        document = graph_payload(
            "F5 Event OR skipped",
            [
                event_or_node(),
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-event-or-display", "event-or-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode="centralized")
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""))
        expect(run.get("status") == "success", "A silent Event OR must not fail the run.")
        expect(
            run.get("node_statuses", {}).get("event-or-1") == "skipped",
            "Event OR with no new event must not report success.",
        )


def _verify_duplicate_event_is_skipped() -> None:
    """Verify persisted fingerprints prevent the same event from being relayed twice."""

    event = BlockInputEvent(
        edge_id="edge-source-event-or",
        input_port_id=1,
        input_port_name="input_1",
        source_node_id="source-1",
        source_port_id=1,
        value='  {"event":"same"}\n',
        content_type="application/json",
        sequence=1,
    )
    base_context = {
        "run_id": "unit-run",
        "node_id": "event-or-unit",
        "kind": "event_or",
        "title": "Event OR unit",
        "config": {},
        "inputs": {"input_1": event.value},
        "input_content_types": {"input_1": event.content_type},
        "input_message": event.value,
        "input_ports": (SimpleNamespace(id=1, name="input_1"),),
        "output_ports": (SimpleNamespace(id=1, name="out"),),
        "root_dir": Path.cwd(),
        "input_events": (event,),
    }
    block = EventOrBlock()
    first = block.execute_runtime(BlockRuntimeContext(**base_context))
    expect(first.status == "success", "The first event must be relayed.")
    expect(first.outputs[0].value == event.value, "Event OR must preserve the selected value.")
    expect(
        first.outputs[0].content_type == "application/json",
        "Event OR must preserve the selected content type.",
    )
    expect(first.metadata.get("event_or_seen"), "The first relay must persist its fingerprint.")

    duplicate = block.execute_runtime(
        BlockRuntimeContext(previous_result=first.metadata, **base_context)
    )
    expect(duplicate.status == "skipped", "The same event must not be relayed twice.")
    expect(
        duplicate.outputs == [],
        "An activation holding only a duplicate must not emit an output.",
    )
    expect(
        duplicate.metadata.get("relayed_events") == [],
        "An ignored duplicate must not appear among the relayed events.",
    )
    expect(
        duplicate.metadata.get("event_or_seen") == first.metadata.get("event_or_seen"),
        "Ignoring a duplicate must not alter the deduplication state.",
    )
    next_context = {**base_context, "input_events": (replace(event, sequence=2),)}
    next_result = block.execute_runtime(BlockRuntimeContext(previous_result=first.metadata, **next_context))
    expect(next_result.status == "success" and next_result.outputs[0].value == event.value,
           "A new publication with identical data must not be suppressed.")
    older = block.execute_runtime(BlockRuntimeContext(previous_result=next_result.metadata, **base_context))
    expect(older.status == "skipped" and not older.outputs, "An older sequenced publication must not replay.")
    previous = next_result.metadata
    for sequence in range(3, 103):
        current = {**base_context, "input_events": (replace(event, sequence=sequence),)}
        result = block.execute_runtime(BlockRuntimeContext(previous_result=previous, **current))
        expect(result.status == "success", "Fresh repeated publications must continue to relay.")
        previous = result.metadata
    expect(len(previous["event_or_seen"]) == 1, "One connection must retain one watermark, not event history.")
    expect(len(next(iter(previous["event_or_seen"].values()))["fingerprint"]) == 64,
           "Deduplication state must not retain complete payloads.")

    # The runtime supplies delivery order; input port numbers are not a clock.
    earliest = replace(event, edge_id="second-port", input_port_id=2, value="first arrival")
    latest = replace(event, sequence=2, value="second arrival")
    batch = block.execute_runtime(BlockRuntimeContext(**{**base_context, "input_events": (earliest, latest)}))
    expect(batch.outputs[0].value == earliest.value, "Event OR must select the first fresh event of a batch.")
    expect(len(batch.metadata["relayed_events"]) == 1, "Only the emitted event may be reported as relayed.")

    silence = block.execute_runtime(BlockRuntimeContext(**{**base_context, "input_events": ()}))
    expect(silence.status == "skipped" and not silence.outputs, "An empty activation must emit nothing.")


def _verify_runtime_mode(runtime_mode: str, *, origin: str | None = None) -> None:
    """Run the Event OR mini-graph through each engine and supported package host."""

    with isolated_server() as server:
        node = event_or_node()
        if origin:
            model = install_test_package(server, "event_or", origin=origin)
            node["block_version"] = model["version"]
        document = graph_payload(
            f"F5 Event OR {runtime_mode}",
            [
                text_node("text-1", "First event", "first event", 80, 120),
                node,
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-text-event-or", "text-1", 1, "event-or-1", 1),
                data_edge("edge-event-or-display", "event-or-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=20)
        expect(run.get("status") == "success", f"The event_or {runtime_mode} run must succeed.")
        expect(run.get("runtime_mode") == runtime_mode, f"The run must stay in {runtime_mode}.")
        expect(
            run.get("output_values", {}).get("event-or-1:1", {}).get("value") == "first event",
            f"Event OR does not relay the first event in {runtime_mode}.",
        )
        expect(
            run.get("results", {}).get("event-or-1", {}).get("relayed_events"),
            f"Event OR logs no relayed event in {runtime_mode}.",
        )
        if runtime_mode == "zeromq_active":
            expect(
                run.get("results", {}).get("event-or-1", {}).get("transport") == "zeromq_active",
                "An active Event OR must not use the centralized engine.",
            )


def main() -> None:
    _verify_event_or_without_event_is_skipped()
    _verify_duplicate_event_is_skipped()
    for runtime_mode in ("centralized", "zeromq_active"):
        for origin in (None, "managed", "linked"):
            _verify_runtime_mode(runtime_mode, origin=origin)
    print("[ok] F5.04_event_or_first_event")


if __name__ == "__main__":
    main()
