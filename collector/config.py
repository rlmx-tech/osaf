"""Collector service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Collector settings loaded from environment variables."""

    # OSAF API
    osaf_api_url: str = "http://backend:8000/api/v1"
    osaf_username: str = "collector"
    osaf_password: str  # required — no default

    # Ollama
    ollama_url: str = "https://ollama.com"
    ollama_api_key: str = ""  # Bearer token for Ollama Cloud; empty = no auth (local)
    ollama_model: str = "glm-5.2:cloud"
    ollama_timeout: int = 300

    # Reddit (asyncpraw)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "OSAF-Collector/0.1 (shark incident aggregator)"

    # Poll intervals (seconds)
    youtube_interval: int = 1800      # 30 min
    reddit_interval: int = 900        # 15 min
    news_interval: int = 600          # 10 min
    tracker_interval: int = 1800      # 30 min

    # Dedup database
    state_file: str = "/app/data/collector_state.json"

    model_config = {"env_prefix": "COLLECTOR_"}


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
