# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: ip_addresses_info
short_description: Gather information about fly.io IP addresses
description:
  - Gather IP addresses allocated to a fly.io app.
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - fly.io API token.
  app_name:
    required: true
    type: str
    description:
      - App name.
requirements:
  - python >= 3.9

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
  description: List of fly.io IP addresses.
  returned: always
  type: list
  elements: dict

"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    flyio_client,
    get_ip_addresses,
)


def list_resources(module, client):
    try:
        addresses = get_ip_addresses(client, module.params["app_name"])
    except FlyioApiError as exc:
        if "could not find app" in str(exc).lower():
            addresses = []
        else:
            raise

    module.exit_json(changed=False, ip_addresses=addresses)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        list_resources(module, client)


if __name__ == "__main__":
    main()
