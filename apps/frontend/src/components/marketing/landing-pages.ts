import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Cloud,
  Database,
  Gauge,
  GitBranch,
  KeyRound,
  Layers3,
  LockKeyhole,
  LucideIcon,
  ShieldCheck,
  Target,
  TrendingDown,
  WalletCards,
} from "lucide-react";

export type MarketingPage = {
  slug: string;
  eyebrow: string;
  title: string;
  accent: string;
  summary: string;
  metric: string;
  metricLabel: string;
  rows: Array<{ label: string; value: string }>;
  proof: Array<{ label: string; value: string }>;
  pillars: Array<{ icon: LucideIcon; title: string; body: string }>;
  workflow: string[];
  outcomes: string[];
};

export const marketingPages: MarketingPage[] = [
  {
    slug: "cloud-cost-control",
    eyebrow: "Cloud spend control",
    title: "Find waste, prove impact, and reduce cloud cost before the invoice lands.",
    accent: "Spend does not wait for month-end reports.",
    summary:
      "CloudCare continuously watches EC2, EBS, RDS, S3, Lambda, CloudFront, DynamoDB, and more. It turns raw usage into prioritized savings moves your team can trust.",
    metric: "$42.8K",
    metricLabel: "validated monthly savings pipeline",
    rows: [
      { label: "Idle EC2 capacity", value: "$13.4K" },
      { label: "Over-sized RDS", value: "$9.7K" },
      { label: "Cold storage moves", value: "$7.2K" },
      { label: "Unattached volumes", value: "$4.1K" },
    ],
    proof: [
      { label: "Coverage", value: "8+ AWS cost surfaces" },
      { label: "Signal", value: "resource-level evidence" },
      { label: "Action", value: "approval-gated fixes" },
    ],
    pillars: [
      {
        icon: TrendingDown,
        title: "Waste detection that names the resource",
        body: "Every recommendation points to the exact service, resource, utilization pattern, and estimated savings path.",
      },
      {
        icon: BarChart3,
        title: "Forecasts before finance surprises",
        body: "Daily trend analysis highlights abnormal burn, month-end exposure, and budget drift while there is still time to react.",
      },
      {
        icon: CheckCircle2,
        title: "Savings proposals your team can approve",
        body: "CloudCare moves from insight to controlled execution with owner context, blast-radius checks, and auditable approval records.",
      },
    ],
    workflow: ["Collect live usage", "Score waste", "Attach proof", "Request approval", "Execute safely"],
    outcomes: [
      "Reduce idle infrastructure without relying on spreadsheet hunts.",
      "Give finance and engineering one shared savings queue.",
      "Show leadership the difference between theoretical and approved savings.",
    ],
  },
  {
    slug: "autonomous-finops-agents",
    eyebrow: "Autonomous FinOps agents",
    title: "A cloud cost team that keeps working after the dashboard closes.",
    accent: "Dashboards show problems. Agents keep pushing them forward.",
    summary:
      "CloudCare uses specialized monitor, analyzer, supervisor, decision, and executor agents to keep cloud optimization alive across detection, review, approval, and action.",
    metric: "5",
    metricLabel: "specialized agents in one loop",
    rows: [
      { label: "Monitor agent", value: "live" },
      { label: "Analyzer agent", value: "scoring" },
      { label: "Supervisor agent", value: "guarding" },
      { label: "Executor agent", value: "approval only" },
    ],
    proof: [
      { label: "Loop", value: "observe to execute" },
      { label: "Control", value: "human approval" },
      { label: "Audit", value: "agent activity log" },
    ],
    pillars: [
      {
        icon: Bot,
        title: "Role-based agents",
        body: "Each agent has a narrow job, so recommendations are collected, reasoned, checked, and executed through a visible chain.",
      },
      {
        icon: GitBranch,
        title: "Decision flow, not random automation",
        body: "CloudCare separates finding, approval, and execution so every cost move has a reason and a responsible checkpoint.",
      },
      {
        icon: Activity,
        title: "Always-on follow-through",
        body: "When a savings proposal needs resurfacing, updated evidence, or execution status, the agent loop keeps the work moving.",
      },
    ],
    workflow: ["Observe", "Analyze", "Propose", "Approve", "Execute", "Verify"],
    outcomes: [
      "Stop losing savings opportunities inside static reports.",
      "Give teams an operating model for FinOps work, not only another chart.",
      "Keep automation useful without removing human control.",
    ],
  },
  {
    slug: "governance-security",
    eyebrow: "Governance and safety",
    title: "Cut cloud waste without creating security or production risk.",
    accent: "Cost optimization fails when teams cannot trust the action.",
    summary:
      "CloudCare adds IAM, tag governance, policy checks, dependency context, and approval tokens around recommendations so savings do not come at the cost of control.",
    metric: "0",
    metricLabel: "unauthorized production actions",
    rows: [
      { label: "IAM exposure checks", value: "enabled" },
      { label: "Tag ownership", value: "mapped" },
      { label: "Dependency context", value: "required" },
      { label: "Approval tokens", value: "enforced" },
    ],
    proof: [
      { label: "Security", value: "IAM findings" },
      { label: "Policy", value: "guardrail engine" },
      { label: "Trace", value: "execution audit" },
    ],
    pillars: [
      {
        icon: ShieldCheck,
        title: "Guardrails before action",
        body: "CloudCare checks service risk, dependency signals, governance data, and policy rules before a recommendation becomes executable.",
      },
      {
        icon: KeyRound,
        title: "Approval tokens",
        body: "Actions can require explicit approval, giving finance and engineering confidence that automation remains accountable.",
      },
      {
        icon: LockKeyhole,
        title: "Security-aware optimization",
        body: "IAM and resource findings sit beside cost recommendations, making it easier to avoid trading lower spend for weaker posture.",
      },
    ],
    workflow: ["Detect risk", "Check ownership", "Evaluate policy", "Require approval", "Record audit"],
    outcomes: [
      "Make cost actions acceptable for production workloads.",
      "Show auditors who approved what, when, and why.",
      "Tie cost control to governance instead of treating it as a separate process.",
    ],
  },
  {
    slug: "multi-cloud-vps",
    eyebrow: "Multi-cloud and VPS intelligence",
    title: "One cost brain for AWS, Azure, FOCUS data, and VPS fleets.",
    accent: "Modern infrastructure spend is not only inside one AWS bill.",
    summary:
      "CloudCare normalizes resources and cost signals across providers so teams can compare cloud accounts, VPS nodes, and service categories in one operational view.",
    metric: "4",
    metricLabel: "provider families normalized",
    rows: [
      { label: "AWS accounts", value: "covered" },
      { label: "Azure resources", value: "mapped" },
      { label: "FOCUS data", value: "normalized" },
      { label: "VPS inventory", value: "scored" },
    ],
    proof: [
      { label: "Model", value: "FOCUS-style normalization" },
      { label: "VPS", value: "inventory and metrics" },
      { label: "Cloud", value: "multi-account ready" },
    ],
    pillars: [
      {
        icon: Cloud,
        title: "Cross-provider visibility",
        body: "Cost and resource data are mapped into shared structures so mixed infrastructure can be understood without separate dashboards.",
      },
      {
        icon: Database,
        title: "FOCUS-aligned summaries",
        body: "Normalized spend views make it easier to explain where money goes across accounts, providers, services, and owners.",
      },
      {
        icon: Layers3,
        title: "VPS fleet awareness",
        body: "CloudCare brings VPS inventory and utilization into the same optimization story as cloud-native resources.",
      },
    ],
    workflow: ["Connect providers", "Normalize resources", "Map costs", "Compare owners", "Prioritize savings"],
    outcomes: [
      "Avoid blind spots outside AWS Cost Explorer.",
      "Create one executive view across cloud and VPS spend.",
      "Rank savings opportunities across providers instead of by tool silo.",
    ],
  },
  {
    slug: "executive-command-center",
    eyebrow: "Executive command center",
    title: "Give CFOs, founders, and engineering leaders one live control room.",
    accent: "Leadership needs decisions, not another raw export.",
    summary:
      "CloudCare packages spend velocity, forecasts, unit economics, proposals, resources, and agent activity into an operating dashboard for fast cost decisions.",
    metric: "1",
    metricLabel: "single operating picture",
    rows: [
      { label: "Spend velocity", value: "tracked" },
      { label: "Forecast exposure", value: "projected" },
      { label: "Unit economics", value: "linked" },
      { label: "Savings proposals", value: "queued" },
    ],
    proof: [
      { label: "Finance", value: "forecast-ready" },
      { label: "Engineering", value: "resource-level" },
      { label: "Ops", value: "agent timeline" },
    ],
    pillars: [
      {
        icon: Gauge,
        title: "Spend velocity",
        body: "Track how fast cloud spend is moving and where today's decisions affect the month-end number.",
      },
      {
        icon: WalletCards,
        title: "Unit economics",
        body: "Connect infrastructure cost to business context so savings decisions support margin, runway, and product ownership.",
      },
      {
        icon: Target,
        title: "Proposal pipeline",
        body: "Prioritized opportunities turn leadership reviews into approval decisions instead of open-ended investigation.",
      },
    ],
    workflow: ["Watch spend", "Forecast risk", "Rank proposals", "Approve action", "Track savings"],
    outcomes: [
      "Make cloud spend explainable to finance and actionable for engineering.",
      "Turn cost reviews into decision meetings.",
      "Show savings progress with resource-level accountability.",
    ],
  },
];

