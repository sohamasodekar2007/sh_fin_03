"use client";

import * as React from "react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Cloud, Copy, Loader2, Server, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Panel } from "@/components/cfo/Panel";
import { ThemeToggle } from "@/components/cfo/ThemeToggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, isApiError } from "@/lib/api";

type Provider = "aws" | "gcp" | "azure" | "vps";

interface ProviderMeta {
  id: Provider;
  name: string;
  blurb: string;
  sampleDataOnly: boolean;
}

const PROVIDERS: ProviderMeta[] = [
  { id: "aws", name: "AWS", blurb: "Cross-account role, read-only inventory + Cost Explorer.", sampleDataOnly: false },
  { id: "azure", name: "Azure", blurb: "Service principal, resource inventory + Cost Management.", sampleDataOnly: false },
  { id: "gcp", name: "GCP", blurb: "Service account — collector not yet wired to live data.", sampleDataOnly: true },
  { id: "vps", name: "VPS", blurb: "Company-owned server, SSH key-only, configured server-side.", sampleDataOnly: true },
];

const EXTERNAL_ID_PLACEHOLDER = "your-cloudcare-external-id";

const TRUST_POLICY = (externalId: string) => `{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::<CLOUDCARE_ACCOUNT_ID>:root" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "sts:ExternalId": "${externalId || EXTERNAL_ID_PLACEHOLDER}" }
      }
    }
  ]
}`;

const CLOUDFORMATION_SNIPPET = (externalId: string) => `Resources:
  CloudCareReadOnlyRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: CloudCareReadOnlyRole
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              AWS: "arn:aws:iam::<CLOUDCARE_ACCOUNT_ID>:root"
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: "${externalId || EXTERNAL_ID_PLACEHOLDER}"
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/ReadOnlyAccess`;

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          toast.success(`${label} copied.`);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          toast.error("Could not copy — select and copy manually.");
        }
      }}
      aria-label={`Copy ${label}`}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[11.5px] font-medium text-ink-dim transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : `Copy ${label}`}
    </button>
  );
}

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" aria-live="assertive" className="rounded-md border px-3 py-2 text-[12.5px] leading-relaxed" style={{ borderColor: "var(--destructive)", color: "var(--destructive)", background: "color-mix(in oklab, var(--destructive) 8%, transparent)" }}>
      {message}
    </div>
  );
}

