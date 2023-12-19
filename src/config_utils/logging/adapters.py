import logging
from typing import Dict, List, Tuple


class MessageTypeAdapter(logging.LoggerAdapter):
    """Treat unexpected kwargs in logging methods like "extra" args.

    Logging methods accept a keyword argument "extra" whose value should be a
    dict containing extra contextual information to be added to the LogRecord.
    This adapter stores a list of extra keys to expect and automatically adds
    them to the LogRecord as attributes without having to include them in an
    "extra" dict.  The advantage of this is that custom handlers can then
    format messages which reference these custom keys.

    For example:
    >>> app_logger = MessageTypeLoggingAdapter(logging.getLogger(), "email")
    >>> app_logger.info("This message will be logged normally")
    >>> app_logger.info(
    ...     "This message will produce a LogRecord with attribute 'email' = 'foo'",
    ...     email="foo"
    ... )
    """

    def __init__(
        self, logger: logging.Logger, *keys: List[str], **kwargs: Dict
    ) -> None:
        """
        Args:
            logger: logger instance to wrap
            *keys: list of strings to treat as "extra" args in logging methods
            **kwargs: dict of any extra contextual information to include with
                LogRecords processed by this adapter
        """
        self.message_type_keys = keys
        super().__init__(logger, kwargs)

    def process(self, msg: str, kwargs: Dict) -> Tuple[str, Dict]:
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        for k in self.message_type_keys:
            kwargs["extra"][k] = kwargs.pop(k, None)
        return msg, kwargs
