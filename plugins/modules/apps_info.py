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
      - Either O(name) or O(org_slug) is required.
  org_slug:
    type: str
    description:
      - Organization slug.
      - Mutually exclusive with O(name).
      - Either O(name) or O(org_slug) is required.
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

from urllib.parse import urlencode

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    get_resource,
    get_result,
)


def list_resources(module, client):
    result = get_result(
        client,
        "/apps?{}".format(urlencode({"org_slug": module.params["org_slug"]})),
        default={},
    )

    apps = result.get("apps") if isinstance(result, dict) else None
    if not isinstance(apps, list) or not all(
        isinstance(app, dict) and isinstance(app.get("name"), str) and app["name"]
        for app in apps
    ):
        module.fail_json(
            msg="fly.io API returned a malformed response while listing apps"
        )

    module.exit_json(changed=False, apps=apps)


def info(module, client):
    app = get_resource(
        client,
        "/apps/{}".format(module.params["name"]),
        ok_statuses=[404],
        required_field="name",
        expected_value=module.params["name"],
    )

    if app is None:
        module.fail_json(msg="App '{}' not found".format(module.params["name"]))

    module.exit_json(changed=False, apps=[app])


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
