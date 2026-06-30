import { useState, useCallback } from "react";
import { useNews } from "../api/useNews";
import NewsTabs from "../components/news/NewsTabs";
import NewsSearch from "../components/news/NewsSearch";
import NewsFeed from "../components/news/NewsFeed";

export default function NewsPage() {
  const [eventType, setEventType] = useState("");
  const [search, setSearch] = useState("");
  const { items, loading, error, hasMore, loadMore } = useNews({ eventType, search });
  const handleSearch = useCallback((v) => setSearch(v), []);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <h1 className="text-xl font-bold text-white mb-1">Shark News</h1>
        <p className="text-sm text-gray-500 mb-4">
          Recent shark sightings, incidents, and coverage captured from across the web.
        </p>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-2">
          <NewsTabs active={eventType} onChange={setEventType} />
          <div className="sm:ml-auto">
            <NewsSearch value={search} onChange={handleSearch} />
          </div>
        </div>
        <NewsFeed
          items={items}
          loading={loading}
          error={error}
          hasMore={hasMore}
          onLoadMore={loadMore}
        />
      </div>
    </div>
  );
}
