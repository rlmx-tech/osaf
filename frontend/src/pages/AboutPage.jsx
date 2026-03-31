import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { CLASSIFICATION_COLORS, CLASSIFICATION_LABELS } from "../utils/constants";
import client from "../api/client";

export default function AboutPage() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    client
      .get("/stats/overview")
      .then((res) => setStats(res.data?.data || res.data))
      .catch(() => {});
  }, []);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white">
      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Hero */}
        <div className="mb-10">
          <h1 className="text-4xl font-bold mb-3">About OSAF</h1>
          <p className="text-lg text-gray-300 leading-relaxed">
            The <strong>Open Shark Attack File</strong> is an open-source, community-driven
            shark incident database. It provides transparent, publicly accessible records of
            shark-human interactions worldwide — an open alternative to restricted academic
            databases.
          </p>
        </div>

        {/* Live stats bar */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-10">
            {[
              { label: "Total Incidents", value: stats.total_incidents?.toLocaleString() },
              { label: "Fatal Incidents", value: stats.total_fatal?.toLocaleString() },
              { label: "Year Range", value: stats.year_range },
              { label: "Fatality Rate", value: stats.fatality_rate ? `${stats.fatality_rate}%` : "—" },
            ].map((s) => (
              <div key={s.label} className="bg-gray-800 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-blue-400">{s.value || "—"}</div>
                <div className="text-xs text-gray-500 mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Why OSAF */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-4">Why OSAF?</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {[
              {
                title: "Open Data",
                desc: "All incident data is public. No gatekeeping behind academic access requests or institutional affiliations.",
              },
              {
                title: "Community-Driven",
                desc: "Anyone can submit incidents. Verified contributors auto-publish; public submissions go through admin review.",
              },
              {
                title: "Faster Coverage",
                desc: "Automated collectors monitor news, social media, and tracking sites for rapid documentation of new incidents.",
              },
              {
                title: "Open Source",
                desc: "The entire codebase, methodology, and dataset are transparent and available for review and contribution.",
              },
            ].map((item) => (
              <div key={item.title} className="bg-gray-800 rounded-lg p-4">
                <h3 className="font-semibold text-blue-400 mb-1">{item.title}</h3>
                <p className="text-sm text-gray-400">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Classification System */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-3">Classification System</h2>
          <p className="text-gray-400 mb-4">
            OSAF uses a classification methodology based on the system developed by the
            International Shark Attack File (ISAF) at the Florida Museum of Natural History.
            Classifications describe shark behavior in response to varying stimuli. They do
            not diminish the experiences of victims.
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {[
              { key: "unprovoked", desc: "Bite on a live human with no provocation in the shark's natural habitat" },
              { key: "provoked", desc: "Human initiated interaction — touching, feeding, unhooking, spearfishing nearby" },
              { key: "boat_bite", desc: "Bite on a vessel of any size, from kayak to yacht" },
              { key: "scavenge", desc: "Feeding on a body after the person died from unrelated causes" },
              { key: "sighting", desc: "Shark spotted near humans but no physical contact" },
              { key: "near_miss", desc: "Shark approached closely but did not bite" },
              { key: "equipment_bite", desc: "Shark bites surfboard, fishing gear, etc. — not the person" },
              { key: "not_confirmed", desc: "Shark involvement unclear or unverified" },
            ].map((c) => (
              <div key={c.key} className="flex items-start gap-2 bg-gray-800/50 rounded px-3 py-2">
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0 mt-0.5"
                  style={{ backgroundColor: CLASSIFICATION_COLORS[c.key] }}
                />
                <div>
                  <span className="text-sm font-medium">{CLASSIFICATION_LABELS[c.key]}</span>
                  <p className="text-xs text-gray-500">{c.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Data Sources */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-3">Data Sources</h2>
          <p className="text-gray-400 mb-4">
            OSAF aggregates data from multiple verified sources to build a comprehensive record.
          </p>
          <div className="space-y-2">
            {[
              {
                name: "Global Shark Attack File (GSAF)",
                desc: "Primary historical dataset maintained by the Shark Research Institute. Covers incidents from 1900 to present.",
                type: "Historical database",
              },
              {
                name: "News Media (Google News RSS)",
                desc: "Automated monitoring of global news for shark incident reports across multiple regions and languages.",
                type: "Automated collector",
              },
              {
                name: "Tracking Sharks",
                desc: "The fastest public aggregator of shark incidents worldwide, cited by BBC, USA Today, and other major outlets.",
                type: "Automated collector",
              },
              {
                name: "YouTube Channels",
                desc: "Drone footage and incident analysis from TheMalibuArtist, DroneSharkApp, SharkBytes, SharksHappen, and others.",
                type: "Automated collector",
              },
              {
                name: "Reddit Communities",
                desc: "Monitoring r/sharks, r/surfing, r/australia, and other subreddits for early incident reports.",
                type: "Automated collector",
              },
              {
                name: "Community Submissions",
                desc: "Public submissions verified by OSAF administrators before publication.",
                type: "User-contributed",
              },
            ].map((s) => (
              <div key={s.name} className="bg-gray-800 rounded-lg px-4 py-3 flex items-start justify-between gap-4">
                <div>
                  <span className="font-medium text-sm">{s.name}</span>
                  <p className="text-xs text-gray-500 mt-0.5">{s.desc}</p>
                </div>
                <span className="text-xs text-gray-600 bg-gray-700 px-2 py-0.5 rounded flex-shrink-0">
                  {s.type}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* How to Contribute */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-3">How to Contribute</h2>
          <div className="bg-gray-800 rounded-lg p-5">
            <ol className="space-y-3 text-sm text-gray-300">
              <li className="flex gap-3">
                <span className="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
                <span><Link to="/login" className="text-blue-400 hover:underline">Create an account</Link> or sign in to OSAF.</span>
              </li>
              <li className="flex gap-3">
                <span className="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
                <span><Link to="/submit" className="text-blue-400 hover:underline">Submit an incident</Link> with location, date, classification, and at least one source URL.</span>
              </li>
              <li className="flex gap-3">
                <span className="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
                <span>An admin reviews your submission and approves, requests changes, or rejects it.</span>
              </li>
              <li className="flex gap-3">
                <span className="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">4</span>
                <span>Once approved, the incident goes live with an OSAF case number (e.g., OSAF-2026-0042).</span>
              </li>
            </ol>
            <p className="text-xs text-gray-500 mt-4">
              Trusted contributors can be promoted to <strong>Verified Contributor</strong> status,
              which allows direct publishing without admin review.
            </p>
          </div>
        </section>

        {/* Contact */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-3">Contact</h2>
          <p className="text-gray-400 text-sm">
            Questions, corrections, or partnership inquiries:{" "}
            <a href="mailto:contact@osaf.net" className="text-blue-400 hover:underline">
              contact@osaf.net
            </a>
          </p>
        </section>

        {/* Inspiration */}
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-3">Inspiration & Acknowledgments</h2>
          <ul className="space-y-2 text-sm text-gray-400">
            <li>
              <strong className="text-gray-300">ISAF Classification System</strong> — Florida Museum of Natural History.
              The gold standard for shark incident classification methodology.
            </li>
            <li>
              <strong className="text-gray-300">Global Shark Attack File</strong> — Shark Research Institute.
              Historical incident data forming the backbone of OSAF's records.
            </li>
            <li>
              <strong className="text-gray-300">SharkBytes</strong> (Kristian Parton) — Marine biologist providing
              educational case analysis and research context on YouTube.
            </li>
            <li>
              <strong className="text-gray-300">SharksHappen</strong> (Hal Miller) — In-depth shark incident
              case studies and research on YouTube.
            </li>
          </ul>
        </section>

        {/* Disclaimer */}
        <section className="border-t border-gray-800 pt-6">
          <h2 className="text-lg font-semibold mb-2 text-gray-400">Disclaimer</h2>
          <p className="text-sm text-gray-500 leading-relaxed">
            OSAF is not affiliated with the International Shark Attack File (ISAF), the Florida
            Museum of Natural History, or the Shark Research Institute. It is an independent
            open-source effort. Incident data is aggregated from public sources and community
            submissions. While we strive for accuracy, records should not be considered
            authoritative for scientific research without independent verification. Case
            classifications may be updated as new information becomes available.
          </p>
        </section>
      </div>
    </div>
  );
}
