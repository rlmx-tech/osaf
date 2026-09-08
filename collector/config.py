"""Collector service configuration."""

from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings

# A local Ollama needs no bearer token; Ollama Cloud rejects every request
# without one. Hosts treated as local for that purpose:
_LOCAL_OLLAMA_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"})


def requires_ollama_api_key(ollama_url: str) -> bool:
    """True when the configured Ollama endpoint is remote and so needs auth."""
    host = (urlparse(ollama_url).hostname or "").lower()
    return host not in _LOCAL_OLLAMA_HOSTS


class Settings(BaseSettings):
    """Collector settings loaded from environment variables."""

    # OSAF API
    osaf_api_url: str = "http://backend:8000/api/v1"
    osaf_username: str = "collector"
    osaf_password: str  # required — no default

    # Ollama
    ollama_url: str = "https://ollama.com"
    ollama_api_key: str = ""  # Bearer token for Ollama Cloud; empty = no auth (local)
    ollama_model: str = "glm-5.3-flash:cloud"
    ollama_timeout: int = 300
    # Caps thinking and answer together, not the answer alone. glm-5.3-flash
    # reasons before it replies, and measured 2026-09-08 against the live
    # verification prompt it spent 5,392-9,354 characters doing so — roughly
    # 1,350-2,340 tokens. At 2048 the budget ran out before the model wrote any
    # JSON on half of those calls, which surfaced as an empty 200 response and
    # looked exactly like an outage. Raising it to 4096 cut the production
    # failure rate from 38.6% to 14.3%, so some real articles reason well past
    # what a clean synthetic one does.
    #
    # This is a ceiling, not an allocation: a call that stops early is billed
    # for what it generated, so headroom is free on every request that does not
    # need it. Only a genuine runaway pays, and ollama_timeout bounds that.
    # There is no reason to keep it tight.
    ollama_num_predict: int = 8192

    # Reddit (asyncpraw)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "OSAF-Collector/0.1 (shark incident aggregator)"

    # Poll intervals (seconds)
    youtube_interval: int = 1800      # 30 min
    reddit_interval: int = 900        # 15 min
    news_interval: int = 600          # 10 min
    tracker_interval: int = 1800      # 30 min
    gdelt_interval: int = 1800        # 30 min

    # GDELT document API
    gdelt_max_records: int = 75       # per query; GDELT's ceiling is 250
    gdelt_timespan: str = "6h"        # lookback window per query

    # Shared by every poller that fetches a publisher article body.
    article_fetch_timeout: int = 20   # seconds per article

    # Dedup database
    state_file: str = "/app/data/collector_state.json"

    model_config = {"env_prefix": "COLLECTOR_"}

    @model_validator(mode="after")
    def _require_api_key_for_remote_ollama(self) -> "Settings":
        """Fail startup when a remote Ollama is configured with no bearer token.

        Without this the collector starts cleanly, every extraction call gets a
        401, _call_ollama logs and returns None, and the service reports healthy
        while collecting nothing. A container that refuses to boot is far easier
        to notice than one that silently stops producing incidents.
        """
        if requires_ollama_api_key(self.ollama_url) and not self.ollama_api_key.strip():
            raise ValueError(
                f"COLLECTOR_OLLAMA_API_KEY is required for remote Ollama at "
                f"{self.ollama_url!r}. Set it, or point COLLECTOR_OLLAMA_URL at a "
                f"local instance."
            )
        return self


settings = Settings()


# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------

YOUTUBE_CHANNELS = [
    # Already confirmed sources
    {
        "name": "TheMalibuArtist",
        "channel_id": "UCsykMfh4KIAf_B8Wnx7hzNA",
        "focus": "California great white shark sightings (drone)",
    },
    {
        "name": "SharkBytes",
        "channel_id": "UC4O9LhULkvWqrek88tB52Yg",
        "focus": "Marine biology, global shark incident analysis",
    },
    {
        "name": "SharksHappen",
        "channel_id": "UCfd0MpDa8LrPNKrCHZS7KSg",
        "focus": "Shark incident case studies and research",
    },
    {
        "name": "RiggsAustralia",
        "channel_id": "UC_jzjWuPympmVhjBqYnHLoQ",
        "focus": "Australian shark encounters, tagged shark tracking, Esperance",
    },
    # New sources from research
    {
        "name": "DroneSharkApp",
        "channel_id": "UCi7pChfCUkGmds-yHDqYZ5w",
        "focus": "Daily drone footage of sharks, Sydney/NSW Australia",
    },
    {
        "name": "GreatWhiteDronE",
        "channel_id": "UCT_fDvUK8aZyTa4ASZ0fAHA",
        "focus": "Great white shark drone footage, Southern California",
    },
    {
        "name": "OceanRamsey",
        "channel_id": "UCivi2SDh5sYrMSb6Ga3HS9A",
        "focus": "Shark encounters, conservation, diving, Hawaii",
    },
    {
        "name": "CSULBSharkLab",
        "channel_id": "UC6ZUK3DH6McsT3gRsT198zQ",
        "focus": "Academic shark research, Southern California",
    },
]

REDDIT_SUBREDDITS = [
    "sharks",
    "surfing",
    "australia",
    "florida",
    "thalassophobia",
    "natureismetal",
    "TheDepthsBelow",
    "marinebiology",
    "ocean",
    "hawaii",
    "SouthAfrica",
    "newzealand",
]

