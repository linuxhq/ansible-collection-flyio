#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets_info
short_description: Gather information about Fly.io app secrets
description:
  - Gather secret names and digests for a Fly.io app.
  - Fly.io does not expose secret values, so results contain only the secret
    metadata Fly.io returns.
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
- name: List secrets for an app
  linuxhq.flyio.secrets_info:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
"""

RETURN = r"""
---
secrets:
  description: List of Fly.io secret metadata, as Fly.io returns it.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Secret environment variable name.
      returned: always
      type: str
    digest:
      description: Opaque digest of the secret value.
      returned: always
      type: str
    created_at:
      description: Secret creation timestamp.
      returned: when available
      type: str
    updated_at:
      description: Secret update timestamp.
      returned: when available
      type: str

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_token_option,
    flyio_client,
    flyio_path,
    get_resource,
    require_nonempty,
    valid_secret_metadata,
)


def list_resources(module, client):
    result = get_resource(client, flyio_path("apps", module.params["app_name"], "secrets"), ok_statuses=[404])
    if result is None:
        # A missing app has no secrets.
        result = {"secrets": []}

    secrets = result.get("secrets")
    if not isinstance(secrets, list) or not all(valid_secret_metadata(secret) for secret in secrets):
        module.fail_json(
            msg=f"Fly.io API returned malformed data while listing secrets for app '{module.params['app_name']}'"
        )

    module.exit_json(changed=False, secrets=secrets)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
            "app_name": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )

    require_nonempty(module, "app_name")

    with flyio_client(module) as client:
        list_resources(module, client)


if __name__ == "__main__":
    main()
