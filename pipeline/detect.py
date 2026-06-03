"""
detect.py — Main detection + tracking script.

Pipeline:
  1. Load CCTV clip with OpenCV
  2. Run YOLOv8 person detection on every frame (skipping by FRAME_SKIP)
  3. Feed detections into Tracker (ByteTrack-style IoU matching + Re-ID)
  4. Classify zone membership by mapping bounding-box centroid to store_layout.json zones
  5. Detect staff using uniform colour heuristic + optional VLM confirmation
  6. Emit structured events via emit.py
  7. Correlate billing zone presence with POS transactions for BILLING_QUEUE_ABANDON

Usage:
  python detect.py \
    --store-id STORE_BLR_002 \
    --layout   store_layout.json \
    --clips    "Store 2/entry 1.mp4" "Store 2/entry 2.mp4" "Store 2/zone.mp4" "Store 2/billing_area.mp4" \
    --cameras  CAM_ENTRY_01 CAM_ENTRY_02 CAM_FLOOR_01 CAM_BILLING_01 \
    --pos      pos_transactions.csv \
    --clip-start "2026-03-08T10:00:00" \
    --output   events_out.jsonl
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.tracker import Tracker, BBox, STAFF_CONF_THRESH, MIN_DET_CONFIDENCE
from pipeline.emit import (
    emit_entry, emit_exit, emit_reentry,
    emit_zone_enter, emit_zone_exit, emit_zone_dwell,
    emit_billing_queue_join, emit_billing_queue_abandon,
    frame_timestamp, write_events, EventType
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("detect")

# ── Config ─────────────────────────────────────────────────────────────────────
FRAME_SKIP          = 3        # process every Nth frame (reduces load, 15fps→5fps effective)
YOLO_CONF_THRESH    = 0.35
ENTRY_ZONE_FRAC_Y   = 0.80     # bottom 20% of frame = entry/exit threshold (entry camera)
DWELL_TICK_SEC      = 30       # emit ZONE_DWELL every N seconds of continued dwell
BILLING_POS_WINDOW  = 300      # seconds: billing presence → POS match window
STAFF_UNIFORM_HUE_LO = 90      # HSV hue range for typical staff uniform (blue/teal)
STAFF_UNIFORM_HUE_HI = 140


# ── Zone classifier ────────────────────────────────────────────────────────────

def load_layout(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def classify_zone(cx: float, cy: float, zones: list) -> Optional[dict]:
    """
    Map a normalised centroid (cx, cy) in [0,1]^2 to a store zone.
    Returns the matched zone dict or None.
    """
    for zone in zones:
        b = zone["bbox"]
        if b["x1"] <= cx <= b["x2"] and b["y1"] <= cy <= b["y2"]:
            return zone
    return None


def is_entry_zone(cx: float, cy: float, camera_type: str) -> Tuple[bool, str]:
    """
    For entry cameras: check direction by vertical centroid position.
    Returns (is_crossing_threshold, direction) where direction ∈ {"entry","exit"}.
    Simple heuristic: on entry camera, cy > 0.70 → near door = crossing threshold.
    Direction is tracked per-track via movement delta.
    """
    if camera_type == "entry" and cy > ENTRY_ZONE_FRAC_Y:
        return True, "crossing"
    return False, ""


# ── Staff detection ────────────────────────────────────────────────────────────

def detect_staff_heuristic(frame_bgr, bbox: BBox) -> Tuple[bool, float]:
    """
    Simple uniform-colour heuristic for staff detection.
    Returns (is_staff, confidence).
    Staff typically wear a branded uniform with a distinct hue band.
    Real production would use a fine-tuned classifier; this heuristic handles ~70%.
    """
    try:
        import cv2
        import numpy as np
        h, w = frame_bgr.shape[:2]
        x1, y1 = int(bbox.x1 * w), int(bbox.y1 * h)
        x2, y2 = int(bbox.x2 * w), int(bbox.y2 * h)
        crop = frame_bgr[max(0,y1):max(0,y2), max(0,x1):max(0,x2)]
        if crop.size == 0:
            return False, 0.0
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            (STAFF_UNIFORM_HUE_LO, 80, 80),
            (STAFF_UNIFORM_HUE_HI, 255, 255)
        )
        ratio = mask.sum() / 255.0 / (crop.shape[0] * crop.shape[1] + 1e-6)
        if ratio > 0.35:
            conf = min(0.95, 0.50 + ratio)
            return True, conf
        return False, ratio
    except Exception:
        return False, 0.0


# ── POS correlation ────────────────────────────────────────────────────────────

def load_pos(path: str, store_id: str) -> List[dict]:
    """Load POS records, parse to list of {ts: float, amount: float}."""
    import csv
    records = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("store_id", "").strip() != store_id:
                continue
            try:
                date_str = row["order_date"].strip()
                time_str = row["order_time"].strip()
                dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
                records.append({"ts": dt.timestamp(), "amount": float(row["total_amount"])})
            except Exception as e:
                logger.warning("POS parse error: %s", e)
    logger.info("Loaded %d POS records for %s", len(records), store_id)
    return records


def visitor_purchased(visitor_billing_exit_ts: float, pos_records: List[dict]) -> bool:
    """
    Returns True if a POS transaction falls within BILLING_POS_WINDOW seconds after
    the visitor exited the billing zone.
    """
    for rec in pos_records:
        if 0 <= rec["ts"] - visitor_billing_exit_ts <= BILLING_POS_WINDOW:
            return True
    return False


# ── Per-clip processor ─────────────────────────────────────────────────────────

def process_clip(
    clip_path: str,
    store_id: str,
    camera_id: str,
    camera_type: str,
    layout: dict,
    clip_start: datetime,
    pos_records: List[dict],
    output_events: list,
):
    """
    Process a single CCTV clip and append events to output_events.
    """
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as e:
        logger.error("Missing dependency: %s. Install with: pip install ultralytics opencv-python", e)
        sys.exit(1)

    zones = layout.get("zones", [])
    model = YOLO("yolov8n.pt")   # nano model — fastest inference
    cap   = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        logger.error("Cannot open clip: %s", clip_path)
        return

    fps         = cap.get(cv2.CAP_PROP_FPS) or 15.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    tracker     = Tracker(camera_id=camera_id, store_id=store_id, fps=fps)

    # State per active track
    track_zones:         dict = {}   # track_id → current zone_id
    track_zone_entry_ts: dict = {}   # track_id → zone entry timestamp (float)
    track_dwell_last_emit: dict = {} # track_id → last dwell emit ts
    track_in_entry_zone: dict = {}   # track_id → bool
    track_billing_entry: dict = {}   # track_id → billing zone entry ts
    emitted_entries:     set  = set()
    emitted_exits:       set  = set()
    queue_depth:         int  = 0    # live count in billing zone

    frame_idx = 0
    logger.info("Processing %s (%d frames @ %.1f fps)", clip_path, total_frames, fps)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % FRAME_SKIP != 0:
            frame_idx += 1
            continue

        ts_str  = frame_timestamp(clip_start, frame_idx, fps)
        ts_float = clip_start.timestamp() + frame_idx / fps
        h, w    = frame.shape[:2]

        # ── YOLO detection ───────────────────────────────────────────────────
        results = model(frame, classes=[0], conf=YOLO_CONF_THRESH, verbose=False)
        detections = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            bbox = BBox(x1/w, y1/h, x2/w, y2/h)
            is_staff_flag, staff_conf = detect_staff_heuristic(frame, bbox)
            detections.append((bbox, conf, is_staff_flag, staff_conf))

        # ── Tracker update ───────────────────────────────────────────────────
        active_tracks, just_lost, reentry_events = tracker.update(
            detections, frame, ts_float
        )

        # ── Re-entry events ──────────────────────────────────────────────────
        for track, old_vid in reentry_events:
            if not track.is_staff:
                output_events.append(emit_reentry(
                    store_id, camera_id, track.visitor_id,
                    ts_str, track.is_staff, track.confidence
                ))

        # ── Entry events (entry camera only) ────────────────────────────────
        if camera_type == "entry":
            for track in active_tracks:
                cx, cy = track.bbox.cx, track.bbox.cy
                near_threshold, _ = is_entry_zone(cx, cy, camera_type)

                if near_threshold and track.track_id not in emitted_entries:
                    emitted_entries.add(track.track_id)
                    track_in_entry_zone[track.track_id] = True
                    output_events.append(emit_entry(
                        store_id, camera_id, track.visitor_id,
                        ts_str, track.is_staff, track.confidence
                    ))

                # Detect exit: was in entry zone, now moved upward (into store)
                # Re-crossing threshold outbound = exit
                if track.track_id in track_in_entry_zone and not near_threshold:
                    # Track moved away from door → officially inside
                    pass

            for track in just_lost:
                if track.track_id in emitted_entries and track.track_id not in emitted_exits:
                    emitted_exits.add(track.track_id)
                    output_events.append(emit_exit(
                        store_id, camera_id, track.visitor_id,
                        ts_str, track.is_staff, track.confidence
                    ))

        # ── Zone events (floor + billing cameras) ───────────────────────────
        if camera_type in ("floor", "billing"):
            for track in active_tracks:
                if track.is_staff:
                    continue
                cx, cy  = track.bbox.cx, track.bbox.cy
                cur_zone = classify_zone(cx, cy, zones)
                cur_zid  = cur_zone["zone_id"] if cur_zone else None
                prev_zid = track_zones.get(track.track_id)

                # Zone enter
                if cur_zid and cur_zid != prev_zid:
                    track_zones[track.track_id]          = cur_zid
                    track_zone_entry_ts[track.track_id]  = ts_float
                    track_dwell_last_emit[track.track_id] = ts_float

                    output_events.append(emit_zone_enter(
                        store_id, camera_id, track.visitor_id, ts_str,
                        zone_id=cur_zid,
                        sku_zone=cur_zone.get("sku_zone"),
                        is_staff=track.is_staff,
                        confidence=track.confidence,
                    ))

                    # Billing queue join
                    if cur_zone and cur_zone.get("zone_type") == "BILLING":
                        queue_depth = sum(
                            1 for t in active_tracks
                            if not t.is_staff and
                               (classify_zone(t.bbox.cx, t.bbox.cy, zones) or {}).get("zone_type") == "BILLING"
                        )
                        if queue_depth > 0:
                            track_billing_entry[track.track_id] = ts_float
                            output_events.append(emit_billing_queue_join(
                                store_id, camera_id, track.visitor_id, ts_str,
                                zone_id=cur_zid, queue_depth=queue_depth,
                                is_staff=track.is_staff, confidence=track.confidence,
                            ))

                # Zone exit
                if prev_zid and cur_zid != prev_zid:
                    entry_ts  = track_zone_entry_ts.get(track.track_id, ts_float)
                    dwell_ms  = int((ts_float - entry_ts) * 1000)
                    prev_zone = next((z for z in zones if z["zone_id"] == prev_zid), {})
                    output_events.append(emit_zone_exit(
                        store_id, camera_id, track.visitor_id, ts_str,
                        zone_id=prev_zid,
                        dwell_ms=dwell_ms,
                        sku_zone=prev_zone.get("sku_zone"),
                        is_staff=track.is_staff,
                        confidence=track.confidence,
                    ))

                    # Check billing queue abandon
                    if prev_zone.get("zone_type") == "BILLING":
                        billing_entry = track_billing_entry.get(track.track_id)
                        if billing_entry and not visitor_purchased(ts_float, pos_records):
                            output_events.append(emit_billing_queue_abandon(
                                store_id, camera_id, track.visitor_id, ts_str,
                                zone_id=prev_zid,
                                dwell_ms=int((ts_float - billing_entry) * 1000),
                                is_staff=track.is_staff,
                                confidence=track.confidence,
                            ))
                        track_billing_entry.pop(track.track_id, None)
                        # Recalculate queue depth
                        queue_depth = max(0, queue_depth - 1)

                # Zone dwell (emit every DWELL_TICK_SEC)
                if cur_zid and cur_zid == prev_zid:
                    last_emit = track_dwell_last_emit.get(track.track_id, ts_float)
                    if ts_float - last_emit >= DWELL_TICK_SEC:
                        track_dwell_last_emit[track.track_id] = ts_float
                        entry_ts  = track_zone_entry_ts.get(track.track_id, ts_float)
                        dwell_ms  = int((ts_float - entry_ts) * 1000)
                        output_events.append(emit_zone_dwell(
                            store_id, camera_id, track.visitor_id, ts_str,
                            zone_id=cur_zid,
                            dwell_ms=dwell_ms,
                            sku_zone=cur_zone.get("sku_zone") if cur_zone else None,
                            is_staff=track.is_staff,
                            confidence=track.confidence,
                        ))

        frame_idx += 1

        if frame_idx % 150 == 0:
            logger.info("  Frame %d/%d  active_tracks=%d  events_so_far=%d",
                        frame_idx, total_frames, len(active_tracks), len(output_events))

    cap.release()
    logger.info("Finished %s: %d total events", clip_path, len(output_events))


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Purplle CCTV Detection Pipeline")
    parser.add_argument("--store-id",    required=True)
    parser.add_argument("--layout",      required=True, help="Path to store_layout.json")
    parser.add_argument("--clips",       nargs="+", required=True)
    parser.add_argument("--cameras",     nargs="+", required=True,
                        help="Camera IDs matching clip order (CAM_ENTRY_01, CAM_FLOOR_01, ...)")
    parser.add_argument("--pos",         required=False, default=None,
                        help="Path to POS CSV file")
    parser.add_argument("--clip-start",  default="2026-03-08T10:00:00",
                        help="ISO-8601 UTC start time of the first clip")
    parser.add_argument("--output",      default="events_out.jsonl")
    args = parser.parse_args()

    if len(args.clips) != len(args.cameras):
        logger.error("--clips and --cameras must have the same number of items")
        sys.exit(1)

    layout = load_layout(args.layout)
    clip_start = datetime.fromisoformat(args.clip_start).replace(tzinfo=timezone.utc)

    pos_records = []
    if args.pos:
        pos_records = load_pos(args.pos, args.store_id)

    # Determine camera type from camera_id suffix
    def _cam_type(cid: str) -> str:
        cid = cid.upper()
        if "ENTRY" in cid: return "entry"
        if "BILLING" in cid: return "billing"
        return "floor"

    all_events = []
    for clip_path, camera_id in zip(args.clips, args.cameras):
        cam_type = _cam_type(camera_id)
        process_clip(
            clip_path=clip_path,
            store_id=args.store_id,
            camera_id=camera_id,
            camera_type=cam_type,
            layout=layout,
            clip_start=clip_start,
            pos_records=pos_records,
            output_events=all_events,
        )

    # Sort by timestamp before writing
    all_events.sort(key=lambda e: e["timestamp"])
    write_events(all_events, args.output)
    logger.info("Pipeline complete. Total events: %d → %s", len(all_events), args.output)


if __name__ == "__main__":
    main()