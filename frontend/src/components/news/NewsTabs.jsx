const TABS = [
  { value: "", label: "All" },
  { value: "sighting", label: "Sightings" },
  { value: "attack", label: "Attacks" },
  { value: "news", label: "News" },
];

export default function NewsTabs({ active, onChange }) {
  return (
    <div className="flex gap-1">
      {TABS.map((t) => (
        <button
          key={t.value || "all"}
          onClick={() => onChange(t.value)}
          className={`text-sm px-3 py-1.5 rounded transition-colors ${
            active === t.value
              ? "bg-gray-800 text-white"
              : "text-gray-400 hover:text-white hover:bg-gray-800/50"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
