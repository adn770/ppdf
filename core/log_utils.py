#!/usr/bin/env python3
"""
core/utils.py: Provides auxiliary and utility classes for the main application.
This module contains:
- RichLogFormatter: A custom logging formatter for colorful console output.
- ContextFilter: A logging filter to add contextual data (like preset names)
  to log records.
"""

import logging

PROJECT_TOPICS = {
    "ppdf": {"layout", "structure", "reconstruct", "llm", "tts", "tables", "api"},
    "dmme": {"api", "rag", "ingest", "storage", "config"},
}


def setup_logging(
    project_name: str,
    level=logging.INFO,
    color_logs=False,
    debug_topics=None,
    include_projects: list[str] = None,
    log_file: str = None,
):
    """Configures logging for the application."""
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
            h.close()

    # Console Handler (always enabled)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(RichLogFormatter(use_color=color_logs))
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)

    # File Handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode="w")
            # File logs should not be colored
            file_handler.setFormatter(RichLogFormatter(use_color=False))
            root_logger.addHandler(file_handler)
            logging.getLogger(project_name).info("Logging to file: %s", log_file)
        except IOError as e:
            logging.getLogger(project_name).error(
                "Could not open log file %s: %s", log_file, e
            )

    # Silence noisy libraries
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    if debug_topics:
        projects_to_debug = [project_name] + (include_projects or [])
        user_topics = [t.strip() for t in debug_topics.split(",")]

        for proj in projects_to_debug:
            valid_topics = PROJECT_TOPICS.get(proj, set())
            if "all" in user_topics:
                topics_to_set = valid_topics
            else:
                topics_to_set = {
                    full for u in user_topics for full in valid_topics if full.startswith(u)
                }

            for topic in topics_to_set:
                logging.getLogger(f"{proj}.{topic}").setLevel(logging.DEBUG)


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

        # Use the part of the logger name after the project name as the topic
        name_parts = record.name.split(".")
        topic = name_parts[1][:6] if len(name_parts) > 1 else record.name[:6]

        has_ctx = hasattr(record, "context") and record.context
        context_str = f"[{getattr(record, 'context', '')}]" if has_ctx else ""

        prefix = (
            f"{color}{level_name:<5}{self.RESET}:"
            f"{self.BOLD}{topic:<6}{self.RESET}{context_str}: "
        )
        message = record.getMessage()
        lines = message.split("\n")
        return "\n".join([f"{prefix}{line}" for line in lines])
