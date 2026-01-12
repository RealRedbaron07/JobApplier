#!/usr/bin/env python3
"""
Centralized logging with file output.
All application logs are written to both console and timestamped log files.
"""

import logging
import os
from datetime import datetime
from typing import Optional


class EmojiLogFormatter(logging.Formatter):
    """Custom formatter that adds emojis to log levels."""
    
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }
    
    def format(self, record):
        # Add emoji prefix for console output
        emoji = self.EMOJIS.get(record.levelname, '•')
        record.emoji = emoji
        return super().format(record)


def setup_logger(
    name: str = "job_applier",
    log_dir: str = "logs",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG
) -> logging.Logger:
    """
    Configure logger with both console and file output.
    
    Args:
        name: Logger name (for module identification)
        log_dir: Directory to store log files
        console_level: Minimum level for console output
        file_level: Minimum level for file output
    
    Returns:
        Configured logger instance
    """
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture all levels, handlers filter
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Generate timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"job_applier_{timestamp}.log")
    
    # File handler (detailed output)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler (summary with emojis)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_formatter = EmojiLogFormatter(
        '%(asctime)s %(emoji)s %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Log initialization
    logger.info(f"Logging initialized. Log file: {log_file}")
    
    return logger


def get_logger(name: str = "job_applier") -> logging.Logger:
    """
    Get an existing logger or create a new one.
    
    Args:
        name: Logger name (use __name__ for module-specific logging)
    
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    
    # If no handlers, set up the logger
    if not logger.handlers:
        return setup_logger(name)
    
    return logger


class LogContext:
    """Context manager for logging operation blocks with timing."""
    
    def __init__(self, logger: logging.Logger, operation: str, level: int = logging.INFO):
        self.logger = logger
        self.operation = operation
        self.level = level
        self.start_time: Optional[datetime] = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.log(self.level, f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.log(self.level, f"Completed: {self.operation} ({elapsed:.2f}s)")
        else:
            self.logger.error(f"Failed: {self.operation} ({elapsed:.2f}s) - {exc_val}")
        
        return False  # Don't suppress exceptions


# Create default logger instance for quick import
logger = setup_logger()


# Convenience functions that use the default logger
def debug(message: str):
    """Log debug message."""
    logger.debug(message)


def info(message: str):
    """Log info message."""
    logger.info(message)


def warning(message: str):
    """Log warning message."""
    logger.warning(message)


def error(message: str):
    """Log error message."""
    logger.error(message)


def critical(message: str):
    """Log critical message."""
    logger.critical(message)


def log_exception(message: str, exc: Exception):
    """Log an exception with full traceback."""
    logger.exception(f"{message}: {exc}")


if __name__ == "__main__":
    # Test the logger
    print("Testing logger...")
    
    debug("This is a debug message")
    info("This is an info message")
    warning("This is a warning message")
    error("This is an error message")
    
    with LogContext(logger, "Test operation"):
        info("Doing some work...")
    
    print("\nCheck the 'logs' directory for the log file!")
