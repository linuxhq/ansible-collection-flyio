# machines

Manage Fly.io machines.

## Role Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `machines_api_token` | `null` | Fly.io API token |
| `machines_app_name` | `null` | App name |
| `machines_async` | `300` | Async timeout |
| `machines_batch` | `10` | Batch size |
| `machines_delay` | `3` | Retry delay |
| `machines_list` | `[]` | List of machines to manage |
| `machines_poll` | `0` | Poll interval |
| `machines_retries` | `100` | Max retries |

### machines_list item

| Key | Required | Description |
| --- | -------- | ----------- |
| `name` | yes* | Machine name (mutually exclusive with `id`) |
| `id` | yes* | Machine identifier (mutually exclusive with `name`) |
| `image` | yes | Container image reference (required for `state: present`) |
| `region` | no | Region code |
| `guest` | no | Guest VM config (`cpu_kind`, `cpus`, `memory_mb`) |
| `services` | no | Service port mappings |
| `env` | no | Environment variables |
| `mounts` | no | Volume mounts |
| `auto_destroy` | no | Auto-destroy on exit (default: `false`) |
| `wait` | no | Wait for target state (default: `true`) |
| `wait_timeout` | no | Wait timeout in seconds (default: `60`) |
| `state` | no | `present`, `absent`, `started`, `stopped` (default: `present`) |

## Example

```yaml
- role: machines
  machines_api_token: "{{ flyio_api_token }}"
  machines_app_name: my-app
  machines_list:
    - name: web
      region: ord
      image: registry.fly.io/my-app:latest
      guest:
        cpu_kind: shared
        cpus: 1
        memory_mb: 256
      services:
        - internal_port: 8080
          protocol: tcp
          ports:
            - port: 443
              handlers:
                - tls
                - http
```

## License

GPL-3.0-or-later
