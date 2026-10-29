"""Shared map style for the monthly products.

Domains, units, and color scales match across ERA5, ECMWF, C3S, and NMME.
Palettes are the colorblind-safe cmocean diverging and sequential sets
(perceptually uniform, no red/green pairs). Libre Franklin is SIL OFL 1.1.
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
PRECIP_LEVELS = (-2.0, 2.0, 100)  # inches over a 90-day season
PRECIP_TICKS = (-2, 0, 2)
TEMP_USA_LEVELS = (-5.0, 5.0, 11)  # degrees Fahrenheit
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
        if name == "seaborn":
            _patch_seaborn(module)
        elif name in {"matplotlib.pyplot", "matplotlib.axes", "matplotlib.figure"}:
            _patch_plot_module(name, module)
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
        axes = module.Axes
        _wrap_text_method(axes, "set_title", ap_rewrite)
        _wrap_text_method(axes, "set_xlabel", ap_rewrite)
        _wrap_text_method(axes, "set_ylabel", ap_rewrite)
        _wrap_text_method(axes, "text", ap_rewrite, arg_index=2)
        _wrap_tick_labels(axes, ap_rewrite)
    elif name == "matplotlib.figure":
        _wrap_text_method(module.Figure, "suptitle", ap_rewrite)
        _wrap_text_method(module.Figure, "text", ap_rewrite, arg_index=2)


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


def levels(spec: tuple[float, float, int]):
    import numpy as np

    start, stop, count = spec
    return np.linspace(start, stop, count)
