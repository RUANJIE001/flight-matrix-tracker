from .base import FlightOffer, BaseScraper

__all__ = ["FlightOffer", "BaseScraper", "GoogleFlightsScraper", "CtripScraper", "SkyscannerScraper"]

def __getattr__(name):
    if name == "GoogleFlightsScraper":
        from .google_flights import GoogleFlightsScraper
        return GoogleFlightsScraper
    elif name == "CtripScraper":
        from .ctrip_trip import CtripScraper
        return CtripScraper
    elif name == "SkyscannerScraper":
        from .skyscanner import SkyscannerScraper
        return SkyscannerScraper
    raise AttributeError(f"module {__name__} has no attribute {name}")
