# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines
short_description: Manage fly.io machines
description:
  - Create, update, start, stop, and destroy fly.io machines.
  - Machines are the compute units that run container images on fly.io.
  - Use O(id) or O(name) to identify an existing machine.
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
  id:
    type: str
    description:
      - Machine identifier.
      - Mutually exclusive with O(name).
      - Either O(id) or O(name) is required.
  name:
    type: str
    description:
      - Machine name.
      - Mutually exclusive with O(id).
      - Either O(id) or O(name) is required.
  region:
    type: str
    description:
      - Region code.
      - Cannot be changed on an existing machine.
  image:
    type: str
    description:
      - Container image reference.
      - Required when O(state=present).
  init:
    type: dict
    description:
      - Container init configuration passed to the fly.io API.
    suboptions:
      cmd:
        type: list
        elements: str
        description:
          - Command to run.
      entrypoint:
        type: list
        elements: str
        description:
          - Entrypoint for the container.
      exec:
        type: list
        elements: str
        description:
          - Exec command.
      tty:
        type: bool
        description:
          - Allocate a pseudo-TTY.
  guest:
    type: dict
    description:
      - Guest VM configuration passed to the fly.io API.
  services:
    type: list
    elements: dict
    description:
      - Service port mappings passed to the fly.io API.
  checks:
    type: dict
    description:
      - Health checks passed to the fly.io API.
      - Each key is a check name and its value is a dict with C(type)
        (C(http) or C(tcp)), C(port), and optionally C(interval),
        C(timeout), C(grace_period), C(method), C(path), and C(headers).
  env:
    type: dict
    description:
      - Environment variables.
  files:
    type: list
    elements: dict
    description:
      - Files injected into the rootfs overlay at launch.
      - Each entry requires O(files[].guest_path) and one of O(files[].raw_value)
        or O(files[].secret_name).
    suboptions:
      guest_path:
        type: str
        required: true
        description:
          - Absolute path inside the machine where the file is placed.
      raw_value:
        type: str
        description:
          - Base64-encoded file content.
          - Mutually exclusive with O(files[].secret_name).
      secret_name:
        type: str
        description:
          - Name of a fly.io secret whose value populates the file.
          - Mutually exclusive with O(files[].raw_value).
  mounts:
    type: list
    elements: dict
    description:
      - Volume mounts passed to the fly.io API.
  auto_destroy:
    type: bool
    description:
      - Automatically destroy the machine when it exits.
      - Defaults to C(false) on the fly.io API when not specified.
  restart:
    type: dict
    description:
      - Restart policy for the machine passed to the fly.io API.
    suboptions:
      policy:
        type: str
        choices:
          - "no"
          - always
          - on-failure
        description:
          - Restart policy name.
      max_retries:
        type: int
        description:
          - Maximum restart attempts (only for C(on-failure) policy).
  metadata:
    type: dict
    description:
      - Metadata key-value pairs attached to the machine.
  statics:
    type: list
    elements: dict
    description:
      - Static files served by the Fly proxy passed to the fly.io API.
  wait:
    type: bool
    default: true
    description:
      - Wait for the machine to reach the target state.
  wait_timeout:
    type: int
    default: 60
    description:
      - Timeout in seconds when waiting for machine state.
      - Must be greater than zero when O(wait=true).
  state:
    type: str
    choices:
      - present
      - absent
      - started
      - stopped
    default: present
    description:
      - Desired state of the resource.
      - C(present) creates or updates the machine.
      - C(started) ensures the machine is running.
      - C(stopped) ensures the machine is stopped.
      - C(absent) destroys the machine.
requirements:
  - python >= 3.9

"""

EXAMPLES = r"""
- name: Deploy a container
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    guest:
      cpu_kind: shared
      cpus: 1
      memory_mb: 256
    services:
      - internal_port: 8080
        protocol: tcp
        ports:
          - port: 443
            handlers:
              - tls
              - http
    state: present

- name: Deploy with health checks
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    checks:
      httpcheck:
        type: http
        port: 8080
        path: /healthz
        interval: 10000
        timeout: 2000
    state: present

