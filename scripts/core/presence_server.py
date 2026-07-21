"""SSE-based presence server for real-time collaboration.

Provides Server-Sent Events endpoint for broadcasting user presence
(who is currently editing which section) to all collaborators.

Usage:
    server = PresenceServer()
    server.add_user("paper_001", "alice", section="introduction")
    # In FastAPI/Starlette:
    @app.get("/presence/{paper_id}")
    async def presence_events(paper_id: str):
        return server.create_sse_response(paper_id)
"""

from __future__ import annotations

__all__ = [
    "PresenceEvent",
    "PresenceServer",
]

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator


@dataclass
class PresenceEvent:
    """A presence update event."""
    event_type: str          # "join" | "leave" | "cursor_move" | "heartbeat"
    paper_id: str
    user_id: str
    section: str = ""
    cursor_position: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "event": self.event_type,
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "section": self.section,
            "cursor": self.cursor_position,
            "ts": self.timestamp,
            **self.metadata,
        }, ensure_ascii=False)


class PresenceServer:
    """Manages real-time presence for collaborative paper editing.

    Provides:
    - User join/leave tracking per paper
    - Cursor position broadcasting
    - Heartbeat for connection health
    - SSE (Server-Sent Events) response generator
    """

    def __init__(self, heartbeat_interval: float = 30.0):
        # paper_id -> {user_id -> PresenceEvent}
        self._presence: dict[str, dict[str, PresenceEvent]] = {}

        # paper_id -> list of asyncio.Queue for SSE clients
        self._queues: dict[str, list[asyncio.Queue]] = {}

        self._heartbeat_interval = heartbeat_interval
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the heartbeat task."""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop the presence server."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat events to all clients."""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            for paper_id in list(self._queues.keys()):
                event = PresenceEvent(
                    event_type="heartbeat",
                    paper_id=paper_id,
                    user_id="",
                    timestamp=time.time(),
                )
                await self._broadcast(paper_id, event)

    async def join(self, paper_id: str, user_id: str, section: str = "") -> None:
        """Register a user's presence in a paper."""
        event = PresenceEvent(
            event_type="join",
            paper_id=paper_id,
            user_id=user_id,
            section=section,
        )
        self._presence.setdefault(paper_id, {})[user_id] = event
        await self._broadcast(paper_id, event)

    async def leave(self, paper_id: str, user_id: str) -> None:
        """Remove a user's presence."""
        if paper_id in self._presence and user_id in self._presence[paper_id]:
            del self._presence[paper_id][user_id]
            event = PresenceEvent(
                event_type="leave",
                paper_id=paper_id,
                user_id=user_id,
            )
            await self._broadcast(paper_id, event)

    async def cursor_move(
        self,
        paper_id: str,
        user_id: str,
        section: str,
        position: int,
    ) -> None:
        """Update a user's cursor position."""
        event = PresenceEvent(
            event_type="cursor_move",
            paper_id=paper_id,
            user_id=user_id,
            section=section,
            cursor_position=position,
        )
        self._presence.setdefault(paper_id, {})[user_id] = event
        await self._broadcast(paper_id, event)

    async def _broadcast(self, paper_id: str, event: PresenceEvent) -> None:
        """Send an event to all SSE clients watching a paper."""
        if paper_id not in self._queues:
            return
        data = event.to_json()
        dead = []
        for i, queue in enumerate(self._queues[paper_id]):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                dead.append(i)
        # Remove dead queues
        for i in reversed(dead):
            self._queues[paper_id].pop(i)

    async def subscribe(self, paper_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to presence events for a paper (SSE generator)."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._queues.setdefault(paper_id, []).append(queue)

        try:
            # Send current presence state first
            for event in self._presence.get(paper_id, {}).values():
                yield f"data: {event.to_json()}\n\n"

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=60)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
        finally:
            if paper_id in self._queues and queue in self._queues[paper_id]:
                self._queues[paper_id].remove(queue)

    def get_active_users(self, paper_id: str) -> list[dict[str, Any]]:
        """Get all active users for a paper."""
        return [
            e for e in (
                {
                    "user_id": e.user_id,
                    "section": e.section,
                    "cursor": e.cursor_position,
                    "last_seen": e.timestamp,
                }
                for e in self._presence.get(paper_id, {}).values()
            )
            if time.time() - e["last_seen"] < 120
        ]


if __name__ == "__main__":
    async def demo():
        server = PresenceServer(heartbeat_interval=5.0)
        await server.start()

        # Join users
        await server.join("paper_001", "alice", "introduction")
        await server.join("paper_001", "bob", "methodology")

        # Cursor moves
        await server.cursor_move("paper_001", "alice", "introduction", 100)
        await server.cursor_move("paper_001", "bob", "methodology", 250)

        # Check active users
        users = server.get_active_users("paper_001")
        print(f"Active users: {users}")

        # Subscribe and receive events
        event_count = 0
        async for data in server.subscribe("paper_001"):
            print(f"SSE event: {data.strip()}")
            event_count += 1
            if event_count >= 3:
                break

        await server.stop()
        print("✅ Presence server demo complete")

    asyncio.run(demo())
