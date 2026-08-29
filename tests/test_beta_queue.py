"""The `beta.md` queue integrity validator, and the live file it guards.

BETA-038: the autonomous work queue is operational infrastructure, and a
stale marker in it has already outlived several commits. `scripts/
validate_beta_queue.py` turns the queue's own header-comment grammar into a
check; these tests pin each failure mode against a minimal fixture and then
assert the real `beta.md` still passes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BETA_MD = REPO_ROOT / "beta.md"
_VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_beta_queue.py"

_spec = importlib.util.spec_from_file_location("validate_beta_queue", _VALIDATOR_PATH)
validate_beta_queue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_beta_queue)
validate = validate_beta_queue.validate


# A well-formed miniature queue. Each failure-mode fixture is this with one
# thing broken, so a test that fails names exactly the rule it broke.
GOOD_QUEUE = """\
# Beta

## Autonomous Work Queue

<!--
AUTONOMOUS_QUEUE_VERSION: 1
Valid states:
NEXT
IN_PROGRESS
BLOCKED
DONE
-->

### IN_PROGRESS

- [IN_PROGRESS] BETA-100 | A current item
  - priority: P1
  - impact: 5
  - effort: 2
  - confidence: 5
  - risk: 1
  - area: engineering
  - objective: Do the thing.
  - next_action: Keep doing the thing.

### NEXT

- [NEXT] BETA-101 | A queued item
  - priority: P2
  - impact: 4
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: web
  - objective: Do the next thing.

### DONE

- [DONE] BETA-099 | An old item with none of the modern metadata
  - completed: 2026-01-01

## Something Else
"""


def test_the_reference_queue_is_clean():
    errors, warnings = validate(GOOD_QUEUE)
    assert errors == []
    assert warnings == []


def test_missing_queue_section_is_an_error():
    errors, _ = validate("# Beta\n\nNo queue here.\n")
    assert errors
    assert "Autonomous Work Queue" in errors[0]


def test_duplicate_item_id_is_an_error():
    broken = GOOD_QUEUE.replace(
        "- [NEXT] BETA-101 | A queued item", "- [NEXT] BETA-100 | A queued item"
    )
    errors, _ = validate(broken)
    assert any("duplicate item id BETA-100" in e for e in errors)


def test_unknown_state_heading_is_an_error():
    broken = GOOD_QUEUE.replace("### NEXT", "### SOON")
    errors, _ = validate(broken)
    assert any("SOON" in e for e in errors)


def test_unknown_item_state_prefix_is_an_error():
    broken = GOOD_QUEUE.replace(
        "- [NEXT] BETA-101 | A queued item", "- [SOON] BETA-101 | A queued item"
    )
    errors, _ = validate(broken)
    assert any("BETA-101 has unknown state '[SOON]'" in e for e in errors)


def test_item_state_heading_mismatch_is_an_error():
    broken = GOOD_QUEUE.replace(
        "- [NEXT] BETA-101 | A queued item", "- [DONE] BETA-101 | A queued item"
    )
    errors, _ = validate(broken)
    assert any("BETA-101 is '[DONE]' under '### NEXT'" in e for e in errors)


def test_more_than_one_in_progress_is_an_error():
    broken = GOOD_QUEUE.replace(
        "### NEXT\n\n- [NEXT] BETA-101 | A queued item",
        "### IN_PROGRESS\n\n- [IN_PROGRESS] BETA-101 | A second current item",
    )
    errors, _ = validate(broken)
    assert any("more than one IN_PROGRESS item" in e for e in errors)


def test_in_progress_without_next_action_is_an_error():
    broken = GOOD_QUEUE.replace("  - next_action: Keep doing the thing.\n", "")
    errors, _ = validate(broken)
    assert any("BETA-100 has no 'next_action'" in e for e in errors)


def test_malformed_item_bullet_is_an_error():
    broken = GOOD_QUEUE.replace(
        "- [IN_PROGRESS] BETA-100 | A current item",
        "- [IN_PROGRESS] BETA-100 - A current item",
    )
    errors, _ = validate(broken)
    assert any("malformed queue item" in e for e in errors)


def test_missing_version_marker_is_an_error():
    broken = GOOD_QUEUE.replace("AUTONOMOUS_QUEUE_VERSION: 1\n", "")
    errors, _ = validate(broken)
    assert any("AUTONOMOUS_QUEUE_VERSION" in e for e in errors)


def test_unknown_version_is_a_warning_not_an_error():
    changed = GOOD_QUEUE.replace("AUTONOMOUS_QUEUE_VERSION: 1", "AUTONOMOUS_QUEUE_VERSION: 2")
    errors, warnings = validate(changed)
    assert errors == []
    assert any("queue version is '2'" in w for w in warnings)


def test_actionable_item_missing_metadata_is_a_warning_not_an_error():
    changed = GOOD_QUEUE.replace("  - risk: 2\n", "")
    errors, warnings = validate(changed)
    assert errors == []
    assert any("BETA-101 is missing recommended metadata: risk" in w for w in warnings)


def test_done_item_missing_metadata_is_silent():
    # The DONE fixture item already has only `completed:`; the clean-queue
    # test proves that produces no warning. This asserts the intent directly.
    _, warnings = validate(GOOD_QUEUE)
    assert not any("BETA-099" in w for w in warnings)


@pytest.mark.skipif(not BETA_MD.exists(), reason="beta.md is only on the beta branch")
def test_live_beta_md_queue_has_no_errors():
    errors, _ = validate(BETA_MD.read_text(encoding="utf-8"))
    assert errors == [], "beta.md queue integrity errors:\n" + "\n".join(errors)


@pytest.mark.skipif(not BETA_MD.exists(), reason="beta.md is only on the beta branch")
def test_live_beta_md_queue_has_no_warnings():
    # The live file is expected to stay on the current metadata template for
    # actionable items. This is the check that a new NEXT/READY item added
    # without its scoring fields trips.
    _, warnings = validate(BETA_MD.read_text(encoding="utf-8"))
    assert warnings == [], "beta.md queue warnings:\n" + "\n".join(warnings)
