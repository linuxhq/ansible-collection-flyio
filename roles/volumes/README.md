# volumes

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io volumes

See the [Fly.io API reference](https://docs.fly.io/machines/api/volumes-resource).

## Requirements

None

## Role Variables

| Variable            | Default | Description                                        |
| ------------------- | ------- | -------------------------------------------------- |
| `volumes_api_token` | `null`  | Fly.io API token; null skips the role              |
| `volumes_async`     | `300`   | Seconds each async job may run                     |
| `volumes_batch`     | `10`    | Items submitted per batch                          |
| `volumes_delay`     | `3`     | Seconds between job status checks                  |
| `volumes_list`      | `[]`    | Apps and their volumes to manage                   |
| `volumes_poll`      | `0`     | Async poll interval; 0 runs jobs in the background |
| `volumes_retries`   | `100`   | Job status checks before failing                   |

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.volumes
          volumes_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          volumes_list:
            - app_name: molecule-test-app
              volumes:
                - name: molecule_data
                  region: ord
                  size_gb: 1
                - name: molecule_logs
                  region: ord
                  size_gb: 1
