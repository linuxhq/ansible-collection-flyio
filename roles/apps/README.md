# apps

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io apps

See the [Fly.io API reference](https://docs.fly.io/machines/api/apps-resource).

## Requirements

None

## Role Variables

| Variable         | Default | Description                                        |
| ---------------- | ------- | -------------------------------------------------- |
| `apps_api_token` | `null`  | Fly.io API token; null skips the role              |
| `apps_async`     | `300`   | Seconds each async job may run                     |
| `apps_batch`     | `10`    | Items submitted per batch                          |
| `apps_delay`     | `3`     | Seconds between job status checks                  |
| `apps_list`      | `[]`    | Apps to manage                                     |
| `apps_poll`      | `0`     | Async poll interval; 0 runs jobs in the background |
| `apps_retries`   | `100`   | Job status checks before failing                   |

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.apps
          apps_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          apps_list:
            - name: my-app
              org_slug: "{{ lookup('env', 'FLY_ORG_SLUG') }}"
            - name: my-app-2
              org_slug: "{{ lookup('env', 'FLY_ORG_SLUG') }}"
