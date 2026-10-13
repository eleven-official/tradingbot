"""
Loki Trading Platform - Celery Worker Configuration
Distributed task queue for asynchronous processing
"""
from celery import Celery
from celery.schedules import crontab
import os

# Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
app = Celery(
    'loki',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['loki.tasks.trading_tasks', 'loki.tasks.analytics_tasks']
)

# Configuration
app.conf.update(
    result_expires=3600,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Periodic tasks schedule
app.conf.beat_schedule = {
    'update-portfolio-snapshots': {
        'task': 'loki.tasks.trading_tasks.update_all_portfolio_snapshots',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    'calculate-strategy-performance': {
        'task': 'loki.tasks.analytics_tasks.calculate_strategy_metrics',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    'cleanup-old-data': {
        'task': 'loki.tasks.maintenance_tasks.cleanup_old_data',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'generate-daily-reports': {
        'task': 'loki.tasks.reporting_tasks.generate_daily_report',
        'schedule': crontab(hour=18, minute=0),  # Daily at 6 PM
    },
}

if __name__ == '__main__':
    app.start()
