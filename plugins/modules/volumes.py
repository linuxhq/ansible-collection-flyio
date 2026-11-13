#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes
short_description: Manage Fly.io volumes
description:
  - Create, extend, and delete Fly.io volumes.
  - Volumes are identified by O(id) or by O(name) with O(app_name) and O(region).
  - If multiple live volumes have the same name and region, use O(id) to select one.
  - When O(state=present) and a volume with the given O(name) already exists
    in O(region), it will be extended if O(size_gb) exceeds the current size.
  - Volumes cannot be shrunk.
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
      - Either O(id) or O(name) is required.
      - A destroyed volume is treated as missing, and so is a volume being
        deleted unless O(state=absent).
      - Mutually exclusive with O(name).
  name:
    type: str
    description:
      - Volume name.
      - Either O(id) or O(name) is required.
      - Requires O(region).
      - Destroyed volumes are ignored, and so are volumes being deleted, except
        that O(state=absent) considers those when no live volume has this name.
      - The task fails when more than one live volume has this name.
      - Mutually exclusive with O(id).
  region:
    type: str
    description:
      - Region code, such as C(ord).
      - Must be a single region code. Region lists and region groups such as
        C(us) are not supported.
      - Surrounding whitespace is removed and the code is lowercased.
      - Required when O(name) is specified.
      - When used with O(id), must match the volume's current region.
  size_gb:
    type: int
    description:
      - Volume size in GiB.
      - Required when creating a volume.
      - Must be greater than zero and at most the organization's maximum
        volume size (C(500) by default).
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
      - With O(wait=false) and O(state=present), the task fails if an existing
        volume is transitioning and needs a change.
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
    support: full

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
  description: Fly.io volume. After deletion, the last known state of the volume.
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
      description: Volume size in GiB.
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
    required_host_features:
      description: Host features the volume's host was required to have when the volume was created.
      returned: when available
      type: list
      elements: str
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
needs_restart:
  description: Whether an attached Machine must restart to use an extended volume.
  returned: when a volume is extended, except in check mode
  type: bool
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    api_request,
    api_token_option,
    delete_result,
    diff_result,
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    positive_int,
    post_result,
    report_changed_on_failure,
    require_nonempty,
    require_positive,
    require_region_code,
    seconds_left,
    select_fields,
    valid_volume,
    wait_deadline,
    wait_for_volume,
)

DEAD_STATES = {"destroyed", "pending_destroy"}
DELETING_STATES = {"destroying", "fork_cleanup", "scheduling_destroy", "waiting_for_detach"}
FAILED_STATE = "failed"
TRANSITIONAL_STATES = {
    "creating",
    "enabling_remote_export",
    "extending",
    "hydrating",
    "recovering",
    "restoring",
}


def validate_volume_data(module, volume):
    if volume is not None and not valid_volume(volume):
        volume_id = volume.get("id") if isinstance(volume, dict) else None
        detail = f" for volume '{volume_id}'" if volume_id else ""
        module.fail_json(
            msg=f"Fly.io API returned malformed data{detail} in app '{module.params['app_name']}'",
            volume=volume,
        )

    return require_matching_volume(module, volume)


def require_matching_volume(module, volume):
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
    # Callers pass a volume that already passed valid_volume.
    volume = require_matching_volume(module, volume)
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
    return volume is not None and volume.get("state") not in (DEAD_STATES | DELETING_STATES)


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
            required_fields=("id", "state"),
            expected={"id": volume_id},
        )
        if is_live(volume) or (include_deleting and volume is not None and volume.get("state") in DELETING_STATES):
            return volume

        return None

    volumes = list_all(
        client,
        flyio_path("apps", app_name, "volumes"),
        ok_statuses=[404] if missing_ok else None,
        required_fields=("id", "name", "region", "state"),
    )
    named = [
        volume
        for volume in volumes
        if volume.get("state") not in DEAD_STATES and volume.get("name") == name and volume.get("region") == region
    ]
    # Prefer live volumes; fall back to one being deleted only when asked. Only live matches are ambiguous.
    live = [volume for volume in named if is_live(volume)]
    if len(live) > 1:
        module.fail_json(
            msg=f"Multiple volumes named '{name}' in region '{region}' match in app '{app_name}'; specify id",
            volume_ids=[volume.get("id") for volume in live],
        )

    matches = live or (named if include_deleting else [])
    return matches[0] if matches else None


