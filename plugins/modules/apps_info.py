# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: apps_info
short_description: Gather information about fly.io apps
description:
  - Gather information about fly.io apps.
  - Use O(name) to look up a single app, or O(org_slug) to list apps in an organization.
  - O(name) is mutually exclusive with O(org_slug).
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - fly.io API token.
  name:
    type: str
    description:
      - App name.
      - Mutually exclusive with O(org_slug).
  org_slug:
    type: str
    description:
      - Organization slug.
      - Mutually exclusive with O(name).
requirements:
  - python >= 3.9

"""

EXAMPLES = r"""
- name: Gather app info
  linuxhq.flyio.apps_info:
    api_token: "{{ flyio_api_token }}"
    name: my-app

- name: List all apps in an organization
  linuxhq.flyio.apps_info:
    api_token: "{{ flyio_api_token }}"
    org_slug: linuxhq
"""

RETURN = r"""
---
apps:
  description: List of fly.io apps.
  returned: always
  type: list
  elements: dict

"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    get_result,
)


def info(module, client):
    app = get_result(
        client,
        "/apps/{}".format(module.params["name"]),
        ok_statuses=[404],
    )

    if app is None:
        module.fail_json(msg="App '{}' not found".format(module.params["name"]))

    module.exit_json(changed=False, apps=[app])


def list_resources(module, client):
    result = get_result(
        client,
        "/apps?org_slug={}".format(module.params["org_slug"]),
        default={},
    )

    apps = result.get("apps", []) if isinstance(result, dict) else result

    module.exit_json(changed=False, apps=apps)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "name": {"type": "str"},
            "org_slug": {"type": "str"},
        },
        mutually_exclusive=[
            ("name", "org_slug"),
        ],
        required_one_of=[
            ("name", "org_slug"),
        ],
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["name"] is not None:
            info(module, client)
        else:
            list_resources(module, client)


if __name__ == "__main__":
    main()
