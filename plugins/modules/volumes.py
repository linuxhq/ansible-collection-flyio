#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes
short_description: Manage Fly.io volumes
description:
  - Create, extend, and delete Fly.io volumes.
  - Volumes are identified by O(id) or by O(name) with O(app_name) and O(region).
  - If multiple volumes have the same name and region, use O(id) to select one.
  - When O(state=present) and a volume with the given O(name) already exists
    in O(region), it will be extended if O(size_gb) exceeds the current size.
  - Volumes cannot be shrunk.
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
      - Either O(id) or O(name) is required.
      - Mutually exclusive with O(name).
  name:
    type: str
    description:
      - Volume name.
      - Either O(id) or O(name) is required.
      - Requires O(region).
      - Mutually exclusive with O(id).
  region:
    type: str
    description:
      - Region code.
      - Must not be empty when specified.
      - Required when O(name) is specified.
      - When used with O(id), must match the volume's current region.
  size_gb:
    type: int
    description:
      - Volume size in gigabytes.
      - Fly.io defaults to C(3) when creating a volume.
      - Must be between C(1) and C(500).
      - Used only when O(state=present).
  encrypted:
    type: bool
    description:
      - Whether a newly created volume is encrypted.
      - Fly.io defaults to C(true) when creating a volume.
      - Cannot be changed on an existing volume.
      - Used only when O(state=present).
  wait:
    type: bool
    default: true
    description:
      - Wait for the volume to reach the target state.
  wait_timeout:
    type: int
    default: 60
    description:
      - Timeout in seconds when waiting for volume state.
      - Must be greater than zero when O(wait=true).
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
- name: Ensure volume exists
  linuxhq.flyio.volumes:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: data
    region: ord
    size_gb: 10
    state: present

- name: Ensure volume is absent
  linuxhq.flyio.volumes:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: vol_abc123
    state: absent
"""

RETURN = r"""
---
volume:
  description: Fly.io volume.
  returned: when available
  type: dict
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
needs_restart:
  description: Whether an attached Machine must restart to use an extended volume.
  returned: after extending a volume
  type: bool
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
    get_resource,
    list_all,
    post_result,
    put_result,
    require_positive,
    valid_volume,
    wait_for_volume,
)

DEAD_STATES = {"destroyed", "pending_destroy"}
DELETING_STATES = {"scheduling_destroy"}
TRANSITIONAL_STATES = {
    "creating",
    "enabling_remote_export",
    "extending",
    "hydrating",
    "recovering",
    "restoring",
}


def validate_name_region(module):
    params = module.params
    region = params.get("region")
    if params.get("name") is not None and not (params.get("region") or "").strip():
        module.fail_json(msg="region must not be empty when name is specified")
    if region is not None and not region.strip():
        module.fail_json(msg="region must not be empty")


def validate_volume_data(module, volume):
    if volume is not None and not valid_volume(volume):
        volume_id = volume.get("id") if isinstance(volume, dict) else None
        detail = f" for volume '{volume_id}'" if volume_id else " volume"
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data{detail} in app "
                f"'{module.params['app_name']}'"
            ),
            volume=volume,
        )
    name = module.params.get("name")
    if volume is not None and name is not None and volume.get("name") != name:
        module.fail_json(
            msg=(
                f"Volume '{volume['id']}' in app '{module.params['app_name']}' "
                f"does not match requested name '{name}'"
            ),
            volume=volume,
        )
    region = module.params.get("region")
    if volume is not None and region is not None and volume.get("region") != region:
        module.fail_json(
            msg=(
                f"Volume '{volume['id']}' in app '{module.params['app_name']}' "
                f"is in region '{volume.get('region')}', not '{region}'"
            ),
            volume=volume,
        )
    return volume


def validate_created_volume(module, volume):
    volume = validate_volume_data(module, volume)
    if volume is None:
        return None
    for field in ("size_gb", "encrypted"):
        expected = module.params.get(field)
        if expected is not None and volume.get(field) != expected:
            module.fail_json(
                msg=(
                    f"Fly.io API did not apply requested {field} to volume "
                    f"'{volume['id']}' in app '{module.params['app_name']}'"
                ),
                volume=volume,
            )
    return volume


def is_live(volume):
    return volume is not None and volume.get("state") not in (
        DEAD_STATES | DELETING_STATES
    )


