from loguru import logger
import sys

def setup_logger():
    logger.remove()  # Remove default handler
    logger.add(
        sink=sys.stdout,  # Change to sys.stdout to output logs to the terminal
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True,  # Enable colorized output
        serialize=False  # Output must be human-readable
    )
    return logger

# Call the setup function to ensure the logger is configured when imported
setup_logger()