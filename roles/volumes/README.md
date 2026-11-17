# volumes

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io volumes

## Requirements

None

## Role Variables

    volumes_api_token: null
    volumes_async: 300
    volumes_batch: 10
    volumes_delay: 3
    volumes_list: []
    volumes_poll: 0
    volumes_retries: 100

| Variable | Purpose |
| --- | --- |
| `volumes_api_token` | Fly.io API token. When `null`, the role skips every task. |
| `volumes_async` | Maximum runtime, in seconds, of each asynchronous module job. Check mode runs each item synchronously instead. |
| `volumes_batch` | Number of volumes submitted together before the role waits for their jobs. |
| `volumes_delay` | Seconds between job status checks when `volumes_poll` is `0`. |
| `volumes_list` | List of apps whose volumes to manage, described below. An empty list does nothing. |
| `volumes_poll` | Seconds between Ansible's polls of each job. `0` submits a batch without waiting, then checks its jobs with `ansible.builtin.async_status`. |
| `volumes_retries` | Maximum job status checks for each job when `volumes_poll` is `0`. |

Each `volumes_list[]` item describes one app:

| Key | Purpose |
| --- | --- |
| `app_name` | App that owns the volumes. Required; an item without it is skipped. |
| `state` | Default `state` for the item's volumes. Defaults to `present`. |
| `volumes` | List of volumes, described below. An item without this key is skipped. |

Each `volumes_list[].volumes[]` item is passed to the `linuxhq.flyio.volumes` module; see its documentation for accepted values:

| Key | Purpose |
| --- | --- |
| `name` | Volume name. Either `name` or `id` is required; an item with neither is skipped. |
| `id` | Volume ID. Either `name` or `id` is required; an item with neither is skipped. |
| `region` | Region code. |
| `size_gb` | Volume size in GB. |
| `encrypted` | Whether a new volume is encrypted. |
| `wait` | Whether to wait for the volume to reach its target state. |
| `wait_timeout` | Seconds to wait when `wait` is enabled. |
| `state` | `present` or `absent`. Defaults to the app item's `state`. |

Omitted optional keys are not sent to the module, so its defaults apply.

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
