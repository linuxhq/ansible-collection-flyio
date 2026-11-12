#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets
short_description: Manage Fly.io app secrets
description:
  - Set and remove encrypted Fly.io app secrets.
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
      - Used only when O(state=present).
  state:
    type: str
    choices:
      - present
      - absent
    default: present
    description:
      - Desired state of the secret.
notes:
  - Running Machines do not pick up a changed secret on their own. Create or
    update them, for example with a deploy, to load the new value. Fly.io
    guarantees the change is visible when Machines are created or updated with
    C(min_secrets_version) set to the returned RV(version).
requirements:
  - python >= 3.9
attributes:
  check_mode:
    description: Supports predicting changes without applying them.
    support: partial
    details: Present secrets report changed because Fly.io does not expose their values.
  diff_mode:
    description: Determines whether the module returns change details in diff format.
    support: partial
    details: Diffs show secret names and digests, never values. Check mode cannot predict the new digest.

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
  description: Fly.io secret metadata, as Fly.io returns it.
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
      returned: always
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

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    api_token_option,
    delete_result,
    diff_result,
    flyio_client,
    flyio_path,
    get_app,
    get_resource,
    post_result,
    require_nonempty,
    select_fields,
    valid_secret_metadata,
)

# Secret values are never readable, so diffs compare names and digests.
DIFF_FIELDS = ("name", "digest")


def secret_path(app_name, name):
    return flyio_path("apps", app_name, "secrets", name)


def valid_version(value):
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def get_secret(client, path, name):
    secret = get_resource(
        client,
        path,
        ok_statuses=[404],
        required_fields=("name",),
        expected={"name": name},
    )
    if secret is not None and not valid_secret_metadata(secret):
        raise FlyioApiError(f"GET {path} returned malformed data: expected a secret")

    return secret


def ensure_present(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_secret(client, path, module.params["name"])

    before = select_fields(current, DIFF_FIELDS) if current is not None else {}
    if module.check_mode:
        # A missing secret may mean a missing app; predict the real run's failure instead of a change.
        if current is None and get_app(client, module.params["app_name"]) is None:
            module.fail_json(msg=f"App '{module.params['app_name']}' not found")

        values = {
            "changed": True,
            "message": "Secret would be set",
            **diff_result(module, before, {"name": module.params["name"]}),
        }
        if current is not None:
            values["secret"] = current

        module.exit_json(**values)

    result = post_result(client, path, {"value": module.params["value"]})
    if (
        not valid_secret_metadata(result)
        or result["name"] != module.params["name"]
        or not valid_version(result.get("version"))
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while setting secret "
                f"'{module.params['name']}' for app '{module.params['app_name']}'"
            )
        )

    secret = result
    changed = current is None or current["digest"] != result["digest"]
    values = {
        "changed": changed,
        "message": "Secret set" if changed else "Secret value unchanged",
        "secret": secret,
    }
    if changed:
        values.update(diff_result(module, before, select_fields(result, DIFF_FIELDS)))

    if result.get("version") is not None:
        values["version"] = result["version"]

    module.exit_json(**values)


def ensure_absent(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_secret(client, path, module.params["name"])

    if current is None:
        module.exit_json(changed=False, message="Secret already absent")

    secret = current
    diff = diff_result(module, select_fields(current, DIFF_FIELDS), {})
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Secret would be removed",
            secret=secret,
            **diff,
        )

    result = delete_result(client, path, ok_statuses=[404])
    if result is None:
        result = {}
    elif not isinstance(result, dict) or not valid_version(result.get("version")):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while removing secret "
                f"'{module.params['name']}' from app '{module.params['app_name']}'"
            )
        )

    values = {"changed": True, "message": "Secret removed", "secret": secret, **diff}
    if result.get("version") is not None:
        values["version"] = result["version"]

    module.exit_json(**values)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
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

    require_nonempty(module, "app_name", "name")

    with flyio_client(module) as client:
        if module.params["state"] == "present":
            ensure_present(module, client)
        else:
            ensure_absent(module, client)


if __name__ == "__main__":
    main()
