import os
import threading
import queue
import time
import inspect
from datetime import datetime

# -----------------------------
# CONFIGURATION
# -----------------------------

ENABLE_FILE_LOGGING = True
LOG_DIR = "logs"
MAX_LOG_SIZE_BYTES = 1_000_000  # 1 MB per file before rotation
MSG_COUNTER = 0
DATE_STR = datetime.now().strftime("%Y%m%d")

# Log levels
LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARN": 30,
    "ERROR": 40
}

# Set the minimum level allowed for terminal printing
PRINT_LEVEL = LEVELS["INFO"]   # Only INFO, WARN, ERROR will show in terminal   
LOGGING_LEVEL = LEVELS["DEBUG"]  # All levels will be logged to file
#-------------------------------------------------------------

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILES = {
    "ERROR": os.path.join(LOG_DIR, f"{DATE_STR}_error.log"),
    "WARN": os.path.join(LOG_DIR, f"{DATE_STR}_warn.log"),
    "INFO": os.path.join(LOG_DIR, f"{DATE_STR}_info.log"),
    "DEBUG": os.path.join(LOG_DIR, f"{DATE_STR}_debug.log"),
}

# Terminal Colors
COLORS = {
    "ERROR": "\033[91m",  # Red
    "WARN":  "\033[93m",  # Yellow
    "INFO":  "\033[92m",  # Green
    "DEBUG": "\033[94m",  # Blue
    "END":   "\033[0m"
}

# Thread-safe queue for async logging
log_queue = queue.Queue()
stop_signal = False

# -----------------------------
# INTERNAL HELPERS
# -----------------------------

def _create_log_files():
    """Create log files if they don't exist."""
    for log_file in LOG_FILES.values():
        if not os.path.exists(log_file):
            with open(log_file, "w") as f:
                pass  # just create the file

def _name_log_files_with_current_date():
    """Rename log files to include the current date."""
    DATE_STR = datetime.now().strftime("%Y%m%d")
    for level, log_file in LOG_FILES.values():
        base, ext = os.path.splitext(log_file)
        dated_log_file = f"{base}_{DATE_STR}{ext}"
        LOG_FILES[level] = dated_log_file

def _create_log_files_if_needed():
    """Create log files with current date if the date has changed."""
    global DATE_STR
    date_str = datetime.now().strftime("%Y%m%d")
    if date_str == DATE_STR:
        return  # already created for today
    DATE_STR = date_str
    _name_log_files_with_current_date()
    _create_log_files()
           
def _rotate_if_needed(log_file):
    """Rotate log file if it exceeds MAX_LOG_SIZE_BYTES."""
    if os.path.exists(log_file) and os.path.getsize(log_file) > MAX_LOG_SIZE_BYTES:
        base, ext = os.path.splitext(log_file)

        # Find next free rotated filename
        i = 1
        while True:
            rotated = f"{base}_{i}{ext}"
            if not os.path.exists(rotated):
                os.rename(log_file, rotated)
                break
            i += 1


def _async_log_worker():
    """Background thread that processes queued log entries."""
    global stop_signal, MSG_COUNTER
    while not stop_signal or not log_queue.empty():
        try:
            level, message = log_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        log_file = LOG_FILES[level]
        _create_log_files_if_needed() 
        _rotate_if_needed(log_file)  # rotate file if needed

        MSG_COUNTER += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"{MSG_COUNTER:06d} [{timestamp}] [{level}] {message}\n"

        # Thread-safe file write
        with open(log_file, "a") as f:
            f.write(log_line)

def _get_caller():
    """
    Return accurate caller even when the logging API is nested.
    """
    stack = inspect.stack()

    for frame in stack:
        fname = os.path.basename(frame.filename)
        if fname != "logger.py":        # skip internal logger calls
            return f"{fname}:{frame.lineno}"

    return "unknown:0"

# Start logger thread
log_thread = threading.Thread(target=_async_log_worker, daemon=True)
log_thread.start()

# -----------------------------
# PUBLIC TRACE FUNCTION
# -----------------------------
def set_print_level(level):
    """Set the minimum level for terminal printing."""
    global PRINT_LEVEL
    level = level.upper()
    if level not in LEVELS:
        warn(f"Invalid print level: {level}. Using default level {PRINT_LEVEL}")
    PRINT_LEVEL = LEVELS[level]
    
def set_log_level(level):
    """Set the minimum level for file logging."""
    global LOGGING_LEVEL
    level = level.upper()
    if level not in LEVELS:
        warn(f"Invalid log level: {level}. Using default level {LOGGING_LEVEL}")
    LOGGING_LEVEL = LEVELS[level]
    
def set_max_file_size(size_bytes):
    """Set the maximum log file size before rotation."""
    global MAX_LOG_SIZE_BYTES
    if size_bytes <= 0:
        warn(f"Invalid max log size: {size_bytes}. Using default {MAX_LOG_SIZE_BYTES}")
        return
    MAX_LOG_SIZE_BYTES = size_bytes
    
def set_logs_dir(dir_path):
    """Set the directory where log files are stored."""
    global LOG_DIR, LOG_FILES
    if dir_path.strip() == "":
        warn(f"Invalid log directory path. Using default {LOG_DIR}")
        return
    LOG_DIR = dir_path
    os.makedirs(LOG_DIR, exist_ok=True)
    for level in LOG_FILES:
        LOG_FILES[level] = os.path.join(LOG_DIR, f"{level.lower()}.log")

def set_file_logging_enabled(enabled):
    """Enable or disable logging to files."""
    global ENABLE_FILE_LOGGING
    ENABLE_FILE_LOGGING = enabled

def debug(message): trace("DEBUG", message)
def info(message): trace("INFO", message)
def warn(message): trace("WARN", message)
def error(message): trace("ERROR", message)

def trace(level, message):
    """
    Print to terminal (with colors) and store in log file (async).
    Includes filename + line number automatically.
    """
    level = level.upper()
    if level not in LOG_FILES:
        raise ValueError(f"Invalid log level: {level}")

    caller = _get_caller()

    # Add context to message
    context_msg = f"({caller}) {message} "

    # TERMINAL PRINTING (with color)
    if LEVELS[level] >= PRINT_LEVEL:
        color = COLORS[level]
        print(f"{color}[{level}] {context_msg}{COLORS['END']}")
    
    # FILE LOGGING
    if ENABLE_FILE_LOGGING and LEVELS[level] >= LOGGING_LEVEL:
        # Put into async log queue
        log_queue.put((level, context_msg))

# -----------------------------
# CLEAN SHUTDOWN (optional)
# -----------------------------

def close_logger():
    """Flush and stop logging thread cleanly (call on shutdown)."""
    global stop_signal
    stop_signal = True
    log_thread.join(timeout=2)
