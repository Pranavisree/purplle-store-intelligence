from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid, json
from datetime import datetime

app = FastAPI()

# In-memory store — replace with SQLite for production
event_store = {}  # event_id -> event dict

class EventIn(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: str
    zone_id: Optional[str] = None
    dwell_ms: Optional[int] = 0
    is_staff: bool = False
    confidence: float
    metadata: Optional[dict] = {}

class IngestRequest(BaseModel):
    events: List[EventIn]

@app.post("/events/ingest")
def ingest_events(payload: IngestRequest):
    ingested = 0
    duplicates = 0
    errors = []
    
    for event in payload.events:
        if event.event_id in event_store:
            duplicates += 1
            continue
        event_store[event.event_id] = event.dict()
        ingested += 1
    
    return {
        "ingested": ingested,
        "duplicates": duplicates,
        "errors": errors
    }

@app.get("/stores/{store_id}/metrics")
def metrics(store_id: str):
    events = [e for e in event_store.values() 
              if e["store_id"] == store_id and not e["is_staff"]]
    
    visitors = set(e["visitor_id"] for e in events)
    entries = [e for e in events if e["event_type"] == "ENTRY"]
    billing = set(e["visitor_id"] for e in events 
                  if e["event_type"] == "BILLING_QUEUE_JOIN")
    
    conversion = len(billing) / len(visitors) if visitors else 0
    
    return {
        "store_id": store_id,
        "unique_visitors": len(visitors),
        "conversion_rate": round(conversion, 3),
        "entry_count": len(entries),
        "billing_queue_depth": sum(
            e.get("metadata", {}).get("queue_depth", 0) or 0 
            for e in events if e["event_type"] == "BILLING_QUEUE_JOIN"
        )
    }

@app.get("/stores/{store_id}/funnel")
def funnel(store_id: str):
    events = [e for e in event_store.values()
              if e["store_id"] == store_id and not e["is_staff"]]
    
    sessions = {}
    for e in events:
        vid = e["visitor_id"]
        if vid not in sessions:
            sessions[vid] = {"entry": False, "zone": False, "billing": False}
        if e["event_type"] == "ENTRY": sessions[vid]["entry"] = True
        if e["event_type"] == "ZONE_ENTER": sessions[vid]["zone"] = True
        if e["event_type"] == "BILLING_QUEUE_JOIN": sessions[vid]["billing"] = True
    
    total = len(sessions)
    entered = sum(1 for s in sessions.values() if s["entry"])
    zoned = sum(1 for s in sessions.values() if s["zone"])
    billed = sum(1 for s in sessions.values() if s["billing"])
    
    return {
        "store_id": store_id,
        "entry": entered,
        "zone_visit": zoned,
        "billing_queue": billed,
        "entry_to_zone_dropoff": round(1 - zoned/entered, 3) if entered else 0,
        "zone_to_billing_dropoff": round(1 - billed/zoned, 3) if zoned else 0,
    }

@app.get("/stores/{store_id}/heatmap")
def heatmap(store_id: str):
    events = [e for e in event_store.values()
              if e["store_id"] == store_id 
              and e["event_type"] == "ZONE_ENTER"
              and not e["is_staff"]]
    
    zone_counts = {}
    for e in events:
        z = e.get("zone_id", "UNKNOWN")
        zone_counts[z] = zone_counts.get(z, 0) + 1
    
    max_count = max(zone_counts.values(), default=1)
    normalized = {z: round(c/max_count * 100) for z, c in zone_counts.items()}
    total_sessions = len(set(e["visitor_id"] for e in event_store.values()
                             if e["store_id"] == store_id))
    
    return {
        "store_id": store_id,
        "zones": normalized,
        "data_confidence": "LOW" if total_sessions < 20 else "OK"
    }

@app.get("/stores/{store_id}/anomalies")
def anomalies(store_id: str):
    events = [e for e in event_store.values() if e["store_id"] == store_id]
    found = []
    
    billing_events = [e for e in events if e["event_type"] == "BILLING_QUEUE_JOIN"]
    if len(billing_events) > 10:
        found.append({
            "type": "BILLING_QUEUE_SPIKE",
            "severity": "WARN",
            "suggested_action": "Deploy additional staff to billing counter"
        })
    
    return {"store_id": store_id, "anomalies": found}

@app.get("/health")
def health():
    last_ts = None
    if event_store:
        last_ts = max(e["timestamp"] for e in event_store.values())
    return {
        "status": "healthy",
        "total_events": len(event_store),
        "last_event_timestamp": last_ts
    }