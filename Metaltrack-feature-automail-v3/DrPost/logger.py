from datetime import datetime


class log_level:
    INFO: str = "INFO"
    WARNING: str = "WARNING"
    ERROR: str = "ERROR"
    CRITICAL: str = "CRITICAL"


# ANSI colour codes per level. Python has no "\e" escape, so the old CRITICAL
# line printed a literal "\e[31m"; "\033" is the correct escape.
_COLOURS = {
    log_level.INFO: "\033[32m",
    log_level.WARNING: "\033[33m",
    log_level.ERROR: "\033[31m",
    log_level.CRITICAL: "\033[7m\033[31m",
}
_RESET = "\033[0m"


class logger:
    def log(self, level: str, file: str, msg: str):
        timestamp = datetime.now().isoformat(timespec="seconds")
        colour = _COLOURS.get(level, _COLOURS[log_level.INFO])
        print(f"{colour}>>{level} |{_RESET} At: {timestamp} | File: {file} | Msg: {msg} |>", flush=True)
