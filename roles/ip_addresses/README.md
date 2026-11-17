# ip\_addresses

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io ip addresses

## Requirements

None

## Role Variables

    ip_addresses_api_token: null
    ip_addresses_async: 300
    ip_addresses_batch: 10
    ip_addresses_delay: 3
    ip_addresses_list: []
    ip_addresses_poll: 0
    ip_addresses_retries: 100

| Variable | Purpose |
| --- | --- |
| `ip_addresses_api_token` | Fly.io API token. When `null`, the role skips every task. |
| `ip_addresses_async` | Maximum runtime, in seconds, of each asynchronous module job. Check mode runs each item synchronously instead. |
| `ip_addresses_batch` | Number of IP addresses submitted together before the role waits for their jobs. |
| `ip_addresses_delay` | Seconds between job status checks when `ip_addresses_poll` is `0`. |
| `ip_addresses_list` | List of apps whose ip addresses to manage, described below. An empty list does nothing. |
| `ip_addresses_poll` | Seconds between Ansible's polls of each job. `0` submits a batch without waiting, then checks its jobs with `ansible.builtin.async_status`. |
| `ip_addresses_retries` | Maximum job status checks for each job when `ip_addresses_poll` is `0`. |

Each `ip_addresses_list[]` item describes one app:

| Key | Purpose |
| --- | --- |
| `app_name` | App that owns the IP addresses. Required; an item without it is skipped. |
| `state` | Default `state` for the item's IP addresses. Defaults to `present`. |
| `ip_addresses` | List of IP addresses, described below. An item without this key is skipped. |

Each `ip_addresses_list[].ip_addresses[]` item is passed to the `linuxhq.flyio.ip_addresses` module; see its documentation for accepted values:

| Key | Purpose |
| --- | --- |
| `type` | Address type. Required when `state` is `present`; either `type` or `address` is required. |
| `address` | Address to release when `state` is `absent`. |
| `region` | Region code; omit for a global address. |
| `state` | `present` or `absent`. Defaults to the app item's `state`. |

Omitted optional keys are not sent to the module, so its defaults apply.

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
