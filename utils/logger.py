import logging
import os

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:  # avoid duplicate handlers on re-import
        logger.setLevel(logging.DEBUG)

        # Console handler — shows in terminal
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)

        # File handler — writes to logs/etl.log
        os.makedirs("logs", exist_ok=True)
        file = logging.FileHandler("logs/etl.log")
        file.setLevel(logging.DEBUG)

        # Format
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console.setFormatter(formatter)
        file.setFormatter(formatter)

        logger.addHandler(console)
        logger.addHandler(file)

    return logger