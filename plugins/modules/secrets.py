# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: secrets
short_description: Manage fly.io app secrets
description:
  - Set and remove encrypted fly.io app secrets.
  - Secret values are write-only and are never returned by the module.
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
      - fly.io does not expose stored values, so the value is submitted on every run and
        the returned digest determines whether it changed.
  state:
    type: str
    choices:
      - present
      - absent
    default: present
    description:
      - Desired state of the secret.
notes:
  - In check mode, an existing secret is reported as changed because its write-only value
    cannot be compared without submitting it.
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
    get_result,
    post_result,
    select_fields,
)

SECRET_FIELDS = ("name", "digest", "created_at", "updated_at")


def secret_path(app_name, name):
    return f"/apps/{quote(app_name, safe='')}/secrets/{quote(name, safe='')}"


def ensure_present(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_result(client, path, ok_statuses=[404])

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Secret would be set",
            secret=select_fields(current, SECRET_FIELDS),
        )

    result = post_result(client, path, {"value": module.params["value"]}) or {}
    secret = select_fields(result, SECRET_FIELDS)
    changed = current is None or current.get("digest") != secret.get("digest")

    module.exit_json(
        changed=changed,
        message="Secret set" if changed else "Secret value unchanged",
        secret=secret,
        version=result.get("version"),
    )


def ensure_absent(module, client):
    path = secret_path(module.params["app_name"], module.params["name"])
    current = get_result(client, path, ok_statuses=[404])

    if current is None:
        module.exit_json(changed=False, message="Secret already absent")

    secret = select_fields(current, SECRET_FIELDS)
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Secret would be removed",
            secret=secret,
        )

    result = delete_result(client, path) or {}
    module.exit_json(
        changed=True,
        message="Secret removed",
        secret=secret,
        version=result.get("version"),
    )


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
