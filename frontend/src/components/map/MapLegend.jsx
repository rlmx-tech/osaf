import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../../utils/constants";

function LegendContents() {
  return (
    <>
      <div className="space-y-1">
        {Object.entries(CLASSIFICATION_COLORS).map(([key, color]) => (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span
              className="h-3 w-3 flex-shrink-0 rounded-full border border-gray-600"
              style={{ backgroundColor: color }}
            />
            <span>{CLASSIFICATION_LABELS[key]}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2 border-t border-gray-700 pt-2 text-xs">
        <span className="h-3 w-3 flex-shrink-0 rounded-full border-2 border-gray-900 bg-red-500" />
        <span>Fatal (bold ring)</span>
      </div>
    </>
  );
}

export default function MapLegend() {
  return (
    <>
      <div className="absolute bottom-6 right-4 z-[1000] hidden rounded-lg border border-gray-700/70 bg-gray-900/95 p-3 text-white shadow-xl backdrop-blur-sm md:block">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
          Classification
        </h4>
        <LegendContents />
      </div>

      <details className="group absolute bottom-5 right-3 z-[1000] rounded-lg border border-gray-700/70 bg-gray-900/95 text-white shadow-xl backdrop-blur-sm md:hidden">
        <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium marker:hidden">
          <span className="group-open:hidden">Legend</span>
          <span className="hidden group-open:inline">Hide legend</span>
        </summary>
        <div className="max-h-[55dvh] overflow-y-auto border-t border-gray-700 px-3 pb-3 pt-2">
          <LegendContents />
        </div>
      </details>
    </>
  );
}
