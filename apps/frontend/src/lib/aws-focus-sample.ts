import type { ParquetAnalysis } from "@/lib/cloudcare-data";

export function awsFocusSampleAnalysis(): ParquetAnalysis {
  const generatedAt = new Date().toISOString();
  return {
    file: {
      source: "local",
      uri: "Horizon-00001.snappy.parquet",
      bucket: "",
      key: "Horizon-00001.snappy.parquet",
      name: "Horizon-00001.snappy.parquet",
      size_bytes: 26374,
      compression: "snappy",
      last_modified: "2026-09-04T06:21:12.698135+00:00",
    },
    summary: {
      tenant_id: "demo-tenant",
      rows: 210,
      columns: 63,
      row_groups: 1,
      distinct_resources: 6,
      distinct_services: 8,
      billed_cost_usd: 0,
      effective_cost_usd: 0,
      list_cost_usd: 0,
      savings_vs_list_usd: 0,
    },
    schema: [],
    breakdowns: {
      by_service: [
        { name: "Amazon Elastic Compute Cloud", cost_usd: 0, rows: 162 },
        { name: "Amazon Simple Storage Service", cost_usd: 0, rows: 5 },
        { name: "AWS Glue", cost_usd: 0, rows: 17 },
        { name: "AWS Data Transfer", cost_usd: 0, rows: 13 },
        { name: "AWS Cost Explorer", cost_usd: 0, rows: 3 },
      ],
      by_category: [
        { name: "Compute", cost_usd: 0, rows: 42 },
        { name: "Storage", cost_usd: 0, rows: 125 },
        { name: "Analytics", cost_usd: 0, rows: 17 },
        { name: "Networking", cost_usd: 0, rows: 19 },
      ],
      by_region: [
        { name: "Asia Pacific (Mumbai)", cost_usd: 0, rows: 162 },
        { name: "US East (N. Virginia)", cost_usd: 0, rows: 13 },
        { name: "EU (Stockholm)", cost_usd: 0, rows: 5 },
        { name: "External", cost_usd: 0, rows: 12 },
      ],
      by_charge_category: [
        { name: "Usage", cost_usd: 0.1434, rows: 182 },
        { name: "Credit", cost_usd: -0.1434, rows: 10 },
        { name: "Tax", cost_usd: 0, rows: 18 },
      ],
      by_billing_account: [{ name: "teamalpha", cost_usd: 0, rows: 210 }],
      by_resource: [
        { name: "vol-017e496e755be671e", cost_usd: 0.0588, rows: 58 },
        { name: "vol-070e7805dff70ee77", cost_usd: 0.0588, rows: 58 },
        { name: "arn:aws:ec2:ap-south-1:350381001148:network-interface/eni-052b2b701cb22a2fa", cost_usd: 0.0079, rows: 2 },
        { name: "arn:aws:ec2:ap-south-1:350381001148:network-interface/eni-08b45c125f8bbf17b", cost_usd: 0.0079, rows: 2 },
        { name: "i-0a34c54ac18e0eb62", cost_usd: 0, rows: 22 },
        { name: "i-0a243d0480eab6ce6", cost_usd: 0, rows: 20 },
      ],
      by_usage: [
        { name: "APS3-EBS:VolumeUsage.gp3", cost_usd: 0.1176, rows: 120 },
        { name: "APS3-DataTransfer-In-Bytes", cost_usd: 0, rows: 13 },
        { name: "APS3-DataTransfer-Out-Bytes", cost_usd: 0, rows: 13 },
        { name: "USE1-APIRequest", cost_usd: 0, rows: 3 },
      ],
    },
    sample_rows: [],
    converter: {
      cadence_minutes: 60,
      scheduler_interval_minutes: 60,
      parquet_analysis_interval_minutes: 60,
      s3_configured: false,
      bucket: null,
      prefix: "",
      target_key: "parquet-analysis/latest.json",
      target_uri: null,
      formats: ["json-summary", "csv-preview", "focus-normalized-json", "snappy-parquet"],
      compression: "snappy",
      mode: "local AWS FOCUS sample fallback",
    },
    generated_at: generatedAt,
  };
}
