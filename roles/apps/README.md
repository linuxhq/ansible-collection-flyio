# apps

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io apps

## Requirements

None

## Role Variables

    apps_api_token: null
    apps_async: 300
    apps_batch: 10
    apps_delay: 3
    apps_list: []
    apps_poll: 0
    apps_retries: 100

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.apps
          apps_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          apps_list:
            - name: my-app
              org_slug: "{{ lookup('env', 'FLY_ORG_SLUG') }}"
