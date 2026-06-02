# -*- coding: utf-8 -*-
"""Deterministic ANON-NAME generator + collision heuristic (SERVER copy).

From a random install id derive a stable, funny Metin2-/fishing-themed BASE
display name from a fixed pool of 100 (e.g. ``GoldenTuna``, ``NemereSlayer``).
The SAME install id always yields the SAME base name. Names are language-neutral
gaming proper-nouns, so ``lang`` is accepted for signature compatibility but
ignored.

``anon_name`` returns only the BASE name (no suffix). With a 100-name pool,
collisions are expected, so the leaderboard aggregation in ``db.py`` calls
``disambiguate`` to keep every board label unique WITHOUT ugly digits:

  * the EARLIEST install (by first-seen ts) keeps the bare name;
  * the next ones get an ADJECTIVE prefix ("MightyGoldenTuna", "FrostGoldenTuna")
    -- 100 adjectives x 100 names = ~10,000 clean, digit-free names;
  * only past that (>~10k installs sharing ONE base -- never in practice) a small
    cycle number is appended.

This staged heuristic lives server-side because only the aggregation can see all
installs + their order.

Derivation of the base (deterministic, never raises):
  * ``h = sha256(install_id).digest()``  ->  name index = ``int(h[0:8])`` mod 100

NOTE: ``telemetry/anon_name.py`` on the client holds the SAME ``NAMES`` + base
``anon_name`` (import-isolated -> duplicated). The client never disambiguates (it
shows the server's ``display_name``), so ``ADJECTIVES``/``disambiguate`` are
server-only. A shared test vector pins the base ``anon_name`` so the two copies
can never silently drift.
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

# 100 adjective prefixes for collision disambiguation (Tier 2). They compound
# onto a base name -> "MightyGoldenTuna". 100 x 100 names = ~10,000 digit-free
# names. Fun / Metin2- / fishing-flavoured so the result still reads like a name.
ADJECTIVES = (
    'Mighty', 'Golden', 'Silver', 'Bronze', 'Iron', 'Steel', 'Frost', 'Flame',
    'Shadow', 'Storm', 'Thunder', 'Crimson', 'Azure', 'Emerald', 'Jade', 'Ruby',
    'Onyx', 'Obsidian', 'Marble', 'Crystal', 'Royal', 'Noble', 'Savage', 'Feral',
    'Rabid', 'Swift', 'Silent', 'Lucky', 'Cursed', 'Blessed', 'Ancient', 'Mystic',
    'Arcane', 'Holy', 'Demonic', 'Divine', 'Infernal', 'Eternal', 'Spectral',
    'Phantom', 'Epic', 'Legendary', 'Mythic', 'Heroic', 'Vile', 'Grim', 'Sly',
    'Nimble', 'Hardy', 'Fierce', 'Bold', 'Brave', 'Wild', 'Mad', 'Cosmic',
    'Lunar', 'Solar', 'Stellar', 'Astral', 'Radiant', 'Toxic', 'Venom', 'Spicy',
    'Salty', 'Sweet', 'Sour', 'Bitter', 'Smoky', 'Frosty', 'Sunny', 'Stormy',
    'Misty', 'Rusty', 'Shiny', 'Dusty', 'Chonky', 'Tiny', 'Giant', 'Mega',
    'Ultra', 'Hyper', 'Turbo', 'Nitro', 'Atomic', 'Quantum', 'Glacial',
    'Volcanic', 'Tidal', 'Abyssal', 'Coral', 'Pearly', 'Gloomy', 'Fluffy',
    'Scaly', 'Slimy', 'Prickly', 'Sneaky', 'Drunken', 'Snoozy', 'Cranky',
)


def _digest(install_id):
    """sha256 digest of ``install_id`` (or its repr on junk). Never raises."""
    try:
        data = install_id.encode('utf-8', 'replace')
    except Exception:
        data = repr(install_id).encode('utf-8', 'replace')
    return hashlib.sha256(data).digest()


def anon_name(install_id, lang='en'):
    """Return the stable funny BASE name for ``install_id`` (NO suffix).

    Deterministic for a given ``install_id``. ``lang`` is accepted for signature
    compatibility but ignored (names are language-neutral). Pure, never raises.
    The Tier-2/3 disambiguation is added by :func:`disambiguate`.
    """
    h = _digest(install_id)
    return NAMES[int.from_bytes(h[0:8], 'big') % len(NAMES)]


def disambiguate(base, position):
    """Distinct display name for the ``position``-th install sharing ``base``.

    ``position`` is 0-based, ordered by first-seen ts (the aggregation passes it):

      * ``0``                         -> the bare ``base`` ("GoldenTuna") -- 1st;
      * ``1 .. len(ADJECTIVES)``      -> adjective prefix ("MightyGoldenTuna"),
                                         ~100*100 = 10k clean, digit-free names;
      * beyond that                   -> a cycle number ("MightyGoldenTuna2"),
                                         only at >~10k installs sharing ONE base.

    Pure + deterministic for a given ``(base, position)``; never raises.
    """
    try:
        position = int(position)
    except Exception:
        position = 0
    if position <= 0:
        return base
    idx = (position - 1) % len(ADJECTIVES)
    cycle = (position - 1) // len(ADJECTIVES)
    name = ADJECTIVES[idx] + base
    return name if not cycle else '{}{}'.format(name, cycle + 1)


__all__ = ['NAMES', 'ADJECTIVES', 'anon_name', 'disambiguate']
