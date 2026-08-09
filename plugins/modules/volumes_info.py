# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: volumes_info
short_description: Gather information about fly.io volumes
description:
  - Gather information about fly.io volumes.
  - Use O(id) to look up a single volume, or omit it to list all volumes for an app.
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
requirements:
  - python >= 3.9

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
  description: List of fly.io volumes.
  returned: always
  type: list
  elements: dict

"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    get_resource,
    list_all,
)


def list_resources(module, client):
    app_name = module.params["app_name"]
    volumes = list_all(
        client,
        f"/apps/{app_name}/volumes",
        ok_statuses=[404],
        required_field="id",
    )

    module.exit_json(changed=False, volumes=volumes)


def info(module, client):
    volume = get_resource(
        client,
        "/apps/{}/volumes/{}".format(module.params["app_name"], module.params["id"]),
        ok_statuses=[404],
        required_field="id",
        expected_value=module.params["id"],
    )

    if volume is None:
        module.fail_json(msg="Volume '{}' not found".format(module.params["id"]))

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