export const comparisonRows = [
  {
    capability: "Primary job",
    aws: "Report AWS spend and billing history",
    cloudcare: "Find, prioritize, approve, and execute savings opportunities",
  },
  {
    capability: "Actionability",
    aws: "Charts, exports, budgets, and alerts",
    cloudcare: "Resource-level proposals with evidence, owners, risk checks, and next actions",
  },
  {
    capability: "Automation",
    aws: "Limited billing alerts and service-native recommendations",
    cloudcare: "Agent loop from monitoring to safe approval-gated execution",
  },
  {
    capability: "Governance",
    aws: "IAM and account tools live separately",
    cloudcare: "Cost, IAM, tags, policies, approvals, and execution audit in one workflow",
  },
  {
    capability: "Provider scope",
    aws: "AWS-first by design",
    cloudcare: "AWS plus Azure, FOCUS-style summaries, and VPS fleet intelligence",
  },
  {
    capability: "Best for",
    aws: "Finance recordkeeping and native AWS billing truth",
    cloudcare: "Winning daily FinOps execution across finance, engineering, and leadership",
  },
];

export const comparisonVerdict = [
  "Keep AWS Billing as the source of billing truth.",
  "Use CloudCare when you need a working system that turns spend data into savings action.",
  "CloudCare is not just a bill viewer. It is an AI-powered FinOps operating layer.",
];

export const solutionLinks = [
  { label: "Cost Control", href: "/solutions/cloud-cost-control" },
  { label: "AI Agents", href: "/solutions/autonomous-finops-agents" },
  { label: "Governance", href: "/solutions/governance-security" },
  { label: "Multi-Cloud", href: "/solutions/multi-cloud-vps" },
  { label: "Command Center", href: "/solutions/executive-command-center" },
  { label: "Vs AWS Billing", href: "/cloudcare-vs-aws-billing" },
];
