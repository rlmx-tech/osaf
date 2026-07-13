"""Data models for the collector pipeline."""

from datetime import date, datetime
from enum import Enum
import hashlib

from pydantic import BaseModel, Field


class SourcePlatform(str, Enum):
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    TWITTER = "twitter"
    NEWS_RSS = "news_rss"
    WEB_SCRAPE = "web_scrape"


class RawItem(BaseModel):
    """A raw item from a source poller, before extraction."""

    source_platform: SourcePlatform
    source_name: str
    source_url: str
    title: str
    content: str  # full text, description, or transcript
    published_at: datetime | None = None
    author: str | None = None
    extra: dict = Field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        """Unique key for deduplication based on source URL."""
        key = f"{self.source_platform.value}:{self.source_url}"
        if len(key) <= 512:
            return key
        digest = hashlib.sha256(self.source_url.encode()).hexdigest()
        return f"{self.source_platform.value}:sha256:{digest}"


class ExtractedIncident(BaseModel):
    """Structured incident data extracted by Ollama."""

    # Core fields
    incident_date: date | None = None
    location_description: str
    country: str
    state_province: str | None = None
    body_of_water: str | None = None
    classification: str = "not_confirmed"
    classification_subtype: str | None = None
    report_source: str | None = None
    report_platform: str | None = None

    # Shark
    shark_species_suspected: str | None = None

    # Victim
    victim_activity: str | None = None
    victim_injury_severity: str | None = None
    victim_name: str | None = None
    victim_age: int | None = None
    victim_sex: str | None = None
    fatal: bool = False

    # Location coordinates (estimated by LLM)
    latitude: float | None = None
    longitude: float | None = None

    # Narrative
    description: str | None = None

    # Source tracking
    source_url: str
    source_title: str
    source_publisher: str | None = None
    source_date: date | None = None
    source_type: str = "news_article"

    # Extraction metadata
    confidence: float = 0.0  # 0-1 confidence from Ollama
    is_relevant: bool = True  # whether this is actually a shark incident
    raw_item_key: str = ""  # dedup key from RawItem


class VerificationResult(BaseModel):
    """Result of Ollama verification pass."""

    is_valid: bool = False
    is_duplicate_likely: bool = False
    corrections: dict = Field(default_factory=dict)
    notes: str = ""
    confidence: float = 0.0
