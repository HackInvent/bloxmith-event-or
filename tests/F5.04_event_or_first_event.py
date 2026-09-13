#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies event or first event behavior for the event OR block.
# File Name: F5.04_event_or_first_event.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-12-07
# -----------------------------------------------------------------------------

"""F5.04 - Event OR relaie le premier input reçu.

Le test connecte une source texte au premier input de `event_or` et vérifie que
le message est relayé tel quel, sans comportement de merge.
"""

# Test cases:
# - FB1/FB3 - Connect one text source to EventOr and verify the first non-empty event is relayed unchanged with its content.
# - FB2 - Replay the same event with the persisted fingerprint state and verify it is skipped.
# - FB4 - Verify both an empty activation and a duplicate-only activation return skipped.
# - Runtime modes - Run the graph scenario in centralized and zeromq_active.

from pathlib import Path
from types import SimpleNamespace

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
        expect(run.get("status") == "success", "Un Event OR silencieux ne doit pas faire echouer le run.")
        expect(
            run.get("node_statuses", {}).get("event-or-1") == "skipped",
            "Event OR sans nouvel evenement ne doit pas apparaitre comme success.",
        )


def _verify_duplicate_event_is_skipped() -> None:
    """Verify persisted fingerprints prevent the same event from being relayed twice."""

    event = BlockInputEvent(
        edge_id="edge-source-event-or",
        input_port_id=1,
        input_port_name="input_1",
        source_node_id="source-1",
        source_port_id=1,
        value='{"event":"same"}',
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
    expect(first.status == "success", "Le premier événement doit être relayé.")
    expect(first.outputs[0].value == event.value, "Event OR doit préserver la valeur sélectionnée.")
    expect(
        first.outputs[0].content_type == "application/json",
        "Event OR doit préserver le content type sélectionné.",
    )
    expect(first.metadata.get("event_or_seen"), "Le premier relais doit persister son fingerprint.")

    duplicate = block.execute_runtime(
        BlockRuntimeContext(previous_result=first.metadata, **base_context)
    )
    expect(duplicate.status == "skipped", "Le même événement ne doit pas être relayé deux fois.")
    expect(
        duplicate.outputs and duplicate.outputs[0].value == "",
        "Une activation ne contenant qu'un doublon doit émettre une sortie vide.",
    )
    expect(
        duplicate.metadata.get("relayed_events") == [],
        "Un doublon ignoré ne doit pas apparaître parmi les événements relayés.",
    )
    expect(
        duplicate.metadata.get("event_or_seen") == first.metadata.get("event_or_seen"),
        "Ignorer un doublon ne doit pas altérer l'état de déduplication.",
    )


def _verify_runtime_mode(runtime_mode: str) -> None:
    """Run the same Event OR mini-graph through one selected execution engine."""

    with isolated_server() as server:
        document = graph_payload(
            f"F5 Event OR {runtime_mode}",
            [
                text_node("text-1", "Premier événement", "first event", 80, 120),
                event_or_node(),
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-text-event-or", "text-1", 1, "event-or-1", 1),
                data_edge("edge-event-or-display", "event-or-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=20)
        expect(run.get("status") == "success", f"Le run event_or {runtime_mode} doit réussir.")
        expect(run.get("runtime_mode") == runtime_mode, f"Le run doit rester en {runtime_mode}.")
        expect(
            run.get("output_values", {}).get("event-or-1:1", {}).get("value") == "first event",
            f"Event OR ne relaie pas le premier événement en {runtime_mode}.",
        )
        expect(
            run.get("results", {}).get("event-or-1", {}).get("relayed_events"),
            f"Event OR ne trace aucun événement relayé en {runtime_mode}.",
        )
        if runtime_mode == "zeromq_active":
            expect(
                run.get("results", {}).get("event-or-1", {}).get("transport") == "zeromq_active",
                "Event OR actif ne doit pas utiliser le moteur centralisé.",
            )


def main() -> None:
    _verify_event_or_without_event_is_skipped()
    _verify_duplicate_event_is_skipped()
    for runtime_mode in ("centralized", "zeromq_active"):
        _verify_runtime_mode(runtime_mode)
    print("[ok] F5.04_event_or_first_event")


if __name__ == "__main__":
    main()
