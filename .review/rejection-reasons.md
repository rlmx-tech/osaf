# Canonical rejection reasons (candidates + evidence queue)

Adopted 2026-09-18. One-click buttons in AdminPage.jsx map to canned
`review_notes`; "Other…" takes free text. Vocabulary aligns with the two
existing scripted notes (reject_headline_only, auto-publisher holds) and the
shadow-soak failure classes — the reasons ARE retrain training-signal labels,
so use the closest match rather than free-text when it applies.

| Button | Canned note (stored in review_notes) | Use when |
|---|---|---|
| Duplicate | Duplicate of an already-published incident (same real-world event). | Same story, already covered; match_rationale confirms the cluster. |
| Headline-only | Source was headline-only; no article body to ground the extraction. | Google News wrappers, stubs — matches the 600 existing bulk rejections. |
| Not shark | Source does not describe a shark incident, sighting, or encounter. | Bird-flu/sea-lion class, politics blogs, unrelated wildlife stories. |
| Wrong date | The extracted incident date is not supported by the source text. | Publication-date vs incident-date confusion (soak's worst field). |
| Wrong location | The extracted location is not supported by the source text. | Geocode mismatches, wrong beach/city. |
| Wrong class | The classification does not match the described incident. | unprovoked/boat_bite/sighting disputes. |
| Fabricated | Extraction contains details not present in the source text. | Over-fill class: invented names, whale/whaler confusion. |
| Superseded | Newer, more complete coverage of the same event exists. | Developing-story cluster cleanup. |
| Other… | (free text) | Anything else — write the actual reason. |

Rationale for the set:
- The two existing prod notes (headline-only, auto-published) are preserved as-is;
  new buttons extend rather than redefine them.
- The soak digest's named disagreement classes (wrong date, fabricated details,
  classification conservatism) each get a dedicated button — these are the
  labels a v3 retrain would train on.
- Approvals need no button set: "created" audit rows need no reason.

Backend note: `review_notes`/`reviewed_by`/`reviewed_at` columns already exist
on incident_candidates and the PUT endpoints accept {"notes": ...} — this is
frontend-only wiring. Optional follow-up: return review_notes in
list_candidates' serializer so rejected rows display their reason.
