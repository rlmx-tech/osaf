import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../../utils/constants";

export default function MapLegend() {
  return (
    <div className="absolute bottom-6 right-4 z-[1000] bg-gray-900/90 backdrop-blur-sm text-white rounded-lg shadow-lg p-3">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
        Classification
      </h4>
      <div className="space-y-1">
        {Object.entries(CLASSIFICATION_COLORS).map(([key, color]) => (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span
              className="w-3 h-3 rounded-full border border-gray-600 flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <span>{CLASSIFICATION_LABELS[key]}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-xs mt-1 pt-1 border-t border-gray-700">
          <span className="w-3 h-3 rounded-full border-2 border-gray-900 bg-red-500 flex-shrink-0" />
          <span>Fatal (bold ring)</span>
        </div>
      </div>
    </div>
  );
}
