#!/usr/bin/python
# Copyright: Ansible Project
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
extends_documentation_fragment:
  - linuxhq.flyio.api
options:
  app_name:
    required: true
    type: str
    description:
      - App name.
  id:
    type: str
    description:
      - Machine identifier.
      - Fails when the Machine does not exist in the app.
      - Can return a destroyed, replaced, or migrated Machine. Check
        RV(machines[].state) to select live Machines.
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
  description:
    - List of Fly.io Machines.
    - Returned as Fly.io reports them, including C(env), HTTP headers, and
      file contents, which can contain secrets. Use task-level C(no_log) to
      keep them out of output.
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
    config:
      description: Machine configuration. Null when the host could not be reached.
      returned: when available
      type: dict
    incomplete_config:
      description: Last known configuration, returned in place of RV(machines[].config) when the host could not be reached.
      returned: when available
      type: dict
    version:
      description: Identifier of this Machine version. Every update creates a new version.
      returned: when available
      type: str
    instance_id:
      description: Deprecated by Fly.io. Same value as the Machine version.
      returned: when available
      type: str
    private_ip:
      description: Private IPv6 address on the organization's network.
      returned: when available
      type: str
    host_status:
      description: Whether Fly.io could reach the Machine's host, such as C(ok), C(unreachable), or C(unknown).
      returned: when available
      type: str
    created_at:
      description: Creation timestamp.
      returned: when available
      type: str
    updated_at:
      description: Timestamp of the Machine's most recent event.
      returned: when available
      type: str
    image_ref:
      description: Image the Machine runs, as resolved when it was last created or updated.
      returned: when available
      type: dict
    events:
      description: Up to five of the most recent events of the current Machine version, newest first.
      returned: when available
      type: list
      elements: dict
    checks:
      description: Status of each health check.
      returned: when available
      type: list
      elements: dict
    cordoned:
      description: Whether Fly Proxy does not route requests to the Machine.
      returned: when available
      type: bool

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_token_option,
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    require_nonempty,
    valid_machine,
)


def validate_machines(module, machines):
    if not all(valid_machine(machine) for machine in machines):
        module.fail_json(msg=f"Fly.io API returned malformed Machine data for app '{module.params['app_name']}'")


def list_resources(module, client):
    app_name = module.params["app_name"]
    machines = list_all(
        client,
        flyio_path("apps", app_name, "machines"),
        ok_statuses=[404],
    )
    validate_machines(module, machines)

    module.exit_json(
        changed=False,
        machines=machines,
    )


def info(module, client):
    machine = get_resource(
        client,
        flyio_path("apps", module.params["app_name"], "machines", module.params["id"]),
        ok_statuses=[404],
        required_fields=("id",),
        expected={"id": module.params["id"]},
    )

    if machine is None:
        module.fail_json(msg=f"Machine '{module.params['id']}' not found in app '{module.params['app_name']}'")

    validate_machines(module, [machine])

    module.exit_json(changed=False, machines=[machine])


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
        },
        supports_check_mode=True,
    )

    require_nonempty(module, "app_name", "id")

    with flyio_client(module) as client:
        if module.params["id"] is not None:
            info(module, client)
        else:
            list_resources(module, client)


if __name__ == "__main__":
    main()
