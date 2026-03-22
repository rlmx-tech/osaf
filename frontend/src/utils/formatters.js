export function formatDate(dateStr) {
  if (!dateStr) return "Unknown date";
  return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatSpecies(scientific) {
  if (!scientific) return "Unknown species";
  const COMMON_NAMES = {
    "Carcharodon carcharias": "Great White",
    "Galeocerdo cuvier": "Tiger Shark",
    "Carcharhinus leucas": "Bull Shark",
    "Carcharhinus longimanus": "Oceanic Whitetip",
    "Carcharhinus limbatus": "Blacktip",
    "Carcharhinus brachyurus": "Bronze Whaler",
    "Carcharhinus perezi": "Caribbean Reef",
    "Carcharhinus brevipinna": "Spinner Shark",
    "Carcharhinus amblyrhynchos": "Grey Reef",
    "Isurus oxyrinchus": "Shortfin Mako",
    "Sphyrna mokarran": "Great Hammerhead",
    "Prionace glauca": "Blue Shark",
    "Ginglymostoma cirratum": "Nurse Shark",
    "Negaprion brevirostris": "Lemon Shark",
    "Orectolobus maculatus": "Wobbegong",
  };
  return COMMON_NAMES[scientific] || scientific;
}

export function formatCoordinates(lon, lat) {
  if (lon == null || lat == null) return "";
  const latDir = lat >= 0 ? "N" : "S";
  const lonDir = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${latDir}, ${Math.abs(lon).toFixed(4)}°${lonDir}`;
}
