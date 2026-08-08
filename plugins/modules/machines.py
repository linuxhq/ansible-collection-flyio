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
  name:
    type: str
    description:
      - Machine name.
      - Mutually exclusive with O(id).
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
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_request,
    delete_result,
    flyio_client,
    get_result,
    list_all,
    post_result,
    values_differ,
    wait_for_machine,
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


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def find_machine(client, app_name, name=None, machine_id=None):
    if machine_id is not None:
        return get_result(
            client,
            f"/apps/{app_name}/machines/{machine_id}",
            ok_statuses=[404],
        )

    machines = list_all(client, f"/apps/{app_name}/machines")

    for machine in machines:
        if machine.get("name") == name:
            return get_result(
                client,
                "/apps/{}/machines/{}".format(app_name, machine["id"]),
            )

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


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    desired_config = build_config(params)

    if current is not None:
        current_config = current.get("config", {})
        current_region = current.get("region")
        if (
            params.get("region") is not None
            and current_region is not None
            and params["region"] != current_region
        ):
            module.fail_json(msg="region cannot be changed for an existing machine")

        changed = current_config.get("image") != desired_config["image"]
        for field, value in desired_config.items():
            if field != "image" and values_differ(
                current_config.get(field), value, purge=isinstance(value, dict)
            ):
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

        config = dict(current_config)
        config.update(desired_config)

        body = {"config": config}
        if current_region is not None or params.get("region") is not None:
            body["region"] = current_region or params["region"]

        result = post_result(
            client,
            "/apps/{}/machines/{}".format(app_name, current["id"]),
            body,
        )

        if result is None:
            module.fail_json(msg="fly.io API returned an empty response during update")

        if params["wait"]:
            wait_for_machine(
                client, app_name, result["id"], "started", params["wait_timeout"]
            )

        module.exit_json(changed=True, message="Machine updated", machine=result)

    if module.check_mode:
        module.exit_json(changed=True, message="Machine would be created")

    body = {"config": desired_config}
    if params.get("name") is not None:
        body["name"] = params["name"]
    if params.get("region") is not None:
        body["region"] = params["region"]

    result = post_result(client, f"/apps/{app_name}/machines", body)

    if result is None:
        module.fail_json(msg="fly.io API returned an empty response during create")

    if params["wait"]:
        wait_for_machine(
            client, app_name, result["id"], "started", params["wait_timeout"]
        )

    module.exit_json(changed=True, message="Machine created", machine=result)


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    if current is None:
        module.exit_json(changed=False, message="Machine already absent")

    if module.check_mode:
        module.exit_json(
            changed=True, message="Machine would be destroyed", machine=current
        )

    machine_state = current.get("state", "")
    if machine_state == "destroyed":
        module.exit_json(changed=False, message="Machine already absent")

    if machine_state in ("started", "starting", "created", "replacing"):
        api_request(
            client,
            "post",
            "/apps/{}/machines/{}/stop".format(app_name, current["id"]),
        )

        if params["wait"]:
            wait_for_machine(
                client, app_name, current["id"], "stopped", params["wait_timeout"]
            )

    delete_result(
        client, "/apps/{}/machines/{}?force=true".format(app_name, current["id"])
    )

    module.exit_json(changed=True, message="Machine destroyed", machine=current)


def ensure_started(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    if current is None:
        module.fail_json(msg="Machine not found")

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
            client, app_name, current["id"], "started", params["wait_timeout"]
        )

    current = get_result(client, "/apps/{}/machines/{}".format(app_name, current["id"]))

    module.exit_json(changed=True, message="Machine started", machine=current)


def ensure_stopped(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    if current is None:
        module.fail_json(msg="Machine not found")

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
            client, app_name, current["id"], "stopped", params["wait_timeout"]
        )

    current = get_result(client, "/apps/{}/machines/{}".format(app_name, current["id"]))

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
