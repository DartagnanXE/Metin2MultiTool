# -*- coding: utf-8 -*-
"""Inventory-management model + image variants (Pillow, NO Tk).

Every managed item is shown (in the Inventory view) as a small image that cycles
through THREE states on click:

    KEEP     (0): icon at full brightness          -> keep it
    REMOVE   (1): icon greyed + faded              -> remove it
    CAMPFIRE (2): icon with a flame drawn over it  -> into the campfire

After a scan, the recognised STACK COUNT is drawn over each icon (bottom-right,
game style) in every state; 0 shows nothing. Lagerfeuer (the campfire you
process WITH) is excluded as a tool; baits (Worm) STACK so they stay. Fish first,
the rest grouped by kind (dyes, keys, rings, boxes, ...). Item names localise to
the official German Metin2 names on hover.

PURE, Tk-free parts live here (unit-testable): order, state cycle, item set,
localised names, and the Pillow image variants / number overlay / legend image.
The Tk grid + the placeholder apply live on ``InventoryViewMixin``.
"""

import os

try:
    from PIL import Image, ImageDraw, ImageOps, ImageFont
    _HAS_PIL = True
except Exception:                       # pragma: no cover - headless/no Pillow
    _HAS_PIL = False

# Three cycle states.
KEEP, REMOVE, CAMPFIRE = 0, 1, 2
_NUM_STATES = 3

# Items recognised as 'fish' (the actual catch) -> listed FIRST.
FISH = frozenset({
    'Brook_Trout', 'Carp', 'Catfish', 'Eel', 'Goldfish', 'Grass_Carp',
    'Large_Zander', 'Lotus_Fish', 'Mandarin_Fish', 'Mirror_Carp', 'Perch',
    'Rainbow_Trout', 'Red_King_Crab', 'River_Trout', 'Rudd', 'Salmon', 'Shiri',
    'Skygazer', 'Smelt', 'Snakehead', 'Sweetfish', 'Tenchi', 'Yabby', 'Zander',
})

# Nothing is hard-excluded any more -- EVERY item shows in the grid. What a click
# can DO is gated per item instead (see :func:`allowed_states`).
EXCLUDE = frozenset()

# Tools/specials shown but NOT changeable (always 'keep' -- you only SEE + count
# them): the campfire itself, the baits you fish with, the puzzle boxes.
FIXED_KEEP = frozenset({
    'Lagerfeuer', 'Worm', 'Fischpuzzlebox', 'Fischpuzzlebox_Deluxe',
})

# Items that may be sent to the CAMPFIRE (grillable at the Lagerfeuer). The German
# Metin2 wiki confirms EVERY one of the 24 fish grills (alive/dead/grilled state,
# incl. the crustaceans + the rare fish) and NO special drop / tool does -- so
# this is exactly the fish set.
BURNABLE = frozenset(FISH)

