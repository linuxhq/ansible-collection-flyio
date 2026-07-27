# apps_info

Gather information about Fly.io apps.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `apps_info_api_token` | `null` | Fly.io API token |
| `apps_info_org_slug` | `null` | Organization slug |

## Published Facts

| Fact | Type | Description |
| ---- | ---- | ----------- |
| `_apps_info_list` | list | List of apps |
| `_apps_info_dict` | dict | Dict of apps keyed by name |

## Example

```yaml
- role: apps_info
  apps_info_api_token: "{{ flyio_api_token }}"
  apps_info_org_slug: personal
```

## License

GPL-3.0-or-later
