"""
emit.py — Event schema definition and emission helpers.

Converts tracker output → structured JSON events matching the required schema.
All timestamps are ISO-8601 UTC derived from clip start time + frame offset.
"""

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# ── Event type constants ──────────────────────────────────────────────────────

class EventType:
    ENTRY                  = "ENTRY"
    EXIT                   = "EXIT"
    ZONE_ENTER             = "ZONE_ENTER"
    ZONE_EXIT              = "ZONE_EXIT"
    ZONE_DWELL             = "ZONE_DWELL"
    BILLING_QUEUE_JOIN     = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON  = "BILLING_QUEUE_ABANDON"
    REENTRY                = "REENTRY"


# ── Session tracker ───────────────────────────────────────────────────────────

class SessionManager:
    """Per-store session sequence tracker."""
    def __init__(self):
        self._seq: dict = {}  # visitor_id → int

    def next(self, visitor_id: str) -> int:
        self._seq[visitor_id] = self._seq.get(visitor_id, 0) + 1
        return self._seq[visitor_id]

    def reset(self, visitor_id: str):
        self._seq.pop(visitor_id, None)


_session_mgr = SessionManager()


# ── Schema builder ────────────────────────────────────────────────────────────

def _make_event(
    store_id: str,
    camera_id: str,
    visitor_id: str,
    event_type: str,
    timestamp: str,
    zone_id: Optional[str] = None,
    dwell_ms: int = 0,
    is_staff: bool = False,
    confidence: float = 1.0,
    queue_depth: Optional[int] = None,
    sku_zone: Optional[str] = None,
) -> dict:
    """Produce a fully-formed event dict matching the required schema."""
    seq = _session_mgr.next(visitor_id)
    return {
        "event_id":    str(uuid.uuid4()),
        "store_id":    store_id,
        "camera_id":   camera_id,
        "visitor_id":  visitor_id,
        "event_type":  event_type,
        "timestamp":   timestamp,
        "zone_id":     zone_id,
        "dwell_ms":    dwell_ms,
        "is_staff":    is_staff,
        "confidence":  round(confidence, 4),
        "metadata": {
            "queue_depth":  queue_depth,
            "sku_zone":     sku_zone,
            "session_seq":  seq,
        },
    }


def frame_timestamp(clip_start: datetime, frame_idx: int, fps: float) -> str:
    """Convert frame index → ISO-8601 UTC string."""
    offset = timedelta(seconds=frame_idx / fps)
    ts = (clip_start + offset).replace(tzinfo=timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── High-level emitters ───────────────────────────────────────────────────────

def emit_entry(store_id, camera_id, visitor_id, timestamp, is_staff, confidence) -> dict:
    logger.debug("ENTRY %s @ %s", visitor_id, timestamp)
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.ENTRY, timestamp=timestamp,
        is_staff=is_staff, confidence=confidence,
    )


def emit_exit(store_id, camera_id, visitor_id, timestamp, is_staff, confidence) -> dict:
    logger.debug("EXIT %s @ %s", visitor_id, timestamp)
    ev = _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.EXIT, timestamp=timestamp,
        is_staff=is_staff, confidence=confidence,
    )
    _session_mgr.reset(visitor_id)   # reset sequence for next visit
    return ev


def emit_reentry(store_id, camera_id, visitor_id, timestamp, is_staff, confidence) -> dict:
    logger.debug("REENTRY %s @ %s", visitor_id, timestamp)
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.REENTRY, timestamp=timestamp,
        is_staff=is_staff, confidence=confidence,
    )


def emit_zone_enter(store_id, camera_id, visitor_id, timestamp,
                    zone_id, sku_zone, is_staff, confidence) -> dict:
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.ZONE_ENTER, timestamp=timestamp,
        zone_id=zone_id, sku_zone=sku_zone,
        is_staff=is_staff, confidence=confidence,
    )


def emit_zone_exit(store_id, camera_id, visitor_id, timestamp,
                   zone_id, dwell_ms, sku_zone, is_staff, confidence) -> dict:
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.ZONE_EXIT, timestamp=timestamp,
        zone_id=zone_id, dwell_ms=dwell_ms, sku_zone=sku_zone,
        is_staff=is_staff, confidence=confidence,
    )


def emit_zone_dwell(store_id, camera_id, visitor_id, timestamp,
                    zone_id, dwell_ms, sku_zone, is_staff, confidence) -> dict:
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.ZONE_DWELL, timestamp=timestamp,
        zone_id=zone_id, dwell_ms=dwell_ms, sku_zone=sku_zone,
        is_staff=is_staff, confidence=confidence,
    )


def emit_billing_queue_join(store_id, camera_id, visitor_id, timestamp,
                            zone_id, queue_depth, is_staff, confidence) -> dict:
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.BILLING_QUEUE_JOIN, timestamp=timestamp,
        zone_id=zone_id, queue_depth=queue_depth,
        is_staff=is_staff, confidence=confidence,
    )


def emit_billing_queue_abandon(store_id, camera_id, visitor_id, timestamp,
                               zone_id, dwell_ms, is_staff, confidence) -> dict:
    return _make_event(
        store_id=store_id, camera_id=camera_id, visitor_id=visitor_id,
        event_type=EventType.BILLING_QUEUE_ABANDON, timestamp=timestamp,
        zone_id=zone_id, dwell_ms=dwell_ms,
        is_staff=is_staff, confidence=confidence,
    )


def write_events(events: List[dict], path: str):
    """Append events to a JSONL file."""
    with open(path, "a") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    logger.info("Wrote %d events to %s", len(events), path)


def events_to_jsonl(events: List[dict]) -> str:
    return "\n".join(json.dumps(e) for e in events)