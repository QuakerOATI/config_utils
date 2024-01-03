from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import cached_property
from typing import Iterable, Optional

from ..file_utils import resolve_path
from .types import PathLike


@dataclass
class Email:
    subject: str
    fromAddr: str
    toAddrs: Iterable[str]
    ccAddrs: Iterable[str] = ()
    mime_type: str = "text"
    attachment: Optional[PathLike] = None
    body: str = ""

    @cached_property
    def email(self):
        email = MIMEMultipart()
        email["To"] = ",".join(self.toAddrs)
        email["From"] = self.fromAddr
        email["CC"] = ",".join(self.ccAddrs)
        email["Subject"] = self.subject
        if self.attachment is not None:
            file = resolve_path(self.attachment)
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(file.read_bytes())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition", f"attachment; filename = {file}"
            )
            email.attach(attachment)
        email.attach(MIMEText(self.body, self.mime_type))
        return email

    def __str__(self):
        return self.email.as_string()
