# ip\_addresses\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io IP addresses

## Requirements

None

## Role Variables

    ip_addresses_info_api_token: null
    ip_addresses_info_app_name: null

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
