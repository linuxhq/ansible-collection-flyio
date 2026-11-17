# apps\_info

[![License](https://img.shields.io/badge/license-GPLv3-brightgreen.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0.txt)

Gather information about fly.io apps

## Requirements

None

## Role Variables

    apps_info_api_token: null
    apps_info_org_slug: null

## Dependencies

None

## Return Values

    _apps_info_dict
    _apps_info_list

## Example Playbook

    - hosts: flyio
      connection: local
      roles:
        - role: linuxhq.flyio.apps_info
          apps_info_api_token: "{{ lookup('env', 'FLY_API_TOKEN') }}"
          apps_info_org_slug: "{{ lookup('env', 'FLY_ORG_SLUG') }}"
