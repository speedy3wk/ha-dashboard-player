"""Play queue tests."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.ha_dashboard_player.const import MAX_QUEUE_SIZE
from custom_components.ha_dashboard_player.queue import MediaQueue, QueueItem


def _items(*names: str) -> list[QueueItem]:
    return [QueueItem(name, name, "video", name) for name in names]


def _ids(queue: MediaQueue) -> list[str]:
    return [item.media_content_id for item in queue.items]


def test_replace_add_next_play() -> None:
    """The enqueue modes insert at the expected positions."""
    queue = MediaQueue()
    assert queue.current is None
    queue.add(_items("a"))
    assert queue.current.media_content_id == "a"

    queue.replace(_items("b", "c"))
    assert _ids(queue) == ["b", "c"]
    assert queue.current.media_content_id == "b"

    queue.add(_items("d"))
    queue.insert_next(_items("e"))
    assert _ids(queue) == ["b", "e", "c", "d"]
    assert queue.current.media_content_id == "b"

    queue.play_now(_items("f"))
    assert _ids(queue) == ["b", "f", "e", "c", "d"]
    assert queue.current.media_content_id == "f"


def test_play_now_on_empty_queue() -> None:
    """play_now on an empty queue plays the first new item."""
    queue = MediaQueue()
    queue.play_now(_items("a", "b"))
    assert queue.current.media_content_id == "a"


def test_advance_and_previous() -> None:
    """Navigation stops at the ends unless wrapping."""
    queue = MediaQueue()
    queue.replace(_items("a", "b"))
    assert not queue.previous(wrap=False)
    assert queue.previous(wrap=True)
    assert queue.current.media_content_id == "b"
    assert not queue.has_next(wrap=False)
    assert not queue.advance(wrap=False)
    assert queue.has_next(wrap=True)
    assert queue.advance(wrap=True)
    assert queue.current.media_content_id == "a"
    assert queue.advance(wrap=False)
    assert queue.current.media_content_id == "b"


def test_single_item_does_not_wrap_previous() -> None:
    """A single item has no other item to go to."""
    queue = MediaQueue()
    queue.replace(_items("a"))
    assert not queue.previous(wrap=True)
    assert not queue.has_next(wrap=True)
    assert queue.advance(wrap=True)


def test_duplicates_are_distinct() -> None:
    """The same media can be queued twice."""
    queue = MediaQueue()
    queue.replace(_items("a", "a"))
    queue.advance(wrap=False)
    queue.set_shuffle(True)
    queue.set_shuffle(False)
    assert queue.index == 1


def test_shuffle_keeps_current_and_restores_order() -> None:
    """Shuffle starts with the current item, unshuffle restores the order."""
    queue = MediaQueue()
    queue.replace(_items("a", "b", "c", "d"))
    queue.advance(wrap=False)
    with patch("random.shuffle", side_effect=lambda items: items.reverse()):
        queue.set_shuffle(True)
    assert queue.shuffle
    assert _ids(queue) == ["b", "d", "c", "a"]
    assert queue.index == 0

    queue.insert_next(_items("x"))
    queue.set_shuffle(False)
    assert _ids(queue) == ["a", "b", "x", "c", "d"]
    assert queue.current.media_content_id == "b"


def test_shuffle_add_and_replace() -> None:
    """Items added while shuffled join the upcoming items and the original order."""
    queue = MediaQueue()
    queue.set_shuffle(True)
    with patch("random.shuffle", side_effect=lambda items: items.reverse()):
        queue.replace(_items("a", "b", "c"))
        assert _ids(queue) == ["c", "b", "a"]
        queue.add(_items("d"))
    assert _ids(queue) == ["c", "d", "a", "b"]
    queue.set_shuffle(False)
    assert _ids(queue) == ["a", "b", "c", "d"]
    assert queue.current.media_content_id == "c"


def test_clear_upcoming_and_clear() -> None:
    """clear_upcoming keeps the current item, clear removes everything."""
    queue = MediaQueue()
    queue.replace(_items("a", "b", "c"))
    queue.advance(wrap=False)
    queue.set_shuffle(True)
    queue.clear_upcoming()
    assert _ids(queue) == ["b"]
    queue.set_shuffle(False)
    assert _ids(queue) == ["b"]
    queue.clear()
    assert len(queue) == 0
    assert queue.current is None


def test_size_limit() -> None:
    """The queue never grows beyond the limit."""
    queue = MediaQueue()
    names = [str(i) for i in range(MAX_QUEUE_SIZE + 5)]
    assert queue.replace(_items(*names)) == MAX_QUEUE_SIZE
    assert queue.add(_items("x")) == 0
    assert queue.insert_next(_items("y")) == 0
    assert len(queue) == MAX_QUEUE_SIZE


def test_serialization_round_trip() -> None:
    """The queue survives as_dict/from_dict including the shuffle order."""
    queue = MediaQueue()
    queue.replace(_items("a", "b", "c"))
    queue.advance(wrap=False)
    with patch("random.shuffle", side_effect=lambda items: items.reverse()):
        queue.set_shuffle(True)

    restored = MediaQueue.from_dict(queue.as_dict())
    assert restored is not None
    assert _ids(restored) == _ids(queue)
    assert restored.current.media_content_id == "b"
    assert restored.current.title == "b"
    restored.set_shuffle(False)
    assert _ids(restored) == ["a", "b", "c"]
    assert restored.current.media_content_id == "b"


def test_from_dict_invalid() -> None:
    """Broken stored data is ignored, the index is clamped."""
    assert MediaQueue.from_dict(None) is None
    assert MediaQueue.from_dict({"items": [{"source": "x"}]}) is None
    assert MediaQueue.from_dict({"items": [], "unshuffled": [3]}) is None
    queue = MediaQueue.from_dict(
        {
            "items": [{"media_content_id": "a", "source": "a", "kind": "video"}],
            "index": 9,
        }
    )
    assert queue is not None
    assert queue.index == 0
