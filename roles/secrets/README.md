# secrets

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io app secrets

See the [Fly.io API reference](https://docs.fly.io/machines/api/apps-resource#set-app-secrets).

## Requirements

None

## Role Variables

| Variable            | Default | Description                                        |
| ------------------- | ------- | -------------------------------------------------- |
| `secrets_api_token` | `null`  | Fly.io API token; null skips the role              |
| `secrets_async`     | `300`   | Seconds each async job may run                     |
| `secrets_batch`     | `10`    | Items submitted per batch                          |
| `secrets_delay`     | `3`     | Seconds between job status checks                  |
| `secrets_list`      | `[]`    | Apps and their secrets to manage                   |
| `secrets_no_log`    | `true`  | Hide task output that has secrets                  |
| `secrets_poll`      | `0`     | Async poll interval; 0 runs jobs in the background |
| `secrets_retries`   | `100`   | Job status checks before failing                   |

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
                  value: molecule-secret