# Localised display names (EN, DE) -- the German column is the official Metin2
# name (verified via the DE Metin2 wiki). Unlisted items fall back to a
# prettified icon stem.
ITEM_NAMES = {
    'Brook_Trout': ('Brook Trout', 'Bachforelle'),
    'Carp': ('Carp', 'Karpfen'),
    'Catfish': ('Catfish', 'Wels'),
    'Eel': ('Eel', 'Aal'),
    'Goldfish': ('Goldfish', 'Goldfisch'),
    'Grass_Carp': ('Grass Carp', 'Graskarpfen'),
    'Large_Zander': ('Large Zander', 'Großer Zander'),
    'Lotus_Fish': ('Lotus Fish', 'Lotusfisch'),
    'Mandarin_Fish': ('Mandarin Fish', 'Mandarinfisch'),
    'Mirror_Carp': ('Mirror Carp', 'Spiegelkarpfen'),
    'Perch': ('Perch', 'Barsch'),
    'Rainbow_Trout': ('Rainbow Trout', 'Regenbogenforelle'),
    'Red_King_Crab': ('Red King Crab', 'Königskrabbe'),
    'River_Trout': ('River Trout', 'Flussforelle'),
    'Rudd': ('Rudd', 'Rotfeder'),
    'Salmon': ('Salmon', 'Lachs'),
    'Shiri': ('Shiri', 'Shiri'),
    'Skygazer': ('Skygazer', 'Skygazer'),
    'Smelt': ('Smelt', 'Stint'),
    'Snakehead': ('Snakehead', 'Schlangenkopffisch'),
    'Sweetfish': ('Sweetfish', 'Ayu'),
    'Tenchi': ('Tenchi', 'Tenchi'),
    'Yabby': ('Yabby', 'Yabbie-Krebs'),
    'Zander': ('Zander', 'Zander'),
    'Black_Hair_Dye': ('Black Hair Dye', 'Schwarzes Haarfärbemittel'),
    'Blonde_Hair_Dye': ('Blonde Hair Dye', 'Blondes Haarfärbemittel'),
    'Brown_Hair_Dye': ('Brown Hair Dye', 'Braunes Haarfärbemittel'),
    'Red_Hair_Dye': ('Red Hair Dye', 'Rotes Haarfärbemittel'),
    'White_Hair_Dye': ('White Hair Dye', 'Weißes Haarfärbemittel'),
    'Bleach': ('Bleach', 'Bleichmittel'),
    'Cloak_of_Secrecy': ('Cloak of Secrecy', 'Tarnumhang'),
    'Fischpuzzlebox': ('Fish Puzzle Box', 'Fischpuzzlebox'),
    'Fischpuzzlebox_Deluxe': ('Fish Puzzle Box Deluxe', 'Fischpuzzlebox Deluxe'),
    'Gold_Key': ('Gold Key', 'Goldener Schlüssel'),
    'Silver_Key': ('Silver Key', 'Silberner Schlüssel'),
    'Kelpie_Key': ('Kelpie Key', 'Wassernixenschlüssel'),
    'Gold_Ring': ('Gold Ring', 'Goldring'),
    "Lucy's_Ring": ("Lucy's Ring", 'Lucys Ring'),
    'Lump_of_Gold': ('Lump of Gold', 'Goldklumpen'),
    "Sage_King's_Glove": ("Sage King's Glove", 'Handschuh weiser Kaiser'),
    'Sage_King_Symbol': ('Sage King Symbol', 'Symbol d. weisen Kaisers'),
}

# Legend labels per state (EN, DE).
LEGEND_LABELS = {
    'en': ('Keep', 'Remove', 'Campfire'),
    'de': ('Behalten', 'Entfernen', 'Lagerfeuer'),
}


def cycle_state(state):
    """Raw next state in the keep -> remove -> campfire -> keep cycle (ignores
    per-item rules). Never raises."""
    try:
        return (int(state) + 1) % _NUM_STATES
    except Exception:
        return KEEP


def allowed_states(name):
    """The states ``name`` may take, in click-cycle order:

      * ``FIXED_KEEP`` (campfire / baits / puzzle boxes -- tools & specials you
        only SEE + count): ``(KEEP,)`` -- a click changes nothing.
      * ``BURNABLE`` (grillable at the campfire -- the fish):
        ``(KEEP, REMOVE, CAMPFIRE)``.
      * everything else (dyes, keys, rings, ...): ``(KEEP, REMOVE)`` -- may be
        removed but NOT burned.
    """
    if name in FIXED_KEEP:
        return (KEEP,)
    if name in BURNABLE:
        return (KEEP, REMOVE, CAMPFIRE)
    return (KEEP, REMOVE)


def next_state(name, current):
    """Next state for ``name`` cycling WITHIN its allowed states (wraps). A fixed
    item always stays on ``KEEP``. Never raises."""
    states = allowed_states(name)
    try:
        return states[(states.index(int(current)) + 1) % len(states)]
    except Exception:
        return states[0]


def pretty_name(name):
    """'Red_King_Crab' -> 'Red King Crab' (fallback display)."""
    return str(name).replace('_', ' ')


