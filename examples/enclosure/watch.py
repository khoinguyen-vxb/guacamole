"""Follow a running enclosure project's activity log, read-only, beside the host.

Run with: .venv/bin/python -m examples.enclosure.watch [--all] [--detail] [--tools]
See guacamole.console.watch for the flags.
"""

import sys

from guacamole.console import watch

from .enclosure import WORKSPACE

if __name__ == "__main__":
    watch(WORKSPACE, sys.argv[1:])