def reject_failed(module, volume):
    if volume is not None and volume.get("state") == FAILED_STATE:
        module.fail_json(
            msg=f"Volume '{volume['id']}' in app '{module.params['app_name']}' is in failed state",
            volume=volume,
        )


def wait_volume(module, client, volume_id, deadline, **kwargs):
    current = wait_for_volume(client, module.params["app_name"], volume_id, seconds_left(deadline), **kwargs)
    reject_failed(module, current)
    return current


def wait_volume_created(module, client, volume_id, deadline, **kwargs):
    gone_states = DEAD_STATES | DELETING_STATES
    current = wait_volume(module, client, volume_id, deadline, stop_states=gone_states, **kwargs)
    if current["state"] in gone_states:
        module.fail_json(
            msg=f"Volume '{volume_id}' in app '{module.params['app_name']}' was deleted while waiting",
            volume=current,
        )

    return current


def settle_volume(module, client, current, deadline):
    params = module.params
    app_name = params["app_name"]
    volume_id = current["id"]
    reject_failed(module, current)
    if current.get("state") not in TRANSITIONAL_STATES:
        return current

    if not params["wait"]:
        module.fail_json(
            msg=f"Volume '{volume_id}' in app '{app_name}' is transitioning; enable wait or retry",
            volume=current,
        )

    current = wait_volume_created(module, client, volume_id, deadline)
    if current.get("state") != "created":
        module.fail_json(
            msg=f"Transition of volume '{volume_id}' in app '{app_name}' timed out",
            volume=current,
        )

    return current


def validate_volume_update(module, current):
    app_name = module.params["app_name"]
    volume_id = current["id"]
    desired_encrypted = module.params["encrypted"]
    desired_size = module.params["size_gb"]
    current_size = current.get("size_gb")
    if (desired_encrypted is not None and not isinstance(current.get("encrypted"), bool)) or (
        desired_size is not None and not positive_int(current_size)
    ):
        module.fail_json(
            msg=f"Fly.io API returned malformed data for volume '{volume_id}' in app '{app_name}'",
            volume=current,
        )

    if desired_encrypted is not None and current["encrypted"] != desired_encrypted:
        module.fail_json(
            msg=f"Encryption cannot be changed for volume '{volume_id}' in app '{app_name}'",
            volume=current,
        )

    return current_size


def reject_shrink(module, current, current_size):
    desired_size = module.params["size_gb"]
    if desired_size is not None and desired_size < current_size:
        module.fail_json(
            msg=(
                f"Volume '{current['id']}' in app '{module.params['app_name']}' cannot be shrunk "
                f"from {current_size} GiB to {desired_size} GiB"
            ),
            volume=current,
        )


def update_volume(module, client, current, deadline):
    params = module.params
    app_name = params["app_name"]
    volume_id = current["id"]
    desired_size = params["size_gb"]
    if not params["wait"] and current.get("state") in TRANSITIONAL_STATES:
        # Without wait, a volume that needs no change is reported unchanged instead of failing.
        current_size = validate_volume_update(module, current)
        reject_shrink(module, current, current_size)
        if desired_size is None or desired_size == current_size:
            module.exit_json(changed=False, message="Volume already present", volume=current)

    current = settle_volume(module, client, current, deadline)
    current_size = validate_volume_update(module, current)
    reject_shrink(module, current, current_size)

    if desired_size is None or desired_size == current_size:
        module.exit_json(changed=False, message="Volume already present", volume=current)

    original_size = current_size
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Volume would be extended",
            volume=current,
            **diff_result(module, {"size_gb": original_size}, {"size_gb": desired_size}),
        )

    extension_error = f"Fly.io API returned malformed data while extending volume '{volume_id}' in app '{app_name}'"
    result = api_request(
        client,
        "put",
        flyio_path("apps", app_name, "volumes", volume_id, "extend"),
        body={"size_gb": desired_size},
    )
    report_changed_on_failure(module)
    needs_restart = result.get("needs_restart") if isinstance(result, dict) else None
    response_volume = result.get("volume") if isinstance(result, dict) else None
    response_size = response_volume.get("size_gb") if isinstance(response_volume, dict) else None
    if (
        not isinstance(result, dict)
        or not isinstance(needs_restart, bool)
        or not valid_volume(response_volume)
        or response_volume["id"] != volume_id
        or not positive_int(response_size)
        or response_size < desired_size
    ):
        module.fail_json(msg=extension_error, volume=response_volume)

    if params["wait"]:
        current = wait_volume_created(module, client, volume_id, deadline, size_gb=desired_size)
        current_size = current.get("size_gb")
        if current.get("state") != "created" or not positive_int(current_size) or current_size < desired_size:
            module.fail_json(
                msg=f"Extension of volume '{volume_id}' in app '{app_name}' timed out",
                volume=current,
            )
    else:
        current = response_volume

    module.exit_json(
        changed=True,
        message="Volume extended",
        volume=current,
        needs_restart=needs_restart,
        # Fly.io may extend beyond the request, so report the size it applied.
        **diff_result(module, {"size_gb": original_size}, {"size_gb": current["size_gb"]}),
    )


