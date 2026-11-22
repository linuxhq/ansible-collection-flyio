# ip\_addresses\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io ip addresses

See the [Fly.io API reference](https://docs.fly.io/machines/api/apps-resource#allocate-an-ip-address-for-global-request-routing).

## Requirements

None

## Role Variables

| Variable                      | Default | Description                           |
| ----------------------------- | ------- | ------------------------------------- |
| `ip_addresses_info_api_token` | `null`  | Fly.io API token; null skips the role |
| `ip_addresses_info_app_name`  | `null`  | App name; null skips the role         |

## Dependencies

None

## Return Values

    _ip_addresses_info_dict
    _ip_addresses_info_list

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.ip_addresses_info
          ip_addresses_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          ip_addresses_info_app_name: my-app
