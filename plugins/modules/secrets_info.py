#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets_info
short_description: Gather information about Fly.io app secrets
description:
  - Gather secret names and digests for a Fly.io app.
  - Secret values are never returned.
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
  description: List of Fly.io secret metadata. Values are never returned.
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
    flyio_client,
    flyio_path,
    get_result,
    select_fields,
    valid_secret_metadata,
)

SECRET_FIELDS = ("name", "digest", "created_at", "updated_at")


def list_resources(module, client):
    result = get_result(
        client,
        flyio_path("apps", module.params["app_name"], "secrets"),
        default={"secrets": []},
        ok_statuses=[404],
    )
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("secrets"), list)
        or not all(valid_secret_metadata(secret) for secret in result["secrets"])
    ):
        module.fail_json(
            msg=("Fly.io API returned malformed data while listing secrets for app " f"'{module.params['app_name']}'")
        )

    secrets = [select_fields(secret, SECRET_FIELDS) for secret in result["secrets"]]
    module.exit_json(changed=False, secrets=secrets)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        list_resources(module, client)


if __name__ == "__main__":
    main()
