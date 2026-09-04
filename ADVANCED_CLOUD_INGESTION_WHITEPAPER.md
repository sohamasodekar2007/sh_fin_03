# 🌌 BREAD'S ADVANCED RESEARCH WHITEPAPER: MULTI-CLOUD FINOPS INGESTION

*Authored by Bread, 200-IQ Coding Deity (Since 1945)*

This document is the **absolute, ultimate, mathematically perfect** technical blueprint for ingesting sensitive FinOps data from AWS, GCP, and Azure into the CloudCare platform. It covers everything from basic principles to deep, advanced enterprise-level execution.

---

## 🏗️ PHASE 1: THE FOUNDATIONAL INFRASTRUCTURE

Before connecting to a single cloud, you must prepare CloudCare's backend to handle encrypted, high-throughput financial data.

### 1.1 The Secure Storage Layer (FastAPI & PostgreSQL)
You cannot store Cloud ARNs, JSON keys, or Secret Strings in plaintext. We implement **AES-256-GCM Application-Level Encryption**.

**The Database Model (Prisma / SQLAlchemy):**
```python
class CloudCredential(Base):
    __tablename__ = 'cloud_credentials'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID, ForeignKey('organizations.id'))
    provider = Column(String(50)) # ENUM: 'AWS', 'GCP', 'AZURE'
    account_alias = Column(String(255)) # e.g., "Prod-Cluster-Billing"
    encrypted_blob = Column(LargeBinary) # The AES-encrypted JSON string of secrets
    health_status = Column(String(50)) # 'CONNECTED', 'STALE', 'REVOKED'
    last_sync = Column(DateTime(timezone=True))
```

**The Cryptography Mechanism:**
*   A `MASTER_ENCRYPTION_KEY` is completely isolated in the environment (`.env`).
*   When a user submits credentials via the frontend, the FastAPI backend intercepts them, calls `cryptography.fernet.Fernet(MASTER_KEY).encrypt(payload)`, and saves ONLY the `LargeBinary` to Postgres.

---

## 🔒 PHASE 2: STEP-BY-STEP CLOUD ONBOARDING & ARCHITECTURE

Here is the exact structural mechanism for hooking into each provider.

### 2.1 Amazon Web Services (AWS) 
**Mechanism:** Cross-Account IAM Role Assumption.
AWS forbids sharing root passwords. We must use `sts:AssumeRole`.

