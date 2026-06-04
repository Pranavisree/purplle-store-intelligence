# PROMPT:
# "Write pytest tests for a FastAPI analytics API that ingests retail
# store events (ENTRY, EXIT, ZONE_ENTER, BILLING_QUEUE_JOIN). Include edge cases:
# empty store, duplicate event_id idempotency, staff exclusion from metrics,
# zero-purchase conversion rate, and the /stores/{id}/metrics URL pattern."

# CHANGES MADE:
# - Added store_id path param to match actual route structure
# - Added is_staff=True fixture to verify staff exclusion
# - Added heatmap and anomaly tests
# - Added funnel dropoff assertions
# - Modified assertions to match actual API response structure

import pytest
from fastapi.testclient import TestClient
from app.main import app, event_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_store():
    event_store.clear()
    yield
    event_store.clear()


def make_event(
    event_id,
    visitor_id,
    event_type,
    is_staff=False,
    zone_id=None
):
    return {
        "event_id": event_id,
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": "2026-03-03T14:22:10Z",
        "zone_id": zone_id,
        "dwell_ms": 0,
        "is_staff": is_staff,
        "confidence": 0.9,
        "metadata": {}
    }


def test_health():
    r = client.get("/health")

    assert r.status_code == 200
    assert "status" in r.json()


def test_ingest_basic():
    r = client.post(
        "/events/ingest",
        json={
            "events": [
                make_event(
                    "evt-001",
                    "VIS_001",
                    "ENTRY"
                )
            ]
        }
    )

    assert r.status_code == 200
    assert r.json()["ingested"] == 1


def test_ingest_idempotent():
    event = make_event(
        "evt-dup",
        "VIS_001",
        "ENTRY"
    )

    client.post(
        "/events/ingest",
        json={"events": [event]}
    )

    r = client.post(
        "/events/ingest",
        json={"events": [event]}
    )

    assert r.json()["duplicates"] == 1
    assert r.json()["ingested"] == 0


def test_metrics_empty_store():
    r = client.get(
        "/stores/STORE_BLR_002/metrics"
    )

    assert r.status_code == 200
    assert r.json()["unique_visitors"] == 0


def test_metrics_excludes_staff():
    client.post(
        "/events/ingest",
        json={
            "events": [
                make_event(
                    "e1",
                    "VIS_001",
                    "ENTRY",
                    is_staff=False
                ),
                make_event(
                    "e2",
                    "STAFF_001",
                    "ENTRY",
                    is_staff=True
                ),
            ]
        }
    )

    r = client.get(
        "/stores/STORE_BLR_002/metrics"
    )

    assert r.json()["unique_visitors"] == 1


def test_conversion_rate_zero_purchases():
    client.post(
        "/events/ingest",
        json={
            "events": [
                make_event(
                    "e1",
                    "VIS_001",
                    "ENTRY"
                ),
                make_event(
                    "e2",
                    "VIS_002",
                    "ENTRY"
                ),
            ]
        }
    )

    r = client.get(
        "/stores/STORE_BLR_002/metrics"
    )

    assert r.json()["conversion_rate"] == 0.0


def test_funnel_dropoff():
    client.post(
        "/events/ingest",
        json={
            "events": [
                make_event(
                    "e1",
                    "VIS_001",
                    "ENTRY"
                ),
                make_event(
                    "e2",
                    "VIS_001",
                    "ZONE_ENTER",
                    zone_id="SKINCARE"
                ),
                make_event(
                    "e3",
                    "VIS_002",
                    "ENTRY"
                ),
            ]
        }
    )

    r = client.get(
        "/stores/STORE_BLR_002/funnel"
    )

    data = r.json()

    assert data["entry"] == 2
    assert data["zone_visit"] == 1
    assert data["billing_queue"] == 0
    assert data["entry_to_zone_dropoff"] == 0.5


def test_heatmap():
    client.post(
        "/events/ingest",
        json={
            "events": [
                make_event(
                    "e1",
                    "VIS_001",
                    "ZONE_ENTER",
                    zone_id="SKINCARE"
                ),
                make_event(
                    "e2",
                    "VIS_002",
                    "ZONE_ENTER",
                    zone_id="SKINCARE"
                ),
            ]
        }
    )

    r = client.get(
        "/stores/STORE_BLR_002/heatmap"
    )

    assert r.status_code == 200
    assert "zones" in r.json()


def test_anomalies():
    events = []

    for i in range(11):
        events.append(
            make_event(
                f"bill-{i}",
                f"VIS_{i}",
                "BILLING_QUEUE_JOIN"
            )
        )

    client.post(
        "/events/ingest",
        json={"events": events}
    )

    r = client.get(
        "/stores/STORE_BLR_002/anomalies"
    )

    assert r.status_code == 200
    assert len(r.json()["anomalies"]) > 0