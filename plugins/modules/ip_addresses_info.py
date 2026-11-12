#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: ip_addresses_info
short_description: Gather information about Fly.io IP addresses
description:
  - Gather IP addresses allocated to a Fly.io app.
version_added: '1.0.0'
author:
  - Taylor Kimball (@tkimball83)
extends_documentation_fragment:
  - linuxhq.flyio.api
options:
  app_name:
    required: true
    type: str
    description:
      - App name.
requirements:
  - python >= 3.9
attributes:
  check_mode:
    description: Supports predicting changes without applying them.
    support: full
  diff_mode:
    description: Determines whether the module returns change details in diff format.
    support: none

"""

EXAMPLES = r"""
- name: List IP addresses for an app
  linuxhq.flyio.ip_addresses_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
"""

RETURN = r"""
---
ip_addresses:
  description: List of Fly.io IP addresses.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description:
        - IP address identifier.
        - Null when Fly.io reports none. Absent for the shared IPv4 address.
      returned: when available
      type: str
    address:
      description: Allocated IP address.
      returned: always
      type: str
    type:
      description: IP address type.
      returned: always
      type: str
    region:
      description:
        - Region code as Fly.io reports it, such as C(global), or null.
        - Empty for the shared IPv4 address.
      returned: when available
      type: str
    created_at:
      description:
        - Allocation timestamp.
        - Null when Fly.io reports none. Absent for the shared IPv4 address.
      returned: when available
      type: str

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_token_option,
    flyio_client,
    get_ip_addresses,
    require_nonempty,
)


def list_resources(module, client):
    addresses = get_ip_addresses(client, module.params["app_name"], missing_ok=True)
    module.exit_json(changed=False, ip_addresses=addresses)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
            "app_name": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )

    require_nonempty(module, "app_name")

    with flyio_client(module) as client:
        list_resources(module, client)


if __name__ == "__main__":
    main()
