# Event OR Block

<!-- block-metadata:start -->
[![Block version: 0.1.0](https://img.shields.io/badge/block-0.1.0-blue)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


## Role

`event_or` forwards the first new incoming event among its inputs. It is used to unblock a downstream path when any connected input receives data.

## Files

- `block.py`: event deduplication, first-event selection, and runtime emission.
- `model.json`: two optional inputs and one output.
- `inspector_panel.html`, `assets/`: inspector UI.
- `assets/js/block_modal.js`: modal-owned mount hook used by the framework to keep the modal stable during polling.
- `node_card.html`: block-owned canvas card body.

## Ports

- Inputs:
  - `input_1` (`id: 1`): optional `message/*`.
  - `input_2` (`id: 2`): optional `message/*`.
- Outputs:
  - `out` (`id: 1`): emits `message/*`.

## Configuration

No config is required.

## Runtime Behavior

`execute_runtime()` inspects `context.input_events` in the order delivered by the
runtime and emits the first non-blank event not already relayed. Its value,
including leading/trailing whitespace, and content type are preserved. Only that
selected event is recorded as relayed. If there is no new event, the block returns
`skipped` with no outputs.

The block retains one sequence watermark and one fixed-size fingerprint per
incoming route, not the full history or copies of earlier payloads. A second
publication with the same value and a higher source sequence is a new event;
replaying an equal or older sequence is ignored. State is carried by
`context.previous_result` and returned as runtime metadata, not stored on the block
singleton. With no source sequence, only a repeat of the last route/value/type can
be identified; older unsequenced publications have no reliable event identity.

The runtime registry marks this block with `centralized_dependency_mode="any_event"` and `active_execution_policy="on_each_event"`.

The block-owned tests exercise both runtime modes with bundled, managed and linked
packages, plus repeated publications, batch selection, exact payload preservation
and empty/duplicate-only activations.
They also verify that repeated publications do not grow the per-connection state.

## UI Behavior

The inspector provides a structural summary for the OR behavior.

## Editor Display

The canvas card is rendered by this block through `node_card.html`. It exposes the OR trigger summary while the shared editor shell keeps ports, dragging, status, and graph links generic.

## Modal

`block_modal.html` is owned by this block and rendered by the generic modal contract. It shows block state and lets users edit supported title/config fields through generic bindings.
The modal declares `data-block-runtime-refresh="autonomous"`; it is a lightweight block-owned surface so runtime polling does not replace the open modal or overwrite draft generic fields before **Apply**.

## Maintenance Notes

Any fingerprint or state-key change can affect deduplication and active runtime behavior. Update active runtime event tests when changing this block.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. Only the versions listed above have been verified, using the block-owned suites in a **bundled-block test installation**. This is not a certification of managed-package installation, every browser/OS, or live provider availability. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.

## Properties ergonomics

Modal and inspector styles are owned by this package and scoped to its exact
release. Forms adapt to narrow panels, checkboxes stay beside their labels, and
long values do not widen the inspector. Existing labels are associated with
controls; keyboard navigation complements the block’s own tab handlers.
These presentation helpers do not change port bindings, authored settings,
runtime behavior or the block’s original surface cleanup.
