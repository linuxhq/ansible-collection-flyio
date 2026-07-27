# volumes

Manage Fly.io volumes.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `volumes_api_token` | `null` | Fly.io API token |
| `volumes_app_name` | `null` | App name |
| `volumes_async` | `300` | Async timeout |
| `volumes_batch` | `10` | Batch size |
| `volumes_delay` | `3` | Retry delay |
| `volumes_list` | `[]` | List of volumes to manage |
| `volumes_poll` | `0` | Poll interval |
| `volumes_retries` | `100` | Max retries |

### volumes_list item

| Key | Required | Description |
| --- | -------- | ----------- |
| `name` | yes* | Volume name (mutually exclusive with `id`) |
| `id` | yes* | Volume identifier (mutually exclusive with `name`) |
| `region` | no | Region code (required when creating) |
| `size_gb` | no | Volume size in GB (default: `1`) |
| `encrypted` | no | Encrypt volume (default: `true`) |
| `state` | no | `present` or `absent` (default: `present`) |

## Example

```yaml
- role: volumes
  volumes_api_token: "{{ flyio_api_token }}"
  volumes_app_name: my-app
  volumes_list:
    - name: data
      region: ord
      size_gb: 10
```

## License

GPL-3.0-or-later
