"""Reference library: standards, textbooks and procedures ingested once, then pinned.

A Library holds originals and frozen snapshots of their elements; a project pins
the snapshots it binds to (Project.pin) and agents read them with the readers.
"""

from .parsing import Block, DoclingParser, LayoutParser, PypdfParser, default_parser
from .profiles import PROFILES, FallbackProfile, NumberedClauseProfile, Profile
from .readers import LibraryHit, register_library_tools
from .store import Library

__all__ = [
    "PROFILES",
    "Block",
    "DoclingParser",
    "FallbackProfile",
    "LayoutParser",
    "Library",
    "LibraryHit",
    "NumberedClauseProfile",
    "Profile",
    "PypdfParser",
    "default_parser",
    "register_library_tools",
]
