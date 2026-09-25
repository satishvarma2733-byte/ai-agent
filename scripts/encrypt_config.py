"""Encrypt the credentials already stored in the runtime config file (data/config.json).

Usage, with SECRETS_ENCRYPTION_KEY set in the environment or .env:
    python -m scripts.encrypt_config
"""
from dotenv import load_dotenv

load_dotenv()

import config_crypto  # noqa: E402
from backend_config import SECRET_CONFIG_KEYS, read_config, write_config  # noqa: E402
from runtime_env import get_primary_config_path  # noqa: E402


def main() -> None:
    if not config_crypto.encryption_available():
        raise SystemExit("Set SECRETS_ENCRYPTION_KEY first (config_crypto.py shows how to generate one).")
    config = read_config()
    write_config({key: config[key] for key in SECRET_CONFIG_KEYS if key in config})
    print(f"Encrypted credentials in {get_primary_config_path()}")


if __name__ == "__main__":
    main()
