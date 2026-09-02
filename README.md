## Celery

Redis must be running at the URL configured by `REDIS_URL`.

Start the worker:

```powershell
celery -A celery_worker.celery worker --loglevel=info
```

Start the scheduler in a second terminal:

```powershell
celery -A celery_worker.celery beat --loglevel=info
```

The worker handles appointment reminders, overdue invoices, and monthly AI usage resets. Beat queues those recurring tasks according to the schedule configured in `app/extensions.py`.
