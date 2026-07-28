# volumes\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io volumes

## Requirements

None

## Role Variables

    volumes_info_api_token: null
    volumes_info_app_name: null

## Dependencies

None

## Return Values

    _volumes_info_dict
    _volumes_info_list

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.volumes_info
          volumes_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          volumes_info_app_name: my-app
