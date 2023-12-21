import logging
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, Optional

from ..file_utils import resolve_path

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


class FormatterConfig:
    format: str
    datefmt: Optional[str]


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
        body_template: str = "%(message)s",
        datefmt: Optional[str] = None,
        style: Optional[str] = "%",
        mime_type: str = "text",
        defaultFromAddr: str = "",
        defaultToAddrs: Iterable[str] = (),
        defaultSubject: str = "",
        defaultCCAddrs: Iterable[str] = (),
        defaultAttachment: Optional[str] = None,
    ) -> None:
        super().__init__(body_template, datefmt, style)
        self.mime_type = mime_type
        self.defaults = {
            "subject": defaultSubject,
            "fromAddr": defaultFromAddr,
            "toAddrs": defaultToAddrs,
            "ccAddrs": defaultCCAddrs,
            "attachment": defaultAttachment,
        }

    def format(self, record: logging.LogRecord) -> str:
        msg = MIMEMultipart()
        msg_data = getattr(record, "email", {})
        msg["From"] = msg_data.get("fromAddr", self.defaults["fromAddr"])
        msg["Subject"] = msg_data.get("subject", self.defaults["subject"])

        # Don't include BCC addresses in the message (that's the whole point)
        msg["To"] = ", ".join(msg_data.get("toAddrs", self.defaults["toAddrs"]))
        msg["Cc"] = ", ".join(msg_data.get("ccAddrs", self.defaults["ccAddrs"]))

        attachment = msg_data.get("attachment", self.defaults["attachment"])
        if attachment is not None:
            file = resolve_path(attachment)
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(file.read_bytes())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition", f"attachment; filename = {file}"
            )
            msg.attach(attachment)
        msg.attach(MIMEText(super().format(record), self.mime_type))
        return msg.as_string()
