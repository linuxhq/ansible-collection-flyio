# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes
short_description: Manage fly.io volumes
description:
  - Create, extend, and delete fly.io volumes.
  - Volumes are identified by O(id) or by O(name) with O(app_name) and O(region).
  - If multiple volumes have the same name and region, use O(id) to select one.
  - When O(state=present) and a volume with the given O(name) already exists in the
    specified O(region), it will be extended if O(size_gb) is larger than the current size.
  - Volumes cannot be shrunk.
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
  id:
    type: str
    description:
      - Volume identifier.
      - Mutually exclusive with O(name).
      - Either O(id) or O(name) is required.
  name:
    type: str
    description:
      - Volume name.
      - Mutually exclusive with O(id).
      - Either O(id) or O(name) is required.
      - Requires O(region).
  region:
    type: str
    description:
      - Region code.
      - Required when O(name) is specified.
  size_gb:
    type: int
    default: 1
    description:
      - Volume size in gigabytes.
      - Must be greater than zero.
  encrypted:
    type: bool
    default: true
    description:
      - Whether the volume is encrypted.
      - Cannot be changed on an existing volume.
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
  description: fly.io volume.
  returned: when available
  type: dict
needs_restart:
  description: Whether an attached Machine must restart to use an extended volume.
  returned: when returned by fly.io after extending a volume
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
    get_resource,
    list_all,
    post_result,
    put_result,
    require_positive,
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
            f"/apps/{app_name}/volumes/{volume_id}",
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
        f"/apps/{app_name}/volumes",
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
            msg="Multiple volumes match name and region; specify id",
            volume_ids=[volume.get("id") for volume in matches],
        )

    return matches[0] if matches else None


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]
    require_positive(module, "size_gb")
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_volume(
        module,
        client,
        app_name,
        name=params.get("name"),
        volume_id=params.get("id"),
        region=params.get("region"),
    )

    if current is not None:
        if current.get("state") in TRANSITIONAL_STATES:
            if not params["wait"]:
                module.fail_json(
                    msg="Volume transition already in progress; enable wait or retry",
                    volume=current,
                )
            current = wait_for_volume(
                client,
                app_name,
                current["id"],
                params["wait_timeout"],
            )
            if current is None or current.get("state") != "created":
                module.fail_json(msg="Volume transition timed out", volume=current)

        current_size = current.get("size_gb")
        if (
            not isinstance(current.get("encrypted"), bool)
            or not isinstance(current_size, int)
            or isinstance(current_size, bool)
        ):
            module.fail_json(
                msg="fly.io API returned a malformed volume response",
                volume=current,
            )

        if current["encrypted"] != params["encrypted"]:
            module.fail_json(
                msg="encryption cannot be changed for an existing volume",
                volume=current,
            )

        desired_size = params["size_gb"]

        if desired_size > current_size:
            if module.check_mode:
                module.exit_json(
                    changed=True,
                    message="Volume would be extended",
                    volume=current,
                )

            result = put_result(
                client,
                "/apps/{}/volumes/{}/extend".format(app_name, current["id"]),
                {"size_gb": desired_size},
            )
            if result is None:
                result = {}
            elif not isinstance(result, dict):
                module.fail_json(
                    msg="fly.io API returned a malformed response during extension",
                    volume=result,
                )

            needs_restart = result.get("needs_restart")
            response_volume = result.get("volume")
            if response_volume is None and result.get("id"):
                response_volume = result
            if response_volume is not None and (
                not isinstance(response_volume, dict)
                or not isinstance(response_volume.get("id"), str)
                or not response_volume["id"]
                or response_volume["id"] != current["id"]
            ):
                module.fail_json(
                    msg="fly.io API returned a malformed response during extension",
                    volume=response_volume,
                )
            if needs_restart is not None and not isinstance(needs_restart, bool):
                module.fail_json(
                    msg="fly.io API returned a malformed response during extension",
                    volume=response_volume,
                )

            if params["wait"]:
                current = wait_for_volume(
                    client,
                    app_name,
                    current["id"],
                    params["wait_timeout"],
                    size_gb=desired_size,
                )
                if current is None or current.get("state") != "created":
                    module.fail_json(
                        msg="Volume extension timed out",
                        volume=current,
                    )
            else:
                current = response_volume or get_resource(
                    client,
                    "/apps/{}/volumes/{}".format(app_name, current["id"]),
                    required_field="id",
                    expected_value=current["id"],
                )

            values = {
                "changed": True,
                "message": "Volume extended",
                "volume": current,
            }
            if needs_restart is not None:
                values["needs_restart"] = needs_restart

            module.exit_json(**values)

        module.exit_json(
            changed=False, message="Volume already present", volume=current
        )

    if params.get("id") is not None:
        module.fail_json(msg="Volume '{}' not found".format(params["id"]))

    if module.check_mode:
        module.exit_json(changed=True, message="Volume would be created")

    body = {
        "name": params["name"],
        "region": params["region"],
        "size_gb": params["size_gb"],
        "encrypted": params["encrypted"],
    }

    current = post_result(client, f"/apps/{app_name}/volumes", body)

    if (
        not isinstance(current, dict)
        or not isinstance(current.get("id"), str)
        or not current["id"]
    ):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response during create",
            volume=current,
        )

    if params["wait"]:
        current = wait_for_volume(
            client, app_name, current["id"], params["wait_timeout"]
        )

        if current is None or current.get("state") != "created":
            module.fail_json(
                msg="Volume creation timed out",
                volume=current,
            )

    module.exit_json(changed=True, message="Volume created", volume=current)


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_volume(
        module,
        client,
        app_name,
        name=params.get("name"),
        volume_id=params.get("id"),
        region=params.get("region"),
        include_deleting=True,
        missing_ok=True,
    )

    if current is None:
        module.exit_json(changed=False, message="Volume already absent")

    if current.get("state") in DELETING_STATES:
        if params["wait"]:
            current = wait_for_volume(
                client,
                app_name,
                current["id"],
                params["wait_timeout"],
                states=DEAD_STATES,
                ok_statuses=[404],
            )
            if current is not None and current.get("state") not in DEAD_STATES:
                module.fail_json(msg="Volume deletion timed out", volume=current)
        module.exit_json(
            changed=False, message="Volume already being deleted", volume=current
        )

    if module.check_mode:
        module.exit_json(
            changed=True, message="Volume would be deleted", volume=current
        )

    delete_result(
        client,
        "/apps/{}/volumes/{}".format(app_name, current["id"]),
        ok_statuses=[404],
    )

    if params["wait"]:
        current = wait_for_volume(
            client,
            app_name,
            current["id"],
            params["wait_timeout"],
            states=DEAD_STATES,
            ok_statuses=[404],
        )
        if current is not None and current.get("state") not in DEAD_STATES:
            module.fail_json(msg="Volume deletion timed out", volume=current)

    module.exit_json(changed=True, message="Volume deleted", volume=current)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
            "name": {"type": "str"},
            "region": {"type": "str"},
            "size_gb": {"type": "int", "default": 1},
            "encrypted": {"type": "bool", "default": True},
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
