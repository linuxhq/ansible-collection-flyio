# volumes_info

Gather information about Fly.io volumes.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `volumes_info_api_token` | `null` | Fly.io API token |
| `volumes_info_app_name` | `null` | App name |

## Published Facts

| Fact | Type | Description |
| ---- | ---- | ----------- |
| `_volumes_info_list` | list | List of volumes |
| `_volumes_info_dict` | dict | Dict of volumes keyed by name |

## Example

```yaml
- role: volumes_info
  volumes_info_api_token: "{{ flyio_api_token }}"
  volumes_info_app_name: my-app
```

## License

GPL-3.0-or-later
