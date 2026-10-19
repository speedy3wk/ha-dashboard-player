"""Play queue of HA Dashboard Player."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import random
from typing import Any, Self

from .const import MAX_QUEUE_SIZE


@dataclass(slots=True, eq=False)
class QueueItem:
    """A queued media item.

    `media_content_id` is what the caller requested, `source` is what the card
    loads (possibly a cached media-source id). Compared by identity, so the
    same media can be queued more than once.
    """

    media_content_id: str
    source: str
    kind: str
    title: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create an item from `as_dict` output."""
        return cls(
            media_content_id=str(data["media_content_id"]),
            source=str(data["source"]),
            kind=str(data["kind"]),
            title=data.get("title"),
        )


class MediaQueue:
    """Ordered play queue with shuffle support.

    `items` is the play order. While shuffle is on, `_unshuffled` keeps the
    original order so turning shuffle off restores it.
    """

    def __init__(self) -> None:
        """Initialize an empty queue."""
        self.items: list[QueueItem] = []
        self.index = 0
        self._unshuffled: list[QueueItem] | None = None

    def __len__(self) -> int:
        """Return the number of queued items."""
        return len(self.items)

    @property
    def shuffle(self) -> bool:
        """Return whether shuffle is on."""
        return self._unshuffled is not None

    @property
    def current(self) -> QueueItem | None:
        """Return the current item."""
        return self.items[self.index] if self.items else None

    def replace(self, new: list[QueueItem]) -> int:
        """Replace the queue and start at its first item."""
        new = new[:MAX_QUEUE_SIZE]
        self.items = list(new)
        self.index = 0
        if self.shuffle:
            self._unshuffled = list(new)
            random.shuffle(self.items)
        return len(new)

    def add(self, new: list[QueueItem]) -> int:
        """Append items to the end of the queue."""
        new = self._fit(new)
        if self.shuffle and self.items:
            upcoming = self.items[self.index + 1 :] + new
            random.shuffle(upcoming)
            self.items[self.index + 1 :] = upcoming
        else:
            self.items.extend(new)
        if self._unshuffled is not None:
            self._unshuffled.extend(new)
        return len(new)

    def insert_next(self, new: list[QueueItem]) -> int:
        """Insert items right after the current item."""
        new = self._fit(new)
        if not self.items:
            return self.add(new)
        self.items[self.index + 1 : self.index + 1] = new
        if self._unshuffled is not None:
            position = self._position(self._unshuffled, self.current) + 1
            self._unshuffled[position:position] = new
        return len(new)

    def play_now(self, new: list[QueueItem]) -> int:
        """Insert items after the current item and jump to the first of them."""
        was_empty = not self.items
        added = self.insert_next(new)
        if added and not was_empty:
            self.index += 1
        return added

    def advance(self, wrap: bool) -> bool:
        """Go to the next item; wrap to the start when `wrap` is set."""
        if self.index + 1 < len(self.items):
            self.index += 1
            return True
        if wrap and self.items:
            self.index = 0
            return True
        return False

    def previous(self, wrap: bool) -> bool:
        """Go to the previous item; wrap to the end when `wrap` is set."""
        if self.index > 0:
            self.index -= 1
            return True
        if wrap and len(self.items) > 1:
            self.index = len(self.items) - 1
            return True
        return False

    def has_next(self, wrap: bool) -> bool:
        """Return whether `advance` would move to another item."""
        return self.index + 1 < len(self.items) or (wrap and len(self.items) > 1)

    def clear_upcoming(self) -> None:
        """Keep only the current item."""
        current = self.current
        self.items = [current] if current else []
        self.index = 0
        if self._unshuffled is not None:
            self._unshuffled = list(self.items)

    def clear(self) -> None:
        """Remove all items; the shuffle setting is kept."""
        self.items = []
        self.index = 0
        if self._unshuffled is not None:
            self._unshuffled = []

    def set_shuffle(self, shuffle: bool) -> None:
        """Turn shuffle on or off, keeping the current item."""
        if shuffle == self.shuffle:
            return
        current = self.current
        if shuffle:
            self._unshuffled = list(self.items)
            if current is None:
                return
            upcoming = [item for item in self.items if item is not current]
            random.shuffle(upcoming)
            self.items = [current, *upcoming]
            self.index = 0
            return
        self.items = self._unshuffled or []
        self._unshuffled = None
        self.index = self._position(self.items, current) if current else 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return {
            "items": [item.as_dict() for item in self.items],
            "index": self.index,
            "unshuffled": (
                [self._position(self.items, item) for item in self._unshuffled]
                if self._unshuffled is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self | None:
        """Create a queue from `as_dict` output; None if the data is invalid."""
        try:
            items = [QueueItem.from_dict(item) for item in data["items"]]
            index = int(data.get("index", 0))
            order = data.get("unshuffled")
            unshuffled = [items[i] for i in order] if order is not None else None
        except KeyError, IndexError, TypeError, ValueError:
            return None
        queue = cls()
        queue.items = items[:MAX_QUEUE_SIZE]
        queue.index = min(max(index, 0), max(len(queue.items) - 1, 0))
        if unshuffled is not None:
            queue._unshuffled = [item for item in unshuffled if item in queue.items]
        return queue

    def _fit(self, new: list[QueueItem]) -> list[QueueItem]:
        return new[: max(MAX_QUEUE_SIZE - len(self.items), 0)]

    @staticmethod
    def _position(items: list[QueueItem], item: QueueItem | None) -> int:
        return next(i for i, candidate in enumerate(items) if candidate is item)
