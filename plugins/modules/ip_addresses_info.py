# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: ip_addresses_info
short_description: Gather information about Fly.io IP addresses
description:
  - Gather IP addresses allocated to a Fly.io app.
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - Fly.io API token.
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
  description: List of Fly.io IP addresses.
  returned: always
  type: list
  elements: dict

"""

import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import open_url
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    flyio_client,
)


GRAPHQL_URL = "https://api.fly.io/graphql"


def list_resources(module, client):
    query = """
        query($appName: String!) {
            app(name: $appName) {
                sharedIpAddress
                ipAddresses {
                    nodes {
                        id
                        address
                        type
                        region
                        createdAt
                    }
                }
            }
        }
    """
    payload = {
        "query": query,
        "variables": {"appName": module.params["app_name"]},
    }

    try:
        response = open_url(
            GRAPHQL_URL,
            method="POST",
            data=json.dumps(payload),
            headers=client["headers"],
        )
        result = json.loads(response.read())
    except Exception as exc:
        raise FlyioApiError(str(exc))

    if "errors" in result and result["errors"]:
        raise FlyioApiError(result["errors"][0].get("message", "GraphQL error"))

    data = result.get("data", {})
    app = data.get("app") or {}
    addresses = list(app.get("ipAddresses", {}).get("nodes", []))

    shared = app.get("sharedIpAddress")
    if shared:
        addresses.append(
            {"address": shared, "type": "shared_v4", "region": ""}
        )

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
