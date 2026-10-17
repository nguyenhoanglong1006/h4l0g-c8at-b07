"""Entry point for the daily sync job (Docker: `docker run ... main.py`)."""

import sys

from optibot.jobs.daily_sync import main

if __name__ == "__main__":
    sys.exit(main())
