"""Shared map style for the monthly products.

Domains, units, and color scales match across ERA5, ECMWF, C3S, and NMME.
Palettes are the colorblind-safe cmocean diverging and sequential sets
(perceptually uniform, no red/green pairs). Libre Franklin is SIL OFL 1.1.
Map drawing stays in the original scripts. This module only keeps the font,
rewrites dates into AP style, moves a lower-right swatch legend into the
bottom margin, and writes the unit onto the colorbar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"

# Plate Carree extents: west, east, south, north. Longitudes are 0..360 so the
# Pacific-centered seasonal maps and the continental maps frame the same area.
USA = (205, 315, 20, 60)
ATLANTIC = (240, 358, -5, 40)
TROPICS = (0, 359.9, -20, 20)
NORTHERN_HEMISPHERE = (-179, 179, 0, 90)

# One scale per variable, used by every product that draws that variable.
PRECIP_LEVELS = (-4.0, 4.0, 9)  # inches over a 90-day season, one-inch steps
PRECIP_TICKS = (-4, -2, 0, 2, 4)
TEMP_USA_LEVELS = (-3.0, 3.0, 13)  # degrees Celsius
TEMP_GLOBE_LEVELS = (-3.0, 3.0, 13)  # degrees Celsius
SST_LEVELS = (-2.0, 2.0, 60)  # degrees Celsius
SST_TICKS = (-2, 0, 2)

# cmocean balance is blue-gray-red. cmocean tarn is brown-gray-blue.
# Neither pair is red/green, which is the failure mode of BrBG, PiYG, and jet.
ANOMALY_CMAP = "cmo.balance"
PRECIP_CMAP = "cmo.tarn"
DIVERGING_CMAP = "cmo.delta"
SEQUENTIAL_WARM_CMAP = "cmo.amp"
SEQUENTIAL_COOL_CMAP = "cmo.ice"
MOISTURE_CMAP = "cmo.rain"
THERMAL_CMAP = "cmo.thermal"

# Legend swatches sampled to agree with those cmaps and with the Okabe-Ito set.
WET = "#2166AC"
DRY = "#B35806"
WARM = "#B2182B"
COLD = "#2166AC"

# kg m-2 s-1 (or mm s-1) to inches over 90 days. C3S rates are m s-1 and also
# multiply by 1000; NMME precipitation rates are already kg m-2 s-1.
INCHES_PER_90_DAYS = 86400 * 0.0394 * 90

_APPLIED = False
_IMPORT_PATCHED = False


def work_root(name: str) -> Path:
    """Disposable working directory. Never a home-directory path."""
    override = os.environ.get("WORK_ROOT")
    if override:
        return Path(override)
    base = Path(os.environ.get("TMPDIR", "/tmp"))
    return base / "monthly-updates" / name


def apply() -> None:
    """Register Libre Franklin and keep it in place after seaborn.set()."""
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True
    _register_fonts()
    _set_rcparams()
    _patch_seaborn_import()
    _patch_loaded_plot_modules()


def _register_fonts() -> None:
    if not FONT_DIR.is_dir():
        return
    try:
        from matplotlib import font_manager
    except Exception:
        return
    for font_file in sorted(FONT_DIR.glob("LibreFranklin-*.ttf")):
        font_manager.fontManager.addfont(str(font_file))


def _set_rcparams() -> None:
    try:
        from matplotlib import rcParams
    except Exception:
        return
    rcParams.update(
        {
            "font.family": "Libre Franklin",
            "font.size": 12,
            "axes.titlesize": 24,
            "axes.titleweight": "bold",
            "axes.unicode_minus": False,
            "text.color": "white",
            "axes.labelcolor": "white",
            "xtick.color": "white",
            "ytick.color": "white",
        }
    )


def _restore_font() -> None:
    try:
        from matplotlib import rcParams
    except Exception:
        return
    rcParams["font.family"] = "Libre Franklin"


def _patch_seaborn(module) -> None:
    setter = getattr(module, "set", None)
    if setter is None or getattr(setter, "_house_style", False):
        return

    def _set(*args, **kwargs):
        setter(*args, **kwargs)
        _restore_font()

    _set._house_style = True
    module.set = _set


def _patch_seaborn_import() -> None:
    global _IMPORT_PATCHED
    if _IMPORT_PATCHED:
        return
    _IMPORT_PATCHED = True
    real_import = __import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        module = real_import(name, globals, locals, fromlist, level)
        # __import__ returns the top-level package when the name has dots.
        # Patch the real submodule from sys.modules instead.
        if name == "seaborn":
            loaded = sys.modules.get("seaborn")
            if loaded is not None:
                _patch_seaborn(loaded)
        elif name in {"matplotlib.pyplot", "matplotlib.axes", "matplotlib.figure"}:
            loaded = sys.modules.get(name)
            if loaded is not None:
                _patch_plot_module(name, loaded)
        return module

    # builtins replacement is intentional: notebook-style scripts import seaborn
    # long after this module is applied.
    import builtins

    builtins.__import__ = _import
    if "seaborn" in sys.modules:
        _patch_seaborn(sys.modules["seaborn"])


def _patch_loaded_plot_modules() -> None:
    for name in ("matplotlib.pyplot", "matplotlib.axes", "matplotlib.figure"):
        module = sys.modules.get(name)
        if module is not None:
            _patch_plot_module(name, module)


def _patch_plot_module(name: str, module) -> None:
    from .ap_dates import ap_rewrite

    if name == "matplotlib.pyplot":
        _wrap_text_callable(module, "title", ap_rewrite)
        _wrap_text_callable(module, "suptitle", ap_rewrite)
        _wrap_text_callable(module, "text", ap_rewrite, text_index=2)
    elif name == "matplotlib.axes":
        axes = getattr(module, "Axes", None)
        if axes is None:
            return
        _wrap_text_method(axes, "set_title", ap_rewrite)
        _wrap_text_method(axes, "set_xlabel", ap_rewrite)
        _wrap_text_method(axes, "set_ylabel", ap_rewrite)
        _wrap_text_method(axes, "text", ap_rewrite, arg_index=2)
        _wrap_tick_labels(axes, ap_rewrite)
        _wrap_legend(axes)
    elif name == "matplotlib.figure":
        _wrap_text_method(module.Figure, "suptitle", ap_rewrite)
        _wrap_text_method(module.Figure, "text", ap_rewrite, arg_index=2)
        _wrap_colorbar(module.Figure)


def _wrap_text_callable(module, name: str, rewrite, text_index: int = 0) -> None:
    original = getattr(module, name, None)
    if original is None or getattr(original, "_ap_dates", False):
        return

    def wrapped(*args, **kwargs):
        args = _rewrite_arg(args, text_index, rewrite)
        return original(*args, **kwargs)

    wrapped._ap_dates = True
    setattr(module, name, wrapped)


def _wrap_text_method(cls, name: str, rewrite, arg_index: int = 0) -> None:
    original = getattr(cls, name, None)
    if original is None or getattr(original, "_ap_dates", False):
        return

    def wrapped(self, *args, **kwargs):
        args = _rewrite_arg(args, arg_index, rewrite)
        return original(self, *args, **kwargs)

    wrapped._ap_dates = True
    setattr(cls, name, wrapped)


def _wrap_tick_labels(cls, rewrite) -> None:
    original = cls.set_xticklabels
    if getattr(original, "_ap_dates", False):
        return

    def set_xticklabels(self, labels, *args, **kwargs):
        labels = [rewrite(label, tabular=True) if isinstance(label, str) else label for label in labels]
        return original(self, labels, *args, **kwargs)

    set_xticklabels._ap_dates = True
    cls.set_xticklabels = set_xticklabels


def _rewrite_arg(args, index: int, rewrite):
    if len(args) <= index or not isinstance(args[index], str):
        return args
    updated = list(args)
    updated[index] = rewrite(updated[index])
    return tuple(updated)


def _is_geo(ax) -> bool:
    return ax.__class__.__name__.startswith("GeoAxes")


def _wrap_legend(axes_cls) -> None:
    original = axes_cls.legend
    if getattr(original, "_house_legend", False):
        return

    def legend(self, *args, **kwargs):
        # The swatch box used to sit on the lower-right corner of the map,
        # on top of the colorbar. Drop it into the margin under the axes.
        if _is_geo(self) and kwargs.get("loc") == "lower right":
            kwargs["loc"] = "upper center"
            kwargs["bbox_to_anchor"] = (0.5, -0.02)
            kwargs["borderaxespad"] = 0.0
        legend_obj = original(self, *args, **kwargs)
        if _is_geo(self) and not getattr(self, "_house_colorbar", False):
            _add_missing_colorbar(self)
        return legend_obj

    legend._house_legend = True
    axes_cls.legend = legend


def _wrap_colorbar(figure_cls) -> None:
    original = figure_cls.colorbar
    if getattr(original, "_house_units", False):
        return

    def colorbar(self, mappable, cax=None, ax=None, **kwargs):
        cbar = original(self, mappable, cax=cax, ax=ax, **kwargs)
        _label_colorbar(cbar, ax, kwargs.get("ticks"))
        return cbar

    colorbar._house_units = True
    figure_cls.colorbar = colorbar


def _label_colorbar(cbar, ax, ticks) -> None:
    import numpy as np

    parents = _parents(ax, getattr(cbar.mappable, "axes", None))
    for parent in parents:
        parent._house_colorbar = True
    if ticks is None:
        ticks = [float(value) for value in cbar.get_ticks()]
    else:
        ticks = [float(value) for value in ticks]
    if len(ticks) < 2:
        return
    unit = _unit_from_context(parents, cbar.ax.figure)
    low, high = min(ticks), max(ticks)
    span = high - low
    signed = span > 0 and abs(low + high) <= 0.08 * span
    labels = [_format_tick(value, unit, signed) for value in ticks]
    if cbar.orientation == "horizontal":
        cbar.ax.set_xticks(ticks)
        cbar.ax.set_xticklabels(labels)
        artists = cbar.ax.get_xticklabels()
    else:
        cbar.ax.set_yticks(ticks)
        cbar.ax.set_yticklabels(labels)
        artists = cbar.ax.get_yticklabels()
    for artist in artists:
        artist.set_color("white")
        artist.set_fontweight("bold")
    if unit:
        _drop_unit_from_titles(parents, cbar.ax.figure, unit)


def _ticks_on_breaks(levels) -> list[float]:
    """Colorbar labels that fall on contour levels, including both ends."""
    import numpy as np

    levels = np.asarray(levels, dtype=float)
    count = int(levels.size)
    if count < 2:
        return [float(value) for value in levels]
    steps = count - 1
    for gaps in (4, 5, 2, 3, 6, 8, 10):
        if steps % gaps == 0:
            stride = steps // gaps
            return [float(value) for value in levels[::stride]]
    return [float(levels[0]), float(levels[count // 2]), float(levels[-1])]


def _add_missing_colorbar(ax) -> None:
    """Snowfall and some height maps have a swatch legend and no scale."""
    import matplotlib.pyplot as plt
    import numpy as np

    filled = [
        coll
        for coll in ax.collections
        if getattr(coll, "filled", False) and hasattr(coll, "levels")
    ]
    if not filled:
        return
    mappable = filled[-1]
    levels = np.asarray(mappable.levels, dtype=float)
    if levels.size < 2:
        return
    low = float(levels[0])
    high = float(levels[-1])
    if high <= low:
        return
    ax._house_colorbar = True
    title = _title_text(ax)
    # Snowfall bands stay one inch apart. Labels are every two inches, and the
    # bar is half the map height so it does not run past the frame.
    discrete = "Snowfall" in title and levels.size <= 15
    # Height bands are one decameter. Labels have to sit on those edges.
    banded = discrete or ("Height Anomaly" in title and levels.size <= 25)
    if discrete:
        ticks = [float(value) for value in levels[::2]]
    else:
        ticks = _ticks_on_breaks(levels)
    cbar = plt.colorbar(
        mappable,
        ax=ax,
        ticks=ticks,
        pad=0.02,
        shrink=0.4,
        aspect=20,
        extend="both",
        drawedges=banded,
    )
    if discrete:
        cbar.ax.tick_params(labelsize=18)


def _parents(ax, fallback):
    if ax is None:
        ax = fallback
    if ax is None:
        return []
    if isinstance(ax, (list, tuple)):
        return [item for item in ax if item is not None]
    return [ax]


def _title_text(ax) -> str:
    chunks = []
    for loc in ("left", "center", "right"):
        getter = getattr(ax, "get_title", None)
        if getter is None:
            continue
        try:
            chunks.append(getter(loc=loc) or "")
        except TypeError:
            chunks.append(getter() or "")
    return "\n".join(chunks)


def _unit_from_context(parents, fig) -> str:
    chunks = []
    for parent in parents:
        for loc in ("left", "center", "right"):
            getter = getattr(parent, "get_title", None)
            if getter is None:
                continue
            try:
                chunks.append(getter(loc=loc) or "")
            except TypeError:
                chunks.append(getter() or "")
    if fig is not None:
        for other in fig.axes:
            getter = getattr(other, "get_title", None)
            if getter is None:
                continue
            try:
                chunks.append(getter(loc="left") or "")
            except TypeError:
                chunks.append(getter() or "")
    return _unit_from_text("\n".join(chunks))


def _unit_from_text(text: str) -> str:
    import re

    if not text:
        return ""
    for raw in re.findall(r"\(([^)]{1,48})\)", text):
        key = raw.strip()
        lowered = key.lower()
        if lowered in {"inches", "inch", "in", "in."}:
            return "in."
        if lowered == "%" or "of normal" in lowered:
            return "%"
        if key in {"°F", "°C", "mph", "kts", "W/m²", "dam", "m/s"}:
            return key
    if "Cloud Cover %" in text:
        return "%"
    if "Snowfall" in text:
        # The snowfall scripts convert m/s to seasonal inches before plotting.
        return "in."
    if "Height Anomaly" in text:
        return "dam"
    return ""


def _drop_unit_from_titles(parents, fig, unit: str) -> None:
    """The colorbar already shows the unit, so the title does not repeat it."""
    axes = []
    axes.extend(parents)
    if fig is not None:
        axes.extend(fig.axes)
    seen = set()
    for ax in axes:
        if ax is None or id(ax) in seen:
            continue
        seen.add(id(ax))
        for attr in ("_left_title", "title", "_right_title"):
            artist = getattr(ax, attr, None)
            if artist is None:
                continue
            old = artist.get_text() or ""
            new = _strip_listed_unit(old, unit)
            if new != old:
                artist.set_text(new)


def _strip_listed_unit(text: str, unit: str) -> str:
    import re

    if not text or not unit:
        return text
    keys = {
        "in.": ("inches", "inch", "in.", "in", "in/day"),
        "%": ("% of normal", "percent of normal", "%"),
        "°F": ("°F",),
        "°C": ("°C",),
        "mph": ("mph",),
        "kts": ("kts",),
        "W/m²": ("W/m²",),
        "dam": ("dam",),
        "m/s": ("m/s",),
    }.get(unit, (unit,))
    for key in keys:
        text = re.sub(
            r"\s*\(\s*" + re.escape(key) + r"\s*\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\(\s*" + re.escape(key) + r"\s*,\s*",
            "(",
            text,
            flags=re.IGNORECASE,
        )
    if unit == "%":
        text = text.replace("Cloud Cover %", "Cloud Cover")
    return text


def _format_tick(value: float, unit: str, signed: bool) -> str:
    magnitude = abs(value)
    if magnitude < 1e-15:
        number = "0"
    elif magnitude < 0.01 or magnitude >= 100_000:
        number = _scientific_number(value, signed)
    elif value < 0:
        number = f"−{magnitude:g}"
    elif signed and value > 0:
        number = f"+{magnitude:g}"
    else:
        number = f"{magnitude:g}"
    if not unit:
        return number
    if unit == "%":
        return f"{number}%"
    if unit.startswith("°"):
        return f"{number}{unit}"
    return f"{number} {unit}"


def _scientific_number(value: float, signed: bool) -> str:
    """−2e−9. Libre Franklin has no superscript minus."""
    import math

    magnitude = abs(value)
    exponent = math.floor(math.log10(magnitude))
    mantissa = round(magnitude / 10**exponent, 2)
    if mantissa >= 10:
        mantissa = round(mantissa / 10, 2)
        exponent += 1
    if abs(mantissa - round(mantissa)) < 1e-6:
        digits = str(int(round(mantissa)))
    else:
        digits = f"{mantissa:.2f}".rstrip("0").rstrip(".")
    if value < 0:
        sign = "−"
    elif signed and value > 0:
        sign = "+"
    else:
        sign = ""
    power = f"−{abs(int(exponent))}" if exponent < 0 else f"+{int(exponent)}"
    return f"{sign}{digits}e{power}"


def levels(spec: tuple[float, float, int]):
    import numpy as np

    start, stop, count = spec
    return np.linspace(start, stop, count)