def create_volume(module, client, deadline):
    params = module.params
    app_name = params["app_name"]

    if params.get("id") is not None:
        module.fail_json(msg=f"Volume '{params['id']}' not found in app '{app_name}'")

    if params["size_gb"] is None:
        module.fail_json(msg="size_gb is required when creating a volume")

    body = {
        "name": params["name"],
        "region": params["region"],
    }
    for field in ("size_gb", "encrypted"):
        if params[field] is not None:
            body[field] = params[field]

    diff = diff_result(module, {}, body)
    if module.check_mode:
        module.exit_json(changed=True, message="Volume would be created", **diff)

    current = post_result(client, flyio_path("apps", app_name, "volumes"), body)
    report_changed_on_failure(module)
    if not valid_volume(current):
        module.fail_json(
            msg=(f"Fly.io API returned malformed data while creating volume '{params['name']}' in app '{app_name}'"),
            volume=current,
        )

    current = validate_created_volume(module, current)

    volume_id = current["id"]
    if params["wait"]:
        current = validate_created_volume(
            module,
            wait_volume_created(module, client, volume_id, deadline),
        )

        if current.get("state") != "created":
            module.fail_json(
                msg=f"Creation of volume '{volume_id}' in app '{app_name}' timed out",
                volume=current,
            )

    module.exit_json(changed=True, message="Volume created", volume=current, **diff)


def ensure_present(module, client):
    params = module.params
    require_region_code(module)
    if params["size_gb"] is not None:
        require_positive(module, "size_gb")

    if params["wait"]:
        require_positive(module, "wait_timeout")

    deadline = wait_deadline(params["wait_timeout"])
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
        return update_volume(module, client, current, deadline)

    return create_volume(module, client, deadline)


def wait_until_volume_deleted(module, client, volume, deadline):
    current = wait_volume(module, client, volume["id"], deadline, states=DEAD_STATES, ok_statuses=[404])
    if current is not None and current.get("state") not in DEAD_STATES:
        module.fail_json(
            msg=f"Deletion of volume '{volume['id']}' in app '{module.params['app_name']}' timed out",
            volume=current,
        )

    return current


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    require_region_code(module)
    if params["wait"]:
        require_positive(module, "wait_timeout")

    deadline = wait_deadline(params["wait_timeout"])
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
        deleting = current
        if params["wait"] and not module.check_mode:
            current = wait_until_volume_deleted(module, client, current, deadline)

        # Keep the last-known volume so callers still get its id once it is gone.
        module.exit_json(changed=False, message="Volume already being deleted", volume=current or deleting)

    # Report the volume's identity and create fields rather than the full API object.
    diff = diff_result(module, select_fields(current, ("id", "name", "region", "size_gb", "encrypted")), {})
    if module.check_mode:
        module.exit_json(changed=True, message="Volume would be deleted", volume=current, **diff)

    try:
        result = delete_result(client, flyio_path("apps", app_name, "volumes", volume_id))
    except FlyioApiError as exc:
        if exc.status_code != 404:
            raise

        module.exit_json(changed=False, message="Volume already absent")

    report_changed_on_failure(module)
    if result is not None and (
        not valid_volume(result)
        or result.get("id") != volume_id
        or result.get("state") not in (DEAD_STATES | DELETING_STATES)
    ):
        module.fail_json(
            msg=f"Fly.io API returned malformed data while deleting volume '{volume_id}' in app '{app_name}'",
            volume=result,
        )

    requested = current
    if params["wait"]:
        current = wait_until_volume_deleted(module, client, current, deadline)
    else:
        current = result

    deleted = (params["wait"] and current is None) or (current is not None and current.get("state") in DEAD_STATES)
    module.exit_json(
        changed=True,
        message="Volume deleted" if deleted else "Volume deletion requested",
        volume=current if current is not None else requested,
        **diff,
    )


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
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

    require_nonempty(module, "app_name", "id", "name")

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
