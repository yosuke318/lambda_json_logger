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


class DummyContext:
    """Stands in for the AWS Lambda context object."""

    def __init__(self, aws_request_id):
        self.aws_request_id = aws_request_id


def _capture(level=logging.DEBUG, context=None, stage=None):
    """Return (logger, buffer) with the handler's output redirected to buffer.

    getLambdaJsonLoggerInstance only builds its handler when the logger has
    none, so the handlers are cleared first to pick up the given context/stage.
    """
    logging.getLogger("lambda_json_logger").handlers.clear()
    logger = getLambdaJsonLoggerInstance(level=level, context=context, stage=stage)
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


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_"):
            case()
            print(f"ok - {name}")
