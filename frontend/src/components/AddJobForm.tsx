import { useState } from "react";
import { api } from "../api/client";
import type { ParsedJob } from "../api/types";

interface Props {
  onJobAdded: () => void;
}

export function AddJobForm({ onJobAdded }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ParsedJob | null>(null);
  const [duplicate, setDuplicate] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleParse = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setPreview(null);
    setDuplicate(null);

    try {
      const dupCheck = await api.checkDuplicate(url.trim());
      if (dupCheck.is_duplicate) {
        setDuplicate(`Already tracked: "${dupCheck.existing_job?.title}" at ${dupCheck.existing_job?.company}`);
        setLoading(false);
        return;
      }
      const parsed = await api.parseUrl(url.trim());
      setPreview(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to parse URL");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!preview) return;
    setSaving(true);
    setError(null);
    try {
      await api.createJob(preview);
      setPreview(null);
      setUrl("");
      onJobAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const formatSalary = (s: ParsedJob["salary"]) => {
    if (!s || (!s.min && !s.max)) return "Not specified";
    const min = s.min?.toLocaleString() ?? "?";
    const max = s.max?.toLocaleString() ?? "?";
    return `${min} - ${max} ${s.currency ?? ""} ${s.type ? `(${s.type})` : ""}`.trim();
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Add Job Offer</h2>

      <div className="flex gap-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleParse()}
          placeholder="Paste justjoin.it or nofluffjobs.com URL..."
          className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
        <button
          onClick={handleParse}
          disabled={loading || !url.trim()}
          className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Parsing..." : "Parse"}
        </button>
      </div>

      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {duplicate && (
        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
          <span className="font-medium">Duplicate detected:</span> {duplicate}
        </div>
      )}

      {preview && (
        <div className="mt-4 border border-gray-200 rounded-lg p-4 bg-gray-50 space-y-3">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold text-gray-900">{preview.title}</h3>
              <p className="text-sm text-gray-600">{preview.company} &middot; {preview.location.join(", ") || "No location"}</p>
            </div>
            <span className="text-xs px-2 py-1 bg-gray-200 rounded-full text-gray-600">
              {preview.source}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <span className="text-gray-500">Salary</span>
              <p className="font-medium">{formatSalary(preview.salary)}</p>
            </div>
            <div>
              <span className="text-gray-500">Seniority</span>
              <p className="font-medium">{preview.seniority || "N/A"}</p>
            </div>
            <div>
              <span className="text-gray-500">Work Type</span>
              <p className="font-medium">{preview.work_type || "N/A"}</p>
            </div>
            <div>
              <span className="text-gray-500">Contract</span>
              <p className="font-medium">{preview.employment_types.join(", ") || "N/A"}</p>
            </div>
          </div>

          {preview.skills_required.length > 0 && (
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Required Skills</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {preview.skills_required.map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded-full">{s}</span>
                ))}
              </div>
            </div>
          )}

          {preview.skills_nice_to_have.length > 0 && (
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Nice to Have</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {preview.skills_nice_to_have.map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-gray-200 text-gray-600 text-xs rounded-full">{s}</span>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving..." : "Save & Track"}
            </button>
            <button
              onClick={() => { setPreview(null); setUrl(""); }}
              className="px-5 py-2 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors"
            >
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
