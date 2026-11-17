# secrets\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io app secrets

## Requirements

None

## Role Variables

    secrets_info_api_token: null
    secrets_info_app_name: null

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
