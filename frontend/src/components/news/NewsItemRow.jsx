import { useState } from "react";
import { Link } from "react-router-dom";
import { safeUrl } from "../../utils/safeUrl";
import { relativeTime } from "../../utils/formatters";
import { EVENT_TYPE_LABELS, EVENT_TYPE_COLORS } from "../../utils/constants";

export default function NewsItemRow({ item }) {
  const [imgError, setImgError] = useState(false);
  const color = EVENT_TYPE_COLORS[item.event_type] || "#7f8c8d";
  const label = EVENT_TYPE_LABELS[item.event_type] || item.event_type;
  const img = safeUrl(item.image_url);
  const href = safeUrl(item.source_url);
  const when = relativeTime(item.published_at || item.captured_at);
  const showImg = img && !imgError;

  return (
    <article className="flex gap-3 py-3 border-b border-gray-800">
      {showImg ? (
        <img
          src={img}
          alt=""
          loading="lazy"
          onError={() => setImgError(true)}
          className="w-20 h-20 object-cover rounded flex-shrink-0 bg-gray-800"
        />
      ) : (
        <div
          className="w-20 h-20 rounded flex-shrink-0"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="inline-flex items-center gap-1 font-medium" style={{ color }}>
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {label}
          </span>
          <span className="text-gray-500">· {item.country || "—"} · {when}</span>
          {item.promoted_incident_id && (
            <Link
              to={`/incidents/${item.promoted_incident_id}`}
              className="text-blue-400 hover:text-blue-300"
            >
              · incident
            </Link>
          )}
        </div>
        <h3 className="text-sm text-gray-100 mt-1">{item.title}</h3>
        <div className="text-xs text-gray-500 mt-1">
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer" className="hover:text-gray-300">
              {item.source_name} ↗
            </a>
          ) : (
            <span>{item.source_name}</span>
          )}
        </div>
      </div>
    </article>
  );
}
