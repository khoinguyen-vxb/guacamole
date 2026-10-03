"""Local append-only record revisions and an atomic activity log."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from .contracts import JSON, ActivityEvent, Model, Ref, now, uid
from .tools.registry import encode

# Latest revision of each record.
CURRENT = "FROM records r JOIN (SELECT kind,id,MAX(revision) rev FROM records GROUP BY kind,id) c ON r.kind=c.kind AND r.id=c.id AND r.revision=c.rev"
LATEST = "SELECT r.* " + CURRENT


class Snapshot(Model):
    ref: Ref
    data: JSON
    dependencies: tuple[Ref, ...]
    stale: bool


class Store:
    def __init__(self, directory: Path, *, read_only: bool = False) -> None:
        self.directory = directory.resolve()
        self.lock = RLock()
        self.depth = 0
        if read_only:
            uri = (self.directory / "project.sqlite3").as_uri() + "?mode=ro"
            self.db = sqlite3.connect(uri, uri=True, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.project_id = self.db.execute(
                "SELECT value FROM metadata WHERE key='project_id'"
            ).fetchone()[0]
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            self.directory / "project.sqlite3", isolation_level=None
        )
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                sha256 TEXT NOT NULL, data TEXT NOT NULL, dependencies TEXT NOT NULL,
                PRIMARY KEY(kind,id,revision)
            );
            CREATE TABLE IF NOT EXISTS invalidations (
                kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                reason TEXT NOT NULL, PRIMARY KEY(kind,id,revision)
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE, timestamp TEXT NOT NULL, actor TEXT NOT NULL,
                type TEXT NOT NULL, entity_id TEXT NOT NULL, request_id TEXT,
                causal_event INTEGER REFERENCES events(sequence), details TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO metadata VALUES ('schema_version','1');
            CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'append-only events'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'append-only events'); END;
            CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records
                BEGIN SELECT RAISE(ABORT, 'append-only records'); END;
            CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records
                BEGIN SELECT RAISE(ABORT, 'append-only records'); END;
        """)
        if (
            self.db.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()[0]
            != "1"
        ):
            raise ValueError("Unsupported project database version")
        self.db.execute(
            "INSERT OR IGNORE INTO metadata VALUES ('project_id',?)", (uid(),)
        )
        self.project_id: str = self.db.execute(
            "SELECT value FROM metadata WHERE key='project_id'"
        ).fetchone()[0]
        self.lock = RLock()
        self.depth = 0

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.lock:
            marker = f"transaction_{self.depth}"
            self.db.execute(f"SAVEPOINT {marker}")
            self.depth += 1
            try:
                yield
                self.db.execute(f"RELEASE {marker}")
            except BaseException:
                self.db.execute(f"ROLLBACK TO {marker}")
                self.db.execute(f"RELEASE {marker}")
                raise
            finally:
                self.depth -= 1

    def event(
        self,
        actor: str,
        type: str,
        entity_id: str,
        details: JSON | None = None,
        *,
        request_id: str | None = None,
        causal_event: int | None = None,
    ) -> int:
        if causal_event is None and request_id:
            previous = self.db.execute(
                "SELECT sequence FROM events WHERE request_id=? ORDER BY sequence DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            causal_event = previous[0] if previous else None
        cursor = self.db.execute(
            "INSERT INTO events(id,timestamp,actor,type,entity_id,request_id,causal_event,details) VALUES (?,?,?,?,?,?,?,?)",
            (
                uid(),
                now(),
                actor,
                type,
                entity_id,
                request_id,
                causal_event,
                encode(details or {}),
            ),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def put(
        self,
        kind: str,
        id: str,
        data: Model | JSON,
        *,
        actor: str,
        dependencies: tuple[Ref, ...] = (),
        request_id: str | None = None,
        event: str | None = None,
        allow_stale_dependencies: bool = False,
    ) -> Ref:
        payload = data.model_dump(mode="json") if isinstance(data, Model) else data
        serialized = encode(payload)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        with self.atomic():
            stale = False
            for dependency in dependencies:
                snapshot = self.resolve(
                    dependency, current=not allow_stale_dependencies
                )
                stale |= snapshot.stale or self.get(
                    dependency.kind, dependency.id
                ).ref != dependency.model_copy(update={"locator": ""})
            previous = self.maybe(kind, id)
            revision = previous.ref.revision + 1 if previous else 1
            self.db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?)",
                (
                    kind,
                    id,
                    revision,
                    digest,
                    serialized,
                    encode([r.model_dump(mode="json") for r in dependencies]),
                ),
            )
            ref = Ref(kind=kind, id=id, revision=revision, sha256=digest)
            self.event(
                actor,
                event or f"{kind}.recorded",
                id,
                {"ref": ref.model_dump(mode="json")},
                request_id=request_id,
            )
            if previous and kind not in {
                "request",
                "inbox",
                "agent_state",
                "run",
                "review",
            }:
                self._invalidate(previous.ref, actor)
            if stale:
                self.invalidate(
                    ref, actor=actor, reason="Input changed while work was running"
                )
        return ref

    def invalidate(self, ref: Ref, *, actor: str, reason: str) -> None:
        """Retain the record and invalidate its dependent work."""
        with self.atomic():
            if self.resolve(ref).stale:
                return
            self.db.execute(
                "INSERT INTO invalidations VALUES (?,?,?,?)",
                (ref.kind, ref.id, ref.revision, reason),
            )
            self.event(
                actor,
                "dependency.stale",
                ref.id,
                {"ref": ref.model_dump(mode="json"), "reason": reason},
            )
            self._invalidate(ref, actor)

    def _invalidate(self, changed: Ref, actor: str) -> None:
        # Index dependency edges once per cascade; record data is never parsed.
        stale = set(
            self.db.execute("SELECT kind,id,revision FROM invalidations").fetchall()
        )
        dependents: dict[tuple[str, str, int], list[Ref]] = {}
        for kind, id, revision, sha256, dependencies in self.db.execute(
            "SELECT r.kind,r.id,r.revision,r.sha256,r.dependencies " + CURRENT
        ):
            if (kind, id, revision) in stale:
                continue
            ref = Ref(kind=kind, id=id, revision=revision, sha256=sha256)
            for r in json.loads(dependencies):
                dependents.setdefault((r["kind"], r["id"], r["revision"]), []).append(
                    ref
                )
        pending = [changed]
        while pending:
            old = pending.pop()
            for ref in dependents.pop((old.kind, old.id, old.revision), ()):
                key = (ref.kind, ref.id, ref.revision)
                if key in stale:
                    continue
                stale.add(key)
                self.db.execute(
                    "INSERT OR IGNORE INTO invalidations VALUES (?,?,?,?)",
                    (*key, f"Changed {old.kind}:{old.id}@{old.revision}"),
                )
                self.event(
                    actor,
                    "dependency.stale",
                    ref.id,
                    {
                        "ref": ref.model_dump(mode="json"),
                        "changed": old.model_dump(mode="json"),
                    },
                )
                pending.append(ref)

    def _snapshot(self, row: sqlite3.Row) -> Snapshot:
        stale = (
            self.db.execute(
                "SELECT 1 FROM invalidations WHERE kind=? AND id=? AND revision=?",
                (row["kind"], row["id"], row["revision"]),
            ).fetchone()
            is not None
        )
        return Snapshot(
            ref=Ref(
                kind=row["kind"],
                id=row["id"],
                revision=row["revision"],
                sha256=row["sha256"],
            ),
            data=json.loads(row["data"]),
            stale=stale,
            dependencies=tuple(
                Ref.model_validate(r) for r in json.loads(row["dependencies"])
            ),
        )

    def maybe(self, kind: str, id: str) -> Snapshot | None:
        row = self.db.execute(
            "SELECT * FROM records WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1",
            (kind, id),
        ).fetchone()
        return self._snapshot(row) if row else None

    def get(self, kind: str, id: str) -> Snapshot:
        snapshot = self.maybe(kind, id)
        if snapshot is None:
            raise KeyError(f"Unknown {kind}: {id}")
        return snapshot

    def model[T: Model](self, kind: str, id: str, cls: type[T]) -> T:
        return cls.model_validate_json(encode(self.get(kind, id).data))

    def resolve(self, ref: Ref, *, current: bool = False) -> Snapshot:
        row = self.db.execute(
            "SELECT * FROM records WHERE kind=? AND id=? AND revision=?",
            (ref.kind, ref.id, ref.revision),
        ).fetchone()
        if row is None or row["sha256"] != ref.sha256:
            raise ValueError(f"Missing or mismatched reference: {ref.kind}:{ref.id}")
        snapshot = self._snapshot(row)
        if current and (
            snapshot.stale
            or self.get(ref.kind, ref.id).ref != ref.model_copy(update={"locator": ""})
        ):
            raise ValueError(f"Stale reference: {ref.kind}:{ref.id}@{ref.revision}")
        return snapshot

    def list(self, *kinds: str) -> tuple[Snapshot, ...]:
        where = f" WHERE r.kind IN ({','.join('?' * len(kinds))})" if kinds else ""
        rows = self.db.execute(LATEST + where, kinds)
        return tuple(self._snapshot(row) for row in rows)

    def history(self, kind: str, id: str) -> tuple[Snapshot, ...]:
        return tuple(
            self._snapshot(row)
            for row in self.db.execute(
                "SELECT * FROM records WHERE kind=? AND id=? ORDER BY revision",
                (kind, id),
            )
        )

    def events(
        self,
        after: int = 0,
        *,
        actor: str | None = None,
        request_id: str | None = None,
        since: str | None = None,
    ) -> tuple[ActivityEvent, ...]:
        clauses = ["sequence > ?"]
        args: list[int | str] = [after]
        for field, value in (
            ("actor", actor),
            ("request_id", request_id),
            ("timestamp", since),
        ):
            if value is not None:
                clauses.append(f"{field} {'>=' if field == 'timestamp' else '='} ?")
                args.append(value)
        rows = self.db.execute(
            "SELECT * FROM events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY sequence",
            args,
        )
        return tuple(
            ActivityEvent.model_validate(
                {**dict(row), "details": json.loads(row["details"])}
            )
            for row in rows
        )

    def close(self) -> None:
        self.db.close()
