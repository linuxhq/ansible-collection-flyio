# apps

Manage Fly.io apps.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `apps_api_token` | `null` | Fly.io API token |
| `apps_async` | `300` | Async timeout |
| `apps_batch` | `10` | Batch size |
| `apps_delay` | `3` | Retry delay |
| `apps_list` | `[]` | List of apps to manage |
| `apps_poll` | `0` | Poll interval |
| `apps_retries` | `100` | Max retries |

### apps_list item

| Key | Required | Description |
| --- | -------- | ----------- |
| `name` | yes | App name |
| `org_slug` | no | Organization slug |
| `network` | no | Private network name |
| `state` | no | `present` or `absent` (default: `present`) |

## Example

```yaml
- role: apps
  apps_api_token: "{{ flyio_api_token }}"
  apps_list:
    - name: my-app
      org_slug: personal
      network: my-network
```

## License

GPL-3.0-or-later
