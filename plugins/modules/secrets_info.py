# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets_info
short_description: Gather information about fly.io app secrets
description:
  - Gather secret names and digests for a fly.io app.
  - Secret values are never returned.
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
requirements:
  - python >= 3.9

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
  description: List of fly.io secret metadata. Values are never returned.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Secret environment variable name.
      type: str
    digest:
      description: Opaque digest of the secret value.
      type: str
    created_at:
      description: Secret creation timestamp.
      type: str
    updated_at:
      description: Secret update timestamp.
      type: str

"""

from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    flyio_client,
    get_result,
    select_fields,
)

SECRET_FIELDS = ("name", "digest", "created_at", "updated_at")


def list_resources(module, client):
    app_name = quote(module.params["app_name"], safe="")
    result = get_result(
        client,
        f"/apps/{app_name}/secrets",
        default={"secrets": []},
        ok_statuses=[404],
    )
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("secrets"), list)
        or not all(
            isinstance(secret, dict)
            and isinstance(secret.get("name"), str)
            and secret["name"]
            for secret in result["secrets"]
        )
    ):
        module.fail_json(
            msg="fly.io API returned a malformed response while listing secrets"
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
