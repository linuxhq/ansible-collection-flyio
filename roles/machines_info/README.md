# machines_info

Gather information about Fly.io machines.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `machines_info_api_token` | `null` | Fly.io API token |
| `machines_info_app_name` | `null` | App name |

## Published Facts

| Fact | Type | Description |
| ---- | ---- | ----------- |
| `_machines_info_list` | list | List of machines |
| `_machines_info_dict` | dict | Dict of machines keyed by name |

## Example

```yaml
- role: machines_info
  machines_info_api_token: "{{ flyio_api_token }}"
  machines_info_app_name: my-app
```

## License

GPL-3.0-or-later
