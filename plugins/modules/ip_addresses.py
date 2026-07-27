# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: ip_addresses
short_description: Manage Fly.io IP addresses
description:
  - Allocate and release Fly.io IP addresses.
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
  type:
    type: str
    choices:
      - v4
      - v6
      - shared_v4
      - private_v6
    description:
      - IP address type.
      - Required when O(state=present).
  region:
    type: str
    default: ''
    description:
      - Region code.
      - Empty string for global addresses.
  address:
    type: str
    description:
      - IP address to release.
      - Required when O(state=absent).
  state:
    type: str
    choices:
      - present
      - absent
    default: present
    description:
      - Desired state of the resource.
requirements:
  - python >= 3.9

"""

EXAMPLES = r"""
- name: Allocate a dedicated IPv4 address
  linuxhq.flyio.ip_addresses:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    type: v4
    state: present

- name: Allocate a shared IPv4 address
  linuxhq.flyio.ip_addresses:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    type: shared_v4
    state: present

- name: Allocate an IPv6 address
  linuxhq.flyio.ip_addresses:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    type: v6
    state: present

- name: Release an IP address
  linuxhq.flyio.ip_addresses:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    address: "1.2.3.4"
    state: absent
"""

RETURN = r"""
---
ip_address:
  description: Fly.io IP address.
  returned: when available
  type: dict
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import open_url
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    flyio_client,
)


GRAPHQL_URL = "https://api.fly.io/graphql"


def graphql_request(client, query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

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

    return result.get("data", {})


def get_ip_addresses(client, app_name):
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
    data = graphql_request(client, query, {"appName": app_name})
    app = data.get("app") or {}
    addresses = list(app.get("ipAddresses", {}).get("nodes", []))

    shared = app.get("sharedIpAddress")
    if shared:
        addresses.append(
            {"address": shared, "type": "shared_v4", "region": ""}
        )

    return addresses


def normalize_region(value):
    return value if value else ""


def find_ip_by_type_and_region(addresses, ip_type, region):
    for addr in addresses:
        if addr.get("type") != ip_type:
            continue

        if ip_type in ("shared_v4", "private_v6"):
            return addr

        if normalize_region(addr.get("region")) == normalize_region(region):
            return addr

    return None


def find_ip_by_address(addresses, address):
    for addr in addresses:
        if addr.get("address") == address:
            return addr
    return None


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]
    ip_type = params["type"]
    region = params.get("region") or ""

    addresses = get_ip_addresses(client, app_name)
    current = find_ip_by_type_and_region(addresses, ip_type, region)

    if current is not None:
        module.exit_json(
            changed=False,
            message="IP address already allocated",
            ip_address=current,
        )

    if module.check_mode:
        module.exit_json(changed=True, message="IP address would be allocated")

    query = """
        mutation($input: AllocateIPAddressInput!) {
            allocateIpAddress(input: $input) {
                app {
                    sharedIpAddress
                }
                ipAddress {
                    id
                    address
                    type
                    region
                    createdAt
                }
            }
        }
    """
    mutation_input = {
        "appId": app_name,
        "type": ip_type,
    }

    if region and ip_type not in ("shared_v4", "private_v6"):
        mutation_input["region"] = region

    data = graphql_request(client, query, {"input": mutation_input})
    result = data.get("allocateIpAddress") or {}

    ip_address = result.get("ipAddress")
    if ip_address is None and ip_type == "shared_v4":
        shared = (result.get("app") or {}).get("sharedIpAddress")
        if shared:
            ip_address = {"address": shared, "type": "shared_v4", "region": ""}

    module.exit_json(
        changed=True, message="IP address allocated", ip_address=ip_address
    )


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    address = params["address"]

    addresses = get_ip_addresses(client, app_name)
    current = find_ip_by_address(addresses, address)

    if current is None:
        module.exit_json(changed=False, message="IP address already released")

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="IP address would be released",
            ip_address=current,
        )

    query = """
        mutation($input: ReleaseIPAddressInput!) {
            releaseIpAddress(input: $input) {
                app {
                    name
                }
            }
        }
    """
    variables = {
        "input": {
            "appId": app_name,
            "ip": address,
        }
    }

    graphql_request(client, query, variables)

    module.exit_json(
        changed=True, message="IP address released", ip_address=current
    )


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "type": {
                "type": "str",
                "choices": ["v4", "v6", "shared_v4", "private_v6"],
            },
            "region": {"type": "str", "default": ""},
            "address": {"type": "str"},
            "state": {
                "type": "str",
                "choices": ["present", "absent"],
                "default": "present",
            },
        },
        required_if=[
            ("state", "present", ("type",)),
            ("state", "absent", ("address",)),
        ],
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
