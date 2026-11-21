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
  - The Machine must be running. Fly.io rejects the command when the Machine
    is in any state other than C(started).
  - The task fails when the command exits with a non-zero status or is
    terminated by a signal.
  - The task fails and reports a change when the command ran but Fly.io
    could not return its output because the output exceeded the maximum
    response size.
  - The task fails and reports a change when Fly.io reports that the command
    exceeded O(timeout), or when the response to the request is lost, because
    the command may have run.
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
      - Sent only when specified.
      - Not treated as sensitive. Use task-level C(no_log) when passing
        sensitive input.
  timeout:
    default: 30
    type: int
    description:
      - Command timeout in seconds.
      - Must be greater than zero.
      - When the command exceeds the timeout, the task fails and reports a
        change because the command may have run.
      - Fly.io accepts at most C(600).
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
    MACHINE_TERMINAL_STATES,
    FlyioApiError,
    api_error_result,
    api_token_option,
    flyio_client,
    flyio_path,
    get_machine,
    post_result,
    require_nonempty,
    require_positive,
)


def exec_command(module, client):
    require_positive(module, "timeout")
    app_name = module.params["app_name"]
    machine_id = module.params["id"]
    if module.check_mode:
        # Predict the real run's failure for a missing app or Machine instead of a change.
        machine = get_machine(client, app_name, machine_id)
        if machine is None or machine["state"] in MACHINE_TERMINAL_STATES:
            module.fail_json(msg=f"Machine '{machine_id}' not found in app '{app_name}'")

        # Fly.io rejects exec with HTTP 412 unless the Machine is running.
        if machine["state"] != "started":
            module.fail_json(
                msg=f"Machine '{machine_id}' in app '{app_name}' is not running (state '{machine['state']}')",
                machine=machine,
            )

        module.exit_json(changed=True)

    body = {
        "command": ["/bin/sh", "-c", module.params["command"]],
        "timeout": module.params["timeout"],
    }
    for option in ("container", "stdin"):
        if module.params[option] is not None:
            body[option] = module.params[option]

    try:
        result = post_result(
            client,
            flyio_path("apps", app_name, "machines", machine_id, "exec"),
            body,
            timeout=module.params["timeout"] + 10,
        )
    except FlyioApiError as exc:
        response = exc.response_body
        if exc.status_code == 408:
            # Fly.io started the command before the timeout expired.
            module.fail_json(
                msg=(
                    f"Executing a command on Machine '{machine_id}' for app '{app_name}' timed out; "
                    "the command may have run"
                ),
                changed=True,
                **api_error_result(exc),
            )

        if exc.write_sent:
            module.fail_json(
                msg=(
                    f"Executing a command on Machine '{machine_id}' for app '{app_name}' lost its response "
                    f"({exc}); the command may have run"
                ),
                changed=True,
                **api_error_result(exc),
            )

        if (
            exc.status_code != 413
            or not isinstance(response, dict)
            or response.get("status") != "exec_output_too_large"
        ):
            raise

        # Fly.io ran the command but could not return its output.
        module.fail_json(
            msg=(
                f"Executing a command on Machine '{machine_id}' for app '{app_name}' ran the command, "
                "but Fly.io could not return output that exceeded its maximum response size"
            ),
            changed=True,
            **api_error_result(exc),
        )

    if not isinstance(result, dict):
        module.fail_json(
            msg=(
                "Fly.io API returned malformed data while executing a command on "
                f"Machine '{machine_id}' for app '{app_name}'"
            ),
            changed=True,
            response=result,
        )

    # Return the response as reported. The API marks no field as required, so the documented
    # fields default when absent; a missing exit code means success.
    values = {"exit_code": 0, "exit_signal": 0, "stderr": "", "stdout": "", **result, "changed": True}

    if values["exit_code"] != 0 or values["exit_signal"] != 0:
        module.fail_json(
            msg=f"Command failed on Machine '{machine_id}' for app '{app_name}'",
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
            "stdin": {"type": "str"},
            "timeout": {"default": 30, "type": "int"},
        },
        supports_check_mode=True,
    )

    require_nonempty(module, "app_name", "id", "container")

    with flyio_client(module) as client:
        exec_command(module, client)


if __name__ == "__main__":
    main()
