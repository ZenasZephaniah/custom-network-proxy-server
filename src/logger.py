import logging
import sys

def setup_logger(log_file_path: str) -> logging.Logger:
    """
    Sets up a thread-safe logger that outputs to both a log file and the console.
    """
    logger = logging.getLogger("ProxyServer")
    logger.setLevel(logging.INFO)

    # Prevent adding handlers multiple times if setup is called again
    if not logger.handlers:
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console Handler (Stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler
        try:
            file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file at {log_file_path}. Logging to console only. Error: {e}")

    return logger