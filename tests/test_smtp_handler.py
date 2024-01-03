import logging
import os
import textwrap
import time

import pytest

from config_utils.logging.adapters import MessageTypeAdapter
from config_utils.logging.handlers import BufferingSMTPHandler


@pytest.fixture
def template():
    return textwrap.dedent(
        """
        <!DOCTYPE html>
        <html>
          <body>
            Message: %(message)s
            Timestamp: %(asctime)s
          </body>
        </html>
    """
    )


@pytest.fixture(params=["", "foo", "foo.bar", "foo.bar.baz"])
def logger_name(request):
    return request.param


@pytest.fixture
def logger(logger_name):
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel("DEBUG")
    return logger


@pytest.fixture
def smtp_logger_adapter(logger, smtp_handler):
    logger.addHandler(smtp_handler)
    adapter = MessageTypeAdapter(logger, email=False)
    yield adapter
    logger.handlers.clear()


@pytest.fixture(params=["testy@irate.net"])
def fromAddr(request):
    return request.param


@pytest.fixture(
    params=[
        ["one@first.com", "two@second.com"],
    ]
)
def toAddrs(request):
    return request.param


@pytest.fixture(
    params=[
        ["one@first.com", "two@second.com"],
    ]
)
def ccAddrs(request):
    return request.param


@pytest.fixture(
    params=[
        ["one@first.com"],
    ]
)
def bccAddrs(request):
    return request.param


@pytest.fixture(params=["Test"])
def subject(request):
    return request.param


@pytest.fixture
def datefmt():
    return "%Y-%m-%d %H:%M:%S"


@pytest.fixture
def smtp_handler(
    template, smtpd, datefmt, toAddrs, fromAddr, ccAddrs, bccAddrs, subject
):
    return BufferingSMTPHandler(
        1,
        template,
        "html",
        smtpd.hostname,
        smtpd.port,
        datefmt=datefmt,
        toAddrs=toAddrs,
        fromAddr=fromAddr,
        ccAddrs=ccAddrs,
        bccAddrs=bccAddrs,
        subject=subject,
    )


@pytest.fixture(
    params=[
        ("This is a %s", "log message"),
        ("The first rule of %s is %r", "Fight Club", "don't talk about Fight Club"),
    ]
)
def log_record(logger_name, datefmt, request):
    record = logging.makeLogRecord(
        {
            "name": logger_name,
            "msg": request.param[0],
            "args": request.param[1:],
            "levelname": "DEBUG",
            "levelno": logging.DEBUG,
            "pathname": __file__,
            "module": "TEST",
            "filename": os.path.basename(__file__),
            "exc_info": None,
            "exc_text": None,
            "stack_info": None,
            "lineno": 333,
            "funcname": "",
            "created": time.time(),
            "thread": None,
            "threadName": None,
            "processName": None,
        }
    )
    record.asctime = logging.Formatter(fmt="%(message)s").formatTime(record, datefmt)
    return record


def test_logger_setup(log_record, smtpd, template, smtp_logger_adapter, subject):
    """
    Use the pytest-smtpd fixture to inject a mock SMTP server
    Requires `pip install pytest-smtpd`
    """
    smtp_logger_adapter.info(log_record.msg, *log_record.args, email=True)
    assert len(smtpd.messages) == 1, "No SMTP message was sent"
    message = smtpd.messages[0]
    assert (
        message.get_content_type() == "multipart/mixed"
    ), "SMTP message should have MIME type multipart/mixed"
    body = None
    for part in message.walk():
        ctype = part.get_content_type()
        disp = part.get_content_disposition()
        if disp is not None and "attachment" in disp:
            continue
        elif ctype == "text/html":
            body = part.get_payload(decode=True)
            break
    assert body is not None
    assert body.decode() == (
        template % {**log_record.__dict__, "message": log_record.getMessage()}
    ).replace("\n", "\r\n")


def test_non_smtp_log_messages(smtpd, smtp_logger_adapter):
    smtp_logger_adapter.info("This is an informational log message")
    assert len(smtpd.messages) == 0
