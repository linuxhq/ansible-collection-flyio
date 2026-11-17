# machines\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io machines

## Requirements

None

## Role Variables

    machines_info_api_token: null
    machines_info_app_name: null

| Variable | Purpose |
| --- | --- |
| `machines_info_api_token` | Fly.io API token. |
| `machines_info_app_name` | App whose Machines to list. |

When `machines_info_api_token` or `machines_info_app_name` is `null`, the role skips the query and publishes empty facts.

## Dependencies

None

## Return Values

    _machines_info_dict
    _machines_info_list

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.machines_info
          machines_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          machines_info_app_name: my-app
