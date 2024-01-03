import logging
from typing import Iterable, Optional

from .email import Email

LOGFILE_COLUMNS = (
    ("LEVEL", "%(levelname)s"),
    ("DATETIME", "%(asctime)s"),
    ("LOGGER", "%(name)s"),
    ("MESSAGE", "%(message)s"),
    ("MODULE", "%(module)s"),
    ("FILENAME", "%(filename)s"),
    ("FUNCTION", "%(funcname)s"),
    ("LINENO", "%(lineno)s"),
    ("THREAD", "%(threadName)s:%(thread)d"),
    ("PID", "%(process)d"),
)
CONSOLE = "%(name)-12s: %(levelname)-8s %(message)s"
TSV = "\t".join([s for _, s in LOGFILE_COLUMNS])


class EmailFormatter(logging.Formatter):
    """Format LogRecords as emails using data stored in "extra" record attrs.

    The formatter expects LogRecords to have an attribute "email"
    containing a Mapping of email-related data, in the following form:
        record.email = {
            "mime_type": str,
            "fromAddr": str,
            "toAddrs": List[str],
            "subject": str,
            "ccAddrs": List[str],
            "attachment": str,
            # more optional key-value pairs
        }
    The contructor takes optional default values for each key; individual
    records missing one or more keys will fall back to these defaults when
    formatted.

    This class is designed to be used with the BufferingSMTPHandler, which
    will automatically add an instance of EmailFormatter on construction.
    This class should therefore likely not be constructed directly.
    """

    def __init__(
        self,
        body: str = "%(message)s",
        datefmt: Optional[str] = None,
        style: Optional[str] = "%",
        mime_type: str = "text",
        fromAddr: str = "",
        toAddrs: Iterable[str] = (),
        subject: str = "",
        ccAddrs: Iterable[str] = (),
    ) -> None:
        self._email_fmt = {
            "subject": subject,
            "body": body,
            "mime_type": mime_type,
            "fromAddr": fromAddr,
            "toAddrs": toAddrs,
            "ccAddrs": ccAddrs,
        }
        super().__init__(str(Email(**self._email_fmt)), datefmt, style)

    def get_attachment(self, record: logging.LogRecord) -> Optional[str]:
        if hasattr(record, "attachment"):
            return getattr(record, "attachment")
        elif hasattr(record, "email"):
            email_cfg = getattr(record, "email")
            if isinstance(email_cfg, dict):
                return email_cfg.get("attachment", None)
