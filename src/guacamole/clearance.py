"""Clearance: which providers and projects may receive labelled library content.

A library pin carries its snapshot's label. Every record built on a pin, however
indirectly (an extracted excerpt, a requirement quoting it, a tool result, a
summary), carries that label too, found through the dependencies the store
already keeps. Before a packet goes to a provider, everything whose content it
shows must be within the provider's clearance.
"""

from collections.abc import Iterable

from .context import ProviderError
from .contracts import LEVELS, Label, Ref
from .storage import Store
from .tools.registry import encode

PUBLIC = Label(level="public")


class ClearanceBlocked(ProviderError):
    """A packet held content its provider is not cleared to receive; nothing was sent."""


def permits(holder: Label, label: Label) -> bool:
    """Whether a holder may receive content: at or above its level, every compartment held."""
    return LEVELS.index(label.level) <= LEVELS.index(holder.level) and set(
        label.compartments
    ) <= set(holder.compartments)


def join(labels: Iterable[Label]) -> Label:
    """The label of content combined from these: the highest level, every compartment."""
    labels = list(labels)
    return Label(
        level=max((l.level for l in labels), key=LEVELS.index, default="public"),
        compartments=tuple(sorted({c for l in labels for c in l.compartments})),
    )


def label_of(store: Store, ref: Ref, memo: dict[tuple[str, str, int], Label]) -> Label:
    """A record's label: its own if it is a library pin, else its dependencies' join."""
    key = (ref.kind, ref.id, ref.revision)
    if key not in memo:
        memo[key] = PUBLIC  # Breaks a cycle; dependencies only point back in time
        snapshot = store.resolve(ref)
        if snapshot.data.get("kind") == "library_pin":
            memo[key] = Label.model_validate_json(encode(snapshot.data["label"]))
        else:
            memo[key] = join(label_of(store, d, memo) for d in snapshot.dependencies)
    return memo[key]


def check(store: Store, refs: Iterable[Ref], holder: Label, provider: str) -> None:
    """Refuse when any of refs carries content beyond the provider's clearance."""
    memo: dict[tuple[str, str, int], Label] = {}
    for ref in refs:
        label = label_of(store, ref, memo)
        if not permits(holder, label):
            beyond = sorted(set(label.compartments) - set(holder.compartments))
            raise ClearanceBlocked(
                f"{ref.kind}:{ref.id} carries {label.level} content"
                + (f" in {', '.join(beyond)}" if beyond else "")
                + f"; {provider} is cleared to {holder.level}"
                + (
                    f" with {', '.join(holder.compartments)}"
                    if holder.compartments
                    else ""
                )
                + ". Route this work to a cleared tier or ask the human."
            )
