# machines

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io machines

## Requirements

None

## Role Variables

    machines_api_token: null
    machines_async: 300
    machines_batch: 10
    machines_delay: 3
    machines_list: []
    machines_poll: 0
    machines_retries: 100

## Dependencies

* [volumes\_info](../volumes_info)

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.machines
          machines_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          machines_list:
            - app_name: my-app
              name: my-machine
              region: ord
              image: nginx:alpine
              guest:
                cpu_kind: shared
                cpus: 1
                memory_mb: 256
              mounts:
                - volume: "{{ _volumes_info_dict['my_data'].id }}"
                  path: /data

          volumes_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          volumes_info_app_name: my-app
