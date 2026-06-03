# AI-Powered Store Intelligence System

An end-to-end retail analytics pipeline built for Purplle Tech Challenge 2026.

## Overview
This system processes CCTV footage from retail stores and generates real-time business intelligence using computer vision, event generation, and analytics APIs.

The pipeline performs:

- Person detection using YOLOv8
- Multi-object tracking
- Zone-based event generation
- Retail analytics APIs
- Funnel analysis
- Heatmap generation
- Basic anomaly detection

---
# Demo

Swagger API Docs:
http://127.0.0.1:8000/docs

# Architecture

CCTV Videos
↓
YOLOv8 Detection
↓
Tracking Pipeline
↓
Event Generation
↓
events_out.jsonl
↓
FastAPI Analytics APIs

---

# Features

## Detection Pipeline
- Person detection using YOLOv8
- Multi-object tracking
- Entry/Exit detection
- Zone detection
- Billing queue detection

## Analytics APIs
- /metrics
- /funnel
- /heatmap
- /anomalies
- /health

## Anomaly Detection
- Queue spike detection
- Low traffic zone detection

---

# Tech Stack

- Python
- YOLOv8
- OpenCV
- FastAPI
- JSONL Event Streaming

---

# Project Structure

```text
store-intelligence/
│
├── pipeline/
├── app/
├── data/
├── output/
└── README.md
```

---

# Setup Instructions

## Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run detection pipeline

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

## Run API server

```bash
uvicorn app.main:app --reload
```

---

# API Endpoints

| Endpoint | Description |
|---|---|
| /metrics | Store metrics |
| /funnel | Visitor funnel |
| /heatmap | Zone popularity |
| /anomalies | Retail anomaly detection |
| /events | Raw events |
| /health | Health check |

---

# Future Improvements

- Cross-camera re-identification
- Real-time Kafka streaming
- Streamlit dashboard
- Better anomaly detection
- GPU optimization

---

# Author

Palleboina Pranavi Sree
