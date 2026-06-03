from fastapi import FastAPI
import json

app = FastAPI()

EVENTS_FILE = "output/events_out.jsonl"


def load_events():
    events = []

    try:
        with open(EVENTS_FILE, "r") as f:
            for line in f:
                events.append(json.loads(line))
    except FileNotFoundError:
        return []

    return events


@app.get("/")
def home():
    return {"message": "Store Intelligence API Running"}


@app.get("/health")
def health():
    events = load_events()

    return {
        "status": "healthy",
        "total_events": len(events)
    }


@app.get("/events")
def get_events():
    return load_events()


@app.get("/metrics")
def metrics():
    events = load_events()

    unique_visitors = set()
    entry_count = 0
    exit_count = 0

    for e in events:
        visitor_id = e.get("visitor_id")

        if visitor_id:
            unique_visitors.add(visitor_id)

        if e.get("event_type") == "ENTRY":
            entry_count += 1

        if e.get("event_type") == "EXIT":
            exit_count += 1

    return {
        "unique_visitors": len(unique_visitors),
        "entry_events": entry_count,
        "exit_events": exit_count,
        "total_events": len(events)
    }
    
@app.get("/funnel")
def funnel():

    events = load_events()

    visitors = {}

    for e in events:

        vid = e.get("visitor_id")

        if not vid:
            continue

        if vid not in visitors:
            visitors[vid] = {
                "entry": False,
                "zone": False,
                "billing": False
            }

        if e.get("event_type") == "ENTRY":
            visitors[vid]["entry"] = True

        if e.get("event_type") == "ZONE_ENTER":
            visitors[vid]["zone"] = True

        if e.get("event_type") == "BILLING_QUEUE_JOIN":
            visitors[vid]["billing"] = True

    total_entry = sum(v["entry"] for v in visitors.values())
    total_zone = sum(v["zone"] for v in visitors.values())
    total_billing = sum(v["billing"] for v in visitors.values())

    return {
        "entry_stage": total_entry,
        "zone_stage": total_zone,
        "billing_stage": total_billing
    }
    
@app.get("/heatmap")
def heatmap():

    events = load_events()

    zone_counts = {}

    for e in events:

        if e.get("event_type") == "ZONE_ENTER":

            zone = e.get("zone_id", "UNKNOWN")

            if zone not in zone_counts:
                zone_counts[zone] = 0

            zone_counts[zone] += 1

    return {
        "zone_heatmap": zone_counts
    }
    
@app.get("/anomalies")
def anomalies():

    events = load_events()

    zone_counts = {}

    for e in events:

        if e.get("event_type") == "ZONE_ENTER":

            zone = e.get("zone_id", "UNKNOWN")

            zone_counts[zone] = zone_counts.get(zone, 0) + 1

    anomalies_found = []

    # Queue spike detection
    if zone_counts.get("ZONE_BILLING", 0) > 25:

        anomalies_found.append({
            "type": "QUEUE_SPIKE",
            "zone": "ZONE_BILLING",
            "count": zone_counts["ZONE_BILLING"]
        })

    # Low traffic detection
    if zone_counts.get("ZONE_WALL_LEFT", 0) < 3:

        anomalies_found.append({
            "type": "LOW_TRAFFIC",
            "zone": "ZONE_WALL_LEFT",
            "count": zone_counts.get("ZONE_WALL_LEFT", 0)
        })

    return {
        "anomalies": anomalies_found
    }
    
    
@app.post("/events/ingest")
def ingest_events():

    events = []

    with open(EVENTS_FILE, "r") as f:
        for line in f:
            events.append(json.loads(line))

    return {
        "status": "success",
        "events_ingested": len(events)
    }