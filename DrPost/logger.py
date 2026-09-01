from datetime import datetime
import sys
import threading

class log_level:
    INFO :str = "INFO"
    WARNING :str = "WARNING"
    ERROR :str = "ERROR"
    CRITICAL :str = "CRITICAL"

class logger:
    stop_loading = threading.Event()

    def log(self, level :log_level, file :str, msg :str):
        timestamp = datetime.now().isoformat()

        if(level == log_level.WARNING):
            print(f"\033[33m>>{level} |\033[0m At: {timestamp} | File: {file} | Msg: {msg} |>")
            return
        elif(level == log_level.ERROR):
            print(f"\033[31m>>{level} |\033[0m At: {timestamp} | File: {file} | Msg: {msg} |>")
            return
        elif(level == log_level.CRITICAL):
            print(f"\033[7m\e[31m>>{level} |\033[0m At: {timestamp} | File: {file} | Msg: {msg} |>")
            return

        print(f"\033[32m>>{level} |\033[0m At: {timestamp} | File: {file} | Msg: {msg} |>")
        return




