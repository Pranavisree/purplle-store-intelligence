# System Design Decisions

## Overview

The goal of this project was to build an AI-powered Store Intelligence System capable of converting raw CCTV footage into structured retail analytics.

The system combines:
- computer vision
- event-driven architecture
- analytics APIs
- anomaly detection
- Dockerized deployment

while remaining lightweight enough to run on CPU-only systems.

The implementation prioritizes:
- modularity
- explainability
- deployment simplicity
- reproducibility

over enterprise-scale infrastructure complexity.

---

# High-Level Architecture

CCTV Videos
↓
YOLOv8 Detection
↓
Tracking Pipeline
↓
Zone Classification
↓
Event Generation
↓
JSONL Event Stream
↓
FastAPI Analytics APIs

---

# Pipeline Architecture

## 1. Detection Layer

The detection layer processes CCTV frames using YOLOv8 person detection.

Responsibilities:
- detect retail visitors
- filter non-person objects
- generate bounding boxes
- provide confidence scores

The output of this stage becomes the input for tracking and zone analytics.

---

# 2. Tracking Layer

The tracking layer assigns temporary visitor identities across sequential frames.

Responsibilities:
- maintain visitor continuity
- reduce duplicate detections
- generate visitor-level analytics

The implementation uses lightweight centroid-style tracking to prioritize:
- CPU compatibility
- low operational complexity
- deterministic debugging behavior

Cross-camera re-identification was intentionally simplified for the prototype.

---

# 3. Zone Classification Layer

Store zones are defined using deterministic polygon boundaries from the provided store layout configuration.

Responsibilities:
- classify visitor movement across store sections
- detect zone entry events
- support heatmap generation
- support funnel analytics

Zone assignment uses geometric bounding-box overlap calculations instead of AI-based scene understanding models.

---

# 4. Event Generation Layer

The system emits structured retail events into JSONL format.

Generated events include:
- ENTRY
- EXIT
- ZONE_ENTER
- BILLING_QUEUE_JOIN

The event-driven architecture decouples:
- video processing
- analytics APIs
- downstream reporting

This improves:
- modularity
- replayability
- debugging
- future scalability

---

# 5. Analytics API Layer

FastAPI exposes analytics endpoints over generated events.

Implemented endpoints:
- /health
- /events/ingest
- /stores/{store_id}/metrics
- /stores/{store_id}/funnel
- /stores/{store_id}/heatmap
- /stores/{store_id}/anomalies

The API layer provides:
- store metrics
- conversion analytics
- zone heatmaps
- anomaly detection
- ingestion validation

---

# Production Readiness Considerations

The project includes several production-oriented design choices:

## Dockerized Deployment
The system can run using:
docker compose up

This reduces setup friction and improves reproducibility across environments.

## Structured Event Schema
The JSONL schema provides:
- replayability
- schema validation
- deterministic analytics
- future streaming compatibility

## Health Monitoring
The API exposes health endpoints to validate:
- ingestion state
- event counts
- pipeline availability

## Automated Tests
Basic API tests were added using pytest to validate endpoint availability and API correctness.

---

# AI-Assisted Engineering Decisions

AI tools including Claude and ChatGPT were used during development as engineering assistants rather than autonomous code generators.

The tools were primarily used for:
- comparing architectural alternatives
- evaluating tracking approaches
- reviewing deployment strategies
- refining API structure
- validating tradeoffs

---

## 1. Tracking Approach

Claude suggested ByteTrack because of stronger identity consistency under occlusion.

I selected lightweight centroid tracking instead because:
- it is easier to debug
- it performs reliably on CPU-only systems
- it introduces fewer dependencies
- it is simpler to explain during evaluation

The decision prioritized deployment reliability and explainability over advanced re-identification accuracy.

---

## 2. Zone Classification

Claude suggested using a Vision Language Model (VLM) to infer retail zones from visual context.

I rejected this approach and implemented deterministic geometric zone classification instead.

The store cameras use mostly fixed viewpoints, making polygon intersection significantly more efficient and reliable.

Using geometry instead of a VLM:
- reduces latency dramatically
- avoids unnecessary inference overhead
- improves deterministic behavior
- simplifies debugging

This was a deliberate override of the AI recommendation.

---

## 3. API Architecture

ChatGPT suggested a more complex event-sourcing architecture with separate read models and persistent storage.

I adopted the core event-driven principle but simplified the implementation:
- JSONL acts as the append-only event stream
- the API uses lightweight in-memory analytics structures

This reduced infrastructure complexity while preserving replayability and modularity.

---

# Future Improvements

Potential future extensions include:

## Better Tracking
- ByteTrack integration
- DeepSORT integration
- cross-camera re-identification

## Real-Time Streaming
- Kafka-based ingestion
- streaming analytics consumers
- live event dashboards

## Analytics Expansion
- dwell-time analytics
- conversion attribution
- queue prediction
- staff movement analytics

## Performance Optimization
- GPU acceleration
- frame skipping
- batched inference
- asynchronous ingestion

---

# Conclusion

This project demonstrates how computer vision, event-driven architecture, and lightweight analytics APIs can be combined to build a scalable retail intelligence platform from raw CCTV footage.

The implementation intentionally prioritizes:
- explainability
- deployment simplicity
- reproducibility
- modular architecture

while remaining extensible for future production-scale improvements.