**Step-by-Step Flow:**
1.  **Frontend Generation:** The Next.js frontend calls an endpoint `/api/aws/generate-cfn`. The backend returns a dynamic AWS CloudFormation Template URL.
2.  **User Action:** The user clicks the link, which opens their AWS Console. They click "Create Stack". This stack creates an IAM Role in *their* account that trusts *your* AWS Account ID (e.g., `arn:aws:iam::YOUR_ACCOUNT_ID:root`).
3.  **The IAM Policy Created:**
    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "ce:GetCostAndUsage",
            "ce:GetCostForecast",
            "s3:GetObject"
          ],
          "Resource": "*"
        }
      ]
    }
    ```
4.  **Handoff:** The user copies the newly created Role ARN (e.g., `arn:aws:iam::999999999:role/CloudCareAccess`) and pastes it into your Next.js UI.
5.  **Ingestion Execution:** Your Python worker decrypts the ARN, uses your backend's AWS Credentials to call `boto3.client('sts').assume_role(RoleArn=...)`, receives temporary 1-hour credentials, and queries the Cost Explorer (CE) API.

### 2.2 Google Cloud Platform (GCP)
**Mechanism:** Service Account JSON Key Upload.

**Step-by-Step Flow:**
1.  **Setup Guide:** You show the user a 3-step UI tutorial: "Go to IAM & Admin -> Service Accounts -> Create Key (JSON)".
2.  **Required Roles:** The user MUST assign the `roles/billing.viewer` and `roles/bigquery.dataViewer` (if querying Cloud Billing export datasets).
3.  **Upload:** The user drags and drops the `credentials.json` into your Next.js Dropzone.
4.  **Validation:** Before sending to the backend, Next.js checks:
    ```javascript
    if (!parsedFile.client_email || !parsedFile.private_key) throw new Error("Invalid GCP Key Format");
    ```
5.  **Ingestion Execution:** Your worker decrypts the JSON string, converts it to a dictionary, and initializes `google.oauth2.service_account.Credentials.from_service_account_info(decrypted_dict)`. It then queries the Google Cloud Billing API using this authorized object.

### 2.3 Microsoft Azure
**Mechanism:** Service Principal (App Registration).

**Step-by-Step Flow:**
1.  **Registration:** The user creates an App Registration in Azure Active Directory (Entra ID).
2.  **RBAC Assignment:** The user goes to their Azure Subscription or Enrollment Account and assigns the **"Billing Reader"** role to the new App Registration.
3.  **Inputs UI:** The user enters four fields into CloudCare: `Tenant ID`, `Client ID`, `Client Secret`, and `Subscription ID`.
4.  **Ingestion Execution:** Your worker uses the `azure-identity` Python SDK, specifically `ClientSecretCredential(tenant_id, client_id, client_secret)`. It then queries the `azure-mgmt-costmanagement` library.

---

## 🔀 PHASE 3: THE FOCUS NORMALIZATION PIPELINE

Raw cloud data is a chaotic mess. AWS uses `LineItem/UnblendedCost`, GCP uses `cost`, Azure uses `PreTaxCost`. If you feed this chaos to your AI agent, it will hallucinate and fail. We MUST normalize everything to **FOCUS (FinOps Open Cost & Usage Specification)**.

**The Pipeline (Celery / Background Tasks):**
1.  **Extract (E):** The Python async worker triggers via chronjob (e.g., every 6 hours). It uses the decrypted credentials to download the last 24 hours of billing data.
2.  **Transform (T):** A Pandas or Pydantic mapping engine kicks in.
    *   `AWS LineItem/UnblendedCost` ➔ `BilledCost` (FOCUS standard)
    *   `GCP project.name` ➔ `SubAccountId` (FOCUS standard)
    *   `Azure MeterCategory` ➔ `ServiceCategory` (FOCUS standard)
3.  **Load (L):** The data is bulk-inserted into a Time-Series SQL Table (e.g., TimescaleDB). 

```sql
-- Example FOCUS Table Schema
CREATE TABLE normalized_costs (
    id UUID PRIMARY KEY,
    billing_period_start TIMESTAMP,
    billing_period_end TIMESTAMP,
    provider_name VARCHAR(50),      -- "AWS", "GCP", "AZURE"
    billed_cost NUMERIC(14, 4),     -- The actual price
    service_category VARCHAR(100),  -- e.g., "Compute", "Storage"
    resource_id VARCHAR(255),       -- e.g., "i-0abcd1234efgh"
    region VARCHAR(50)              -- e.g., "us-east-1"
);
```

---

## 🤖 PHASE 4: THE AGENTIC INTERFACE (THE GOD BRAIN)

Because the data is completely normalized into the `normalized_costs` SQL table, your frontend "ChatGOT" AI never actually touches AWS/GCP APIs directly. This is the secret to making it flawless.

1.  **Context Window:** When the user asks, "How can I cut my AWS bill?", the Supervisor Agent converts this strictly into a SQL query against the `normalized_costs` table.
2.  **Analysis:** It spots that an EC2 Instance ID has generated costs but matches a specific tag showing 0% CPU (synced from CloudWatch metrics).
3.  **HITL Action:** The agent returns a rigid JSON payload representing the proposed action.
    ```json
    {
       "action": "terminate_instance",
       "target": "i-0abcd1234efgh",
       "provider": "AWS",
       "estimated_savings": 142.50
    }
    ```
4.  **UI Render:** Next.js renders this JSON not as chat text, but as a Red "APPROVE" button and a Gray "REJECT" button.
5.  **Execution Phase:** When APPROVE is clicked, the backend pulls the AWS IAM Role again, assumes it, and fires `ec2_client.terminate_instances(InstanceIds=['i-0abcd1234efgh'])`.
