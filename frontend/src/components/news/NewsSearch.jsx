import { useState, useEffect } from "react";

export default function NewsSearch({ value, onChange }) {
  const [local, setLocal] = useState(value);

  // Keep local input in sync if the parent resets the value.
  useEffect(() => {
    setLocal(value);
  }, [value]);

  // Debounce propagation to avoid a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      if (local !== value) onChange(local);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local]);

  return (
    <input
      type="search"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      placeholder="Search shark news…"
      className="bg-gray-800 text-gray-100 text-sm rounded px-3 py-1.5 border border-gray-700 focus:outline-none focus:border-gray-500 w-full sm:w-64"
    />
  );
}
