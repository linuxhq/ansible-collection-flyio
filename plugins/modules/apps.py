#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: apps
short_description: Manage Fly.io apps
description:
  - Create and delete Fly.io apps.
version_added: '1.0.0'
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - Fly.io API token.
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
      - Must not be empty when specified.
      - Used only when creating an app.
  force:
    type: bool
    default: true
    description:
      - Stop and destroy the app's Machines when deleting the app.
      - Used only when O(state=absent).
  delete_timeout:
    type: int
    default: 60
    description:
      - Timeout in seconds when waiting for app deletion.
      - Used only when O(state=absent).
      - Must be greater than zero.
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
attributes:
  check_mode:
    description: Supports predicting changes without applying them.
    support: full
  diff_mode:
    description: Determines whether the module returns change details in diff format.
    support: none

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
    delete_timeout: 120
    force: true
    state: absent
"""

RETURN = r"""
---
app:
  description: Fly.io app.
  returned: when available
  type: dict
  contains:
    name:
      description: App name.
      returned: always
      type: str
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

import time

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    delete_result,
    flyio_client,
    flyio_path,
    get_resource,
    post_result,
    require_positive,
    wait_for_app_absent,
)


def ensure_present(module, client):
    params = module.params

    current = get_resource(
        client,
        flyio_path("apps", params["name"]),
        ok_statuses=[404],
        required_field="name",
        expected_value=params["name"],
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

    current = get_resource(
        client,
        flyio_path("apps", params["name"]),
        required_field="name",
        expected_value=params["name"],
    )

    module.exit_json(changed=True, message="App created", app=current)


def ensure_absent(module, client):
    params = module.params
    require_positive(module, "delete_timeout")

    current = get_resource(
        client,
        flyio_path("apps", params["name"]),
        ok_statuses=[404],
        required_field="name",
        expected_value=params["name"],
    )

    if current is None:
        module.exit_json(changed=False, message="App already absent")

    if module.check_mode:
        module.exit_json(changed=True, message="App would be deleted", app=current)

    path = flyio_path("apps", params["name"])
    if params["force"]:
        path += "?force=true"

    deadline = time.monotonic() + params["delete_timeout"]
    result = delete_result(
        client,
        path,
        timeout=params["delete_timeout"],
        ok_statuses=[404],
    )
    if result is not None:
        module.fail_json(
            msg=(
                "Fly.io API returned malformed data while deleting app "
                f"'{params['name']}'"
            ),
            response=result,
        )

    current = wait_for_app_absent(
        client,
        params["name"],
        max(0, deadline - time.monotonic()),
    )
    if current is not None:
        module.fail_json(
            msg=f"Deletion of app '{params['name']}' timed out",
            app=current,
        )

    module.exit_json(changed=True, message="App deleted")


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "name": {"required": True, "type": "str"},
            "org_slug": {"type": "str"},
            "network": {"type": "str"},
            "force": {"type": "bool", "default": True},
            "delete_timeout": {"type": "int", "default": 60},
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
