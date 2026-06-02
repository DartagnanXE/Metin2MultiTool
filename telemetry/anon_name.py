# -*- coding: utf-8 -*-
"""Deterministic ANON-NAME generator (PURE, stdlib-only).

From a random install id derive a stable, funny Metin2-/fishing-themed display
name picked from a fixed pool of 100 (e.g. ``GoldenTuna``, ``NemereSlayer``). The
SAME install id always yields the SAME base name; different ids (almost surely)
differ. Names are language-neutral gaming proper-nouns, so ``lang`` is accepted
for signature compatibility but ignored.

NO numeric suffix is attached here -- the pool has only 100 entries, so
collisions are EXPECTED. DISAMBIGUATION ("GoldenTuna", "GoldenTuna2", ...) is
done SERVER-SIDE in the leaderboard aggregation (``server/app/db.py``), the only
place that sees all installs and can order them by who-appeared-first. The client
never computes a name (the board always shows the server's ``display_name``);
this copy exists only to pin the shared base-name test vector.

Derivation (deterministic, never raises):
  * ``h = sha256(install_id).digest()``
  * name index = ``int(h[0:8])`` mod 100
On a junk id (non-str / unhashable) it falls back to hashing ``repr(id)``.

NOTE: a logically-identical copy lives in ``server/app/anon_name.py`` (the server
package is import-isolated from ``telemetry/``, so the code is duplicated). The
two are NOT byte-identical (docstrings differ); a shared test vector pins the
OUTPUT so they can never silently drift.
"""

import hashlib

# 100 fixed, funny Metin2-/fishing-themed display names (language-neutral).
# The ORDER is part of the contract: index = sha256(install_id) mod 100, so
# reordering/editing remaps existing installs to new names (fine pre-launch).
NAMES = (
    'GoldenTuna', 'SleepyCarp', 'DrunkenAngler', 'LuckyHook', 'GrumpyCatfish',
    'NoobBaiter', 'MasterReeler', 'TunaTornado', 'CarpDiem', 'BassBoss',
    'PikePunisher', 'EelEnjoyer', 'TroutScout', 'SalmonSensei', 'FishyBusiness',
    'BaitGod', 'HookHero', 'ReelDeal', 'CastAway', 'FloatKing',
    'LureLord', 'SushiThief', 'SlipperyEel', 'ChonkyCarp', 'ThiccTuna',
    'BabyShark', 'KrakenKisser', 'SquidSquad', 'PearlPincher', 'KelpieKeeper',
    'CarbonRodPro', 'GoldenScale', 'SilverFin', 'DeepDiver', 'AbyssAngler',
    'HarpoonHomie', 'NetNinja', 'TideTurner', 'WaveWrecker', 'ReefRogue',
    'MetinSmasher', 'StoneBreaker', 'MetinHunter', 'NemereSlayer', 'RazadorRekt',
    'MeleyMauler', 'TartarosTamer', 'EnkaEnjoyer', 'HydraHugger', 'BeranBopper',
    'HwanaHunter', 'NymphNapper', 'SetenSlapper', 'SuraSupreme', 'NinjaNoodle',
    'WarriorWeeb', 'ShamanSlapper', 'LycanLover', 'ShinsooSoldier', 'ChunjoChamp',
    'JinnoJester', 'BoarBuster', 'WolfWhisperer', 'SpiderSquasher', 'ZombieZapper',
    'OrcOverlord', 'BerserkerBro', 'TigerTickler', 'DragonDuelist', 'MountMaster',
    'HorseHugger', 'YangFarmer', 'WonWaster', 'MetinMagnet', 'ExpGrinder',
    'AFKFisher', 'BotBuster', 'UpgradeFail', 'PlusNineCurse', 'BlessedScroll',
    'MoonlightMage', 'DesertDrifter', 'SnowSneak', 'TempleThief', 'ValleyViper',
    'CritKitten', 'DropHunter', 'LagLord', 'PingPenguin', 'RareDropRon',
    'GoldGoblin', 'PotionGulper', 'BuffBandit', 'SkillSpammer', 'ComboKing',
    'RespawnRyu', 'GankGremlin', 'LootLlama', 'QuestQuitter', 'FinalBossFish',
)


def _digest(install_id):
    """sha256 digest of ``install_id`` (or its repr on junk). Never raises."""
    try:
        data = install_id.encode('utf-8', 'replace')
    except Exception:
        data = repr(install_id).encode('utf-8', 'replace')
    return hashlib.sha256(data).digest()


def anon_name(install_id, lang='en'):
    """Return the stable funny BASE name for ``install_id`` (NO numeric suffix).

    Deterministic for a given ``install_id``; different ids (almost surely)
    differ. ``lang`` is accepted for signature compatibility but ignored (names
    are language-neutral). Pure, no I/O, never raises. Collision disambiguation
    (the trailing 2/3/...) is the SERVER aggregation's job, not this function's.
    """
    h = _digest(install_id)
    return NAMES[int.from_bytes(h[0:8], 'big') % len(NAMES)]


__all__ = ['NAMES', 'anon_name']
