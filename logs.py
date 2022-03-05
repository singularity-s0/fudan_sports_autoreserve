LOG_LEVELS = ['INFO', 'WARNING', 'ERROR', 'VITAL']  # ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'VITAL']
FULL_LOG = ""


def log_console(message, level):
    global FULL_LOG
    FULL_LOG += f"{level}\t\t\t\t{message}\n"

    if level in LOG_LEVELS:
        print(f"{level}\t\t\t\t{message}")
