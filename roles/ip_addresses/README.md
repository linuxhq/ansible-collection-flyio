# ip\_addresses

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io ip addresses

See the [Fly.io API reference](https://docs.fly.io/machines/api/apps-resource#allocate-an-ip-address-for-global-request-routing).

## Requirements

None

## Role Variables

| Variable                 | Default | Description                                        |
| ------------------------ | ------- | -------------------------------------------------- |
| `ip_addresses_api_token` | `null`  | Fly.io API token; null skips the role              |
| `ip_addresses_async`     | `300`   | Seconds each async job may run                     |
| `ip_addresses_batch`     | `10`    | Items submitted per batch                          |
| `ip_addresses_delay`     | `3`     | Seconds between job status checks                  |
| `ip_addresses_list`      | `[]`    | Apps and their IP addresses to manage              |
| `ip_addresses_poll`      | `0`     | Async poll interval; 0 runs jobs in the background |
| `ip_addresses_retries`   | `100`   | Job status checks before failing                   |

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.ip_addresses
          ip_addresses_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          ip_addresses_list:
            - app_name: molecule-test-app
              ip_addresses:
                - type: v4
                - type: v6
