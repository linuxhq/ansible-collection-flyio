# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes
short_description: Manage fly.io volumes
description:
  - Create, extend, and delete fly.io volumes.
  - Volumes are identified by O(id) or by O(name) with O(app_name) and O(region).
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
  name:
    type: str
    description:
      - Volume name.
      - Mutually exclusive with O(id).
  region:
    type: str
    description:
      - Region code.
      - Required when creating a volume.
  size_gb:
    type: int
    default: 1
    description:
      - Volume size in gigabytes.
  encrypted:
    type: bool
    default: true
    description:
      - Whether the volume is encrypted.
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
    list_all,
    post_result,
    put_result,
    wait_for_volume,
)

DEAD_STATES = {"destroyed", "pending_destroy"}


def is_live(volume):
    return volume is not None and volume.get("state") not in DEAD_STATES


def find_volume(client, app_name, name=None, volume_id=None, region=None):
    if volume_id is not None:
        volume = get_result(
            client,
            f"/apps/{app_name}/volumes/{volume_id}",
            ok_statuses=[404],
        )
        return volume if is_live(volume) else None

    volumes = list_all(client, f"/apps/{app_name}/volumes")

    for volume in volumes:
        if (
            is_live(volume)
            and volume.get("name") == name
            and (region is None or volume.get("region") == region)
        ):
            return volume

    return None


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_volume(
        client,
        app_name,
        name=params.get("name"),
        volume_id=params.get("id"),
        region=params.get("region"),
    )

    if current is not None:
        current_size = current.get("size_gb", 0)
        desired_size = params["size_gb"]

        if desired_size > current_size:
            if module.check_mode:
                module.exit_json(
                    changed=True,
                    message="Volume would be extended",
                    volume=current,
                )

            put_result(
                client,
                "/apps/{}/volumes/{}/extend".format(app_name, current["id"]),
                {"size_gb": desired_size},
            )

            current = get_result(
                client,
                "/apps/{}/volumes/{}".format(app_name, current["id"]),
            )

            module.exit_json(changed=True, message="Volume extended", volume=current)

        module.exit_json(
            changed=False, message="Volume already present", volume=current
        )

    if params.get("name") is None:
        module.fail_json(msg="name is required when creating a volume")

    if params.get("region") is None:
        module.fail_json(msg="region is required when creating a volume")

    if module.check_mode:
        module.exit_json(changed=True, message="Volume would be created")

    body = {
        "name": params["name"],
        "region": params["region"],
        "size_gb": params["size_gb"],
        "encrypted": params["encrypted"],
    }

    current = post_result(client, f"/apps/{app_name}/volumes", body)

    if current is None or not current.get("id"):
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

    current = find_volume(
        client,
        app_name,
        name=params.get("name"),
        volume_id=params.get("id"),
        region=params.get("region"),
    )

    if current is None:
        module.exit_json(changed=False, message="Volume already absent")

    if module.check_mode:
        module.exit_json(
            changed=True, message="Volume would be deleted", volume=current
        )

    delete_result(client, "/apps/{}/volumes/{}".format(app_name, current["id"]))

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
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
