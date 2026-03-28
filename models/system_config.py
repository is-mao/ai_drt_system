import os
from models import db
from datetime import datetime

# Mapping of config keys to environment variable names
_ENV_FALLBACK = {
    "gemini_api_key": "GEMINI_API_KEY",
}


class SystemConfig(db.Model):
    __tablename__ = "system_config"

    config_key = db.Column(db.String(100), primary_key=True)
    config_value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get_value(key, default=None):
        config = db.session.get(SystemConfig, key)
        if config and config.config_value:
            return config.config_value
        # Fallback to environment variable
        env_key = _ENV_FALLBACK.get(key)
        if env_key:
            env_val = os.environ.get(env_key)
            if env_val:
                return env_val
        return default

    @staticmethod
    def set_value(key, value):
        config = db.session.get(SystemConfig, key)
        if config:
            config.config_value = value
        else:
            config = SystemConfig(config_key=key, config_value=value)
            db.session.add(config)
        db.session.commit()
