# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines
short_description: Manage Fly.io machines
description:
  - Create, update, start, stop, and destroy Fly.io machines.
  - Machines are the compute units that run container images on Fly.io.
  - Use O(id) or O(name) to identify an existing machine.
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
  image:
    type: str
    description:
      - Container image reference.
      - Required when O(state=present).
  guest:
    type: dict
    description:
      - Guest VM configuration.
    suboptions:
      cpu_kind:
        type: str
        choices:
          - shared
          - performance
        default: shared
        description:
          - CPU type.
      cpus:
        type: int
        default: 1
        description:
          - Number of CPUs.
      memory_mb:
        type: int
        default: 256
        description:
          - Memory in megabytes.
  services:
    type: list
    elements: dict
    description:
      - Service port mappings.
    suboptions:
      internal_port:
        type: int
        required: true
        description:
          - Port inside the container.
      protocol:
        type: str
        choices:
          - tcp
          - udp
        default: tcp
        description:
          - Network protocol.
      ports:
        type: list
        elements: dict
        required: true
        description:
          - External port mappings.
        suboptions:
          port:
            type: int
            required: true
            description:
              - External port number.
          handlers:
            type: list
            elements: str
            description:
              - Connection handlers.
  env:
    type: dict
    description:
      - Environment variables.
  mounts:
    type: list
    elements: dict
    description:
      - Volume mounts.
    suboptions:
      volume:
        type: str
        required: true
        description:
          - Volume identifier.
      path:
        type: str
        required: true
        description:
          - Mount path inside the container.
  auto_destroy:
    type: bool
    default: false
    description:
      - Automatically destroy the machine when it exits.
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
  description: Fly.io machine.
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
    select_fields,
    values_differ,
    wait_for_machine,
)


def find_machine(client, app_name, name=None, machine_id=None):
    if machine_id is not None:
        return get_result(
            client,
            "/apps/{}/machines/{}".format(app_name, machine_id),
            ok_statuses=[404],
        )

    machines = list_all(client, "/apps/{}/machines".format(app_name))

    for machine in machines:
        if machine.get("name") == name:
            return machine

    return None


def build_config(params):
    config = {
        "image": params["image"],
    }

    if params.get("guest") is not None:
        config["guest"] = params["guest"]

    if params.get("services") is not None:
        config["services"] = params["services"]

    if params.get("env") is not None:
        config["env"] = params["env"]

    if params.get("mounts") is not None:
        config["mounts"] = params["mounts"]

    if params.get("auto_destroy") is not None:
        config["auto_destroy"] = params["auto_destroy"]

    return config


def ensure_present(module, client):
    params = module.params
    app_name = params["app_name"]

    current = find_machine(
        client,
        app_name,
        name=params.get("name"),
        machine_id=params.get("id"),
    )

    config = build_config(params)

    if current is not None:
        current_config = current.get("config", {})
        desired_fields = select_fields(current_config, config.keys())

        if not values_differ(desired_fields, config):
            module.exit_json(
                changed=False, message="Machine already present", machine=current
            )

        if module.check_mode:
            module.exit_json(
                changed=True,
                message="Machine would be updated",
                machine=current,
            )

        body = {"config": config}
        if params.get("region") is not None:
            body["region"] = params["region"]

        current = post_result(
            client,
            "/apps/{}/machines/{}".format(app_name, current["id"]),
            body,
        )

        if params["wait"]:
            wait_for_machine(
                client, app_name, current["id"], "started", params["wait_timeout"]
            )

        module.exit_json(changed=True, message="Machine updated", machine=current)

    if module.check_mode:
        module.exit_json(changed=True, message="Machine would be created")

    body = {"config": config}
    if params.get("name") is not None:
        body["name"] = params["name"]
    if params.get("region") is not None:
        body["region"] = params["region"]

    current = post_result(
        client, "/apps/{}/machines".format(app_name), body
    )

    if params["wait"]:
        wait_for_machine(
            client, app_name, current["id"], "started", params["wait_timeout"]
        )

    module.exit_json(changed=True, message="Machine created", machine=current)


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
    if machine_state == "started":
        api_request(
            client,
            "post",
            "/apps/{}/machines/{}/stop".format(app_name, current["id"]),
        )
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

    current = get_result(
        client, "/apps/{}/machines/{}".format(app_name, current["id"])
    )

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

    current = get_result(
        client, "/apps/{}/machines/{}".format(app_name, current["id"])
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
            "guest": {"type": "dict"},
            "services": {"type": "list", "elements": "dict"},
            "env": {"type": "dict"},
            "mounts": {"type": "list", "elements": "dict"},
            "auto_destroy": {"type": "bool", "default": False},
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
