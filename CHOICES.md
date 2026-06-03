# Key Engineering Choices

## Why YOLOv8
I chose YOLOv8 because it provides fast real-time inference and good accuracy for person detection in retail environments.

## Why Event-Driven Architecture
The pipeline generates events independently from analytics APIs, making the system modular and scalable.

## Why Simple Tracking Instead of DeepSORT
I considered DeepSORT and ByteTrack. However, I selected lightweight centroid tracking because it is simpler to explain, easier to run on CPU-only systems, and sufficient for the hackathon prototype.

## Why FastAPI
FastAPI provides fast API development with automatic Swagger documentation and async support.

## AI-Assisted Decisions
I used Claude and ChatGPT to compare tracking approaches, improve Docker deployment, and structure analytics APIs. I reviewed and modified suggestions before implementation.