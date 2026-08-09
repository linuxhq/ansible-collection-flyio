#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines_info
short_description: Gather information about Fly.io Machines
description:
  - Gather information about Fly.io Machines.
  - Use O(id) to look up a single Machine, or omit it to list all Machines for an app.
version_added: '1.0.0'
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
  id:
    type: str
    description:
      - Machine identifier.
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
- name: List all machines for an app
  linuxhq.flyio.machines_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app

- name: Gather a specific Machine
  linuxhq.flyio.machines_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
"""

RETURN = r"""
---
machines:
  description: List of Fly.io Machines.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: Machine identifier.
      returned: always
      type: str
    name:
      description: Machine name.
      returned: when available
      type: str
    region:
      description: Region code.
      returned: when available
      type: str
    state:
      description: Current Machine state.
      returned: when available
      type: str

"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    sanitize_machine,
    valid_machine,
)


def validate_machines(module, machines):
    if not all(valid_machine(machine) for machine in machines):
        module.fail_json(
            msg=(
                "Fly.io API returned malformed Machine data for app "
                f"'{module.params['app_name']}'"
            )
        )


def list_resources(module, client):
    app_name = module.params["app_name"]
    machines = list_all(
        client,
        flyio_path("apps", app_name, "machines"),
        ok_statuses=[404],
        required_field="id",
    )
    validate_machines(module, machines)

    module.exit_json(
        changed=False,
        machines=[sanitize_machine(machine) for machine in machines],
    )


def info(module, client):
    machine = get_resource(
        client,
        flyio_path("apps", module.params["app_name"], "machines", module.params["id"]),
        ok_statuses=[404],
        required_field="id",
        expected_value=module.params["id"],
    )

    if machine is None:
        module.fail_json(
            msg=(
                f"Machine '{module.params['id']}' not found in app "
                f"'{module.params['app_name']}'"
            )
        )
    validate_machines(module, [machine])

    module.exit_json(changed=False, machines=[sanitize_machine(machine)])


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
        },
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["id"] is not None:
            info(module, client)
        else:
            list_resources(module, client)


if __name__ == "__main__":
    main()
