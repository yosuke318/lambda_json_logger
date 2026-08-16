"""Checks for lambda_json_logger.

Requires lambda_json_logger to be importable. Either install it from the repo
root (`pip install -e .`), or put the repo root on the import path:

    pytest tests/test.py
    PYTHONPATH=. python tests/test.py
"""
import io
import json
import logging

from lambda_json_logger import getLambdaJsonLoggerInstance
from lambda_json_logger.lambda_json_logger import LOGGER_NAME


class DummyContext:
    """Stands in for the AWS Lambda context object."""

    def __init__(self, aws_request_id):
        self.aws_request_id = aws_request_id


def _capture(level=logging.DEBUG, context=None, stage=None, event=None):
    """Return (logger, buffer) with the handler's output redirected to buffer."""
    logger = getLambdaJsonLoggerInstance(
        level=level, context=context, stage=stage, event=event
    )
    buffer = io.StringIO()
    logger.handlers[0].setStream(buffer)
    return logger, buffer


def test_log_record_is_json():
    logger, buffer = _capture(context=DummyContext("1234"), stage="dev")
    logger.info("This is an info message")

    record = json.loads(buffer.getvalue())
    assert record["level"] == "INFO"
    assert record["message"] == "This is an info message"
    assert record["aws_request_id"] == "1234"
    assert record["stage"] == "dev"
    assert record["module"] == "test"
    assert record["function_name"] == "test_log_record_is_json"
    assert record["time"]


def test_context_and_stage_are_optional():
    logger, buffer = _capture()
    logger.debug("no context")

    record = json.loads(buffer.getvalue())
    assert record["aws_request_id"] is None
    assert record["stage"] is None


def test_level_filters_lower_records():
    logger, buffer = _capture(level=logging.WARNING)
    logger.info("dropped")
    logger.warning("kept")

    lines = buffer.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "kept"


def test_warm_start_refreshes_context_and_stage():
    """A reused container must not keep logging the first request's id."""
    logger, first = _capture(context=DummyContext("req-1"), stage="dev")
    logger.info("first invocation")

    logger, second = _capture(context=DummyContext("req-2"), stage="prd")
    logger.info("second invocation")

    assert json.loads(first.getvalue())["aws_request_id"] == "req-1"

    record = json.loads(second.getvalue())
    assert record["aws_request_id"] == "req-2"
    assert record["stage"] == "prd"


def test_handler_is_not_duplicated_across_calls():
    logging.getLogger(LOGGER_NAME).handlers.clear()
    getLambdaJsonLoggerInstance()
    getLambdaJsonLoggerInstance()

    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1


def test_propagate_is_disabled():
    """Propagating would make the Lambda runtime print every record twice."""
    logger, _ = _capture()

    assert logger.propagate is False


def test_event_is_included_when_passed():
    logger, buffer = _capture(event={"path": "/health", "httpMethod": "GET"})
    logger.info("with event")

    record = json.loads(buffer.getvalue())
    assert record["event"] == {"path": "/health", "httpMethod": "GET"}


def test_event_is_absent_when_not_passed():
    logger, buffer = _capture()
    logger.info("no event")

    assert "event" not in json.loads(buffer.getvalue())


def test_unserializable_event_does_not_break_logging():
    logger, buffer = _capture(event={"ctx": object()})
    logger.info("weird event")

    record = json.loads(buffer.getvalue())
    assert record["message"] == "weird event"
    assert record["event"]["ctx"].startswith("<object object at")


def test_exception_traceback_is_captured():
    logger, buffer = _capture()
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed while processing")

    record = json.loads(buffer.getvalue())
    assert record["level"] == "ERROR"
    assert record["message"] == "failed while processing"
    assert "ValueError: boom" in record["exception"]
    assert "Traceback (most recent call last)" in record["exception"]


def test_exception_key_is_absent_without_exc_info():
    logger, buffer = _capture()
    logger.error("plain error")

    assert "exception" not in json.loads(buffer.getvalue())


def test_traceback_stays_on_one_log_line():
    """A multi-line traceback must not break the one-record-per-line contract."""
    logger, buffer = _capture()
    try:
        raise RuntimeError("nested")
    except RuntimeError:
        logger.exception("wrapped")

    assert len(buffer.getvalue().splitlines()) == 1


def test_non_ascii_message_is_not_escaped():
    logger, buffer = _capture()
    logger.info("処理を開始しました")

    assert "処理を開始しました" in buffer.getvalue()
    assert json.loads(buffer.getvalue())["message"] == "処理を開始しました"


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_"):
            case()
            print(f"ok - {name}")