def find_volume(
    module,
    client,
    app_name,
    name=None,
    volume_id=None,
    region=None,
    include_deleting=False,
    missing_ok=False,
):
    if volume_id is not None:
        volume = get_resource(
            client,
            flyio_path("apps", app_name, "volumes", volume_id),
            ok_statuses=[404],
            required_field="id",
            expected_value=volume_id,
            required_fields=("state",),
        )
        if is_live(volume) or (
            include_deleting
            and volume is not None
            and volume.get("state") in DELETING_STATES
        ):
            return volume
        return None

    volumes = list_all(
        client,
        flyio_path("apps", app_name, "volumes"),
        ok_statuses=[404] if missing_ok else None,
        required_field="id",
        required_fields=("name", "region", "state"),
    )
    matches = [
        volume
        for volume in volumes
        if (
            (
                is_live(volume)
                or (include_deleting and volume.get("state") in DELETING_STATES)
            )
            and volume.get("name") == name
            and (region is None or volume.get("region") == region)
        )
    ]

    if len(matches) > 1:
        module.fail_json(
            msg=(
                f"Multiple volumes named '{name}' in region '{region}' match "
                f"in app '{app_name}'; specify id"
            ),
            volume_ids=[volume.get("id") for volume in matches],
        )

    return matches[0] if matches else None


def settle_volume(module, client, current):
    params = module.params
    app_name = params["app_name"]
    volume_id = current["id"]
    if current.get("state") not in TRANSITIONAL_STATES:
        return current
    if not params["wait"]:
        module.fail_json(
            msg=(
                f"Volume '{volume_id}' in app '{app_name}' is transitioning; "
                "enable wait or retry"
            ),
            volume=current,
        )
    current = wait_for_volume(
        client,
        app_name,
        volume_id,
        params["wait_timeout"],
    )
    if current is None or current.get("state") != "created":
        module.fail_json(
            msg=f"Transition of volume '{volume_id}' in app '{app_name}' timed out",
            volume=current,
        )
    return current


def validate_volume_update(module, current):
    app_name = module.params["app_name"]
    volume_id = current["id"]
    current_size = current.get("size_gb")
    if (
        not isinstance(current.get("encrypted"), bool)
        or not isinstance(current_size, int)
        or isinstance(current_size, bool)
        or current_size <= 0
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data for volume "
                f"'{volume_id}' in app '{app_name}'"
            ),
            volume=current,
        )

    if (
        module.params["encrypted"] is not None
        and current["encrypted"] != module.params["encrypted"]
    ):
        module.fail_json(
            msg=(
                f"Encryption cannot be changed for volume '{volume_id}' "
                f"in app '{app_name}'"
            ),
            volume=current,
        )
    return current_size


def update_volume(module, client, current):
    params = module.params
    app_name = params["app_name"]
    volume_id = current["id"]
    current = settle_volume(module, client, current)
    current_size = validate_volume_update(module, current)

    desired_size = params["size_gb"]
    if desired_size is not None and desired_size < current_size:
        module.fail_json(
            msg=(
                f"Volume '{volume_id}' in app '{app_name}' cannot be shrunk "
                f"from {current_size} GB to {desired_size} GB"
            ),
            volume=current,
        )

    if desired_size is None or desired_size == current_size:
        module.exit_json(
            changed=False, message="Volume already present", volume=current
        )
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Volume would be extended",
            volume=current,
        )

    extension_error = (
        f"Fly.io API returned malformed data while extending volume "
        f"'{volume_id}' in app '{app_name}'"
    )
    result = put_result(
        client,
        flyio_path("apps", app_name, "volumes", volume_id, "extend"),
        {"size_gb": desired_size},
    )
    needs_restart = result.get("needs_restart") if isinstance(result, dict) else None
    response_volume = result.get("volume") if isinstance(result, dict) else None
    response_size = (
        response_volume.get("size_gb") if isinstance(response_volume, dict) else None
    )
    if (
        not isinstance(result, dict)
        or not isinstance(needs_restart, bool)
        or not valid_volume(response_volume)
        or response_volume["id"] != volume_id
        or not isinstance(response_size, int)
        or isinstance(response_size, bool)
        or response_size < desired_size
    ):
        module.fail_json(msg=extension_error, volume=response_volume)

    if params["wait"]:
        current = wait_for_volume(
            client,
            app_name,
            volume_id,
            params["wait_timeout"],
            size_gb=desired_size,
        )
        if (
            current is None
            or current.get("state") != "created"
            or current.get("size_gb") < desired_size
        ):
            module.fail_json(
                msg=(
                    f"Extension of volume '{volume_id}' in app "
                    f"'{app_name}' timed out"
                ),
                volume=current,
            )
    else:
        current = response_volume

    module.exit_json(
        changed=True,
        message="Volume extended",
        volume=current,
        needs_restart=needs_restart,
    )


