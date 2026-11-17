# apps

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io apps

## Requirements

None

## Role Variables

    apps_api_token: null
    apps_async: 300
    apps_batch: 10
    apps_delay: 3
    apps_list: []
    apps_poll: 0
    apps_retries: 100

| Variable | Purpose |
| --- | --- |
| `apps_api_token` | Fly.io API token. When `null`, the role skips every task. |
| `apps_async` | Maximum runtime, in seconds, of each asynchronous module job. Check mode runs each item synchronously instead. |
| `apps_batch` | Number of apps submitted together before the role waits for their jobs. |
| `apps_delay` | Seconds between job status checks when `apps_poll` is `0`. |
| `apps_list` | List of apps to manage, described below. An empty list does nothing. |
| `apps_poll` | Seconds between Ansible's polls of each job. `0` submits a batch without waiting, then checks its jobs with `ansible.builtin.async_status`. |
| `apps_retries` | Maximum job status checks for each job when `apps_poll` is `0`. |

Each `apps_list[]` item is passed to the `linuxhq.flyio.apps` module; see its documentation for accepted values:

| Key | Purpose |
| --- | --- |
| `name` | App name. Required; an item without it is skipped. |
| `org_slug` | Organization slug. Required when the app is created. |
| `network` | Custom network for a new app. |
| `delete_timeout` | Seconds to wait for deletion when `state` is `absent`. |
| `state` | `present` or `absent`. Defaults to `present`. |

Omitted optional keys are not sent to the module, so its defaults apply.

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
