"""Small, explicit skill packs for the v2 helper."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    system_prompt: str
    default_queries: tuple[str, ...]
    requires_power_off: bool
    refuse: Callable[[str], str | None]
    voice: str = ''                                   # default server voice for this pack (hello.voice wins)
    guard: Callable[..., str] | None = None           # post-condition on every spoken line: guard(text, question, first)


STYLE = (' Speak one or two sentences per turn. Point and draw only at real things '
         'visible in the scene. Say when unsure; never invent locations.')


def get(pack_id):
    from . import general, pc_build, cooking, assemble, memory
    return {p.id: p for p in (general.PACK, pc_build.PACK, cooking.PACK, assemble.PACK, memory.PACK)}[pack_id]
