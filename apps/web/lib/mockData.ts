// ---------------------------------------------------------------------------
// MOCK DATA
// ---------------------------------------------------------------------------
// Everything in this file is hardcoded demo data for the hackathon prototype.
// PLACEHOLDER: replace these with real fetch() calls to the FastAPI backend
// once it's wired to MongoDB + AWS, e.g.:
//
//   const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/resources`);
//   const resources: Resource[] = await res.json();
//
// The shapes below intentionally mirror the backend Pydantic schemas in
// backend/app/models/schemas.py so swapping mock -> real data is a
// find-and-replace, not a redesign.
// ---------------------------------------------------------------------------

export const kpis = [
  { label: "Total monthly spend", value: "$12,450", tone: "neutral" as const },
  { label: "Wasted spend detected", value: "$3,890", sub: "31%", tone: "amber" as const },
  { label: "Savings this month", value: "$2,100", tone: "teal" as const },
  { label: "Resources monitored", value: "47", tone: "neutral" as const },
];

export const costTrend = [
  { day: "Day 1", cost: 480 },
  { day: "Day 5", cost: 495 },
  { day: "Day 10", cost: 505 },
  { day: "Day 14", cost: 512 },
  { day: "Day 15", cost: 470 }, // optimization started
  { day: "Day 18", cost: 440 },
  { day: "Day 22", cost: 410 },
  { day: "Day 26", cost: 390 },
  { day: "Day 30", cost: 365 },
];

export const healthBreakdown = [
  { name: "Healthy", value: 60, color: "#3FA796" },
  { name: "Idle", value: 20, color: "#E2A93B" },
  { name: "Over-provisioned", value: 15, color: "#2F6690" },
  { name: "At-risk", value: 5, color: "#D85A30" },
];

export type AgentName = "Monitor" | "Analyzer" | "Decision" | "Supervisor" | "Executor";

export interface AgentActivityEntry {
  id: string;
  agent: AgentName;
  message: string;
  timestamp: string;
}

export const agentActivity: AgentActivityEntry[] = [
  { id: "1", agent: "Monitor", message: "Collected CloudWatch metrics for 47 EC2 instances", timestamp: "10:02:14" },
  { id: "2", agent: "Analyzer", message: "Flagged i-0912ab3c4d5e6f701 as idle — CPU 3% avg over 7 days", timestamp: "10:02:41" },
  { id: "3", agent: "Decision", message: "Proposed: stop instance i-0912ab3c4d5e6f701 — risk: low", timestamp: "10:02:55" },
  { id: "4", agent: "Supervisor", message: "Approved — auto-executing (env=dev, low risk)", timestamp: "10:03:02" },
  { id: "5", agent: "Executor", message: "Stopped i-0912ab3c4d5e6f701 — saved $14.20/month", timestamp: "10:03:09" },
  { id: "6", agent: "Supervisor", message: "Routed i-0455cd8e9f0a1b234 (env=prod) to human review", timestamp: "10:04:18" },
];

export type ResourceStatus = "Healthy" | "Idle" | "Over-provisioned" | "At-risk";

export interface ResourceRow {
  id: string;
  type: string;
  cpu: number;
  status: ResourceStatus;
  monthlyCost: string;
}

export const resources: ResourceRow[] = [
  { id: "i-0912ab3c4d5e6f701", type: "t3.medium", cpu: 3, status: "Idle", monthlyCost: "$28.40" },
  { id: "i-0455cd8e9f0a1b234", type: "t3.large", cpu: 78, status: "Healthy", monthlyCost: "$61.20" },
  { id: "i-0a1b2c3d4e5f60789", type: "t2.micro", cpu: 12, status: "Over-provisioned", monthlyCost: "$8.50" },
  { id: "i-0f9e8d7c6b5a41230", type: "m5.large", cpu: 91, status: "At-risk", monthlyCost: "$98.10" },
  { id: "i-0cafe1234deadbeef", type: "t3.small", cpu: 45, status: "Healthy", monthlyCost: "$16.80" },
  { id: "i-0b00b1e5f00dcafe0", type: "t3.medium", cpu: 6, status: "Idle", monthlyCost: "$28.40" },
];

export const nextSteps = [
  "Connect your AWS account (read-only) to start real monitoring",
  "Review the resources flagged as idle or over-provisioned",
  "Check the Agent Activity feed to see what CloudCare is proposing",
  "Approve or reject any actions waiting in your Approval Queue",
  "Visit Settings to configure policies and notification preferences",
];

export const teamMembers = [
  { name: "Sumaira Mulla", role: "Team Lead", initials: "SM", from: "#2F6690", to: "#3FA796" },
  { name: "Shruti Jahagirdar", role: "Team Alpha", initials: "SJ", from: "#3FA796", to: "#E2A93B" },
  { name: "Himanshu Lodha", role: "Team Alpha", initials: "HL", from: "#E2A93B", to: "#2F6690" },
  { name: "Soham Asodekar", role: "Team Alpha", initials: "SA", from: "#2F6690", to: "#8CA0AE" },
  { name: "Anay Gawade", role: "Team Alpha", initials: "AG", from: "#3FA796", to: "#2F6690" },
];

export const pipelineStages = [
  { title: "Observe", desc: "Metrics, billing, tags" },
  { title: "Detect", desc: "Idle, waste, anomalies" },
  { title: "Plan", desc: "Savings, risk, confidence" },
  { title: "Validate", desc: "Policies, blast radius" },
  { title: "Approve", desc: "Auto / human gate" },
  { title: "Execute", desc: "Idempotent template" },
  { title: "Verify", desc: "Performance + savings" },
];

export const featureCards = [
  { tag: "MONITOR", title: "Continuous monitoring", desc: "Reads live EC2, CloudWatch and Cost Explorer data around the clock." },
  { tag: "ANALYZE", title: "Evidence-based detection", desc: "Flags idle, over-provisioned and unattached resources with real usage evidence." },
  { tag: "FORECAST", title: "Spend forecasting", desc: "Projects monthly cost and budget burn rate before the bill arrives." },
  { tag: "DECIDE", title: "Risk-scored recommendations", desc: "Every proposal ships with expected savings, confidence and rationale." },
  { tag: "EXECUTE", title: "Safety-first automation", desc: "Low-risk actions run themselves. Production waits for a human." },
  { tag: "VERIFY", title: "Full audit trail", desc: "Every action traces back to the metric, the agent, and the outcome." },
];
