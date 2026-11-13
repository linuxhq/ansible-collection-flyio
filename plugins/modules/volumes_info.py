#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes_info
short_description: Gather information about Fly.io volumes
description:
  - Gather information about Fly.io volumes.
  - Use O(id) to look up a single volume, or omit it to list all volumes for an app.
  - Results can include volumes that are being deleted or were recently
    destroyed. Check RV(volumes[].state) to select live volumes.
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
      - Volume identifier.
      - Fails when the volume does not exist in the app.
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
      description:
        - Current volume state.
        - States such as C(scheduling_destroy), C(fork_cleanup),
          C(waiting_for_detach), C(pending_destroy), C(destroying), and
          C(destroyed) mean the volume is being deleted or is gone.
      returned: when available
      type: str
    attached_machine_id:
      description: Identifier of the Machine the volume is attached to, or null.
      returned: when available
      type: str
    attached_alloc_id:
      description: Deprecated by Fly.io and always null.
      returned: when available
      type: str
    created_at:
      description: Creation timestamp.
      returned: when available
      type: str
    fstype:
      description: Filesystem type, such as C(ext4), or C(raw) for an unformatted block device.
      returned: when available
      type: str
    auto_backup_enabled:
      description: Whether Fly.io takes daily automatic snapshots.
      returned: when available
      type: bool
    snapshot_retention:
      description: Number of days snapshots are kept.
      returned: when available
      type: int
    zone:
      description: Host zone. Volumes in different zones are on different hosts.
      returned: when available
      type: str
    type:
      description: Volume kind, such as C(local) or C(cache).
      returned: when available
      type: str
    host_status:
      description: Whether Fly.io could reach the volume's host, such as C(ok), C(unreachable), or C(unknown).
      returned: when available
      type: str
    block_size:
      description: Filesystem block size in bytes.
      returned: when available
      type: int
    blocks:
      description: Filesystem size in blocks, as last reported by a Machine that mounted the volume, or 0.
      returned: when available
      type: int
    blocks_free:
      description: Free filesystem blocks, including blocks reserved for the root user.
      returned: when available
      type: int
    blocks_avail:
      description: Filesystem blocks available to unprivileged users.
      returned: when available
      type: int
    bytes_total:
      description: Volume size in bytes, or 0 when the host could not be reached.
      returned: when available
      type: int
    bytes_used:
      description: Bytes the volume occupies on its host, or 0 when the host could not be reached.
      returned: when available
      type: int

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_token_option,
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    require_nonempty,
    valid_volume,
)


def validate_volumes(module, volumes):
    if not all(valid_volume(volume) for volume in volumes):
        module.fail_json(msg=f"Fly.io API returned malformed volume data for app '{module.params['app_name']}'")


def list_resources(module, client):
    app_name = module.params["app_name"]
    volumes = list_all(
        client,
        flyio_path("apps", app_name, "volumes"),
        ok_statuses=[404],
    )
    validate_volumes(module, volumes)

    module.exit_json(changed=False, volumes=volumes)


def info(module, client):
    volume = get_resource(
        client,
        flyio_path("apps", module.params["app_name"], "volumes", module.params["id"]),
        ok_statuses=[404],
        required_fields=("id",),
        expected={"id": module.params["id"]},
    )

    if volume is None:
        module.fail_json(msg=f"Volume '{module.params['id']}' not found in app '{module.params['app_name']}'")

    validate_volumes(module, [volume])

    module.exit_json(changed=False, volumes=[volume])


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
