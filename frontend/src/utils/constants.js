export const CLASSIFICATION_COLORS = {
  unprovoked: "#e74c3c",
  provoked: "#f39c12",
  boat_bite: "#3498db",
  scavenge: "#9b59b6",
  aquaria: "#1abc9c",
  sighting: "#2ecc71",
  near_miss: "#e67e22",
  equipment_bite: "#d35400",
  unverified_report: "#7f8c8d",
  doubtful: "#95a5a6",
  no_assignment: "#bdc3c7",
  not_confirmed: "#ecf0f1",
};

export const CLASSIFICATION_LABELS = {
  unprovoked: "Unprovoked",
  provoked: "Provoked",
  boat_bite: "Boat Bite",
  scavenge: "Scavenge",
  aquaria: "Aquaria",
  sighting: "Sighting",
  near_miss: "Near Miss",
  equipment_bite: "Equipment Bite",
  unverified_report: "Unverified Report",
  doubtful: "Doubtful",
  no_assignment: "No Assignment",
  not_confirmed: "Not Confirmed",
};

export const REPORT_SOURCE_LABELS = {
  isaf: "ISAF",
  news_media: "News Media",
  social_media: "Social Media",
  government: "Government",
  community: "Community",
};

export const REPORT_PLATFORM_OPTIONS = [
  { value: "twitter", label: "X (Twitter)" },
  { value: "reddit", label: "Reddit" },
  { value: "instagram", label: "Instagram" },
  { value: "youtube", label: "YouTube" },
  { value: "facebook", label: "Facebook" },
  { value: "tiktok", label: "TikTok" },
  { value: "tv", label: "TV" },
  { value: "print", label: "Print" },
  { value: "radio", label: "Radio" },
  { value: "wire_service", label: "Wire Service" },
  { value: "other", label: "Other" },
];

export const SEVERITY_OPTIONS = [
  { value: "fatal", label: "Fatal" },
  { value: "severe", label: "Severe" },
  { value: "moderate", label: "Moderate" },
  { value: "minor", label: "Minor" },
  { value: "no_injury", label: "No Injury" },
];

export const ACTIVITY_OPTIONS = [
  "swimming",
  "surfing",
  "diving",
  "snorkeling",
  "fishing",
  "spearfishing",
  "wading",
  "kayaking",
  "paddleboarding",
];

export const EVENT_TYPE_LABELS = {
  attack: "Attack",
  sighting: "Sighting",
  news: "News",
};

export const EVENT_TYPE_COLORS = {
  attack: "#e74c3c",
  sighting: "#2ecc71",
  news: "#7f8c8d",
};
