# ip_addresses

Manage Fly.io IP addresses.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `ip_addresses_api_token` | `null` | Fly.io API token |
| `ip_addresses_app_name` | `null` | App name |
| `ip_addresses_async` | `300` | Async timeout |
| `ip_addresses_batch` | `10` | Batch size |
| `ip_addresses_delay` | `3` | Retry delay |
| `ip_addresses_list` | `[]` | List of IP addresses to manage |
| `ip_addresses_poll` | `0` | Poll interval |
| `ip_addresses_retries` | `100` | Max retries |

### ip_addresses_list item

| Key | Required | Description |
| --- | -------- | ----------- |
| `type` | yes | Address type: `v4`, `v6`, `shared_v4`, `private_v6` |
| `region` | no | Region code (default: global) |
| `address` | no | IP address (required for `state: absent`) |
| `state` | no | `present` or `absent` (default: `present`) |

## Example

```yaml
- role: ip_addresses
  ip_addresses_api_token: "{{ flyio_api_token }}"
  ip_addresses_app_name: my-app
  ip_addresses_list:
    - type: v4
    - type: v6
```

## License

GPL-3.0-or-later
