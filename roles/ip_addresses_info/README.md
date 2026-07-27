# ip_addresses_info

Gather information about Fly.io IP addresses.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `ip_addresses_info_api_token` | `null` | Fly.io API token |
| `ip_addresses_info_app_name` | `null` | App name |

## Published Facts

| Fact | Type | Description |
| ---- | ---- | ----------- |
| `_ip_addresses_info_list` | list | List of IP addresses |
| `_ip_addresses_info_dict` | dict | Dict of IP addresses keyed by address |

## Example

```yaml
- role: ip_addresses_info
  ip_addresses_info_api_token: "{{ flyio_api_token }}"
  ip_addresses_info_app_name: my-app
```

## License

GPL-3.0-or-later
