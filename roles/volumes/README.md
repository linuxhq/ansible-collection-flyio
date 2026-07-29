# volumes

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io volumes

## Requirements

None

## Role Variables

    volumes_api_token: null
    volumes_async: 300
    volumes_batch: 10
    volumes_delay: 3
    volumes_list: []
    volumes_poll: 0
    volumes_retries: 100

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.volumes
          volumes_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          volumes_list:
            - app_name: my-app
              name: my_data
              region: ord
              size_gb: 1
            - app_name: my-app
              name: my_logs
              region: ord
              size_gb: 1
