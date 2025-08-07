# --- dmme_lib/services/config_service.py ---
import configparser
import logging

log = logging.getLogger("dmme.config")


class ConfigService:
    """Manages reading from and writing to the dmme.cfg file."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.defaults = {
            "Appearance": {
                "theme": "high-contrast",
                "language": "en",
            },
            "Ollama": {
                "url": "http://localhost:11434",
                "dm_model": "llama3.1:latest",
                "vision_model": "llava:latest",
                "utility_model": "llama3.1:latest",
                "embedding_model": "mxbai-embed-large",
            },
            "Game": {
                "default_ruleset": "",
                "default_setting": "",
            },
        }

    def get_settings(self) -> dict:
        """Reads settings from the config file, applying defaults if missing."""
        config = configparser.ConfigParser()
        # Apply defaults first
        for section, values in self.defaults.items():
            config[section] = values

        # Read existing file to override defaults
        if not config.read(self.config_path):
            log.info("Config file not found at %s. Creating with defaults.", self.config_path)
            self.save_settings(self._config_to_dict(config))

        return self._config_to_dict(config)

    def save_settings(self, settings: dict):
        """Saves a dictionary of settings to the config file."""
        config = configparser.ConfigParser()
        for section, values in settings.items():
            config[section] = {k: str(v) for k, v in values.items()}

        try:
            with open(self.config_path, "w") as configfile:
                config.write(configfile)
            log.info("Settings successfully saved to %s", self.config_path)
        except IOError as e:
            log.error("Failed to write settings to %s: %s", self.config_path, e)

    def _config_to_dict(self, config: configparser.ConfigParser) -> dict:
        """Converts a ConfigParser object to a nested dictionary."""
        return {s: dict(config.items(s)) for s in config.sections()}
