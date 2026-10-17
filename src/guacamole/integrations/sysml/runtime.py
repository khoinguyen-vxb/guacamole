"""Resolve the SysML assets when the SDK was installed from its source distribution."""

import os
from pathlib import Path

import sysml


def standard_library() -> Path:
    try:
        return sysml.standard_library()
    except sysml.SdkError:
        configured = os.environ.get("GUACAMOLE_SYSML_LIBRARY")
        if configured:
            path = Path(configured).expanduser().resolve()
            if path.is_dir():
                return path
        raise
