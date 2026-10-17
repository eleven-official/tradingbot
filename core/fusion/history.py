"""Account-free public benchmark history, with bounded downloads and attribution.

Only the publisher's CC BY factor series is fetched. Raw vendor coin data are
not covered by that release and are never fetched here. No candles are invented
from returns. This is a research benchmark, not executable exchange quotations.
"""

from __future__ import annotations

import csv
import hashlib
import io
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SOURCE_URL = "https://huggingface.co/datasets/sstoeckl/opencryptoassetpricing/resolve/main/factors/daily/factors_cg_investable_daily.csv"
ATTRIBUTION = "Stoeckl, S. and Pukrop, M. (2026), Open Crypto Pricing, University of Liechtenstein. Factor series adapted by Loki."
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
MAX_BYTES = 2_000_000
_cache = None
_cached_at = 0.0
_retry_after = 0.0
_lock = threading.Lock()


class _PublisherRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "huggingface.co"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("History redirect left the publisher's allowed HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_factor_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if not {"date", "CMKT"} <= set(reader.fieldnames or []):
        raise ValueError("History CSV needs date and CMKT columns")
    result = []
    for row in reader:
        if len(result) >= 250_000:
            raise ValueError("History exceeds 250000 observations")
        result.append({"timestamp": row["date"], "return": row["CMKT"]})
    return result


def public_history():
    """Fetch at most daily per worker; coalesce requests and back off failures."""
    global _cache, _cached_at, _retry_after
    with _lock:
        now = time.monotonic()
        if _cache is not None and now - _cached_at < 86400:
            return _cache
        if now < _retry_after:
            raise ConnectionError(
                "Public history is temporarily unavailable; retry after one minute"
            )
        try:
            request = Request(
                SOURCE_URL, headers={"User-Agent": "Loki-Fusion/1.0", "Accept": "text/csv"}
            )
            with build_opener(_PublisherRedirects()).open(request, timeout=15) as response:
                if response.status != 200:
                    raise ValueError("History publisher did not return a complete CSV")
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Public history download exceeded its size limit")
            observations = parse_factor_csv(raw.decode("utf-8-sig"))
            # Validate before caching. Imports stay lazy to avoid network on import.
            from core.fusion.learning import validate_observations

            validate_observations(observations)
            result = {
                "observations": observations,
                "source": {
                    "name": "Open Crypto Pricing · CoinGecko canonical daily market factor",
                    "url": SOURCE_URL,
                    "website": "https://opencryptopricing.com/download.html",
                    "license": "CC BY 4.0",
                    "license_url": LICENSE_URL,
                    "attribution": ATTRIBUTION,
                    "citation_note": "See also Liu, Tsyvinski & Wu (2022), Journal of Finance 77(2), and Fieberg et al. (2024), IRFA 92.",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "kind": "retrospectively constructed daily excess-market-return factor",
                    "execution_prices": False,
                    "requires_api_key": False,
                    "limitation": "The factor-series license does not extend to the underlying vendor coin data. Retrospective factor design and revisions can introduce hindsight bias.",
                },
            }
        except (OSError, ValueError, UnicodeError) as exc:
            _retry_after = time.monotonic() + 60
            raise ConnectionError(
                "Public history unavailable or invalid; no substitute or synthetic data was used"
            ) from exc
        _cache, _cached_at = result, time.monotonic()
        return result
