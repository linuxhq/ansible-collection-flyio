#!/usr/bin/python
# Copyright: Ansible Project
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
      - Used only when creating an app. An existing app is not checked against
        O(org_slug) or O(network).
  network:
    type: str
    description:
      - Custom private network name.
      - Must not be empty when specified.
      - Used only when creating an app.
  force:
    type: bool
    description:
      - Ignored. The Fly.io Machines API does not support a force option when deleting an app.
      - This option will be removed in version 2.0.0 of linuxhq.flyio.
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
    state: absent
"""

RETURN = r"""
---
app:
  description: Fly.io app. After deletion, the app as it was before deletion.
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

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    delete_result,
    flyio_client,
    flyio_path,
    get_app,
    post_result,
    require_positive,
    seconds_left,
    wait_deadline,
    wait_for_app_absent,
)


def ensure_present(module, client):
    params = module.params

    current = get_app(client, params["name"])

    if current is not None:
        module.exit_json(changed=False, message="App already present", app=current)

    if params.get("org_slug") is None:
        module.fail_json(msg="org_slug is required when creating an app")

    if module.check_mode:
        module.exit_json(changed=True, message="App would be created")

    body = {
        "name": params["name"],
        "org_slug": params["org_slug"],
    }

    if params.get("network") is not None:
        body["network"] = params["network"]

    post_result(client, "/apps", body)

    # The create succeeded; tolerate read-after-write lag instead of failing.
    current = get_app(client, params["name"]) or {"name": params["name"]}

    module.exit_json(changed=True, message="App created", app=current)


def ensure_absent(module, client):
    params = module.params
    require_positive(module, "delete_timeout")

    current = get_app(client, params["name"])

    if current is None:
        module.exit_json(changed=False, message="App already absent")

    if module.check_mode:
        module.exit_json(changed=True, message="App would be deleted", app=current)

    path = flyio_path("apps", params["name"])
    deadline = wait_deadline(params["delete_timeout"])
    delete_result(
        client,
        path,
        timeout=params["delete_timeout"],
        ok_statuses=[404],
    )

    remaining = wait_for_app_absent(
        client,
        params["name"],
        seconds_left(deadline),
    )
    if remaining is not None:
        module.fail_json(
            msg=f"Deletion of app '{params['name']}' timed out",
            app=remaining,
        )

    module.exit_json(changed=True, message="App deleted", app=current)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "name": {"required": True, "type": "str"},
            "org_slug": {"type": "str"},
            "network": {"type": "str"},
            "force": {
                "type": "bool",
                "removed_in_version": "2.0.0",
                "removed_from_collection": "linuxhq.flyio",
            },
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