- name: Deploy with a volume mount
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: worker
    region: ord
    image: registry.fly.io/my-app:latest
    mounts:
      - volume: vol_abc123
        path: /data
    state: present

- name: Deploy with a custom entrypoint
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: worker
    region: ord
    image: registry.fly.io/my-app:latest
    init:
      entrypoint:
        - /bin/sh
      cmd:
        - -c
        - "exec my-worker"
    state: present

- name: Deploy with injected files
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    files:
      - guest_path: /etc/myapp/config.conf
        raw_value: "{{ lookup('file', 'config.conf') | b64encode }}"
    state: present

- name: Stop a machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: stopped

- name: Destroy a machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: absent
"""

RETURN = r"""
---
machine:
  description: fly.io machine.
  returned: when available
  type: dict
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.dict_transformations import dict_merge
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_request,
    delete_result,
    flyio_client,
    get_resource,
    list_all,
    post_result,
    require_positive,
    values_differ,
    wait_for_machine,
    wait_for_machine_settled,
)

CONFIG_FIELDS = (
    "auto_destroy",
    "checks",
    "env",
    "files",
    "guest",
    "image",
    "init",
    "metadata",
    "mounts",
    "restart",
    "services",
    "statics",
)
PURGE_CONFIG_FIELDS = ("checks", "env", "metadata")
LIST_ITEM_KEYS = (
    "guest_path",
    "internal_port",
    "port",
    "volume",
    "name",
    "path",
    "protocol",
)
TRANSITION_TARGETS = {
    "starting": "started",
    "restarting": "started",
    "stopping": "stopped",
    "suspending": "suspended",
    "destroying": "destroyed",
    "launch_failed": "destroyed",
}
AMBIGUOUS_TRANSITIONS = {"creating", "updating", "replacing"}
TRANSITIONAL_STATES = set(TRANSITION_TARGETS) | AMBIGUOUS_TRANSITIONS
TERMINAL_STATES = {"destroyed", "replaced", "migrated"}


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def find_machine(client, app_name, name=None, machine_id=None, missing_ok=False):
    if machine_id is not None:
        return get_resource(
            client,
            f"/apps/{app_name}/machines/{machine_id}",
            ok_statuses=[404],
            required_field="id",
            expected_value=machine_id,
            required_fields=("state",),
        )

    machines = list_all(
        client,
        f"/apps/{app_name}/machines",
        ok_statuses=[404] if missing_ok else None,
        required_field="id",
        required_fields=("name", "state"),
    )

    for machine in machines:
        if machine.get("name") == name:
            return machine

    return None


def build_config(params):
    config = {"image": params["image"]}

    for field in CONFIG_FIELDS:
        if field == "image":
            continue
        value = params.get(field)
        if value is not None:
            config[field] = value

    return clean(config)


def find_list_item(values, value):
    if not isinstance(value, dict):
        return None

    keys = [key for key in LIST_ITEM_KEYS if key in value]
    matches = [
        item
        for item in values
        if isinstance(item, dict)
        and keys
        and all(item.get(key) == value[key] for key in keys)
    ]
    return matches[0] if len(matches) == 1 else None


def has_list_identity(value):
    return isinstance(value, dict) and any(key in value for key in LIST_ITEM_KEYS)


def match_list_items(current, desired):
    remaining = list(current)
    for value in desired:
        match = find_list_item(remaining, value)
        if match is not None:
            remaining.remove(match)
        yield match, value


def config_values_differ(current, desired, purge=False):
    if (
        isinstance(current, list)
        and isinstance(desired, list)
        and all(has_list_identity(value) for value in desired)
    ):
        if len(current) != len(desired):
            return True
        for match, value in match_list_items(current, desired):
            if match is None or config_values_differ(match, value):
                return True
        return False

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return values_differ(current, desired)

    if purge and current.keys() != desired.keys():
        return True

    return any(
        key not in current or config_values_differ(current[key], value)
        for key, value in desired.items()
    )


