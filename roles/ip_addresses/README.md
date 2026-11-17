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
