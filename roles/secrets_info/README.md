# secrets\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io app secrets

See the [Fly.io API reference](https://docs.fly.io/machines/api/apps-resource#set-app-secrets).

## Requirements

None

## Role Variables

| Variable                 | Default | Description                           |
| ------------------------ | ------- | ------------------------------------- |
| `secrets_info_api_token` | `null`  | Fly.io API token; null skips the role |
| `secrets_info_app_name`  | `null`  | App name; null skips the role         |

## Dependencies

None

## Return Values

    _secrets_info_dict
    _secrets_info_list

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.secrets_info
          secrets_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          secrets_info_app_name: molecule-test-app