def merge_values(current, desired):
    if isinstance(current, list) and isinstance(desired, list):
        if len(current) == len(desired) and not all(
            has_list_identity(value) for value in desired
        ):
            return [merge_values(cur, value) for cur, value in zip(current, desired)]
        return [
            merge_values(match, value) if match is not None else value
            for match, value in match_list_items(current, desired)
        ]

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return desired

    result = dict_merge(current, desired)
    for key, value in desired.items():
        if key in current:
            result[key] = merge_values(current[key], value)

    return result


def merge_config(current, desired):
    config = merge_values(current, desired)
    for field in PURGE_CONFIG_FIELDS:
        if field not in desired:
            continue

        if field == "checks":
            checks = current.get("checks")
            if not isinstance(checks, dict):
                checks = {}
            config[field] = {
                name: merge_values(checks.get(name, {}), value)
                for name, value in desired[field].items()
            }
        else:
            config[field] = desired[field]

    return config


def match_mounts(current, desired):
    remaining = list(current.get("mounts", []))
    for mount in desired.get("mounts", []):
        identifiers = {mount.get(key) for key in ("volume", "name") if mount.get(key)}
        match = next(
            (
                item
                for item in remaining
                if identifiers
                <= {item.get(key) for key in ("volume", "name") if item.get(key)}
            ),
            None,
        )
        if match is not None:
            remaining.remove(match)
        yield match, mount


def mounts_differ(current, desired):
    current_mounts = current.get("mounts", [])
    if not isinstance(current_mounts, list) or not all(
        isinstance(mount, dict) for mount in current_mounts
    ):
        return True
    if len(current_mounts) != len(desired.get("mounts", [])):
        return True
    return any(match is None for match, mount in match_mounts(current, desired))


def mount_values_differ(current, desired):
    for match, mount in match_mounts(current, desired):
        values = {
            key: value for key, value in mount.items() if key not in ("volume", "name")
        }
        if match is None or config_values_differ(match, values):
            return True
    return False


