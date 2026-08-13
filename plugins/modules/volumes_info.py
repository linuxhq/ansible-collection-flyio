#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes_info
short_description: Gather information about Fly.io volumes
description:
  - Gather information about Fly.io volumes.
  - Use O(id) to look up a single volume, or omit it to list all volumes for an app.
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
      - Volume identifier.
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
- name: List all volumes for an app
  linuxhq.flyio.volumes_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app

- name: Gather a specific volume
  linuxhq.flyio.volumes_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: vol_abc123
"""

RETURN = r"""
---
volumes:
  description: List of Fly.io volumes.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: Volume identifier.
      returned: always
      type: str
    name:
      description: Volume name.
      returned: when available
      type: str
    region:
      description: Region code.
      returned: when available
      type: str
    size_gb:
      description: Volume size in gigabytes.
      returned: when available
      type: int
    encrypted:
      description: Whether the volume is encrypted.
      returned: when available
      type: bool
    state:
      description: Current volume state.
      returned: when available
      type: str

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    valid_volume,
)


def validate_volumes(module, volumes):
    if not all(valid_volume(volume) for volume in volumes):
        module.fail_json(msg=("Fly.io API returned malformed volume data for app " f"'{module.params['app_name']}'"))


def list_resources(module, client):
    app_name = module.params["app_name"]
    volumes = list_all(
        client,
        flyio_path("apps", app_name, "volumes"),
        ok_statuses=[404],
        required_field="id",
    )
    validate_volumes(module, volumes)

    module.exit_json(changed=False, volumes=volumes)


def info(module, client):
    volume = get_resource(
        client,
        flyio_path("apps", module.params["app_name"], "volumes", module.params["id"]),
        ok_statuses=[404],
        required_field="id",
        expected_value=module.params["id"],
    )

    if volume is None:
        module.fail_json(msg=(f"Volume '{module.params['id']}' not found in app " f"'{module.params['app_name']}'"))
    validate_volumes(module, [volume])

    module.exit_json(changed=False, volumes=[volume])


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
