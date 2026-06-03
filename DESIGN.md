# System Design Decisions

## Overview

The goal of this project was to build an end-to-end AI-powered Store Intelligence System capable of processing CCTV footage and generating actionable retail analytics.

The system was designed with simplicity, modularity, and production-readiness in mind.

---

# High-Level Architecture

CCTV Videos
↓
YOLOv8 Detection
↓
Tracking Pipeline
↓
Event Generation
↓
JSONL Event Stream
↓
FastAPI Analytics APIs

---

# Key Design Decisions

## 1. YOLOv8 for Person Detection

YOLOv8 was selected because:

- Fast inference speed
- Easy integration
- Strong real-time performance
- Good balance between accuracy and simplicity

The system currently focuses on person detection for visitor analytics.

---

# 2. Modular Pipeline Architecture

The project was separated into independent modules:

- detect.py
- tracker.py
- emit.py
- FastAPI backend

This improves:
- maintainability
- debugging
- scalability

Each component can evolve independently.

---

# 3. Event-Driven Analytics

Instead of directly coupling analytics with video processing, the system emits structured events into JSONL format.

Example events:
- ENTRY
- EXIT
- ZONE_ENTER
- BILLING_QUEUE_JOIN

Advantages:
- decoupled architecture
- replayable analytics
- easier debugging
- future streaming compatibility

---

# 4. FastAPI for Analytics APIs

FastAPI was chosen because:

- lightweight
- fast development
- automatic Swagger documentation
- async-ready architecture

The APIs expose:
- metrics
- funnel analysis
- heatmaps
- anomaly detection

---

# 5. Simplified Tracking Strategy

The current implementation uses lightweight per-camera tracking.

Cross-camera re-identification was intentionally simplified to reduce system complexity and improve reliability during hackathon development.

This tradeoff prioritizes:
- faster implementation
- easier debugging
- stable event generation

---

# Tradeoffs

| Decision | Benefit | Limitation |
|---|---|---|
| YOLOv8 | Fast & simple | No fine-tuning |
| JSONL events | Easy replay/debugging | Not real-time streaming |
| Simple tracking | Lightweight | Weak cross-camera identity |
| FastAPI | Easy APIs | No frontend dashboard |

---

# Production Readiness Considerations

The system includes:
- Dockerized deployment
- Modular architecture
- Structured event schema
- API-based analytics
- Health endpoints

These choices improve deployability and maintainability.

---

# Future Improvements

## Real-Time Streaming
- Kafka-based event streaming
- Live event consumers

## Better Tracking
- Cross-camera re-identification
- DeepSORT / ByteTrack integration

## Dashboard
- Streamlit or React dashboard
- Real-time monitoring

## Advanced Analytics
- Dwell time analysis
- Queue prediction
- Conversion analysis
- Staff analytics

## Performance
- GPU optimization
- Batch inference
- Frame skipping optimization

---

# Conclusion

This project demonstrates how computer vision, event-driven architecture, and analytics APIs can be combined to build a scalable retail intelligence platform from raw CCTV footage.