# -*- coding: utf-8 -*-
"""Pydantic models with STRICT validation matching the client payload.

The schema is the contract with telemetry/payload.py on the client. We never
trust the client: length caps + type coercion + sane numeric maxima at the
boundary. Implausible values are rejected (422) before they ever touch the DB.
"""

from typing import List, Optional

try:
    # pydantic v2
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_V2 = True
except Exception:                       # pragma: no cover - v1 fallback
    from pydantic import BaseModel, Field, validator as field_validator
    _PYDANTIC_V2 = False


# Sane maxima -- reject implausible submissions outright. Mirrors the client's
# clamp ceilings (telemetry/payload.py) and interface/config.py STATS_MAX_*.
MAX_COUNT = 100_000_000          # 100M catches / puzzles
MAX_RUNTIME_S = 100_000_000.0    # ~3 years of seconds
USERNAME_MAXLEN = 32
HWID_MAXLEN = 64
APP_VERSION_MAXLEN = 32


class SubmitIn(BaseModel):
    """One ranking submission from a client (POST /submit body).

    ``hwid`` carries the random per-install id (the wire field name is kept; it
    is NOT a device hash) and is always present. ``username`` is the OPTIONAL
    self-chosen display name -- it may be absent or empty (anonymous); blank is
    accepted and normalised to ''.
    """

    username: Optional[str] = Field(default='', max_length=USERNAME_MAXLEN)
    hwid: str = Field(min_length=1, max_length=HWID_MAXLEN)
    fishing_catches: int = Field(ge=0, le=MAX_COUNT)
    puzzles_solved: int = Field(ge=0, le=MAX_COUNT)
    fishing_runtime_s: float = Field(ge=0, le=MAX_RUNTIME_S)
    puzzler_runtime_s: float = Field(ge=0, le=MAX_RUNTIME_S)
    app_version: str = Field(min_length=1, max_length=APP_VERSION_MAXLEN)
    ts: int = Field(ge=0, le=4_102_444_800)   # epoch seconds, < year 2100

    @field_validator('username')
    @classmethod
    def _strip_username(cls, v):
        # Strip; ALLOW blank (anonymous) -> ''. The chosen name is opt-in.
        return (v or '').strip()


class LeaderboardEntry(BaseModel):
    """One row on the public leaderboard.

    ``username`` is the DISPLAY name: the chosen name when set + not hidden, else
    the deterministic anonymous funny name derived server-side from the install
    id (so a no-name / hidden-name row still shows a stable label).
    """

    rank: int
    username: str
    fishing_catches: int
    puzzles_solved: int
    fishing_runtime_s: float
    puzzler_runtime_s: float


class LeaderboardSelf(BaseModel):
    """The requesting identity's own ranked row (TRUE rank over the full board).

    Returned alongside the top-N so the client can render replace-Nth-with-self
    when the user's rank falls outside the visible top-N. ``username`` is the
    DISPLAY name (chosen-or-anon). ``null`` when the identity is absent or the
    install is blocked.
    """

    rank: int
    username: str
    fishing_catches: int
    puzzles_solved: int
    fishing_runtime_s: float
    puzzler_runtime_s: float


class LeaderboardOut(BaseModel):
    """GET /leaderboard response envelope.

    ``entries`` is the top-N by catches; ``self`` (additive, optional -- old
    clients ignore it) is the caller's own ranked row when an identity
    (hwid/username) was supplied and is present + not banned.
    """

    period: str
    entries: List[LeaderboardEntry]
    self: Optional[LeaderboardSelf] = None
