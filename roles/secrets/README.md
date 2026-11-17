# secrets

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io app secrets

## Requirements

None

## Role Variables

    secrets_api_token: null
    secrets_async: 300
    secrets_batch: 10
    secrets_delay: 3
    secrets_list: []
    secrets_no_log: true
    secrets_poll: 0
    secrets_retries: 100

| Variable | Purpose |
| --- | --- |
| `secrets_api_token` | Fly.io API token. When `null`, the role skips every task. |
| `secrets_async` | Maximum runtime, in seconds, of each asynchronous module job. Check mode runs each item synchronously instead. |
| `secrets_batch` | Number of secrets submitted together before the role waits for their jobs. |
| `secrets_delay` | Seconds between job status checks when `secrets_poll` is `0`. |
| `secrets_list` | List of apps whose secrets to manage, described below. An empty list does nothing. |
| `secrets_no_log` | Hide the role's task output, which includes the plaintext secret value of each item. Set to `false` only to debug, because task output then shows the secret values. |
| `secrets_poll` | Seconds between Ansible's polls of each job. `0` submits a batch without waiting, then checks its jobs with `ansible.builtin.async_status`. |
| `secrets_retries` | Maximum job status checks for each job when `secrets_poll` is `0`. |

Each `secrets_list[]` item describes one app:

| Key | Purpose |
| --- | --- |
| `app_name` | App that owns the secrets. Required; an item without it is skipped. |
| `state` | Default `state` for the item's secrets. Defaults to `present`. |
| `secrets` | List of secrets, described below. An item without this key is skipped. |

Each `secrets_list[].secrets[]` item is passed to the `linuxhq.flyio.secrets` module; see its documentation for accepted values:

| Key | Purpose |
| --- | --- |
| `name` | Secret name. Required; an item without it is skipped. |
| `value` | Secret value. Required when `state` is `present`. |
| `state` | `present` or `absent`. Defaults to the app item's `state`. |

Omitted optional keys are not sent to the module, so its defaults apply.

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.secrets
          secrets_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          secrets_list:
            - app_name: molecule-test-app
              secrets:
                - name: APP_SECRET
                  value: "{{ lookup('env', 'APP_SECRET') }}"
