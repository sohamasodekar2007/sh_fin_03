# CloudCare Chatbot MCP Service

CloudCare exposes a restricted MCP-compatible JSON-RPC bridge for chatbot use at:

```text
POST /v1/chat/mcp
```

Dashboard setup is available at:

```text
/dashboard/chatbot-mcp
```

The dashboard calls authenticated setup APIs under:

```text
GET  /v1/chat/mcp/setup
POST /v1/chat/mcp/setup
POST /v1/chat/mcp/setup/token
POST /v1/chat/mcp/setup/check
```

It is intentionally not a general AWS control plane. It only exposes the same vetted tenant-scoped tools used by the CloudCare chatbot:

- `get_latest_findings`
- `get_proposal_details`
- `get_cost_summary`
- `trigger_monitor_agent`
- `approve_proposal`

`approve_proposal` only returns an approval card. It never approves, rejects, or executes by itself.

## Authentication

Use one of these two auth modes.

### Logged-In Chatbot User

Use the normal CloudCare login token:

```http
Authorization: Bearer <cloudcare_access_token>
```

The backend reads `tenant_id` and `user_id` from the JWT and checks MongoDB for the user account.

### Server-to-Server Env Token

Set these only on the backend service:

```env
CHATBOT_MCP_ENABLED=true
CHATBOT_MCP_TOKEN=<long-random-token>
CHATBOT_MCP_TENANT_ID=demo-tenant
CHATBOT_MCP_USER_ID=chatbot-mcp
CHATBOT_MCP_USER_EMAIL=ops@example.com
```

Call with:

```http
X-CloudCare-MCP-Token: <long-random-token>
```

Do not put the MCP token in the frontend bundle. Use it only from a trusted server-side chatbot/MCP client.

### Dashboard-Generated Chatbot Token

From `/dashboard/chatbot-mcp`, generate a chatbot token. The raw token is shown once, and MongoDB stores only its SHA-256 hash plus metadata.

Call with:

```http
X-CloudCare-MCP-Token: ccmcp_<generated-token>
```

This token is tenant-scoped to the logged-in CloudCare account that created it. The MCP bridge updates `last_used_at` when the token is used.

## AI Model

The chatbot continues to use the existing model env:

```env
OPENAI_API_KEY=<model-key>
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

The MCP bridge itself is only the tool/data layer. The chat reasoning loop stays in `services/chat/service.py` through `LLMClient`, which reads model settings from env.

## MongoDB Storage

CloudCare login and chat data remain MongoDB-backed:

- `users`
- `chat_sessions`
- `chat_rate_limits`
- `chat_mcp_setups`
- `chat_mcp_tokens`
- `chat_mcp_audit`

The MCP audit collection stores tenant, user, method, tool name, success flag, error text, and timestamp. It never stores JWTs, MCP tokens, API keys, passwords, or cloud secrets.

`chat_mcp_setups` stores enabled/disabled state, client name, allowed tools, chatbot instructions, audit preference, and timestamps. `chat_mcp_tokens` stores token metadata and token hashes only.

## Frontend Setup Flow

1. Open `/dashboard/chatbot-mcp`.
2. Enable MCP and audit.
3. Select the exact allowed tools for the chatbot.
4. Save the setup policy.
5. Generate a chatbot token and copy it immediately.
6. Run AI check. With `OPENAI_API_KEY` configured, this performs a lightweight model-backed setup review.
7. Configure your server-side chatbot/MCP client to call `/v1/chat/mcp` with `X-CloudCare-MCP-Token`.
8. Use `tools/list` once and confirm the dashboard audit trail shows the event.

## MCP Calls

Initialize:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

List tools:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

Call a tool:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_cost_summary",
    "arguments": {
      "period_days": 30
    }
  }
}
```

## Security Rules

- Tenant and user identity are never accepted from tool arguments.
- Unknown tools are rejected.
- Tool results are scoped to the authenticated tenant.
- The bridge does not expose raw AWS SDK clients.
- The bridge does not perform direct cloud mutations.
- Secrets must stay in backend env only.
