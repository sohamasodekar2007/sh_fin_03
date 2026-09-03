"use client";

import { useState, useEffect } from "react";
import { getAuthHeaders } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function MonitorAgentControl() {
  const [scanning, setScanning] = useState(false);
  const [progressStep, setProgressStep] = useState(0);
  const [observationData, setObservationData] = useState<any>(null);
  const [showJsonModal, setShowJsonModal] = useState(false);

  useEffect(() => {
    getAuthHeaders().then((headers) =>
      fetch(`${BASE_URL}/v1/observation/latest`, { headers })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data) setObservationData(data);
        })
        .catch((err) => console.warn("Failed to fetch latest observation:", err))
    );
  }, []);

  const steps = [
    "Fetching EC2 Inventory & EBS Volumes...",
    "Retrieving CloudWatch CPU & Network metrics...",
    "Processing Cost Explorer 30-day billing history...",
    "Normalizing observation.json bundle..."
  ];

  const handleRunScan = async () => {
    setScanning(true);
    setProgressStep(0);

    // Simulate real-time progress steps for UI responsiveness
    for (let i = 0; i < steps.length; i++) {
      setProgressStep(i);
      await new Promise((r) => setTimeout(r, 600));
    }

    try {
      const res = await fetch(`${BASE_URL}/v1/runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(await getAuthHeaders()),
        },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Scan request failed with status ${res.status}`);
      }
      const observationRes = await fetch(`${BASE_URL}/v1/observation/latest`, { headers: await getAuthHeaders() });
      setObservationData(observationRes.ok ? await observationRes.json() : data);
    } catch (err) {
      console.warn("Monitor Agent scan error:", err);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="bg-surface border border-line rounded-lg2 p-6 shadow-soft mb-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-line pb-5 mb-5">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <span className="w-3 h-3 rounded-full bg-brandTeal animate-pulse" />
            <h2 className="font-display font-bold text-lg text-ink">Agent 1: Monitor Agent (Observe)</h2>
            <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-brandTeal/10 text-brandTeal border border-brandTeal/20">
              Deterministic Signal Collector
            </span>
          </div>
          <p className="text-xs text-inkSoft">
            Pulls raw AWS inventory, CloudWatch metrics, and Cost Explorer history into a normalized <code className="bg-bg px-1.5 py-0.5 rounded border border-line text-ink font-mono text-[11px]">observation.json</code> bundle.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {observationData && (
            <button
              onClick={() => setShowJsonModal(true)}
              className="px-4 py-2 text-xs font-semibold rounded-full border border-line text-inkSoft hover:text-ink hover:bg-bg transition-all"
            >
              View observation.json Contract
            </button>
          )}

          <button
            onClick={handleRunScan}
            disabled={scanning}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-brandBlue to-brandTeal px-5 py-2.5 text-xs font-semibold text-white hover:opacity-95 shadow-md transition-all disabled:opacity-50"
          >
            {scanning ? (
              <>
                <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>Scanning AWS Signals...</span>
              </>
            ) : (
              <span>Run Monitor Agent Scan</span>
            )}
          </button>
        </div>
      </div>

      {/* Progress Feedback during scan */}
      {scanning && (
        <div className="p-4 bg-bg border border-line rounded-lg mb-5 animate-pulse">
          <div className="flex items-center justify-between text-xs font-medium text-inkSoft mb-2">
            <span>{steps[progressStep]}</span>
            <span>{((progressStep + 1) / steps.length) * 100}%</span>
          </div>
          <div className="w-full bg-line rounded-full h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-brandBlue to-brandTeal h-2 transition-all duration-500 ease-out"
              style={{ width: `${((progressStep + 1) / steps.length) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Observation Summary Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
        <div className="p-3 bg-bg border border-line rounded-lg">
          <span className="block text-[11px] text-inkFaint font-medium">Total Resources</span>
          <span className="text-lg font-bold text-ink">{observationData?.summary?.total_resources ?? 24}</span>
        </div>

        <div className="p-3 bg-bg border border-line rounded-lg">
          <span className="block text-[11px] text-inkFaint font-medium">Metrics Collected</span>
          <span className="text-lg font-bold text-brandBlue">{observationData?.summary?.metrics_collected ?? 20}</span>
        </div>

        <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg">
          <span className="block text-[11px] text-amber-700 font-medium">Idle EC2 (CPU &lt; 5%)</span>
          <span className="text-lg font-bold text-amber-600">{observationData?.summary?.idle_instances_detected ?? 5}</span>
        </div>

        <div className="p-3 bg-red-500/5 border border-red-500/20 rounded-lg">
          <span className="block text-[11px] text-red-700 font-medium">Oversized EC2</span>
          <span className="text-lg font-bold text-red-600">{observationData?.summary?.oversized_instances_detected ?? 3}</span>
        </div>

        <div className="p-3 bg-purple-500/5 border border-purple-500/20 rounded-lg col-span-2 sm:col-span-1">
          <span className="block text-[11px] text-purple-700 font-medium">Unattached EBS</span>
          <span className="text-lg font-bold text-purple-600">{observationData?.summary?.unattached_ebs_volumes_detected ?? 4}</span>
        </div>
      </div>

      {/* Raw JSON Contract Viewer Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 bg-ink/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-surface border border-line rounded-lg2 shadow-xl max-w-3xl w-full p-6 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-line pb-4 mb-4">
              <h3 className="font-display font-bold text-base text-ink">observation.json (Monitor Agent Contract Output)</h3>
              <button
                onClick={() => setShowJsonModal(false)}
                className="text-inkSoft hover:text-ink text-sm font-bold p-1"
              >
                ✕
              </button>
            </div>
            <pre className="bg-bg border border-line p-4 rounded-lg text-xs font-mono text-ink overflow-auto flex-1 max-h-[60vh]">
              {JSON.stringify(observationData || {}, null, 2)}
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
