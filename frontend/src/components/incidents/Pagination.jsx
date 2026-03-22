export default function Pagination({ meta, onPageChange }) {
  if (!meta || meta.pages <= 1) return null;

  const { page, pages, total, per_page } = meta;
  const start = (page - 1) * per_page + 1;
  const end = Math.min(page * per_page, total);

  // Build page numbers to show
  const getPageNumbers = () => {
    const nums = [];
    const delta = 2;
    const left = Math.max(2, page - delta);
    const right = Math.min(pages - 1, page + delta);

    nums.push(1);
    if (left > 2) nums.push("...");
    for (let i = left; i <= right; i++) nums.push(i);
    if (right < pages - 1) nums.push("...");
    if (pages > 1) nums.push(pages);

    return nums;
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-700">
      <div className="text-xs text-gray-500">
        Showing {start}–{end} of {total.toLocaleString()}
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="px-2 py-1 text-xs rounded text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Prev
        </button>

        {getPageNumbers().map((num, i) =>
          num === "..." ? (
            <span key={`ellipsis-${i}`} className="px-1 text-gray-600 text-xs">
              ...
            </span>
          ) : (
            <button
              key={num}
              onClick={() => onPageChange(num)}
              className={`px-2.5 py-1 text-xs rounded ${
                num === page
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-700"
              }`}
            >
              {num}
            </button>
          )
        )}

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          className="px-2 py-1 text-xs rounded text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}
