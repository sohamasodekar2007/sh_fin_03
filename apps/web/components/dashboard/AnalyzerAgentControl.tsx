"use client";

import { useState, useEffect } from "react";
import { getAuthHeaders } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function AnalyzerAgentControl() {
  const [analyzing, setAnalyzing] = useState(false);
  const [findingsData, setFindingsData] = useState<any>(null);
  const [showJsonModal, setShowJsonModal] = useState(false);

  useEffect(() => {
    fetch(`${BASE_URL}/v1/agent/analyze/latest`, {
      credentials: "include",
      headers: { ...getAuthHeaders() },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setFindingsData(data);
      })
      .catch((err) => console.warn("Failed to fetch latest findings:", err));
  }, []);

  const handleRunAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await fetch(`${BASE_URL}/v1/agent/analyze`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Analysis request failed with status ${res.status}`);
      }
      setFindingsData(data);
    } catch (err) {
      console.warn("Analyzer Agent error:", err);
    } finally {
      setAnalyzing(false);
    }
  };

  const getRuleBadgeColor = (ruleId: string) => {
    switch (ruleId) {
      case "ec2.idle.v1":
        return "bg-amber-500/10 text-amber-600 border-amber-500/20";
      case "ec2.overprovisioned.v1":
        return "bg-blue-500/10 text-blue-600 border-blue-500/20";
      case "ebs.unattached.v1":
        return "bg-purple-500/10 text-purple-600 border-purple-500/20";
      case "ec2.nonprod_schedule.v1":
        return "bg-teal-500/10 text-teal-600 border-teal-500/20";
      case "cost.anomaly.v1":
        return "bg-red-500/10 text-red-600 border-red-500/20";
      default:
        return "bg-line text-inkSoft border-line";
    }
  };

  return (
    <div className="bg-surface border border-line rounded-lg2 p-6 shadow-soft mb-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-line pb-5 mb-5">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <span className="w-3 h-3 rounded-full bg-brandBlue animate-pulse" />
            <h2 className="font-display font-bold text-lg text-ink">Agent 2: Analyzer Agent (Detect)</h2>
            <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-brandBlue/10 text-brandBlue border border-brandBlue/20">
              Rule Engine Evaluator
            </span>
          </div>
          <p className="text-xs text-inkSoft">
            Evaluates deterministic rules (idle CPU, over-provisioning, unattached storage, off-hours schedule, spend anomalies) against the Monitor observation bundle.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {findingsData && (
            <button
              onClick={() => setShowJsonModal(true)}
              className="px-4 py-2 text-xs font-semibold rounded-full border border-line text-inkSoft hover:text-ink hover:bg-bg transition-all"
            >
              View findings.json Contract
            </button>
          )}

          <button
            onClick={handleRunAnalysis}
            disabled={analyzing}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-brandBlue to-purple-600 px-5 py-2.5 text-xs font-semibold text-white hover:opacity-95 shadow-md transition-all disabled:opacity-50"
          >
            {analyzing ? (
              <>
                <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>Evaluating Rules...</span>
              </>
            ) : (
              <span>Run Analyzer Agent</span>
            )}
          </button>
        </div>
      </div>

      {/* Findings Breakdown Grid */}
      {findingsData ? (
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-ink">
              Total Inefficiencies Detected: {findingsData.findings_count || 0}
            </span>
            <span className="text-[11px] text-inkFaint font-mono">
              Last Evaluated: {new Date(findingsData.timestamp || Date.now()).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 max-h-64 overflow-y-auto pr-1">
            {findingsData.findings?.map((finding: any, idx: number) => (
              <div key={idx} className="p-3 bg-bg border border-line rounded-lg flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${getRuleBadgeColor(finding.rule_id)}`}>
                      {finding.rule_id}
                    </span>
                    <span className="text-[10px] font-semibold uppercase text-inkFaint">
                      Conf: {Math.round(finding.confidence * 100)}%
                    </span>
                  </div>
                  <p className="text-xs font-semibold text-ink font-mono truncate">{finding.resource_id}</p>
                </div>
                <div className="mt-2 text-[11px] text-inkSoft bg-surface p-2 rounded border border-line/60 font-mono">
                  {Object.entries(finding.evidence || {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-inkFaint">{k}:</span>
                      <span className="font-semibold text-ink">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="p-4 bg-bg border border-line rounded-lg text-center">
          <p className="text-xs text-inkFaint">Click <strong>"Run Analyzer Agent"</strong> to execute rules against the observation bundle.</p>
        </div>
      )}

      {/* Findings Contract Viewer Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 bg-ink/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-surface border border-line rounded-lg2 shadow-xl max-w-3xl w-full p-6 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-line pb-4 mb-4">
              <h3 className="font-display font-bold text-base text-ink">findings.json (Analyzer Agent Contract Output)</h3>
              <button
                onClick={() => setShowJsonModal(false)}
                className="text-inkSoft hover:text-ink text-sm font-bold p-1"
              >
                ✕
              </button>
            </div>
            <pre className="bg-bg border border-line p-4 rounded-lg text-xs font-mono text-ink overflow-auto flex-1 max-h-[60vh]">
              {JSON.stringify(findingsData || {}, null, 2)}
            </pre>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowJsonModal(false)}
                className="px-5 py-2 bg-ink text-white rounded-full text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