def settle_machine(module, client, current, desired_state):
    state = current.get("state")
    if state in TERMINAL_STATES:
        module.fail_json(msg=f"Machine is in terminal state '{state}'", machine=current)

    target = TRANSITION_TARGETS.get(state)
    if target is None:
        if state in AMBIGUOUS_TRANSITIONS:
            if not module.params["wait"]:
                module.fail_json(
                    msg=f"Machine is currently {state}; enable wait or retry",
                    machine=current,
                )
            current = wait_for_machine_settled(
                client,
                module.params["app_name"],
                current["id"],
                TRANSITIONAL_STATES,
                module.params["wait_timeout"],
            )
        else:
            return current
    elif not module.params["wait"]:
        if target == desired_state:
            module.exit_json(
                changed=False,
                message=f"Machine already transitioning to {desired_state}",
                machine=current,
            )
        module.fail_json(
            msg=f"Machine is currently {state}; enable wait or retry",
            machine=current,
        )
    else:
        wait_for_machine(
            client,
            module.params["app_name"],
            current["id"],
            target,
            module.params["wait_timeout"],
            instance_id=(current.get("instance_id") if target != "destroyed" else None),
        )
        current = get_resource(
            client,
            f"/apps/{module.params['app_name']}/machines/{current['id']}",
            ok_statuses=[404],
            required_field="id",
            expected_value=current["id"],
            required_fields=("state",),
        )
    if current is None or current.get("state") in TERMINAL_STATES:
        module.fail_json(msg="Machine is no longer available", machine=current)
    if current.get("state") in TRANSITIONAL_STATES:
        module.fail_json(msg="Machine transition timed out", machine=current)
    return current


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    desired_config = build_config(params)

    if current is not None:
        current = settle_machine(module, client, current, "present")
        current_config = current.get("config")
        if not isinstance(current_config, dict):
            module.fail_json(
                msg="fly.io API returned a malformed machine configuration",
                machine=current,
            )
        current_region = current.get("region")
        if (
            params.get("region") is not None
            and current_region is not None
            and params["region"] != current_region
        ):
            module.fail_json(msg="region cannot be changed for an existing machine")
        if "mounts" in desired_config and mounts_differ(current_config, desired_config):
            module.fail_json(
                msg="attached volume cannot be changed for an existing machine"
            )

        changed = current_config.get("image") != desired_config["image"]
        for field, value in desired_config.items():
            if field == "mounts":
                differs = mount_values_differ(current_config, desired_config)
            else:
                differs = field != "image" and config_values_differ(
                    current_config.get(field),
                    value,
                    purge=field in PURGE_CONFIG_FIELDS,
                )
            if differs:
                changed = True
                break

        if not changed:
            module.exit_json(
                changed=False, message="Machine already present", machine=current
            )

        if module.check_mode:
            module.exit_json(
                changed=True,
                message="Machine would be updated",
                machine=current,
            )

        config = merge_config(current_config, desired_config)

        body = {"config": config}
        if current.get("instance_id") is not None:
            body["current_version"] = current["instance_id"]
        if current.get("state") in ("created", "failed", "stopped", "suspended"):
            body["skip_launch"] = True

        result = post_result(
            client,
            "/apps/{}/machines/{}".format(app_name, current["id"]),
            body,
        )

        if (
            not isinstance(result, dict)
            or not isinstance(result.get("id"), str)
            or not result["id"]
            or result["id"] != current["id"]
        ):
            module.fail_json(
                msg="fly.io API returned an empty or malformed response during update",
                machine=result,
            )

        if params["wait"] and not body.get("skip_launch"):
            wait_for_machine(
                client,
                app_name,
                result["id"],
                "started",
                params["wait_timeout"],
                instance_id=result.get("instance_id"),
            )
            result = get_resource(
                client,
                f"/apps/{app_name}/machines/{result['id']}",
                required_field="id",
                expected_value=result["id"],
            )

        module.exit_json(changed=True, message="Machine updated", machine=result)

    if params.get("id") is not None:
        module.fail_json(msg="Machine '{}' not found".format(params["id"]))

    if module.check_mode:
        module.exit_json(changed=True, message="Machine would be created")

    body = {"config": desired_config}
    if params.get("name") is not None:
        body["name"] = params["name"]
    if params.get("region") is not None:
        body["region"] = params["region"]

    result = post_result(client, f"/apps/{app_name}/machines", body)

    if (
        not isinstance(result, dict)
        or not isinstance(result.get("id"), str)
        or not result["id"]
    ):
        module.fail_json(
            msg="fly.io API returned an empty or malformed response during create",
            machine=result,
        )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            result["id"],
            "started",
            params["wait_timeout"],
            instance_id=result.get("instance_id"),
        )
        result = get_resource(
            client,
            f"/apps/{app_name}/machines/{result['id']}",
            required_field="id",
            expected_value=result["id"],
        )

    module.exit_json(changed=True, message="Machine created", machine=result)


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
        missing_ok=True,
    )

    if current is None:
        module.exit_json(changed=False, message="Machine already absent")

    if current.get("state") == "destroyed":
        module.exit_json(changed=False, message="Machine already absent")

    if current.get("state") == "destroying":
        if params["wait"]:
            wait_for_machine(
                client, app_name, current["id"], "destroyed", params["wait_timeout"]
            )
            current = get_resource(
                client,
                "/apps/{}/machines/{}".format(app_name, current["id"]),
                ok_statuses=[404],
                required_field="id",
                expected_value=current["id"],
            )
        module.exit_json(
            changed=False, message="Machine already being destroyed", machine=current
        )

    if module.check_mode:
        module.exit_json(
            changed=True, message="Machine would be destroyed", machine=current
        )

    delete_result(
        client,
        "/apps/{}/machines/{}?force=true".format(app_name, current["id"]),
        ok_statuses=[404],
    )

    if params["wait"]:
        wait_for_machine(
            client, app_name, current["id"], "destroyed", params["wait_timeout"]
        )
        current = get_resource(
            client,
            "/apps/{}/machines/{}".format(app_name, current["id"]),
            ok_statuses=[404],
            required_field="id",
            expected_value=current["id"],
        )

    module.exit_json(changed=True, message="Machine destroyed", machine=current)


