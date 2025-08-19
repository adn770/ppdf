import logging

# Define the valid logging topics for the dmap project.
PROJECT_TOPICS = {
    "dmap": {
        "main",
        "analysis",
        "grid",
        "ocr",
        "geometry",
        "render",
        "transform",
        "wallscore",
        "llm",
    }
}


class RichLogFormatter(logging.Formatter):
    """A custom logging formatter for rich, colorful, and aligned console output."""

    def __init__(self, use_color=False):
        super().__init__()
        if use_color:
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
                logging.DEBUG: "",
                logging.INFO: "",
                logging.WARNING: "",
                logging.ERROR: "",
                logging.CRITICAL: "",
            }
            self.BOLD = ""
            self.RESET = ""

    def format(self, record):
        if record.__dict__.get("raw"):
            # For raw output like ASCII maps, return the message as is.
            return super().format(record)

        color = self.COLORS.get(record.levelno, self.RESET)
        level_name = record.levelname[:5]
        topic = record.name.split(".")[-1][:8]
        prefix = f"{color}{level_name:<5}{self.RESET}:{self.BOLD}{topic:<8}{self.RESET}: "
        s = super().format(record)
        return "\n".join([f"{prefix}{line}" for line in s.split("\n")])


def setup_logging(level, color_logs, debug_topics, log_file):
    """Configures logging for the application."""
    root_logger = logging.getLogger("dmap")
    if root_logger.hasHandlers():
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
            h.close()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(RichLogFormatter(use_color=color_logs))
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode="w")
            file_handler.setFormatter(RichLogFormatter(use_color=False))
            root_logger.addHandler(file_handler)
            logging.getLogger("dmap.main").info("Logging to file: %s", log_file)
        except IOError as e:
            root_logger.error("Could not open log file %s: %s", log_file, e)

    if debug_topics:
        user_topics = [t.strip() for t in debug_topics.split(",")]
        valid_topics = PROJECT_TOPICS.get("dmap", set())
        topics_to_set = (
            valid_topics
            if "all" in user_topics
            else {full for u in user_topics for full in valid_topics if full.startswith(u)}
        )
        for topic in topics_to_set:
            logging.getLogger(f"dmap.{topic}").setLevel(logging.DEBUG)
