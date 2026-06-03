"""
tracker.py — Re-ID and multi-object tracking logic.

Uses a lightweight IoU + appearance-similarity tracker inspired by ByteTrack.
For Re-ID across camera views or re-entry, we use bounding-box trajectory
history and a cosine similarity on HOG-like colour histogram embeddings
(works without GPU, fast enough for 15fps 1080p).

Re-entry logic: if a visitor exits and reappears within a configurable window
(default 5 min) with embedding similarity > REENTRY_SIM_THRESHOLD, we emit
REENTRY rather than a fresh ENTRY.
"""

import uuid
import time
import math
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────────
IOU_THRESHOLD        = 0.25   # min IoU to link detections across frames
MAX_LOST_FRAMES      = 30     # frames a track can be lost before confirmed exit
REENTRY_WINDOW_SEC   = 300    # 5 min window to consider re-entry
REENTRY_SIM_THRESH   = 0.72   # cosine similarity above which we flag re-entry
STAFF_CONF_THRESH    = 0.60   # minimum confidence to mark as staff
MIN_DET_CONFIDENCE   = 0.30   # detections below this are kept but flagged low-conf


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class BBox:
    x1: float; y1: float; x2: float; y2: float

    @property
    def cx(self): return (self.x1 + self.x2) / 2
    @property
    def cy(self): return (self.y1 + self.y2) / 2
    @property
    def area(self): return max(0, self.x2-self.x1) * max(0, self.y2-self.y1)

    def iou(self, other: "BBox") -> float:
        ix1 = max(self.x1, other.x1); iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2); iy2 = min(self.y2, other.y2)
        inter = max(0, ix2-ix1) * max(0, iy2-iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: str                          # globally unique track ID
    visitor_id: str                        # Re-ID token (may survive re-entry)
    bbox: BBox
    embedding: np.ndarray                  # colour histogram embedding
    is_staff: bool = False
    confidence: float = 1.0
    lost_frames: int = 0
    active: bool = True
    entry_time: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    zone_history: List[str] = field(default_factory=list)
    session_seq: int = 0


@dataclass
class ExitedVisitor:
    """Kept in memory for re-entry detection."""
    visitor_id: str
    embedding: np.ndarray
    exit_time: float
    bbox_at_exit: BBox


# ── Embedding helper ───────────────────────────────────────────────────────────

def _colour_histogram(frame_bgr: np.ndarray, bbox: BBox, bins: int = 32) -> np.ndarray:
    """
    Fast HSV colour histogram as a compact Re-ID embedding.
    Falls back gracefully if the crop is empty.
    """
    try:
        import cv2
        h, w = frame_bgr.shape[:2]
        x1, y1 = int(bbox.x1 * w), int(bbox.y1 * h)
        x2, y2 = int(bbox.x2 * w), int(bbox.y2 * h)
        crop = frame_bgr[max(0,y1):max(0,y2), max(0,x1):max(0,x2)]
        if crop.size == 0:
            return np.zeros(bins * 3)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = []
        for ch in range(3):
            h_vals, _ = np.histogram(hsv[:, :, ch], bins=bins, range=(0, 256))
            hist.append(h_vals.astype(float))
        vec = np.concatenate(hist)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    except Exception:
        return np.zeros(bins * 3)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── Main tracker ──────────────────────────────────────────────────────────────

class Tracker:
    def __init__(self, camera_id: str, store_id: str, fps: float = 15.0):
        self.camera_id = camera_id
        self.store_id  = store_id
        self.fps       = fps
        self.tracks: Dict[str, Track] = {}
        self.exited: List[ExitedVisitor] = []   # for re-entry detection
        self._frame_idx = 0

    # ── public API ──────────────────────────────────────────────────────────

    def update(
        self,
        detections: List[Tuple[BBox, float, bool, float]],
        frame_bgr,
        frame_ts: float,
    ) -> Tuple[List[Track], List[Track], List[Tuple[Track, str]]]:
        """
        Args:
            detections: list of (bbox, detection_confidence, is_staff_flag, staff_confidence)
            frame_bgr:  numpy BGR frame (used for embedding)
            frame_ts:   wall-clock timestamp for this frame

        Returns:
            (active_tracks, just_lost_tracks, reentry_events)
            reentry_events: list of (track, old_visitor_id)
        """
        self._frame_idx += 1

        # Build embeddings for new detections
        det_embeds = [
            _colour_histogram(frame_bgr, bbox) for bbox, *_ in detections
        ]

        # ── Match detections → existing active tracks (greedy IoU) ──────────
        active_ids = [tid for tid, t in self.tracks.items() if t.active]
        matched_dets = set()
        matched_tracks = set()

        if active_ids and detections:
            cost = np.zeros((len(active_ids), len(detections)))
            for i, tid in enumerate(active_ids):
                for j, (bbox, conf, *_) in enumerate(detections):
                    cost[i, j] = self.tracks[tid].bbox.iou(bbox)

            # Greedy match: highest IoU first
            while True:
                idx = np.argmax(cost)
                i, j = divmod(int(idx), cost.shape[1])
                if cost[i, j] < IOU_THRESHOLD:
                    break
                tid = active_ids[i]
                self.tracks[tid].bbox = detections[j][0]
                self.tracks[tid].confidence = detections[j][1]
                self.tracks[tid].is_staff = detections[j][2]
                self.tracks[tid].embedding = det_embeds[j]
                self.tracks[tid].lost_frames = 0
                self.tracks[tid].last_seen = frame_ts
                matched_dets.add(j)
                matched_tracks.add(tid)
                cost[i, :] = -1
                cost[:, j] = -1

        # ── Spawn new tracks for unmatched detections ───────────────────────
        reentry_events = []
        for j, (bbox, conf, is_staff, staff_conf) in enumerate(detections):
            if j in matched_dets:
                continue
            emb = det_embeds[j]
            # Check re-entry
            reentry_match = self._check_reentry(emb, frame_ts)
            if reentry_match:
                visitor_id = reentry_match.visitor_id
                track_id = f"TRK_{uuid.uuid4().hex[:8]}"
                t = Track(
                    track_id=track_id, visitor_id=visitor_id,
                    bbox=bbox, embedding=emb, is_staff=is_staff,
                    confidence=conf, last_seen=frame_ts, entry_time=frame_ts
                )
                self.tracks[track_id] = t
                reentry_events.append((t, visitor_id))
                logger.debug("Re-entry detected: visitor %s", visitor_id)
            else:
                visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
                track_id   = f"TRK_{uuid.uuid4().hex[:8]}"
                t = Track(
                    track_id=track_id, visitor_id=visitor_id,
                    bbox=bbox, embedding=emb, is_staff=is_staff,
                    confidence=conf, last_seen=frame_ts, entry_time=frame_ts
                )
                self.tracks[track_id] = t

        # ── Age unmatched active tracks ──────────────────────────────────────
        just_lost = []
        for tid in active_ids:
            if tid not in matched_tracks:
                self.tracks[tid].lost_frames += 1
                if self.tracks[tid].lost_frames >= MAX_LOST_FRAMES:
                    self.tracks[tid].active = False
                    exited = self.tracks[tid]
                    just_lost.append(exited)
                    self.exited.append(ExitedVisitor(
                        visitor_id=exited.visitor_id,
                        embedding=exited.embedding,
                        exit_time=frame_ts,
                        bbox_at_exit=exited.bbox,
                    ))
                    logger.debug("Track %s lost → EXIT", tid)

        # ── Prune stale exited records ───────────────────────────────────────
        self.exited = [
            ev for ev in self.exited
            if frame_ts - ev.exit_time < REENTRY_WINDOW_SEC
        ]

        active_tracks = [t for t in self.tracks.values() if t.active]
        return active_tracks, just_lost, reentry_events

    def get_active_tracks(self) -> List[Track]:
        return [t for t in self.tracks.values() if t.active]

    # ── private ─────────────────────────────────────────────────────────────

    def _check_reentry(self, embedding: np.ndarray, now: float) -> Optional[ExitedVisitor]:
        """Return the best matching exited visitor if similarity is above threshold."""
        best_sim, best_ev = -1.0, None
        for ev in self.exited:
            if now - ev.exit_time > REENTRY_WINDOW_SEC:
                continue
            sim = _cosine_sim(embedding, ev.embedding)
            if sim > best_sim:
                best_sim, best_ev = sim, ev
        if best_sim >= REENTRY_SIM_THRESH:
            # Remove from exited pool so it's not matched again immediately
            self.exited = [e for e in self.exited if e.visitor_id != best_ev.visitor_id]
            return best_ev
        return None