import {
  useOverview,
  useByYear,
  useByCountry,
  useBySpecies,
  useByActivity,
  useFatalityTrends,
} from "../api/useStats";
import OverviewCards from "../components/stats/OverviewCards";
import AttacksByYear from "../components/stats/AttacksByYear";
import AttacksByCountry from "../components/stats/AttacksByCountry";
import AttacksBySpecies from "../components/stats/AttacksBySpecies";
import AttacksByActivity from "../components/stats/AttacksByActivity";
import FatalityTrends from "../components/stats/FatalityTrends";
import { useSEO } from "../utils/useSEO";

export default function StatsPage() {
  useSEO({
    title: "Shark Attack Statistics & Trends",
    description:
      "Shark incident statistics and trends: attacks by year, country, species, and activity, plus fatality rates over time — from the Open Shark Attack File.",
    path: "/stats",
  });
  const overview = useOverview();
  const byYear = useByYear();
  const byCountry = useByCountry();
  const bySpecies = useBySpecies();
  const byActivity = useByActivity();
  const fatalityTrends = useFatalityTrends();

  const anyLoading =
    overview.loading ||
    byYear.loading ||
    byCountry.loading ||
    bySpecies.loading ||
    byActivity.loading ||
    fatalityTrends.loading;

  const anyError = [overview, byYear, byCountry, bySpecies, byActivity, fatalityTrends].find(
    (h) => h.error
  );

  if (anyLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-900">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (anyError) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-900 text-red-400">
        <div className="text-center">
          <p>Failed to load statistics</p>
          <p className="text-sm text-gray-500 mt-1">{anyError.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white">
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <h1 className="text-2xl font-bold">Statistics</h1>

        {/* Overview cards */}
        <OverviewCards data={overview.data} />

        {/* Charts row 1: Year + Fatality Trends */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AttacksByYear data={byYear.data} />
          <FatalityTrends data={fatalityTrends.data} />
        </div>

        {/* Charts row 2: Country + Species */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AttacksByCountry data={byCountry.data} />
          <AttacksBySpecies data={bySpecies.data} />
        </div>

        {/* Charts row 3: Activity (full width) */}
        <AttacksByActivity data={byActivity.data} />
      </div>
    </div>
  );
}
