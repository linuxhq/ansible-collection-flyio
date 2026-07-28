# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: apps
short_description: Manage fly.io apps
description:
  - Create and delete fly.io apps.
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - fly.io API token.
  name:
    required: true
    type: str
    description:
      - App name.
  org_slug:
    type: str
    description:
      - Organization slug.
      - Required when creating an app.
  network:
    type: str
    description:
      - Custom private network name.
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
- name: Ensure app exists
  linuxhq.flyio.apps:
    api_token: "{{ flyio_api_token }}"
    name: my-app
    org_slug: linuxhq
    state: present

- name: Ensure app exists on custom network
  linuxhq.flyio.apps:
    api_token: "{{ flyio_api_token }}"
    name: my-app
    org_slug: linuxhq
    network: my-network
    state: present

- name: Ensure app is absent
  linuxhq.flyio.apps:
    api_token: "{{ flyio_api_token }}"
    name: my-app
    state: absent
"""

RETURN = r"""
---
app:
  description: fly.io app.
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
    delete_result,
    flyio_client,
    get_result,
    post_result,
)


def ensure_present(module, client):
    params = module.params

    current = get_result(
        client,
        "/apps/{}".format(params["name"]),
        ok_statuses=[404],
    )

    if current is not None:
        module.exit_json(changed=False, message="App already present", app=current)

    if params.get("org_slug") is None:
        module.fail_json(msg="org_slug is required when creating an app")

    if module.check_mode:
        module.exit_json(changed=True, message="App would be created")

    body = {
        "app_name": params["name"],
        "org_slug": params["org_slug"],
    }

    if params.get("network") is not None:
        body["network"] = params["network"]

    post_result(client, "/apps", body)

    current = get_result(client, "/apps/{}".format(params["name"]))

    module.exit_json(changed=True, message="App created", app=current)


def ensure_absent(module, client):
    params = module.params

    current = get_result(
        client,
        "/apps/{}".format(params["name"]),
        ok_statuses=[404],
    )

    if current is None:
        module.exit_json(changed=False, message="App already absent")

    if module.check_mode:
        module.exit_json(changed=True, message="App would be deleted", app=current)

    delete_result(client, "/apps/{}".format(params["name"]))

    module.exit_json(changed=True, message="App deleted", app=current)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "name": {"required": True, "type": "str"},
            "org_slug": {"type": "str"},
            "network": {"type": "str"},
            "state": {
                "type": "str",
                "choices": ["present", "absent"],
                "default": "present",
            },
        },
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
