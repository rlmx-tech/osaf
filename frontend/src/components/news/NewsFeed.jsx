import NewsItemRow from "./NewsItemRow";

export default function NewsFeed({ items, loading, error, hasMore, onLoadMore }) {
  if (error) {
    return (
      <div className="text-red-400 text-sm py-8 text-center">
        Failed to load shark news: {error}
      </div>
    );
  }
  if (!loading && items.length === 0) {
    return <div className="text-gray-500 text-sm py-12 text-center">No shark news yet.</div>;
  }
  return (
    <div>
      {items.map((item) => (
        <NewsItemRow key={item.id} item={item} />
      ))}
      {loading && <div className="text-gray-500 text-sm py-4 text-center">Loading…</div>}
      {hasMore && !loading && (
        <div className="py-4 text-center">
          <button
            onClick={onLoadMore}
            className="text-sm text-gray-300 hover:text-white px-4 py-2 rounded bg-gray-800 hover:bg-gray-700"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
