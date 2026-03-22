import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/useAuth";
import client from "../api/client";
import {
  CLASSIFICATION_LABELS,
  SEVERITY_OPTIONS,
  ACTIVITY_OPTIONS,
} from "../utils/constants";

const EMPTY_SOURCE = {
  source_type: "news_article",
  source_url: "",
  source_title: "",
  source_publisher: "",
  source_date: "",
  source_notes: "",
};

export default function SubmitPage() {
  const navigate = useNavigate();
  const { isContributor } = useAuth();
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    incident_date: "",
    location_description: "",
    country: "",
    state_province: "",
    body_of_water: "",
    classification: "unprovoked",
    victim_activity: "",
    victim_injury_severity: "",
    victim_name: "",
    victim_age: "",
    victim_sex: "",
    fatal: false,
    description: "",
    shark_species_suspected: "",
  });
  const [sources, setSources] = useState([{ ...EMPTY_SOURCE }]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSourceChange = (i, field, value) => {
    setSources((prev) => {
      const updated = [...prev];
      updated[i] = { ...updated[i], [field]: value };
      return updated;
    });
  };

  const addSource = () => setSources((prev) => [...prev, { ...EMPTY_SOURCE }]);
  const removeSource = (i) =>
    setSources((prev) => prev.filter((_, idx) => idx !== i));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        incident_date: form.incident_date || null,
        victim_age: form.victim_age ? Number(form.victim_age) : null,
        victim_activity: form.victim_activity || null,
        victim_injury_severity: form.victim_injury_severity || null,
        victim_name: form.victim_name || null,
        victim_sex: form.victim_sex || null,
        shark_species_suspected: form.shark_species_suspected || null,
        sources: sources
          .filter((s) => s.source_url || s.source_title)
          .map((s) => ({
            ...s,
            source_date: s.source_date || null,
            source_url: s.source_url || null,
            source_title: s.source_title || null,
            source_publisher: s.source_publisher || null,
            source_notes: s.source_notes || null,
          })),
      };
      await client.post("/submissions", payload);
      navigate("/database");
    } catch (err) {
      setError(err.response?.data?.detail || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white">
      <div className="max-w-3xl mx-auto px-6 py-6">
        <h1 className="text-2xl font-bold mb-2">Submit an Incident</h1>
        <p className="text-sm text-gray-400 mb-6">
          {isContributor
            ? "As a verified contributor, your submission will be published automatically."
            : "Your submission will be reviewed by an administrator before being published."}
        </p>

        {error && (
          <div className="bg-red-900/30 text-red-400 text-sm rounded-lg px-4 py-3 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Incident Details */}
          <fieldset className="space-y-4">
            <legend className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 pb-1 border-b border-gray-700 w-full">
              Incident Details
            </legend>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Date *</label>
                <input
                  type="date"
                  name="incident_date"
                  required
                  value={form.incident_date}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Classification *</label>
                <select
                  name="classification"
                  required
                  value={form.classification}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                >
                  {Object.entries(CLASSIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Location Description *</label>
              <input
                name="location_description"
                required
                value={form.location_description}
                onChange={handleChange}
                placeholder="e.g., New Smyrna Beach, near the inlet"
                className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm placeholder-gray-500"
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Country *</label>
                <input
                  name="country"
                  required
                  value={form.country}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">State / Province</label>
                <input
                  name="state_province"
                  value={form.state_province}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Body of Water</label>
                <input
                  name="body_of_water"
                  value={form.body_of_water}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
            </div>
          </fieldset>

          {/* Victim */}
          <fieldset className="space-y-4">
            <legend className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 pb-1 border-b border-gray-700 w-full">
              Victim Information
            </legend>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Name</label>
                <input
                  name="victim_name"
                  value={form.victim_name}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Age</label>
                <input
                  name="victim_age"
                  type="number"
                  min="0"
                  max="120"
                  value={form.victim_age}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Sex</label>
                <select
                  name="victim_sex"
                  value={form.victim_sex}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                >
                  <option value="">Unknown</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Activity</label>
                <select
                  name="victim_activity"
                  value={form.victim_activity}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                >
                  <option value="">Unknown</option>
                  {ACTIVITY_OPTIONS.map((a) => (
                    <option key={a} value={a}>
                      {a.charAt(0).toUpperCase() + a.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Injury Severity</label>
                <select
                  name="victim_injury_severity"
                  value={form.victim_injury_severity}
                  onChange={handleChange}
                  className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm"
                >
                  <option value="">Unknown</option>
                  {SEVERITY_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                name="fatal"
                checked={form.fatal}
                onChange={handleChange}
                className="rounded border-gray-600 text-red-500 focus:ring-red-500 bg-gray-700"
              />
              <span className="text-gray-300">Fatal incident</span>
            </label>
          </fieldset>

          {/* Shark */}
          <fieldset className="space-y-4">
            <legend className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 pb-1 border-b border-gray-700 w-full">
              Shark Information
            </legend>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Suspected Species</label>
              <input
                name="shark_species_suspected"
                value={form.shark_species_suspected}
                onChange={handleChange}
                placeholder="e.g., Carcharodon carcharias"
                className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm placeholder-gray-500"
              />
            </div>
          </fieldset>

          {/* Description */}
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-2">
              Incident Description
            </label>
            <textarea
              name="description"
              rows={4}
              value={form.description}
              onChange={handleChange}
              placeholder="Describe the incident..."
              className="w-full bg-gray-800 text-white rounded px-3 py-2 border border-gray-700 text-sm placeholder-gray-500 resize-y"
            />
          </div>

          {/* Sources */}
          <fieldset className="space-y-3">
            <legend className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 pb-1 border-b border-gray-700 w-full">
              Sources
            </legend>
            {sources.map((src, i) => (
              <div key={i} className="bg-gray-800/50 rounded p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Source {i + 1}</span>
                  {sources.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeSource(i)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={src.source_type}
                    onChange={(e) => handleSourceChange(i, "source_type", e.target.value)}
                    className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 border border-gray-700"
                  >
                    <option value="news_article">News Article</option>
                    <option value="government_report">Government Report</option>
                    <option value="scientific_paper">Scientific Paper</option>
                    <option value="witness_account">Witness Account</option>
                    <option value="video">Video</option>
                    <option value="photo">Photo</option>
                    <option value="social_media">Social Media</option>
                    <option value="other">Other</option>
                  </select>
                  <input
                    placeholder="Publisher"
                    value={src.source_publisher}
                    onChange={(e) => handleSourceChange(i, "source_publisher", e.target.value)}
                    className="bg-gray-800 text-white text-xs rounded px-2 py-1.5 border border-gray-700 placeholder-gray-500"
                  />
                </div>
                <input
                  placeholder="Source URL"
                  value={src.source_url}
                  onChange={(e) => handleSourceChange(i, "source_url", e.target.value)}
                  className="w-full bg-gray-800 text-white text-xs rounded px-2 py-1.5 border border-gray-700 placeholder-gray-500"
                />
                <input
                  placeholder="Title"
                  value={src.source_title}
                  onChange={(e) => handleSourceChange(i, "source_title", e.target.value)}
                  className="w-full bg-gray-800 text-white text-xs rounded px-2 py-1.5 border border-gray-700 placeholder-gray-500"
                />
              </div>
            ))}
            <button
              type="button"
              onClick={addSource}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              + Add another source
            </button>
          </fieldset>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 text-white rounded-lg py-3 font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {submitting ? "Submitting..." : "Submit Incident"}
          </button>
        </form>
      </div>
    </div>
  );
}
