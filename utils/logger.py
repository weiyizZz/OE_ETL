import logging
import os

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Terminal
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        # File
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler("logs/pipeline.log")
        file_handler.setFormatter(formatter)

        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)
    return logger