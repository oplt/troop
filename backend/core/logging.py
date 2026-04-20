import logging

from backend.core.config import settings


class _IgnoreSqlalchemyPoolCancelledTerminate(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("sqlalchemy.pool"):
            return True
        message = record.getMessage()
        if "Exception terminating connection" not in message:
            return True
        if not record.exc_info:
            return True
        exc = record.exc_info[1]
        while exc is not None:
            if isinstance(exc, BaseException) and exc.__class__.__name__ == "CancelledError":
                return False
            exc = exc.__cause__ or exc.__context__
        return True


def setup_logging() -> None:
    pool_logger = logging.getLogger("sqlalchemy.pool")
    root_logger = logging.getLogger()

    if not any(
        isinstance(existing, _IgnoreSqlalchemyPoolCancelledTerminate)
        for existing in pool_logger.filters
    ):
        pool_logger.addFilter(_IgnoreSqlalchemyPoolCancelledTerminate())

    if root_logger.handlers:
        for handler in root_logger.handlers:
            if not any(
                isinstance(existing, _IgnoreSqlalchemyPoolCancelledTerminate)
                for existing in handler.filters
            ):
                handler.addFilter(_IgnoreSqlalchemyPoolCancelledTerminate())
        root_logger.setLevel(settings.LOG_LEVEL.upper())
        return

    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    for handler in root_logger.handlers:
        if not any(
            isinstance(existing, _IgnoreSqlalchemyPoolCancelledTerminate)
            for existing in handler.filters
        ):
            handler.addFilter(_IgnoreSqlalchemyPoolCancelledTerminate())