def localized_name(name):
    """Display name for ``name`` in the CURRENT UI language (DE -> the official
    Metin2 name). Falls back to the prettified stem. Never raises."""
    en, de = ITEM_NAMES.get(name, (pretty_name(name), pretty_name(name)))
    try:
        from i18n import get_lang
        return de if get_lang() == 'de' else en
    except Exception:
        return en


def _category(name):
    """Sort bucket for the non-fish 'rest' so same-kind items group together."""
    if name.endswith('Hair_Dye') or name == 'Bleach':
        return 0                                   # hair dyes / bleach
    if name.endswith('Key'):
        return 1                                   # keys
    if name.endswith('Ring'):
        return 2                                   # rings
    if name.startswith('Fischpuzzlebox'):
        return 3                                   # puzzle boxes
    if name.startswith('Sage_King'):
        return 4                                   # Sage King set
    if 'Gold' in name:
        return 5                                   # gold (lump)
    return 6                                       # misc (cloak, ...)


def item_order(names):
    """Fish first (A->Z), then the rest grouped by kind then A->Z. Tools in
    ``EXCLUDE`` are dropped. Pure + deterministic."""
    names = [n for n in names if n not in EXCLUDE]
    fish = sorted(n for n in names if n in FISH)
    rest = sorted((n for n in names if n not in FISH),
                  key=lambda n: (_category(n), n))
    return fish + rest


def _icon_dir():
    from respath import resource_path
    return resource_path('inventory_icons')


def available_items():
    """All managed item names (icon stems minus tools), in display order. ``[]``
    if the icon directory is unreadable. Never raises."""
    try:
        files = os.listdir(_icon_dir())
    except Exception:
        return []
    names = [f[:-4] for f in files if f.lower().endswith('.png')]
    return item_order(names)


# -- Pillow image variants / overlays (no Tk) ----------------------------

def load_icon(name, px):
    """Load + square-resize a bundled icon to ``px``. ``None`` if unreadable or
    Pillow is missing. Never raises."""
    if not _HAS_PIL:
        return None
    try:
        path = os.path.join(_icon_dir(), name + '.png')
        return Image.open(path).convert('RGBA').resize((px, px))
    except Exception:
        return None


def make_flame(px):
    """A small orange/yellow flame glyph (RGBA ``px`` square) for the CAMPFIRE
    state. ``None`` if Pillow is missing. Never raises."""
    if not _HAS_PIL:
        return None
    try:
        f = Image.new('RGBA', (px, px), (0, 0, 0, 0))
        d = ImageDraw.Draw(f)
        w = h = float(px)
        cx = w / 2.0
        d.polygon([(cx, h * 0.12), (w * 0.80, h * 0.52), (w * 0.72, h * 0.85),
                   (cx, h * 0.96), (w * 0.28, h * 0.85), (w * 0.20, h * 0.52)],
                  fill=(255, 110, 20, 205))
        d.polygon([(cx, h * 0.40), (w * 0.64, h * 0.64), (cx, h * 0.88),
                   (w * 0.36, h * 0.64)], fill=(255, 212, 64, 230))
        return f
    except Exception:
        return None


def variants(name, px, flame=None):
    """``(keep, remove, campfire)`` BASE Pillow images for ``name`` at ``px`` (no
    count). ``(None, None, None)`` if the icon can't load. Never raises."""
    base = load_icon(name, px)
    if base is None:
        return (None, None, None)
    try:
        grey = ImageOps.grayscale(base).convert('RGBA')
        grey.putalpha(base.split()[3].point(lambda v: int(v * 0.35)))
        fire = base.copy()
        fire.putalpha(fire.split()[3].point(lambda v: int(v * 0.80)))
        if flame is None:
            flame = make_flame(px)
        if flame is not None:
            fire.alpha_composite(flame)
        return (base, grey, fire)
    except Exception:
        return (base, base, base)


