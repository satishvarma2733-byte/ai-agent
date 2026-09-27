# Website chat widget and public chat API

Your agents can answer on your website (text, and voice if you turn it on) and from your own apps.
Both use the agent's **production** version: an agent with no activated version won't answer.

## Website widget

1. **Website Chat → Add a widget.** Pick the agent and list the websites it runs on, for example
   `https://www.example.com`. You need `https`; plain `http` works only for `localhost`.
2. Copy the embed code into your site, just before `</body>`:

   ```html
   <script src="https://YOUR-API/widget.js" data-key="wk_..." async></script>
   ```

The widget key is public, because it sits in your page's HTML. The API accepts it only from the websites you
listed, so another site can't use it. If you want a new key, choose **New key**. The old embed code stops
working straight away.

**Voice.** When voice is on, visitors can choose **Talk** to speak with the agent in the browser.
- The browser loads the LiveKit client from `cdn.jsdelivr.net`. If your site has a Content-Security-Policy, allow that host for scripts. Also allow your LiveKit URL under `connect-src`.
- Voice calls appear in call logs with direction `web`, and they count toward the plan's minutes.
- Voice is paused when the month's minutes run out. Text chat keeps working.

**Leads.** When lead capture is on, the widget asks for a name and phone number after the visitor's second message. Those details:
- create a CRM lead, or match an existing lead by phone number;
- attach the conversation to that lead;
- fire the `lead_created` workflow trigger.

**Limits.**
- Each visitor IP can send 20 messages a minute to a widget.
- A conversation can have up to 30 visitor messages.
- Each message can be up to 1,000 characters.

## Public chat API (server to server)

Create a key under **Website Chat → Chat API keys**. It is shown once, so store it as a secret. Never put an
API key in a web page; use a widget there instead. API-key responses carry no CORS headers.

```http
POST /api/public/chat
Authorization: Bearer avn_sk_...
Content-Type: application/json

{"message": "What are your timings?", "agent_id": "<agent id>"}
```

```json
{"session": "<token>", "reply": "We're open 9am to 6pm.", "ask_for_contact": false}
```

To continue the conversation, send the `session` value back with later messages. Only the first response
includes it.

To attach a contact to the conversation:

```http
POST /api/public/chat/contact
Authorization: Bearer avn_sk_...

{"session": "<token>", "name": "Asha", "phone": "+919876543210", "email": "asha@example.com"}
```

Revoking a key stops it immediately. All chats, from widgets and API keys, appear under **Recent conversations**.

## Errors

Errors return JSON in the form `{"detail": "…"}`, with these status codes:

| Status | Meaning |
| --- | --- |
| 401 | Missing or revoked key |
| 403 | The website isn't listed for this widget, or voice is off |
| 404 | Unknown widget, agent or conversation |
| 422 | Invalid input |
| 429 | Too many messages |
| 503 | The agent isn't live, or the model or voice service is unavailable |
