# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: ip_addresses
short_description: Manage fly.io IP addresses
description:
  - Allocate and release fly.io IP addresses.
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
      - When O(state=absent), either O(address) or O(type) is required.
      - Mutually exclusive with O(address).
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
      - When O(state=absent), either O(address) or O(type) is required.
      - Mutually exclusive with O(type).
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
  description: fly.io IP address.
  returned: when available
  type: dict
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    get_ip_addresses,
    graphql_request,
)


def normalize_region(value):
    if not value or value == "global":
        return ""
    return value


def ips_by_type_and_region(addresses, ip_type, region):
    return [
        addr
        for addr in addresses
        if addr.get("type") == ip_type
        and (
            ip_type in ("shared_v4", "private_v6")
            or normalize_region(addr.get("region")) == normalize_region(region)
        )
    ]


def find_ip_by_type_and_region(addresses, ip_type, region):
    return next(iter(ips_by_type_and_region(addresses, ip_type, region)), None)


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
                    created_at: createdAt
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
    result = data.get("allocateIpAddress")
    if not isinstance(result, dict):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response during IP allocation"
        )

    ip_address = result.get("ipAddress")
    if ip_address is None and ip_type == "shared_v4":
        app = result.get("app")
        shared = app.get("sharedIpAddress") if isinstance(app, dict) else None
        if shared:
            ip_address = {"address": shared, "type": "shared_v4", "region": ""}

    if (
        not isinstance(ip_address, dict)
        or not isinstance(ip_address.get("address"), str)
        or not ip_address["address"]
        or not isinstance(ip_address.get("type"), str)
        or not ip_address["type"]
        or ip_address["type"] != ip_type
        or (
            ip_address.get("region") is not None
            and not isinstance(ip_address["region"], str)
        )
        or (
            ip_type not in ("shared_v4", "private_v6")
            and normalize_region(ip_address.get("region")) != normalize_region(region)
        )
    ):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response during IP allocation"
        )

    module.exit_json(
        changed=True, message="IP address allocated", ip_address=ip_address
    )


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    address = params.get("address")
    ip_type = params.get("type")
    region = params.get("region") or ""

    addresses = get_ip_addresses(client, app_name, missing_ok=True)

    if address:
        current = find_ip_by_address(addresses, address)
    elif ip_type:
        matches = ips_by_type_and_region(addresses, ip_type, region)
        if len(matches) > 1:
            module.fail_json(
                msg="Multiple IP addresses match type and region; specify address",
                ip_addresses=matches,
            )
        current = matches[0] if matches else None
    else:
        module.fail_json(msg="Either 'address' or 'type' is required for state=absent")

    if current is None:
        module.exit_json(changed=False, message="IP address already released")

    release_address = current.get("address")

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="IP address would be released",
            ip_address=current,
        )

    query = """
        mutation($input: ReleaseIPAddressInput!) {
            releaseIpAddress(input: $input) {
                clientMutationId
            }
        }
    """
    variables = {
        "input": {
            "appId": app_name,
            "ip": release_address,
        }
    }

    data = graphql_request(client, query, variables)
    result = data.get("releaseIpAddress")
    if (
        not isinstance(result, dict)
        or "clientMutationId" not in result
        or (
            result["clientMutationId"] is not None
            and not isinstance(result["clientMutationId"], str)
        )
    ):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response during IP release"
        )

    module.exit_json(changed=True, message="IP address released", ip_address=current)


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
        ],
        required_one_of=[
            ("address", "type"),
        ],
        mutually_exclusive=[
            ("address", "type"),
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
