"""Ask OptiBot from the terminal.

Usage: python -m optibot.assistant "How do I add a YouTube video?"
"""

import sys

from optibot.assistant.service import ask

if len(sys.argv) != 2:
    sys.exit(__doc__)
print(ask(sys.argv[1]))
