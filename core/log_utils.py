#!/usr/bin/env python3
"""
core/utils.py: Provides auxiliary and utility classes for the main application.

This module contains:
- RichLogFormatter: A custom logging formatter for colorful console output.
- ContextFilter: A logging filter to add contextual data (like preset names)
  to log records.
- ASCIIRenderer: A debugging tool to visualize the detected page layout as
  ASCII art.
"""

import logging


def setup_logging(level=logging.INFO, color_logs=False, debug_topics=None):
    """Configures logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(RichLogFormatter(use_color=color_logs))
    root_logger.addHandler(handler)
    app_logger = logging.getLogger("ppdf")
    app_logger.setLevel(level)

    if debug_topics:
        app_logger.setLevel(logging.INFO)
        topics = {"layout", "structure", "reconstruct", "llm", "tts", "tables"}
        user_topics = [t.strip() for t in debug_topics.split(",")]
        if "all" in user_topics:
            topics_to_set = topics
        else:
            topics_to_set = {
                full for u in user_topics for full in topics if full.startswith(u)
            }
        for topic in topics_to_set:
            logging.getLogger(f"ppdf.{topic}").setLevel(logging.DEBUG)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)


class ContextFilter(logging.Filter):
    """
    A logging filter that injects contextual information into log records.
    """

    def __init__(self, context_str=""):
        super().__init__()
        self.context_str = context_str

    def filter(self, record):
        record.context = self.context_str
        return True


# --- CUSTOM LOGGING FORMATTER ---
class RichLogFormatter(logging.Formatter):
    """A custom logging formatter for rich, colorful, and aligned console output.

    This formatter uses ANSI escape codes to produce colored and structured log
    messages, making it easier to distinguish between log levels and topics,
    especially during debugging.

    Args:
        use_color (bool): If True, ANSI color codes are used. Defaults to False.
    """

    def __init__(self, use_color=False):
        super().__init__()
        if use_color:
            # ANSI escape codes for 256-color terminal
            self.COLORS = {
                logging.DEBUG: "\033[38;5;252m",  # Light Grey
                logging.INFO: "\033[38;5;111m",  # Pastel Blue
                logging.WARNING: "\033[38;5;229m",  # Pale Yellow
                logging.ERROR: "\033[38;5;210m",  # Soft Red
                logging.CRITICAL: "\033[38;5;217m",  # Light Magenta
            }
            self.BOLD = "\033[1m"
            self.RESET = "\033[0m"
        else:
            self.COLORS = {
                level: ""
                for level in [
                    logging.DEBUG,
                    logging.INFO,
                    logging.WARNING,
                    logging.ERROR,
                    logging.CRITICAL,
                ]
            }
            self.BOLD = ""
            self.RESET = ""

    def format(self, record):
        """Formats a log record into a colored, aligned string.

        Each line of the log message is prefixed with a color-coded level and
        a bolded topic name for easy scanning.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log message string.
        """
        color = self.COLORS.get(record.levelno, self.RESET)
        level_name = record.levelname[:5]
        topic = record.name.split(".")[-1][:5]

        has_ctx = hasattr(record, "context") and record.context
        context_str = f"[{getattr(record, 'context', '')}]" if has_ctx else ""

        prefix = (
            f"{color}{level_name:<5}{self.RESET}:"
            f"{self.BOLD}{topic:<5}{self.RESET}{context_str}: "
        )
        message = record.getMessage()
        lines = message.split("\n")
        return "\n".join([f"{prefix}{line}" for line in lines])
