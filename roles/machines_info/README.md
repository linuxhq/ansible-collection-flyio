# machines\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io machines

See the [Fly.io API reference](https://docs.fly.io/machines/api/machines-resource).

## Requirements

None

## Role Variables

| Variable                  | Default | Description                           |
| ------------------------- | ------- | ------------------------------------- |
| `machines_info_api_token` | `null`  | Fly.io API token; null skips the role |
| `machines_info_app_name`  | `null`  | App name; null skips the role         |

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