def create_volume(module, client):
    params = module.params
    app_name = params["app_name"]

    if params.get("id") is not None:
        module.fail_json(msg=f"Volume '{params['id']}' not found in app '{app_name}'")

    if module.check_mode:
        module.exit_json(changed=True, message="Volume would be created")

    body = {
        "name": params["name"],
        "region": params["region"],
    }
    for field in ("size_gb", "encrypted"):
        if params[field] is not None:
            body[field] = params[field]

    current = post_result(client, flyio_path("apps", app_name, "volumes"), body)
    if not valid_volume(current):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while creating volume "
                f"'{params['name']}' in app '{app_name}'"
            ),
            volume=current,
        )
    current = validate_created_volume(module, current)

    volume_id = current["id"]
    if params["wait"]:
        current = validate_created_volume(
            module,
            wait_for_volume(client, app_name, volume_id, params["wait_timeout"]),
        )

        if current is None or current.get("state") != "created":
            module.fail_json(
                msg=(f"Creation of volume '{volume_id}' in app '{app_name}' timed out"),
                volume=current,
            )

    module.exit_json(changed=True, message="Volume created", volume=current)


def ensure_present(module, client):
    params = module.params
    validate_name_region(module)
    if params["size_gb"] is not None:
        require_positive(module, "size_gb")
        if params["size_gb"] > 500:
            module.fail_json(msg="size_gb must not exceed 500")
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = validate_volume_data(
        module,
        find_volume(
            module,
            client,
            params["app_name"],
            name=params.get("name"),
            volume_id=params.get("id"),
            region=params.get("region"),
        ),
    )
    if current is not None:
        return update_volume(module, client, current)
    return create_volume(module, client)


def wait_until_volume_deleted(module, client, volume):
    current = wait_for_volume(
        client,
        module.params["app_name"],
        volume["id"],
        module.params["wait_timeout"],
        states=DEAD_STATES,
        ok_statuses=[404],
    )
    if current is not None and current.get("state") not in DEAD_STATES:
        module.fail_json(
            msg=(
                f"Deletion of volume '{volume['id']}' in app "
                f"'{module.params['app_name']}' timed out"
            ),
            volume=current,
        )
    return current


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    validate_name_region(module)
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = validate_volume_data(
        module,
        find_volume(
            module,
            client,
            app_name,
            name=params.get("name"),
            volume_id=params.get("id"),
            region=params.get("region"),
            include_deleting=True,
            missing_ok=True,
        ),
    )

    if current is None:
        module.exit_json(changed=False, message="Volume already absent")

    volume_id = current["id"]
    if current.get("state") in DELETING_STATES:
        if params["wait"] and not module.check_mode:
            current = wait_until_volume_deleted(module, client, current)
        values = {"changed": False, "message": "Volume already being deleted"}
        if current is not None:
            values["volume"] = current
        module.exit_json(**values)

    if module.check_mode:
        module.exit_json(
            changed=True, message="Volume would be deleted", volume=current
        )

    result = delete_result(
        client,
        flyio_path("apps", app_name, "volumes", volume_id),
        ok_statuses=[404],
    )
    if result is not None and (
        not isinstance(result, dict)
        or not valid_volume(result)
        or result.get("id") != volume_id
        or result.get("state") not in (DEAD_STATES | DELETING_STATES)
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while deleting volume "
                f"'{volume_id}' in app '{app_name}'"
            ),
            volume=result,
        )
    if params["wait"]:
        current = wait_until_volume_deleted(module, client, current)
    else:
        current = result

    deleted = (params["wait"] and current is None) or (
        current is not None and current.get("state") in DEAD_STATES
    )
    message = "Volume deleted" if deleted else "Volume deletion requested"
    values = {"changed": True, "message": message}
    if current is not None:
        values["volume"] = current
    module.exit_json(**values)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
            "name": {"type": "str"},
            "region": {"type": "str"},
            "size_gb": {"type": "int"},
            "encrypted": {"type": "bool"},
            "wait": {"type": "bool", "default": True},
            "wait_timeout": {"type": "int", "default": 60},
            "state": {
                "type": "str",
                "choices": ["present", "absent"],
                "default": "present",
            },
        },
        mutually_exclusive=[
            ("id", "name"),
        ],
        required_one_of=[
            ("id", "name"),
        ],
        required_by={
            "name": ("region",),
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
