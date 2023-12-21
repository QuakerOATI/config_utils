import logging


class AdaptedLogger(logging.Logger):
    """A logger that allows you to register adapters on a instance.

    Taken from this StackOverflow answer: https://stackoverflow.com/a/68287482
    """

    def __init__(self, name: str) -> None:
        """Create a new logger instance."""
        super().__init__(name)
        self._adapters = []

    def add_adapter(self, adapter: logging.LoggerAdapter, *args, **kwargs) -> None:
        """Preprocess this logger's input with the provided LoggerAdapter.

        Positional and keyword arguments after the first are passed to the
        adapter's constructor.
        """
        self._adapters.append(adapter(self, *args, **kwargs))

    def _log(self, level, msg, *args, **kwargs):
        """Let adapters modify the message and keyword arguments."""
        for adapter in self._adapters:
            msg, kwargs = adapter.process(msg, kwargs)
        return super()._log(level, msg, *args, **kwargs)
