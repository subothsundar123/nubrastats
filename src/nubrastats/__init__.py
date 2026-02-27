from . import adapters, nubra, plots, reports, stats, ui, utils
from .version import __version__

__all__ = [
    "__version__",
    "adapters",
    "nubra",
    "plots",
    "reports",
    "stats",
    "ui",
    "utils",
    "extend_pandas",
]


def extend_pandas() -> None:
    """
    Add nubrastats helpers as pandas methods.
    """
    from pandas.core.base import PandasObject as _po  # type: ignore[import]

    _po.ns_to_returns = utils.to_returns  # type: ignore[attr-defined]
    _po.ns_to_equity = utils.to_equity  # type: ignore[attr-defined]
    _po.ns_sharpe = stats.sharpe  # type: ignore[attr-defined]
    _po.ns_sortino = stats.sortino  # type: ignore[attr-defined]
    _po.ns_cagr = stats.cagr  # type: ignore[attr-defined]
    _po.ns_max_drawdown = stats.max_drawdown  # type: ignore[attr-defined]
    _po.ns_drawdown_series = stats.drawdown_series  # type: ignore[attr-defined]
