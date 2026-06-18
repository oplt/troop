from backend.workers.celery_app import celery_app
from backend.workers.email import send_email_sync
from backend.workers.retry import CELERY_TRANSIENT_EXCEPTIONS


@celery_app.task(
    name="backend.workers.tasks.send_email_task",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> None:
    send_email_sync(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )
