# secrets

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Manage fly.io app secrets

## Requirements

None

## Role Variables

    secrets_api_token: null
    secrets_async: 300
    secrets_batch: 10
    secrets_delay: 3
    secrets_list: []
    secrets_no_log: false
    secrets_poll: 0
    secrets_retries: 100

## Dependencies

None

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.secrets
          secrets_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          secrets_list:
            - app_name: molecule-test-app
              secrets:
                - name: APP_SECRET
                  value: molecule-secret
