"""
Forecasting service — blueprint §5.2.

Public API:
    from services.forecasting import select_forecast
"""

from services.forecasting.select import select_forecast

__all__ = ["select_forecast"]
