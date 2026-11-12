#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines_exec
short_description: Execute a command on a Fly.io Machine
description:
  - Execute a command on a Fly.io Machine.
  - Command execution is inherently non-idempotent and reports a change when run.
  - The task fails when the command exits with a non-zero status or is
    terminated by a signal.
  - Results include every field of the Fly.io exec response as Fly.io
    reports it. The documented fields default to C(0) or an empty string
    when Fly.io omits them.
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
  command:
    required: true
    type: str
    description:
      - Command to execute.
      - Commands run through C(/bin/sh -c).
      - Must not be empty.
  container:
    type: str
    description:
      - Container in which to execute the command.
      - Must not be empty when specified.
  id:
    required: true
    type: str
    description:
      - Machine identifier.
  stdin:
    type: str
    description:
      - Data supplied to the command on standard input.
      - Treated as sensitive and masked in module output.
  timeout:
    default: 30
    type: int
    description:
      - Command timeout in seconds.
      - Must be between C(1) and C(600).
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
- name: Check service readiness
  linuxhq.flyio.machines_exec:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    command: wget -qO- http://localhost:8080/ready
    id: d5683606c77187
  changed_when: false
"""

RETURN = r"""
---
exit_code:
  description: Command exit code. A non-zero exit code fails the task.
  returned: except in check mode
  type: int
stderr:
  description: Command standard error.
  returned: except in check mode
  type: str
exit_signal:
  description: Signal that terminated the command, or C(0) if it exited normally.
  returned: except in check mode
  type: int
stdout:
  description: Command standard output.
  returned: except in check mode
  type: str

"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_token_option,
    flyio_client,
    flyio_path,
    get_resource,
    post_result,
    require_nonempty,
    require_positive,
)

# Machines in these states are gone and cannot run commands.
TERMINAL_STATES = {"destroyed", "replaced", "migrated"}


def exec_command(module, client):
    require_positive(module, "timeout")
    if module.params["timeout"] > 600:
        module.fail_json(msg="timeout must not exceed 600")

    app_name = module.params["app_name"]
    machine_id = module.params["id"]
    if module.check_mode:
        # Predict the real run's failure for a missing app or Machine instead of a change.
        machine = get_resource(
            client,
            flyio_path("apps", app_name, "machines", machine_id),
            ok_statuses=[404],
            required_fields=("id",),
            expected={"id": machine_id},
        )
        if machine is None or machine.get("state") in TERMINAL_STATES:
            module.fail_json(msg=f"Machine '{machine_id}' not found in app '{app_name}'")

        module.exit_json(changed=True)

    body = {
        "command": ["/bin/sh", "-c", module.params["command"]],
        "timeout": module.params["timeout"],
    }
    for option in ("container", "stdin"):
        if module.params[option] is not None:
            body[option] = module.params[option]

    result = post_result(
        client,
        flyio_path("apps", module.params["app_name"], "machines", module.params["id"], "exec"),
        body,
        timeout=module.params["timeout"] + 10,
    )
    if (
        not isinstance(result, dict)
        or not all(
            isinstance(result.get(field, 0), int) and not isinstance(result.get(field), bool)
            for field in ("exit_code", "exit_signal")
        )
        or not all(isinstance(result.get(field, ""), str) for field in ("stderr", "stdout"))
    ):
        module.fail_json(
            msg=(
                "Fly.io API returned malformed data while executing a command on "
                f"Machine '{module.params['id']}' for app '{module.params['app_name']}'"
            ),
            response=result,
        )

    # Return the response as reported. The API marks no field as required, so the documented
    # fields default when absent; a missing exit code means success.
    values = {"exit_code": 0, "exit_signal": 0, "stderr": "", "stdout": "", **result, "changed": True}

    if values["exit_code"] != 0 or values["exit_signal"] != 0:
        module.fail_json(
            msg=f"Command failed on Machine '{module.params['id']}' for app '{module.params['app_name']}'",
            **values,
        )

    module.exit_json(**values)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": api_token_option(),
            "app_name": {"required": True, "type": "str"},
            "command": {"required": True, "type": "str"},
            "container": {"type": "str"},
            "id": {"required": True, "type": "str"},
            "stdin": {"type": "str", "no_log": True},
            "timeout": {"default": 30, "type": "int"},
        },
        supports_check_mode=True,
    )

    require_nonempty(module, "app_name", "id", "command", "container")

    with flyio_client(module) as client:
        exec_command(module, client)


if __name__ == "__main__":
    main()
