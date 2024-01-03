import logging
from typing import Any, Dict, Tuple


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

    def __init__(self, logger: logging.Logger, **kwargs: Dict[str, Any]) -> None:
        """
        Args:
            logger: logger instance to wrap
            **kwargs: dict of any extra contextual information to include with
                LogRecords processed by this adapter
        """
        super().__init__(logger, kwargs)

    def _split_kwargs(self, kwargs):
        # make sure to use copies so changes aren't leaked to other logging objects
        extra = self.extra.copy()  # TODO: determine if this is necessary
        for k in extra:
            if k in kwargs:
                extra[k] = kwargs.pop(k)
        return kwargs, extra

    def process(self, msg: str, kwargs: Dict) -> Tuple[str, Dict]:
        kwargs, extra = self._split_kwargs(kwargs)
        kwargs.setdefault("extra", {}).update(extra)
        return msg, kwargs
