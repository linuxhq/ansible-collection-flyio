# machines

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io machines

See the [Fly.io API reference](https://docs.fly.io/machines/api/machines-resource).

## Requirements

None

## Role Variables

| Variable             | Default | Description                                        |
| -------------------- | ------- | -------------------------------------------------- |
| `machines_api_token` | `null`  | Fly.io API token; null skips the role              |
| `machines_async`     | `300`   | Seconds each async job may run                     |
| `machines_batch`     | `10`    | Items submitted per batch                          |
| `machines_delay`     | `3`     | Seconds between job status checks                  |
| `machines_list`      | `[]`    | Apps and their Machines to manage                  |
| `machines_poll`      | `0`     | Async poll interval; 0 runs jobs in the background |
| `machines_retries`   | `100`   | Job status checks before failing                   |

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
