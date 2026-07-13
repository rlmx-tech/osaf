import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { CLASSIFICATION_LABELS, CLASSIFICATION_COLORS } from "../utils/constants";
import { formatDate } from "../utils/formatters";
import { safeUrl } from "../utils/safeUrl";

export default function AdminPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("queue");
  const [submissions, setSubmissions] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [ingestionHealth, setIngestionHealth] = useState(null);
  const [auditLog, setAuditLog] = useState(null);
  const [users, setUsers] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await client.get("/admin/submissions");
      setSubmissions(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAuditLog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await client.get("/admin/audit-log");
      setAuditLog(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [candidatesRes, healthRes] = await Promise.all([
        client.get("/admin/candidates?status=needs_review"),
        client.get("/admin/ingestion-health"),
      ]);
      setCandidates(candidatesRes.data);
      setIngestionHealth(healthRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load evidence queue");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await client.get("/admin/users");
      setUsers(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "queue") fetchQueue();
    if (tab === "candidates") fetchCandidates();
    if (tab === "audit") fetchAuditLog();
    if (tab === "users") fetchUsers();
  }, [tab, fetchQueue, fetchCandidates, fetchAuditLog, fetchUsers]);

  const handleRoleChange = async (userId, newRole) => {
    setActionLoading(userId);
    try {
      await client.put(`/admin/users/${userId}/role`, { role: newRole });
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to update role");
    } finally {
      setActionLoading(null);
    }
  };

  const handleAction = async (id, action) => {
    setActionLoading(id);
    try {
      await client.put(`/admin/submissions/${id}/${action}`);
      fetchQueue();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${action}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCandidateAction = async (id, action) => {
    setActionLoading(id);
    try {
      await client.put(`/admin/candidates/${id}/${action}`, {});
      fetchCandidates();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : detail?.message || `Failed to ${action} candidate`);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white">
      <div className="max-w-6xl mx-auto px-6 py-6">
        <h1 className="text-2xl font-bold mb-4">Admin Panel</h1>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-gray-700">
          {[
            { key: "queue", label: "Review Queue" },
            { key: "candidates", label: "Evidence Queue" },
            { key: "users", label: "Users" },
            { key: "audit", label: "Audit Log" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              {t.label}
              {t.key === "queue" && submissions?.meta?.total > 0 && (
                <span className="ml-2 bg-amber-600 text-white text-xs px-1.5 py-0.5 rounded-full">
                  {submissions.meta.total}
                </span>
              )}
              {t.key === "candidates" && candidates?.meta?.total > 0 && (
                <span className="ml-2 bg-cyan-700 text-white text-xs px-1.5 py-0.5 rounded-full">
                  {candidates.meta.total}
                </span>
              )}
            </button>
          ))}
        </div>

        {error && (
          <div className="bg-red-900/30 text-red-400 text-sm rounded-lg px-4 py-3 mb-4">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex justify-center py-16">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Review Queue */}
        {!loading && tab === "queue" && submissions && (
          <>
            {submissions.data.length === 0 ? (
              <div className="text-center text-gray-500 py-16">
                <p className="text-lg">No pending submissions</p>
                <p className="text-sm mt-1">All caught up!</p>
              </div>
            ) : (
              <div className="space-y-3">
                {submissions.data.map((incident) => (
                  <div
                    key={incident.id}
                    className="bg-gray-800 rounded-lg p-4"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-sm text-blue-400">
                            {incident.case_number}
                          </span>
                          <span
                            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
                            style={{
                              backgroundColor: `${CLASSIFICATION_COLORS[incident.classification] || "#6b7280"}22`,
                              color: CLASSIFICATION_COLORS[incident.classification] || "#9ca3af",
                            }}
                          >
                            <span
                              className="w-1.5 h-1.5 rounded-full"
                              style={{ backgroundColor: CLASSIFICATION_COLORS[incident.classification] }}
                            />
                            {CLASSIFICATION_LABELS[incident.classification] || incident.classification}
                          </span>
                          {incident.fatal && (
                            <span className="text-xs text-red-400 font-semibold">FATAL</span>
                          )}
                          <span className="text-xs text-amber-400 bg-amber-900/30 px-2 py-0.5 rounded">
                            {incident.verification_status}
                          </span>
                        </div>
                        <p className="text-sm text-gray-300">
                          {incident.location_description} — {incident.country}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {formatDate(incident.incident_date)}
                          {incident.description && ` — ${incident.description.substring(0, 120)}...`}
                        </p>
                        <button
                          onClick={() => navigate(`/incidents/${incident.id}`)}
                          className="text-xs text-blue-400 hover:text-blue-300 mt-2"
                        >
                          View full details
                        </button>
                      </div>

                      <div className="flex gap-2 ml-4 flex-shrink-0">
                        <button
                          onClick={() => handleAction(incident.id, "verify")}
                          disabled={actionLoading === incident.id}
                          className="bg-green-600 text-white text-xs px-3 py-1.5 rounded hover:bg-green-700 disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleAction(incident.id, "reject")}
                          disabled={actionLoading === incident.id}
                          className="bg-red-600 text-white text-xs px-3 py-1.5 rounded hover:bg-red-700 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Evidence candidates produced by the durable collector pipeline */}
        {!loading && tab === "candidates" && candidates && (
          <>
            {ingestionHealth && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                {[
                  ["Needs review", candidates.meta.total],
                  ["Retrying", ingestionHealth.retrying],
                  ["Dead letter", ingestionHealth.dead_letter],
                  ["Completed", ingestionHealth.completed],
                ].map(([label, value]) => (
                  <div key={label} className="bg-gray-800 rounded px-3 py-2">
                    <p className="text-xs text-gray-500">{label}</p>
                    <p className="text-lg font-semibold text-gray-200">{value}</p>
                  </div>
                ))}
              </div>
            )}
            {candidates.data.length === 0 ? (
              <div className="text-center text-gray-500 py-16">
                <p className="text-lg">No incident candidates need review</p>
                <p className="text-sm mt-1">The evidence queue is clear.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {candidates.data.map((candidate) => {
                  const payload = candidate.observation?.payload || {};
                  const confidence = candidate.observation?.confidence;
                  return (
                    <div key={candidate.id} className="bg-gray-800 rounded-lg p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="text-xs text-cyan-300 bg-cyan-950 px-2 py-0.5 rounded">
                              {candidate.observation?.event_type || "candidate"}
                            </span>
                            {payload.classification && (
                              <span className="text-xs text-gray-300">
                                {CLASSIFICATION_LABELS[payload.classification] || payload.classification}
                              </span>
                            )}
                            {confidence != null && (
                              <span className="text-xs text-gray-500">
                                {Math.round(confidence * 100)}% extraction confidence
                              </span>
                            )}
                            <span className="text-xs text-gray-600">
                              {candidate.observation_count} supporting observation{candidate.observation_count === 1 ? "" : "s"}
                            </span>
                          </div>
                          <p className="text-sm text-gray-200">
                            {payload.location_description || "Location uncertain"}
                            {payload.country ? ` — ${payload.country}` : ""}
                          </p>
                          <p className="text-xs text-gray-500 mt-1">
                            {formatDate(payload.incident_date)}
                            {payload.description ? ` — ${payload.description.substring(0, 180)}` : ""}
                          </p>
                          {candidate.source && safeUrl(candidate.source.source_url) && (
                            <a
                              href={safeUrl(candidate.source.source_url)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block text-xs text-blue-400 hover:text-blue-300 mt-2 truncate"
                            >
                              {candidate.source.source_name}: {candidate.source.title}
                            </a>
                          )}
                          <p className="text-xs text-gray-600 mt-1">
                            {candidate.match_rationale}
                          </p>
                        </div>
                        <div className="flex gap-2 flex-shrink-0">
                          <button
                            onClick={() => handleCandidateAction(candidate.id, "publish")}
                            disabled={actionLoading === candidate.id}
                            className="bg-green-600 text-white text-xs px-3 py-1.5 rounded hover:bg-green-700 disabled:opacity-50"
                          >
                            Publish
                          </button>
                          <button
                            onClick={() => handleCandidateAction(candidate.id, "reject")}
                            disabled={actionLoading === candidate.id}
                            className="bg-red-600 text-white text-xs px-3 py-1.5 rounded hover:bg-red-700 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* Users */}
        {!loading && tab === "users" && users && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 text-xs uppercase tracking-wider border-b border-gray-700">
                  <th className="pb-2 pr-4">Username</th>
                  <th className="pb-2 pr-4">Email</th>
                  <th className="pb-2 pr-4">Role</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Joined</th>
                  <th className="pb-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {users.data.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-800/50">
                    <td className="py-3 pr-4">
                      <span className="font-medium">{user.username}</span>
                      {user.display_name && (
                        <span className="text-gray-500 ml-1 text-xs">({user.display_name})</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-gray-400">{user.email}</td>
                    <td className="py-3 pr-4">
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded ${
                          user.role === "admin"
                            ? "bg-purple-900/30 text-purple-400"
                            : user.role === "verified_contributor"
                              ? "bg-green-900/30 text-green-400"
                              : "bg-gray-700 text-gray-300"
                        }`}
                      >
                        {user.role === "verified_contributor" ? "Verified" : user.role}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span
                        className={`w-2 h-2 rounded-full inline-block ${
                          user.is_active ? "bg-green-500" : "bg-red-500"
                        }`}
                      />
                    </td>
                    <td className="py-3 pr-4 text-gray-500 text-xs">
                      {user.created_at
                        ? new Date(user.created_at).toLocaleDateString()
                        : "—"}
                    </td>
                    <td className="py-3">
                      <select
                        value={user.role}
                        onChange={(e) => handleRoleChange(user.id, e.target.value)}
                        disabled={actionLoading === user.id}
                        className="bg-gray-700 text-white text-xs rounded px-2 py-1 border border-gray-600 disabled:opacity-50"
                      >
                        <option value="public">Public</option>
                        <option value="verified_contributor">Verified Contributor</option>
                        <option value="admin">Admin</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users.meta && (
              <p className="text-xs text-gray-500 mt-3">
                {users.meta.total} total users
              </p>
            )}
          </div>
        )}

        {/* Audit Log */}
        {!loading && tab === "audit" && auditLog && (
          <div className="space-y-2">
            {auditLog.data.length === 0 ? (
              <p className="text-center text-gray-500 py-16">No audit entries</p>
            ) : (
              auditLog.data.map((entry) => (
                <div
                  key={entry.id}
                  className="bg-gray-800 rounded px-4 py-3 flex items-center gap-4 text-sm"
                >
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded ${
                      entry.action === "verified"
                        ? "bg-green-900/30 text-green-400"
                        : entry.action === "rejected"
                          ? "bg-red-900/30 text-red-400"
                          : "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {entry.action}
                  </span>
                  <span className="text-gray-400 font-mono text-xs">
                    {entry.incident_id?.substring(0, 8)}...
                  </span>
                  {entry.notes && (
                    <span className="text-gray-500 text-xs">{entry.notes}</span>
                  )}
                  <span className="text-gray-600 text-xs ml-auto">
                    {new Date(entry.changed_at).toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
