# Abel AI API Key OAuth Flow

Base URL: `https://api.abel.ai/router/`

`abel-auth` is the canonical skill owner for this flow.

Before using this guide, verify auth state with:

```bash
python ../abel-common/python/abel_common/cap/graph_probe.py auth-status
```

Only continue into this guide after that check shows live Abel auth is missing
or needs repair.

## Rules

- Call `GET /web/credentials/oauth/google/authorize/agent` first.
- Ask the user whether they want to start OAuth before requesting the auth URL.
- Return only the returned `data.authUrl` to the user.
- Do not continue to CAP probing until a user API key is available.
- Do not ask for email, OAuth code, or raw API key.
- Store `data.resultUrl` or `data.pollToken`, wait for the user's confirmation, then poll until the result is `authorized`, `failed`, or expired.
- Treat responses as `{ code, message, time, data }`.

## Recommended Agent Flow

1. Call `GET /web/credentials/oauth/google/authorize/agent`.
2. Read `data.authUrl`, store `data.resultUrl` or `data.pollToken`, and send the auth URL to the user.
3. Ask the user to come back and reply `done` after browser auth.
4. Wait for that confirmation before polling `GET /web/credentials/oauth/google/result?pollToken=...` or `data.resultUrl`.
5. Keep polling while the result is `pending`.
6. If the result is `authorized`, read `data.apiKey`, `data.ratePerMinute`, and `data.expireTime`, then continue with live usage.
7. Persist the key to `skills/abel-auth/.env.skill` when local storage is available.
8. If the result is `failed`, surface the failure message.

The callback page is only a confirmation page. The API key comes from the result endpoint, not the browser HTML.

## Local Env File

Preferred shared auth file for the installed collection:

```dotenv
skills/abel-auth/.env.skill
ABEL_API_KEY=abel_xxx
```

`abel-auth` owns the canonical shared auth file. The bundled probe also checks
collection-level and sibling-skill `.env.skill` / `.env.skills` files when the
current skill-local file is missing.

## Endpoint: Get Agent OAuth Authorization URL

Method: `GET`  
Path: `/web/credentials/oauth/google/authorize/agent`  
Full URL: `https://api.abel.ai/router/web/credentials/oauth/google/authorize/agent`

The browser URL is the returned `data.authUrl`, not this API URL itself.

### Success Response

```json
{
  "code": 200,
  "message": "Success",
  "time": 1773905855,
  "data": {
    "provider": "google",
    "flow": "agent_handoff",
    "authUrl": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "resultUrl": "https://api.abel.ai/router/web/credentials/oauth/google/result?pollToken=POLL_TOKEN",
    "pollToken": "POLL_TOKEN",
    "authorizationState": "pending_user_action",
    "expiresAt": 1773906755
  }
}
```

### Agent Behavior

Respond like this:

`Please use this Google authorization link to get your Abel AI API key: {authUrl}. After you finish Google authorization in the browser, come back here and tell me, and I'll fetch your key.`

Do not send the `authorize/agent` API URL itself to the user.

### Clickable Link Format

If the chat surface supports Markdown links, prefer this format:

`[Open Abel Google authorization]({authUrl})`

If Markdown links are not supported, send the raw URL on its own line:

```text
{authUrl}
```

Do not wrap the actual URL in backticks inside the user-facing message. In many chat surfaces, `` `https://...` `` renders as code and is not clickable.

## Endpoint: Get Agent Authorization Result

Method: `GET`  
Path: `/web/credentials/oauth/google/result`  
Full URL: `https://api.abel.ai/router/web/credentials/oauth/google/result?pollToken=POLL_TOKEN`

### Pending Response

```json
{
  "code": 200,
  "message": "Success",
  "time": 1773905855,
  "data": {
    "status": "pending",
    "ready": false,
    "authorizationState": "pending_user_action"
  }
}
```

### Authorized Response

```json
{
  "code": 200,
  "message": "Success",
  "time": 1773905855,
  "data": {
    "status": "authorized",
    "ready": true,
    "authorizationState": "verified",
    "apiKey": "abel_xxx",
    "ratePerMinute": 60,
    "expireTime": 1776499200
  }
}
```

### Failed Response

```json
{
  "code": 200,
  "message": "Success",
  "time": 1773905855,
  "data": {
    "status": "failed",
    "ready": false,
    "message": "your account is not activated",
    "authorizationState": "failed",
    "errorCode": 403
  }
}
```

## Callback Behavior

`GET /web/credentials/oauth/google/callback` is for the user's browser. Agents should not ask the user to paste the OAuth `code` back into chat.

## Failure Handling

- If the authorize endpoint fails or does not return `data.authUrl`, tell the user the link could not be created and ask them to try again later.
- If the result endpoint stays `pending` after the user says they are done, continue polling until it resolves or expires.
- If the result endpoint returns `404`, restart from the authorize endpoint.
- If the callback flow returns `400`, restart the flow.
- If it returns `403`, tell the user Google auth succeeded but the Abel account is not activated yet.
- If it returns `500`, ask the user to try again later.