def ensure_started(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    if current is None:
        module.fail_json(msg="Machine not found")

    current = settle_machine(module, client, current, "started")

    if current.get("state") == "started":
        module.exit_json(
            changed=False, message="Machine already started", machine=current
        )

    if module.check_mode:
        module.exit_json(
            changed=True, message="Machine would be started", machine=current
        )

    api_request(
        client,
        "post",
        "/apps/{}/machines/{}/start".format(app_name, current["id"]),
    )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            current["id"],
            "started",
            params["wait_timeout"],
            instance_id=current.get("instance_id"),
        )

    current = get_resource(
        client,
        "/apps/{}/machines/{}".format(app_name, current["id"]),
        required_field="id",
        expected_value=current["id"],
    )

    module.exit_json(changed=True, message="Machine started", machine=current)


def ensure_stopped(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    if current is None:
        module.fail_json(msg="Machine not found")

    current = settle_machine(module, client, current, "stopped")

    if current.get("state") == "created":
        module.exit_json(
            changed=False, message="Machine has not been started", machine=current
        )

    if current.get("state") == "stopped":
        module.exit_json(
            changed=False, message="Machine already stopped", machine=current
        )

    if module.check_mode:
        module.exit_json(
            changed=True, message="Machine would be stopped", machine=current
        )

    api_request(
        client,
        "post",
        "/apps/{}/machines/{}/stop".format(app_name, current["id"]),
    )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            current["id"],
            "stopped",
            params["wait_timeout"],
            instance_id=current.get("instance_id"),
        )

    current = get_resource(
        client,
        "/apps/{}/machines/{}".format(app_name, current["id"]),
        required_field="id",
        expected_value=current["id"],
    )

    module.exit_json(changed=True, message="Machine stopped", machine=current)


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
            "name": {"type": "str"},
            "region": {"type": "str"},
            "image": {"type": "str"},
            "init": {
                "type": "dict",
                "options": {
                    "cmd": {"type": "list", "elements": "str"},
                    "entrypoint": {"type": "list", "elements": "str"},
                    "exec": {"type": "list", "elements": "str"},
                    "tty": {"type": "bool"},
                },
            },
            "guest": {"type": "dict"},
            "services": {"type": "list", "elements": "dict"},
            "checks": {"type": "dict"},
            "env": {"type": "dict", "no_log": True},
            "files": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "guest_path": {"type": "str", "required": True},
                    "raw_value": {"type": "str", "no_log": True},
                    "secret_name": {"type": "str"},
                },
                "mutually_exclusive": [("raw_value", "secret_name")],
                "required_one_of": [("raw_value", "secret_name")],
            },
            "mounts": {"type": "list", "elements": "dict"},
            "auto_destroy": {"type": "bool"},
            "restart": {
                "type": "dict",
                "options": {
                    "policy": {
                        "type": "str",
                        "choices": ["no", "always", "on-failure"],
                    },
                    "max_retries": {"type": "int"},
                },
            },
            "metadata": {"type": "dict"},
            "statics": {"type": "list", "elements": "dict"},
            "wait": {"type": "bool", "default": True},
            "wait_timeout": {"type": "int", "default": 60},
            "state": {
                "type": "str",
                "choices": ["present", "absent", "started", "stopped"],
                "default": "present",
            },
        },
        mutually_exclusive=[
            ("id", "name"),
        ],
        required_one_of=[
            ("id", "name"),
        ],
        required_if=[
            ("state", "present", ("image",)),
        ],
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        state = module.params["state"]
        if state == "present":
            ensure_present(module, client)
        elif state == "absent":
            ensure_absent(module, client)
        elif state == "started":
            ensure_started(module, client)
        else:
            ensure_stopped(module, client)


if __name__ == "__main__":
    main()
