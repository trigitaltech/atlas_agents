from typing import Protocol


class BaseAgent(Protocol):
    async def run(self) -> dict: ...
