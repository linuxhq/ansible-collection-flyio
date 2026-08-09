# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets
short_description: Manage fly.io app secrets
description:
  - Set and remove encrypted fly.io app secrets.
  - Secret values are never returned by the module.
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
  name:
    required: true
    type: str
    description:
      - Secret environment variable name.
  value:
    type: str
    description:
      - Secret value.
      - Required when O(state=present).
  state:
    type: str
    choices:
      - present
      - absent
    default: present
    description:
      - Desired state of the secret.
notes:
  - In check mode, present secrets report that they would be set because fly.io does not expose
    their current values.
  - Setting a secret does not restart existing Machines. Deploy or restart them to load an
    updated value.
requirements:
  - python >= 3.9

"""

EXAMPLES = r"""
- name: Set an application secret
  linuxhq.flyio.secrets:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: APP_SECRET
    value: "{{ application_secret }}"
    state: present

- name: Remove an application secret
  linuxhq.flyio.secrets:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: APP_SECRET
    state: absent
"""

RETURN = r"""
---
secret:
  description: fly.io secret metadata. The value is never returned.
  returned: when available
  type: dict
  contains:
    name:
      description: Secret environment variable name.
      type: str
      returned: always
    digest:
      description: Opaque digest of the secret value.
      type: str
      returned: when available
    created_at:
      description: Secret creation timestamp.
      type: str
      returned: when available
    updated_at:
      description: Secret update timestamp.
      type: str
      returned: when available
version:
  description: App secret version after a change request.
  returned: when available
  type: int
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    delete_result,
    flyio_client,
    get_resource,
    post_result,
    select_fields,
)

SECRET_FIELDS = ("name", "digest", "created_at", "updated_at")


def secret_path(app_name, name):
    return f"/apps/{quote(app_name, safe='')}/secrets/{quote(name, safe='')}"


def get_secret(client, path, name):
    return get_resource(
        client,
        path,
        ok_statuses=[404],
        required_field="name",
        expected_value=name,
        required_fields=("digest",),
    )


def ensure_present(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_secret(client, path, module.params["name"])

    if module.check_mode:
        values = {"changed": True, "message": "Secret would be set"}
        if current is not None:
            values["secret"] = select_fields(current, SECRET_FIELDS)
        module.exit_json(**values)

    result = post_result(client, path, {"value": module.params["value"]})
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("name"), str)
        or not result["name"]
        or result["name"] != module.params["name"]
        or not isinstance(result.get("digest"), str)
        or not result["digest"]
        or (
            result.get("version") is not None
            and (
                not isinstance(result["version"], int)
                or isinstance(result["version"], bool)
            )
        )
    ):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response while setting secret"
        )

    secret = select_fields(result, SECRET_FIELDS)
    changed = current is None or current["digest"] != result["digest"]
    values = {
        "changed": changed,
        "message": "Secret set" if changed else "Secret value unchanged",
        "secret": secret,
    }
    if result.get("version") is not None:
        values["version"] = result["version"]

    module.exit_json(**values)


def ensure_absent(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_secret(client, path, module.params["name"])

    if current is None:
        module.exit_json(changed=False, message="Secret already absent")

    secret = select_fields(current, SECRET_FIELDS)
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Secret would be removed",
            secret=secret,
        )

    result = delete_result(client, path, ok_statuses=[404])
    if result is None:
        result = {}
    elif not isinstance(result, dict) or (
        result.get("version") is not None
        and (
            not isinstance(result["version"], int)
            or isinstance(result["version"], bool)
        )
    ):
        module.fail_json(
            msg="fly.io API returned a malformed response while removing secret"
        )

    values = {"changed": True, "message": "Secret removed", "secret": secret}
    if result.get("version") is not None:
        values["version"] = result["version"]

    module.exit_json(**values)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "name": {"required": True, "type": "str"},
            "value": {"type": "str", "no_log": True},
            "state": {
                "type": "str",
                "choices": ["present", "absent"],
                "default": "present",
            },
        },
        required_if=[("state", "present", ("value",))],
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