function SampleDataBadge() {
  return (
    <Badge variant="outline" className="gap-1.5 border-dashed" style={{ color: "var(--ember)", borderColor: "var(--ember-soft)" }}>
      Using FOCUS sample data
    </Badge>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [openProvider, setOpenProvider] = useState<Provider | null>(null);
  const [connected, setConnected] = useState<Set<Provider>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // AWS
  const [roleArn, setRoleArn] = useState("");
  const [externalId, setExternalId] = useState("");
  // GCP
  const [gcpProjectId, setGcpProjectId] = useState("");
  const [gcpJson, setGcpJson] = useState("");
  // Azure
  const [azureTenantId, setAzureTenantId] = useState("");
  const [azureClientId, setAzureClientId] = useState("");
  const [azureClientSecret, setAzureClientSecret] = useState("");
  const [azureSubscriptionId, setAzureSubscriptionId] = useState("");

  function closeDialog() {
    setOpenProvider(null);
    setError(null);
  }

  async function triggerFirstMonitorRun(provider: Provider) {
    if (provider === "gcp") return; // no live collector to trigger yet — sample data only
    try {
      await api.post(`/v1/agent/observe?provider=${provider}`);
    } catch {
      // The onboarding flow's job is to connect the account, not to block
      // on the first scan succeeding — the hourly scheduler will pick it
      // up regardless. Silently continue to the dashboard.
    }
  }

  async function validateAccount(body: Record<string, unknown>, provider: Provider) {
    setError(null);
    setLoading(true);
    try {
      // CloudAccount (packages/schemas/schemas.py) requires tenant_id as a
      // plain string field — the endpoint itself actually scopes persistence
      // by the JWT's tenant_id, not this value, but Pydantic still rejects
      // the request with 422 if it's missing entirely. This was the bug:
      // none of the three submit* functions below were sending it.
      const result = await api.post<{ validated: boolean; error?: string }>("/v1/cloud-accounts/validate", {
        tenant_id: "demo-tenant",
        ...body,
      });
      if (!result.validated) {
        setError(result.error || "Validation failed — check the credentials and try again.");
        return;
      }
      setConnected((prev) => new Set(prev).add(provider));
      toast.success(`${provider.toUpperCase()} connected.`);
      await triggerFirstMonitorRun(provider);
      closeDialog();
      router.push("/dashboard");
    } catch (err) {
      setError(isApiError(err) ? err.message : "Could not reach the CloudCare API.");
    } finally {
      setLoading(false);
    }
  }

  function submitAws(e: React.FormEvent) {
    e.preventDefault();
    if (!roleArn.trim()) {
      setError("Role ARN is required.");
      return;
    }
    validateAccount({ provider: "aws", account_id: roleArn.split(":")[4] || roleArn, role_arn: roleArn, external_id: externalId || null }, "aws");
  }

  function submitGcp(e: React.FormEvent) {
    e.preventDefault();
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = gcpJson.trim() ? JSON.parse(gcpJson) : null;
    } catch {
      setError("That doesn't look like valid JSON.");
      return;
    }
    if (!parsed || !gcpProjectId.trim()) {
      setError("Project ID and service account JSON are both required.");
      return;
    }
    validateAccount({ provider: "gcp", account_id: gcpProjectId, gcp_service_account_json: parsed }, "gcp");
  }

  function submitAzure(e: React.FormEvent) {
    e.preventDefault();
    if (!azureTenantId.trim() || !azureClientId.trim() || !azureClientSecret.trim()) {
      setError("Tenant ID, Client ID and Client Secret are all required.");
      return;
    }
    validateAccount(
      {
        provider: "azure",
        account_id: azureSubscriptionId || "azure-subscription",
        azure_tenant_id: azureTenantId,
        azure_client_id: azureClientId,
        azure_client_secret: azureClientSecret,
      },
      "azure",
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <header className="stage flex flex-wrap items-start justify-between gap-3 pb-6">
          <div>
            <div className="eyebrow">CloudCare · Setup</div>
            <h1 className="mt-1.5 text-[clamp(1.5rem,2.6vw,2rem)] font-bold leading-tight text-foreground">
              Connect a cloud account
            </h1>
            <p className="mt-1.5 max-w-xl text-[12.5px] leading-relaxed text-ink-faint">
              Read-only to start. CloudCare never mutates anything without a separate write role
              and your explicit approval.
            </p>
          </div>
          <ThemeToggle />
        </header>

        <div className="grid gap-5 sm:grid-cols-2">
          {PROVIDERS.map((p, i) => (
            <Panel
              key={p.id}
              eyebrow={p.sampleDataOnly ? "Preview" : "Live"}
              title={p.name}
              subtitle={p.blurb}
              delay={100 + i * 60}
              aside={connected.has(p.id) ? <Badge style={{ background: "var(--mint)", color: "var(--control-on-fg)" }}>Connected</Badge> : undefined}
            >
              <div className="flex items-center justify-between gap-3">
                {p.sampleDataOnly ? <SampleDataBadge /> : <span className="text-[11.5px] text-ink-faint">Real credentials, validated live.</span>}
                <Button
                  type="button"
                  variant={connected.has(p.id) ? "outline" : "default"}
                  onClick={() => setOpenProvider(p.id)}
                  aria-haspopup="dialog"
                >
                  {connected.has(p.id) ? "Reconfigure" : "Connect"}
                </Button>
              </div>
            </Panel>
          ))}
        </div>
      </div>

      {/* ---- AWS ---- */}
      <Dialog open={openProvider === "aws"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Cloud className="size-4" /> Connect AWS</DialogTitle>
            <DialogDescription>A read-only cross-account role. CloudCare assumes it to collect inventory, metrics and cost — never to mutate anything.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitAws} className="flex flex-col gap-4" noValidate>
            <div className="grid gap-1.5">
              <Label htmlFor="roleArn">Role ARN</Label>
              <Input id="roleArn" value={roleArn} onChange={(e) => setRoleArn(e.target.value)} placeholder="arn:aws:iam::123456789012:role/CloudCareReadOnlyRole" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="externalId">External ID</Label>
              <Input id="externalId" value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder={EXTERNAL_ID_PLACEHOLDER} />
            </div>

            <div className="rounded-md border border-dashed border-hairline p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="eyebrow flex items-center gap-1.5"><ShieldCheck className="size-3" /> Trust policy</span>
                <CopyButton text={TRUST_POLICY(externalId)} label="trust policy" />
              </div>
              <pre className="num max-h-32 overflow-auto whitespace-pre-wrap text-[10.5px] leading-relaxed text-ink-dim">{TRUST_POLICY(externalId)}</pre>
            </div>

            <div className="rounded-md border border-dashed border-hairline p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="eyebrow">CloudFormation snippet</span>
                <CopyButton text={CLOUDFORMATION_SNIPPET(externalId)} label="CloudFormation" />
              </div>
              <pre className="num max-h-32 overflow-auto whitespace-pre-wrap text-[10.5px] leading-relaxed text-ink-dim">{CLOUDFORMATION_SNIPPET(externalId)}</pre>
            </div>

            <FormError message={error} />
            <DialogFooter>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="size-4 animate-spin" />}
                Validate & connect
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ---- GCP ---- */}
      <Dialog open={openProvider === "gcp"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Cloud className="size-4" /> Connect GCP</DialogTitle>
            <DialogDescription>The collector for GCP is not wired to live billing data yet — connecting validates your credentials, but the dashboard keeps showing FOCUS sample data for this provider.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitGcp} className="flex flex-col gap-4" noValidate>
            <div className="grid gap-1.5">
              <Label htmlFor="gcpProjectId">Project ID</Label>
              <Input id="gcpProjectId" value={gcpProjectId} onChange={(e) => setGcpProjectId(e.target.value)} placeholder="my-gcp-project" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="gcpJson">Service account JSON</Label>
              <Textarea id="gcpJson" value={gcpJson} onChange={(e) => setGcpJson(e.target.value)} rows={5} className="num text-[11.5px]" placeholder='{"type": "service_account", ...}' />
            </div>
            <SampleDataBadge />
            <FormError message={error} />
            <DialogFooter>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="size-4 animate-spin" />}
                Validate & connect
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ---- Azure ---- */}
      <Dialog open={openProvider === "azure"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Cloud className="size-4" /> Connect Azure</DialogTitle>
            <DialogDescription>A service principal with Reader, Cost Management Reader and Monitoring Reader on the subscription.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitAzure} className="flex flex-col gap-4" noValidate>
            <div className="grid gap-1.5">
              <Label htmlFor="azureTenantId">Tenant ID</Label>
              <Input id="azureTenantId" value={azureTenantId} onChange={(e) => setAzureTenantId(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="azureClientId">Client ID</Label>
              <Input id="azureClientId" value={azureClientId} onChange={(e) => setAzureClientId(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="azureClientSecret">Client secret</Label>
              <Input id="azureClientSecret" type="password" value={azureClientSecret} onChange={(e) => setAzureClientSecret(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="azureSubscriptionId">Subscription ID</Label>
              <Input id="azureSubscriptionId" value={azureSubscriptionId} onChange={(e) => setAzureSubscriptionId(e.target.value)} />
            </div>
            <FormError message={error} />
            <DialogFooter>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="size-4 animate-spin" />}
                Validate & connect
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ---- VPS ---- */}
      <Dialog open={openProvider === "vps"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Server className="size-4" /> Connect a VPS</DialogTitle>
            <DialogDescription>Company-owned servers use a dedicated, key-only SSH user with no sudo access — deliberately not a credential you paste into a browser.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <p className="text-[12.5px] leading-relaxed text-ink-dim">
              Set <span className="num">VPS_HOST</span>, <span className="num">VPS_USERNAME</span> and{" "}
              <span className="num">VPS_SSH_KEY_PATH</span> in the backend&apos;s environment, then restart
              the API. Full setup steps, including the restricted <span className="num">authorized_keys</span>{" "}
              command, are in <span className="num">docs/VPS_SETUP.md</span>.
            </p>
            <SampleDataBadge />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeDialog}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