def _font(size):
    """A bold-ish TrueType font at ``size`` (DejaVu/Arial), else the bitmap
    default. ``None`` if Pillow is missing. Never raises."""
    if not _HAS_PIL:
        return None
    for fname in ('DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'arialbd.ttf',
                  'arial.ttf'):
        try:
            return ImageFont.truetype(fname, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
    except Exception:
        return None


def _count_font(px):
    return _font(max(11, int(px * 0.42)))


def count_overlay(count, px):
    """RGBA ``px`` overlay with ``count`` bottom-right in white + a dark outline
    (game stack-number style). ``None`` for count<=0 / no Pillow. Never raises."""
    if not _HAS_PIL or not count or int(count) <= 0:
        return None
    try:
        o = Image.new('RGBA', (px, px), (0, 0, 0, 0))
        d = ImageDraw.Draw(o)
        s = str(int(count))
        font = _count_font(px)
        bbox = d.textbbox((0, 0), s, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = px - tw - bbox[0] - 2
        y = px - th - bbox[1] - 1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    d.text((x + dx, y + dy), s, font=font, fill=(0, 0, 0, 255))
        d.text((x, y), s, font=font, fill=(255, 255, 255, 255))
        return o
    except Exception:
        return None


def apply_count(variant, count, px):
    """A copy of ``variant`` with the stack ``count`` drawn over it. Unchanged
    copy when count<=0. Never raises."""
    if variant is None:
        return None
    try:
        out = variant.copy()
        ov = count_overlay(count, px)
        if ov is not None:
            out.alpha_composite(ov)
        return out
    except Exception:
        return variant


def legend_image(px=40, lang='en', sample='Carp', borders=None):
    """A self-contained legend: the ``sample`` fish in all 3 states side by side,
    EACH in its state-coloured rounded frame (matching the grid borders: keep /
    remove / campfire) + labelled underneath (localised). Cells are sized to the
    widest label so German words never overlap. ``borders`` = (keep, remove,
    campfire) colours, defaulting to teal/grey/amber. RGBA Pillow image or
    ``None``."""
    keep, remove, fire = variants(sample, px)
    if keep is None:
        return None
    try:
        labels = LEGEND_LABELS.get(lang, LEGEND_LABELS['en'])
        cols = borders or ('#2dd4bf', '#6b7280', '#f59e0b')
        font = _font(13)
        probe = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        lab_w = [probe.textbbox((0, 0), s, font=font)[2] for s in labels]
        bd = 4
        tile = px + 2 * bd                          # icon + state-colour frame
        cell = max(tile, max(lab_w)) + 16
        lab_h, pad = 18, 8
        w, h = cell * 3, tile + lab_h + pad
        img = Image.new('RGBA', (w, h), (24, 28, 36, 255))
        d = ImageDraw.Draw(img)
        for i, (variant, label, color) in enumerate(
                zip((keep, remove, fire), labels, cols)):
            cx = i * cell + cell // 2
            fx, fy = cx - tile // 2, pad // 2
            box = [fx, fy, fx + tile - 1, fy + tile - 1]
            try:
                d.rounded_rectangle(box, radius=6, outline=color, width=2,
                                    fill=(40, 46, 58, 255))
            except Exception:
                d.rectangle(box, outline=color, width=2, fill=(40, 46, 58, 255))
            img.alpha_composite(variant, (cx - px // 2, fy + bd))
            bbox = d.textbbox((0, 0), label, font=font)
            lw = bbox[2] - bbox[0]
            d.text((cx - lw // 2 - bbox[0], tile + pad // 2 + 2),
                   label, font=font, fill=(225, 225, 225, 255))
        return img
    except Exception:
        return None


__all__ = [
    'KEEP', 'REMOVE', 'CAMPFIRE', 'FISH', 'EXCLUDE', 'FIXED_KEEP', 'BURNABLE',
    'ITEM_NAMES', 'LEGEND_LABELS', 'cycle_state', 'allowed_states', 'next_state',
    'pretty_name', 'localized_name', 'item_order', 'available_items',
    'load_icon', 'make_flame', 'variants', 'count_overlay', 'apply_count',
    'legend_image',
]
