"""
A minimal in-process publish/subscribe bus with MQTT topic semantics.

The pipeline only ever talks to this bus. Swapping it for a real MQTT broker
(e.g. Mosquitto on the site gateway) means writing an adapter that forwards
broker messages to `publish` - the pipeline code does not change.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[str, dict[str, Any]], None]


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT matching: `+` matches one level, `#` matches the rest."""
    p_parts, t_parts = pattern.split("/"), topic.split("/")
    for i, p in enumerate(p_parts):
        if p == "#":
            return True
        if i >= len(t_parts):
            return False
        if p != "+" and p != t_parts[i]:
            return False
    return len(p_parts) == len(t_parts)


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._subs[pattern].append(handler)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for pattern, handlers in list(self._subs.items()):
            if topic_matches(pattern, topic):
                for handler in handlers:
                    handler(topic, payload)
