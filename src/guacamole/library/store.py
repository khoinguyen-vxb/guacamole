"""A reference library: original files and frozen, content-addressed snapshots.

The same class serves the shared scope (standards, textbooks, company procedures)
and each project's own scope inside its workspace. Snapshots are never changed;
a correction or a better parse is a new snapshot. Verifications of a snapshot's
elements are appended beside it; the latest for an element is its status.
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Literal, Self

from ..contracts import Element, Label, Scope, SourceSnapshot, Verification
from ..tools.registry import encode
from .parsing import LayoutParser, default_parser
from .profiles import choose


class Library:
    def __init__(self, directory: Path, *, scope: Scope = "shared") -> None:
        self.directory = directory.expanduser().resolve()
        self.scope: Scope = scope
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            self.directory / "library.sqlite3", isolation_level=None
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS elements (
                snapshot TEXT NOT NULL REFERENCES snapshots(id), ordinal INTEGER NOT NULL,
                id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(snapshot,id)
            );
            CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
                BEGIN SELECT RAISE(ABORT, 'immutable snapshots'); END;
            CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
                BEGIN SELECT RAISE(ABORT, 'immutable snapshots'); END;
            CREATE TRIGGER IF NOT EXISTS elements_no_update BEFORE UPDATE ON elements
                BEGIN SELECT RAISE(ABORT, 'immutable snapshots'); END;
            CREATE TRIGGER IF NOT EXISTS elements_no_delete BEFORE DELETE ON elements
                BEGIN SELECT RAISE(ABORT, 'immutable snapshots'); END;
            CREATE TABLE IF NOT EXISTS verifications (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot TEXT NOT NULL REFERENCES snapshots(id),
                element TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS verifications_no_update BEFORE UPDATE ON verifications
                BEGIN SELECT RAISE(ABORT, 'append-only verifications'); END;
            CREATE TRIGGER IF NOT EXISTS verifications_no_delete BEFORE DELETE ON verifications
                BEGIN SELECT RAISE(ABORT, 'append-only verifications'); END;
        """)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def ingest(
        self,
        path: Path,
        *,
        designation: str,
        edition: str,
        title: str = "",
        label: Label | None = None,
        licence: str = "",
        profile: str | None = None,
        parser: LayoutParser | None = None,
    ) -> SourceSnapshot:
        """Parse a PDF, structure it with the best-fitting profile, and freeze it.

        Ingesting the same file the same way again returns the existing snapshot.
        """
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        original = self.directory / "originals" / digest / path.name
        if not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(data)
        parser = parser or default_parser()
        blocks = parser.parse(original)
        chosen = choose(blocks, profile)
        elements = chosen.structure(blocks)
        if not elements:
            raise ValueError(f"{path.name}: no text found; scanned pages need OCR")
        fields = {
            "designation": designation,
            "edition": edition,
            "title": title,
            "file_name": path.name,
            "file_sha256": digest,
            "profile": chosen.name,
            "parser": parser.name,
            "label": (label or Label()).model_dump(mode="json"),
            "licence": licence,
            "elements": len(elements),
        }
        content = encode(
            [fields, [e.model_dump(mode="json") for e in elements]]
        ).encode()
        snapshot = SourceSnapshot.model_validate(
            fields
            | {
                "id": f"snap-{hashlib.sha256(content).hexdigest()[:16]}",
                "label": label or Label(),
            }
        )
        if self.db.execute(
            "SELECT 1 FROM snapshots WHERE id=?", (snapshot.id,)
        ).fetchone():
            return snapshot
        # A snapshot and its elements land together or not at all.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO snapshots VALUES (?,?)",
                (snapshot.id, snapshot.model_dump_json()),
            )
            self.db.executemany(
                "INSERT INTO elements VALUES (?,?,?,?)",
                (
                    (snapshot.id, i, e.id, e.model_dump_json())
                    for i, e in enumerate(elements)
                ),
            )
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return snapshot

    def snapshot(self, id: str) -> SourceSnapshot:
        row = self.db.execute("SELECT data FROM snapshots WHERE id=?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"No snapshot {id} in the {self.scope} library")
        return SourceSnapshot.model_validate_json(row[0])

    def snapshots(self) -> tuple[SourceSnapshot, ...]:
        return tuple(
            SourceSnapshot.model_validate_json(data)
            for (data,) in self.db.execute("SELECT data FROM snapshots ORDER BY id")
        )

    def elements(self, snapshot: str) -> tuple[Element, ...]:
        """Every element of a snapshot, in document order."""
        return tuple(
            Element.model_validate_json(data)
            for (data,) in self.db.execute(
                "SELECT data FROM elements WHERE snapshot=? ORDER BY ordinal",
                (snapshot,),
            )
        )

    def element(self, snapshot: str, id: str) -> Element:
        row = self.db.execute(
            "SELECT data FROM elements WHERE snapshot=? AND id=?", (snapshot, id)
        ).fetchone()
        if row is None:
            raise KeyError(f"No element {id} in {snapshot}")
        return Element.model_validate_json(row[0])

    def original(self, snapshot: SourceSnapshot) -> Path:
        """The original file, refused if its bytes changed since ingestion."""
        path = self.directory / "originals" / snapshot.file_sha256 / snapshot.file_name
        if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot.file_sha256:
            raise ValueError(f"{snapshot.file_name} changed since it was ingested")
        return path

    def record(self, snapshot: str, results: list[Verification]) -> None:
        """Append verifications of a snapshot's elements, all or none."""
        ids = {e.id for e in self.elements(snapshot)}
        if unknown := [r.element for r in results if r.element not in ids]:
            raise KeyError(f"No element {unknown[0]} in {snapshot}")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.executemany(
                "INSERT INTO verifications(snapshot,element,data) VALUES (?,?,?)",
                ((snapshot, r.element, r.model_dump_json()) for r in results),
            )
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def verifications(self, snapshot: str) -> dict[str, Verification]:
        """Each checked element's latest verification; absent ones are unverified."""
        return {
            element: Verification.model_validate_json(data)
            for element, data in self.db.execute(
                "SELECT element, data FROM verifications WHERE snapshot=? ORDER BY sequence",
                (snapshot,),
            )
        }

    def disputes(self, snapshot: str) -> tuple[Verification, ...]:
        """Elements whose latest verification is a dispute, for a person to resolve."""
        return tuple(
            v for v in self.verifications(snapshot).values() if v.status == "disputed"
        )

    def resolve(
        self,
        snapshot: str,
        element: str,
        status: Literal["passed", "disputed"],
        *,
        reviewer: str,
        reason: str,
    ) -> Verification:
        """A person's judgement of an element against its original pages.

        Passing a dispute says the extracted text is right as it stands; a wrong
        extraction stays disputed until a corrected snapshot replaces it.
        """
        if not reason.strip():
            raise ValueError("Say what was compared and why it is right or wrong")
        result = Verification(
            element=element, status=status, method=f"human:{reviewer}", detail=reason
        )
        self.record(snapshot, [result])
        return result
