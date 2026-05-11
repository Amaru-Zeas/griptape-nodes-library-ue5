# Story Prompt Library for Griptape Nodes

This library adds a GTN node for reading generated prompts from your `Story_Pipeline` project.

## Included Node

- **Story Prompt Selector**
  - Fetches recent prompts server-side from `GET /api/prompts?projectId=...&limit=...`
  - If `/api/prompts` is missing, it falls back to `GET /api/projects/:id` and derives prompt candidates from project entity draft/canon content
  - Provides an **Update** button + **dropdown list**
  - Displays the selected `promptText`
  - Outputs selected prompt text and metadata for downstream nodes

## Preferred API Contract

`GET /api/prompts?projectId=proj_123&limit=20`

```json
{
  "items": [
    {
      "id": "gp_001",
      "entityName": "Leo",
      "entityType": "CHARACTER",
      "promptType": "character_full",
      "promptText": "Leo, full body, ...",
      "status": "generated",
      "createdAt": "2026-04-17T15:30:00.000Z"
    }
  ]
}
```

If your Story Pipeline instance does not expose `/api/prompts`, this node can still work using `/api/projects/:id` fallback.

## Node Inputs

- `api_base_url` (default: `http://localhost:3000`)
- `prompts_endpoint` (default: `/api/prompts`)
- `project_id`
- `limit` (default: `20`)
- `selected_prompt_id` (optional override)
- `request_timeout_seconds` (default: `8.0`)

## Node Outputs

- `prompt_text` - selected prompt text
- `prompt_id` - selected prompt id
- `prompt_label` - dropdown label
- `prompt_item` - selected prompt item object
- `prompts_payload` - full `{ items: [...] }`
- `status_message` - fetch/select status

## Usage

1. Refresh libraries in Griptape Nodes.
2. Add **Story Prompt Selector** node.
3. Set `api_base_url` and `project_id`.
4. Click **Update** in the widget.
5. Select a prompt from the dropdown.
6. Connect `prompt_text` output to your generation node.
