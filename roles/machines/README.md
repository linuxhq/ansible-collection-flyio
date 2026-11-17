# machines

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io machines

## Requirements

None

## Role Variables

    machines_api_token: null
    machines_async: 300
    machines_batch: 10
    machines_delay: 3
    machines_list: []
    machines_poll: 0
    machines_retries: 100

| Variable | Purpose |
| --- | --- |
| `machines_api_token` | Fly.io API token. When `null`, the role skips every task. |
| `machines_async` | Maximum runtime, in seconds, of each asynchronous module job. Check mode runs each item synchronously instead. |
| `machines_batch` | Number of Machines submitted together before the role waits for their jobs. |
| `machines_delay` | Seconds between job status checks when `machines_poll` is `0`. |
| `machines_list` | List of apps whose machines to manage, described below. An empty list does nothing. |
| `machines_poll` | Seconds between Ansible's polls of each job. `0` submits a batch without waiting, then checks its jobs with `ansible.builtin.async_status`. |
| `machines_retries` | Maximum job status checks for each job when `machines_poll` is `0`. |

Each `machines_list[]` item describes one app:

| Key | Purpose |
| --- | --- |
| `app_name` | App that owns the Machines. Required; an item without it is skipped. |
| `state` | Default `state` for the item's Machines. Defaults to `present`. |
| `machines` | List of Machines, described below. An item without this key is skipped. |

Each `machines_list[].machines[]` item is passed to the `linuxhq.flyio.machines` module; see its documentation for accepted values:

| Key | Purpose |
| --- | --- |
| `name` | Machine name. Either `name` or `id` is required; an item with neither is skipped. |
| `id` | Machine ID. Either `name` or `id` is required; an item with neither is skipped. |
| `image` | Container image. Required when a Machine is created. |
| `region` | Region code. |
| `guest` | CPU and memory configuration. |
| `env` | Environment variables. |
| `metadata` | Metadata key-value pairs. |
| `init` | Init process configuration. |
| `services` | Fly Proxy services. |
| `checks` | Health checks. |
| `mounts` | Volume mounts. |
| `files` | Files written into the Machine. |
| `statics` | Static file mappings. |
| `restart` | Restart policy. |
| `auto_destroy` | Whether the Machine destroys itself when it exits. |
| `wait` | Whether to wait for the Machine to reach its target state. |
| `wait_timeout` | Seconds to wait when `wait` is enabled. |
| `state` | `present`, `started`, `stopped`, or `absent`. Defaults to the app item's `state`. |

Omitted optional keys are not sent to the module, so its defaults apply.

The role also runs its `volumes_info` dependency, which reads `volumes_info_api_token` and `volumes_info_app_name`; see [volumes\_info](../volumes_info).

## Dependencies

* [volumes\_info](../volumes_info)

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.machines
          machines_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          machines_list:
            - app_name: molecule-test-app
              machines:
                - guest:
                    cpu_kind: shared
                    cpus: 1
                    memory_mb: 256
                  image: nginx:alpine
                  name: molecule-web
                  region: ord
                - guest:
                    cpu_kind: shared
                    cpus: 1
                    memory_mb: 256
                  image: nginx:alpine
                  name: molecule-worker
                  region: ord

          volumes_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          volumes_info_app_name: molecule-test-app
