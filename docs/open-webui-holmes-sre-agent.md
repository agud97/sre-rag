# Open WebUI Pipe: Holmes SRE Agent

## Goal

Expose HolmesGPT in Open WebUI as a selectable model named `Holmes SRE Agent`.

The user flow is:
- user opens Open WebUI
- user selects `Holmes SRE Agent`
- user chats in the normal Open WebUI interface
- the Pipe forwards the current message and earlier turns to HolmesGPT

## Design

HolmesGPT already provides a working `POST /api/chat` endpoint and supports `conversation_history`.

The Pipe uses that contract directly:
- latest Open WebUI user message becomes `ask`
- previous user and assistant turns become `conversation_history`
- HolmesGPT returns `analysis`, optional `instructions`, and optional `tool_calls`
- the Pipe converts that result into an OpenAI-compatible completion response for Open WebUI

This gives multi-turn chat behavior without a second agent state store.

## File

- `open-webui/functions/holmes_sre_agent.py`

## Import Into Open WebUI

1. Open `Admin Panel -> Functions`.
2. Create a new Pipe Function.
3. Paste the code from `open-webui/functions/holmes_sre_agent.py`.
4. Save and enable it.
5. Open the valve settings for the function.
6. Verify `HOLMES_API_BASE_URL`.

Recommended in-cluster value:

```text
http://holmesgpt-holmes.holmesgpt.svc:80
```

## What The User Sees

After enablement, the model selector should include:

```text
Holmes SRE Agent
```

Selecting it routes the chat to HolmesGPT.

## Notes

- The Pipe itself is stateless.
- Multi-turn context comes from the Open WebUI conversation transcript.
- This is intentionally simpler than depending on a separate HolmesGPT session API.
- The Pipe supports both standard and streaming Open WebUI chat requests.
