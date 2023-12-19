import logging

from . import LogLevel


class ReverseLogFilter(logging.Filter):
    """Filter out all records with loglevel greater than a specified base."""

    def __init__(self, level: LogLevel = logging.NOTSET) -> None:
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.level


class AttributeFilter(logging.Filter):
    """Check if LogRecord has a given attribute.

    The intended use-case is to check for attributes included in the record
    via the logging methods' "extra" parameter.  For example, a custom SMTP
    handler could filter for LogRecords containing an "email" attribute
    pointing to a dict containing email data (sender, recipient, subject,
    etc.).

    If a record contains the target attribute, and if its value is a Mapping,
    then the filter will modify the record's __dict__ in-place with the
    key-value pairs in the target attribute.  This is done in order to allow
    formatter template strings to reference keys contained in the target dict.
    """

    def __init__(self, attr_name: str) -> None:
        """
        Args:
            message_type: name of target message type
        """
        self.attr_name = attr_name

    def filter(self, record: logging.LogRecord) -> bool:
        msg_data = getattr(record, self.attr_name, None)
        if msg_data is not None:
            # add dict keys to record instance so they can be referenced in templates
            # TODO: think of a better way to do this
            if isinstance(msg_data, dict):
                for k, v in msg_data.items():
                    setattr(record, k, v)
            return True
        return False