NEWS_RSS_FEEDS = [
    # Google News alerts
    {
        "name": "Google News - Shark Attack",
        "url": "https://news.google.com/rss/search?q=shark+attack&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News - Shark Bite",
        "url": "https://news.google.com/rss/search?q=shark+bite&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News - Shark Sighting",
        "url": "https://news.google.com/rss/search?q=shark+sighting&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News - Shark Attack Australia",
        "url": "https://news.google.com/rss/search?q=shark+attack+australia&hl=en-AU&gl=AU&ceid=AU:en",
    },
    {
        "name": "Google News - Shark Attack South Africa",
        "url": "https://news.google.com/rss/search?q=shark+attack+south+africa&hl=en-ZA&gl=ZA&ceid=ZA:en",
    },
    # Bing News. Its link is a wrapper too, but unlike Google's it redirects to
    # the publisher, so these entries can carry a real article body and become
    # incidents. Verified 2026-09-08; the quoted-phrase form returns nothing, so
    # these stay as bare keyword queries.
    {
        "name": "Bing News - Shark Attack",
        "url": "https://www.bing.com/news/search?q=shark+attack&format=RSS",
    },
    {
        "name": "Bing News - Shark Bite",
        "url": "https://www.bing.com/news/search?q=shark+bite&format=RSS",
    },
    {
        "name": "Bing News - Shark Sighting",
        "url": "https://www.bing.com/news/search?q=shark+sighting&format=RSS",
    },
    {
        "name": "Bing News - Shark Attack Australia",
        "url": "https://www.bing.com/news/search?q=shark+attack&setmkt=en-au&format=RSS",
    },
    {
        "name": "Bing News - Shark Attack South Africa",
        "url": "https://www.bing.com/news/search?q=shark+attack&setmkt=en-za&format=RSS",
    },
]

# GDELT document API queries. Unlike Google News RSS, GDELT returns the
# publisher's own URL, which is what lets the collector fetch a real article
# body — and the promotion gate refuses anything without one.
GDELT_QUERIES = [
    {"name": "GDELT - Shark Attack", "query": '"shark attack"'},
    {"name": "GDELT - Shark Bite", "query": '"shark bite"'},
    {"name": "GDELT - Bitten By A Shark", "query": '"bitten by a shark"'},
    {"name": "GDELT - Shark Sighting", "query": '"shark sighting"'},
    {"name": "GDELT - Beach Closed Shark", "query": '"beach closed" shark'},
]

WEB_SCRAPERS = [
    {
        "name": "Tracking Sharks",
        "url": "https://www.trackingsharks.com",
        "type": "incident_aggregator",
        "focus": "Global shark bite/attack tracking",
    },
]

# Classification mapping for Ollama extraction
VALID_CLASSIFICATIONS = [
    "unprovoked",
    "provoked",
    "boat_bite",
    "scavenge",
    "aquaria",
    "sighting",
    "near_miss",
    "equipment_bite",
    "unverified_report",
    "doubtful",
    "no_assignment",
    "not_confirmed",
]

VALID_SEVERITIES = ["fatal", "severe", "moderate", "minor", "no_injury"]

VALID_ACTIVITIES = [
    "swimming",
    "surfing",
    "diving",
    "snorkeling",
    "fishing",
    "spearfishing",
    "wading",
    "kayaking",
    "paddleboarding",
]

VALID_REPORT_SOURCES = ["isaf", "news_media", "social_media", "government", "community"]

# Canonical country names (match backend seed data + frontend filters).
# Maps common LLM variants -> the canonical form so stats/filters don't fragment
# (e.g. "USA" and "United States" counting as two separate countries).
COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "uae": "United Arab Emirates",
    "rsa": "South Africa",
    "nz": "New Zealand",
    "png": "Papua New Guinea",
}

COMMON_TO_SCIENTIFIC = {
    "great white": "Carcharodon carcharias",
    "white shark": "Carcharodon carcharias",
    "bull shark": "Carcharhinus leucas",
    "tiger shark": "Galeocerdo cuvier",
    "hammerhead": "Sphyrna mokarran",
    "great hammerhead": "Sphyrna mokarran",
    "scalloped hammerhead": "Sphyrna lewini",
    "mako": "Isurus oxyrinchus",
    "shortfin mako": "Isurus oxyrinchus",
    "blue shark": "Prionace glauca",
    "oceanic whitetip": "Carcharhinus longimanus",
    "blacktip": "Carcharhinus limbatus",
    "blacktip reef": "Carcharhinus melanopterus",
    "whitetip reef": "Triaenodon obesus",
    "nurse shark": "Ginglymostoma cirratum",
    "lemon shark": "Negaprion brevirostris",
    "wobbegong": "Orectolobus maculatus",
    "bronze whaler": "Carcharhinus brachyurus",
    "spinner shark": "Carcharhinus brevipinna",
    "sandbar shark": "Carcharhinus plumbeus",
    "dusky shark": "Carcharhinus obscurus",
    "grey reef": "Carcharhinus amblyrhynchos",
    "caribbean reef": "Carcharhinus perezi",
    "sand tiger": "Carcharias taurus",
    "ragged tooth": "Carcharias taurus",
    "sevengill": "Notorynchus cepedianus",
    "porbeagle": "Lamna nasus",
    "salmon shark": "Lamna ditropis",
    "cookie cutter": "Isistius brasiliensis",
    "cookiecutter": "Isistius brasiliensis",
    "galapagos shark": "Carcharhinus galapagensis",
    "thresher": "Alopias vulpinus",
    "whale shark": "Rhincodon typus",
    "basking shark": "Cetorhinus maximus",
}
