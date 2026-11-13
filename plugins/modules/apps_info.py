#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: apps_info
short_description: Gather information about Fly.io apps
description:
  - Gather information about Fly.io apps.
  - Use O(name) to look up a single app, or O(org_slug) to list apps in an organization.
  - O(name) is mutually exclusive with O(org_slug).
version_added: '1.0.0'
author:
  - Taylor Kimball (@tkimball83)
extends_documentation_fragment:
  - linuxhq.flyio.api
options:
  name:
    type: str
    description:
      - App name.
      - Fails when the app does not exist.
      - Either O(name) or O(org_slug) is required.
      - Mutually exclusive with O(org_slug).
  org_slug:
    type: str
    description:
      - Organization slug.
      - Either O(name) or O(org_slug) is required.
      - Mutually exclusive with O(name).
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
  description: List of Fly.io apps.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: App identifier.
      returned: when available
      type: str
    name:
      description: App name.
      returned: always
      type: str
    internal_numeric_id:
      description: Internal numeric app identifier.
      returned: when available
      type: int
    machine_count:
      description: Number of Machines in the app.
      returned: when available
      type: int
    volume_count:
      description: Number of volumes in the app.
      returned: when available
      type: int
    network:
      description: Private network name, such as C(default).
      returned: when available
      type: str
    network_cidr:
      description: Private network CIDR.
      returned: when available
      type: str
    organization:
      description: Organization that owns the app.
      returned: when available
      type: dict
      contains:
        name:
          description: Organization name.
          returned: when available
          type: str
        slug:
          description: Organization slug.
          returned: when available
          type: str
        internal_numeric_id:
          description: Internal numeric organization identifier.
          returned: when available
          type: int
    status:
      description: App status, such as C(pending), C(deployed), or C(suspended).
      returned: when available
      type: str
    cname_target:
      description: CNAME target for custom domains.
      returned: when available
      type: str

"""

from urllib.parse import urlencode

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_request,
    api_token_option,
    flyio_client,
    get_app,
    nonempty_string,
    require_nonempty,
)


def list_resources(module, client):
    org_slug = module.params["org_slug"]
    # Without a limit, Fly.io returns every app in one response.
    result = api_request(client, "get", f"/apps?{urlencode({'org_slug': org_slug})}")
    apps = result.get("apps") if isinstance(result, dict) else None
    if not isinstance(apps, list) or not all(
        isinstance(app, dict) and nonempty_string(app.get("name")) for app in apps
    ):
        module.fail_json(msg=f"Fly.io API returned malformed data while listing apps for organization '{org_slug}'")

    module.exit_json(changed=False, apps=apps)


def info(module, client):
    app = get_app(client, module.params["name"])

    if app is None:
        module.fail_json(msg=f"App '{module.params['name']}' not found")

    module.exit_json(changed=False, apps=[app])


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
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

    require_nonempty(module, "name", "org_slug")

    with flyio_client(module) as client:
        if module.params["name"] is not None:
            info(module, client)
        else:
            list_resources(module, client)


if __name__ == "__main__":
    main()
