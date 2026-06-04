# AI-Powered Store Intelligence System

An end-to-end retail analytics pipeline built for the Purplle Tech Challenge 2026 using computer vision, event-driven analytics, and FastAPI.

---

# Overview

This system processes retail CCTV footage and converts raw video streams into structured retail analytics events.

The pipeline performs:

- Person detection using YOLOv8
- Multi-object tracking
- Entry and exit detection
- Zone-based customer movement analysis
- Billing queue monitoring
- Retail analytics generation
- Funnel analytics
- Heatmap analytics
- Basic anomaly detection

The generated analytics are exposed through production-style FastAPI endpoints.

---

# System Architecture

```text
CCTV Video Streams
        ↓
YOLOv8 Person Detection
        ↓
Multi-Object Tracking
        ↓
Zone/Event Generation
        ↓
events_out.jsonl
        ↓
FastAPI Analytics Layer
        ↓
Retail Intelligence APIs
```

---

# Features

## Detection & Tracking Pipeline

- YOLOv8-based person detection
- Multi-object tracking
- Entry/Exit event generation
- Zone transition tracking
- Billing queue monitoring
- JSONL event streaming

---

## Analytics APIs

| Endpoint | Description |
|---|---|
| `/health` | Health check |
| `/events` | Raw event stream |
| `/events/ingest` | Event ingestion API |
| `/stores/{store_id}/metrics` | Store metrics |
| `/stores/{store_id}/funnel` | Visitor funnel analytics |
| `/stores/{store_id}/heatmap` | Zone popularity analytics |
| `/stores/{store_id}/anomalies` | Retail anomaly detection |

---

## Analytics Capabilities

### Store Metrics
- Unique visitors
- Entry count
- Conversion rate
- Billing queue depth

### Funnel Analytics
- Entry → Zone → Billing progression
- Funnel drop-off calculation

### Heatmap Analytics
- Zone popularity analysis
- Customer movement distribution

### Anomaly Detection
- Billing queue spikes
- Low traffic zone detection

---

# Tech Stack

- Python
- FastAPI
- YOLOv8
- OpenCV
- PyTest
- Docker
- JSONL Event Streaming

---

# Project Structure

```text
store-intelligence/
│
├── app/                  # FastAPI application
├── pipeline/             # Detection & tracking pipeline
├── tests/                # API tests
├── data/                 # Sample input data
├── output/               # Generated event logs
├── Dockerfile
├── docker-compose.yml
├── README.md
├── DESIGN.md
└── CHOICES.md
```

---

# Setup Instructions

## 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Run Detection Pipeline

```bash
python pipeline/detect.py \
--store-id STORE_BLR_002 \
--layout pipeline/store_layout.json \
--clips \
"data/videos/Store 2/entry 1.mp4" \
"data/videos/Store 2/zone.mp4" \
"data/videos/Store 2/billing_area.mp4" \
--cameras \
CAM_ENTRY_01 \
CAM_FLOOR_01 \
CAM_BILLING_01 \
--pos "data/POS - sample transactionsb1e826f.csv" \
--output output/events_out.jsonl
```

---

## 4. Run FastAPI Server

```bash
uvicorn app.main:app --reload
```

Swagger API docs:

```text
http://127.0.0.1:8000/docs
```

---

# Docker Setup

Build and run using Docker:

```bash
docker compose up --build
```

---

# Testing

Run API tests using PyTest:

```bash
python -m pytest
```

---

# AI-Assisted Engineering Decisions

This project intentionally evaluated and challenged AI-generated recommendations during development.

Key decisions are documented in:

- `DESIGN.md`
- `CHOICES.md`

These documents explain:
- Model selection tradeoffs
- API architecture choices
- Storage design decisions
- Tracking pipeline decisions
- Production vs prototype tradeoffs

---

# Future Improvements

- Cross-camera re-identification
- Real-time Kafka streaming
- PostgreSQL persistence layer
- Streamlit analytics dashboard
- GPU optimization
- Advanced anomaly detection

---

# Author

Palleboina Pranavi Sree