import logging
from datetime import datetime
from pathlib import Path

from backend.core.config import settings

_REPO_DIR = Path(__file__).resolve().parents[2]
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


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


def _add_common_filter(handler: logging.Handler) -> None:
    if not any(
        isinstance(existing, _IgnoreSqlalchemyPoolCancelledTerminate)
        for existing in handler.filters
    ):
        handler.addFilter(_IgnoreSqlalchemyPoolCancelledTerminate())


def _add_daily_file_handler(root_logger: logging.Logger) -> None:
    log_dir = _REPO_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now().date().isoformat()}.log"
    resolved_log_path = log_path.resolve()

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler_path = Path(handler.baseFilename).resolve()
            if handler_path == resolved_log_path:
                _add_common_filter(handler)
                return

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(settings.LOG_LEVEL.upper())
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _add_common_filter(file_handler)
    root_logger.addHandler(file_handler)


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
            _add_common_filter(handler)
        root_logger.setLevel(settings.LOG_LEVEL.upper())
        _add_daily_file_handler(root_logger)
        return

    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format=_LOG_FORMAT,
    )
    for handler in root_logger.handlers:
        _add_common_filter(handler)
    _add_daily_file_handler(root_logger)
