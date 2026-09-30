# Cost and Resource Baseline

## Baseline

Current development baseline:
- Python: 3.12.10
- PostgreSQL: 18.3
- Redis: Docker-managed
- Application: Flask + Flask-SocketIO
- Background workers: Celery

## Production Measurement

Record:
- CPU and memory utilization
- PostgreSQL and Redis resource usage
- Celery worker count and concurrency
- Queue depth
- Storage usage
- Monthly infrastructure cost

Review after load testing and production-like validation.
