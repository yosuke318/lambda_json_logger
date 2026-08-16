from logging import getLogger, StreamHandler, DEBUG, CRITICAL, ERROR, WARNING, INFO
import logging ,json

LOG_LEVELS = {
    "CRITICAL" : CRITICAL,
    "ERROR"    : ERROR,
    "WARNING"  : WARNING,
    "INFO"     : INFO,
    "DEBUG"    : DEBUG,
}

LOGGER_NAME = "lambda_json_logger"


class LambdaJsonFormatter(logging.Formatter):
    """Renders each record as one JSON line so Logs Insights can query the fields.

    The per-invocation values live on the instance rather than in a closure, so
    they can be refreshed when the same warm container handles a new request.
    """

    def __init__(self, context=None, stage=None, event=None):
        super().__init__()
        self.context = context
        self.stage = stage
        self.event = event

    def format(self, record):
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "function_name": record.funcName,
            "module": record.module,
            "aws_request_id": getattr(self.context, "aws_request_id", None),
            "stage": self.stage,
        }

        # Only carry the event when the caller asked for it -- it is repeated on
        # every line, so it should not appear unless it was passed in.
        if self.event is not None:
            payload["event"] = self.event

        # logger.exception() and exc_info=True land here. Without this the
        # traceback is dropped and only the message survives.
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str keeps an unserializable event from killing the log call.
        return json.dumps(payload, ensure_ascii=False, default=str)


def getLambdaJsonLoggerInstance(level=DEBUG, context=None, stage=None, event=None):
    # Getting logger instance
    logger = getLogger(LOGGER_NAME)
    logger.setLevel(level)

    # Lambda's runtime already prints anything reaching the root logger, so
    # propagating would emit every record twice.
    logger.propagate = False

    if not logger.handlers:
        logger.addHandler(StreamHandler())

    # The logger is shared across invocations in a warm container. Re-set the
    # formatter every call so the request id, stage and event belong to the
    # invocation being handled now, not to the one that built the handler.
    formatter = LambdaJsonFormatter(context=context, stage=stage, event=event)
    for handler in logger.handlers:
        handler.setFormatter(formatter)

    return logger
