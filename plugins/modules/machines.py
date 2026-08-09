#!/usr/bin/python
# Copyright: Contributors to the Ansible project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines
short_description: Manage Fly.io Machines
description:
  - Create, update, start, stop, and destroy Fly.io Machines.
  - Machines are the compute units that run container images on Fly.io.
  - Use O(id) or O(name) to identify an existing Machine.
  - Machine configuration options are used only when O(state=present).
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
  id:
    type: str
    description:
      - Machine identifier.
      - Either O(id) or O(name) is required.
      - Mutually exclusive with O(name).
  name:
    type: str
    description:
      - Machine name.
      - Either O(id) or O(name) is required.
      - Mutually exclusive with O(id).
  region:
    type: str
    description:
      - Region code.
      - Cannot be changed on an existing Machine.
  image:
    type: str
    description:
      - Container image reference.
      - Required when O(state=present).
  init:
    type: dict
    description:
      - Container init configuration passed to the Fly.io API.
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
      - Guest VM configuration passed to the Fly.io API.
    suboptions:
      cpu_kind:
        type: str
        description:
          - CPU reservation type.
      gpu_kind:
        type: str
        description:
          - GPU reservation type.
      host_dedication_id:
        type: str
        description:
          - Host dedication identifier.
      cpus:
        type: int
        description:
          - Number of CPU cores.
          - Must be greater than zero.
      gpus:
        type: int
        description:
          - Number of GPU cores.
          - Must be greater than zero.
      memory_mb:
        type: int
        description:
          - Memory allocation in megabytes.
          - Must be a positive multiple of C(256).
      kernel_args:
        type: list
        elements: str
        description:
          - Kernel arguments.
      persist_rootfs:
        type: str
        choices:
          - never
          - restart
          - always
        description:
          - Root filesystem persistence policy.
  services:
    type: list
    elements: dict
    description:
      - Service port mappings passed to the Fly.io API.
      - Each service requires O(services[].internal_port).
      - O(services[].protocol) is required for new services.
    suboptions:
      protocol:
        type: str
        choices:
          - tcp
          - udp
        description:
          - Network protocol.
          - Required for a new service.
          - May be omitted when updating one uniquely matched existing service.
      internal_port:
        type: int
        required: true
        description:
          - Port on which the Machine listens.
          - Must be between C(1) and C(65535).
      autostart:
        type: bool
        description:
          - Whether Fly Proxy starts the Machine for incoming requests.
      autostop:
        type: raw
        description:
          - Idle Machine behavior.
          - Accepts C(off), C(stop), C(suspend), C(true), or C(false).
      min_machines_running:
        type: int
        description:
          - Minimum Machines to keep running in the primary region.
          - Must not be negative.
      concurrency:
        type: dict
        description:
          - Fly Proxy concurrency limits.
        suboptions:
          type:
            type: str
            choices:
              - connections
              - requests
            description:
              - Unit counted for load balancing.
          soft_limit:
            type: int
            description:
              - Preferred concurrency limit.
              - Must not be negative.
          hard_limit:
            type: int
            description:
              - Maximum concurrency limit.
              - Must not be negative.
              - Must be greater than or equal to O(services[].concurrency.soft_limit).
      ports:
        type: list
        elements: dict
        description:
          - Public ports and handlers.
        suboptions:
          port:
            type: int
            description:
              - Public port.
              - Either O(services[].ports[].port) or a complete port range is
                required.
              - Must be between C(1) and C(65535).
              - Mutually exclusive with O(services[].ports[].start_port) and
                O(services[].ports[].end_port).
          start_port:
            type: int
            description:
              - First public port in a range.
              - Required with O(services[].ports[].end_port).
              - Either O(services[].ports[].port) or a complete port range is
                required.
              - Must be between C(1) and C(65535).
              - Mutually exclusive with O(services[].ports[].port).
          end_port:
            type: int
            description:
              - Last public port in a range.
              - Required with O(services[].ports[].start_port).
              - Must be between C(1) and C(65535).
              - Must be greater than or equal to O(services[].ports[].start_port).
              - Mutually exclusive with O(services[].ports[].port).
          handlers:
            type: list
            elements: str
            description:
              - Fly Proxy protocol handlers.
          force_https:
            type: bool
            description:
              - Whether HTTP requests redirect to HTTPS.
          http_options:
            type: dict
            description:
              - HTTP handler options.
            suboptions:
              compress:
                type: bool
                description:
                  - Whether Fly Proxy compresses HTTP responses.
              h2_backend:
                type: bool
                description:
                  - Whether the backend supports HTTP/2 with prior knowledge.
              response:
                type: dict
                description:
                  - HTTP response options.
                suboptions:
                  headers:
                    type: dict
                    description:
                      - Response headers added by Fly Proxy.
                      - Header names must not be empty.
                      - Values may be strings, lists of strings, or C(false) to
                        remove a header.
                  pristine:
                    type: bool
                    description:
                      - Whether Fly Proxy preserves response headers unchanged.
          tls_options:
            type: dict
            description:
              - TLS handler options.
            suboptions:
              alpn:
                type: list
                elements: str
                description:
                  - ALPN protocols presented to TLS clients.
              default_self_signed:
                type: bool
                description:
                  - Whether to use a self-signed certificate as a fallback.
              versions:
                type: list
                elements: str
                description:
                  - Permitted TLS protocol versions.
          proxy_proto_options:
            type: dict
            description:
              - PROXY protocol options.
            suboptions:
              version:
                type: str
                description:
                  - PROXY protocol version accepted by the Machine.
  checks:
    type: dict
    description:
      - Health checks passed to the Fly.io API.
      - Each key is a check name and its value is a dictionary.
      - Check names must not be empty.
      - C(type) and C(port) are required when creating a Machine.
      - C(type) accepts C(http) or C(tcp).
      - Optional fields are C(interval), C(timeout), C(grace_period), C(method),
        C(path), C(protocol), C(tls_server_name), C(tls_skip_verify), and C(headers).
      - C(headers) is a list of dictionaries containing C(name) and C(values).
      - C(interval), C(timeout), and C(grace_period) accept integer nanoseconds
        or duration strings such as C(15s).
      - C(port) must be between C(1) and C(65535).
      - Integer durations must be greater than zero.
  env:
    type: dict
    description:
      - Environment variables.
      - Keys must not be empty.
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
          - Absolute path inside the Machine where the file is placed.
      raw_value:
        type: str
        description:
          - Base64-encoded file content.
          - Either O(files[].raw_value) or O(files[].secret_name) is required.
          - Mutually exclusive with O(files[].secret_name).
      secret_name:
        type: str
        description:
          - Name of a Fly.io secret whose value populates the file.
          - Must not be empty.
          - Either O(files[].raw_value) or O(files[].secret_name) is required.
          - Mutually exclusive with O(files[].raw_value).
  mounts:
    type: list
    elements: dict
    description:
      - Volume mount passed to the Fly.io API.
      - Fly.io supports one mounted volume per Machine.
    suboptions:
      volume:
        type: str
        required: true
        description:
          - Volume identifier or name.
          - Must not be empty.
      path:
        type: str
        required: true
        description:
          - Absolute mount path inside the Machine.
      name:
        type: str
        description:
          - Volume name returned by Fly.io.
      extend_threshold_percent:
        type: int
        description:
          - Usage percentage that triggers automatic extension.
          - Required with O(mounts[].add_size_gb).
          - Must be C(0), or between C(1) and C(100).
          - Set this and O(mounts[].add_size_gb) to C(0) to disable extension.
      add_size_gb:
        type: int
        description:
          - Gigabytes added by automatic extension.
          - Required with O(mounts[].extend_threshold_percent).
          - Must not be negative.
          - Set this and O(mounts[].extend_threshold_percent) to C(0) to disable
            extension.
      size_gb_limit:
        type: int
        description:
          - Maximum size after automatic extension.
          - Must not be negative.
          - Set to C(0) to remove the limit.
      encrypted:
        type: bool
        description:
          - Whether the mounted volume is encrypted.
  auto_destroy:
    type: bool
    description:
      - Automatically destroy the Machine when it exits.
      - Defaults to C(false) on the Fly.io API when not specified.
  restart:
    type: dict
    description:
      - Restart policy for the Machine passed to the Fly.io API.
    suboptions:
      policy:
        type: str
        choices:
          - "no"
          - always
          - on-failure
        description:
          - Restart policy name.
          - Required when configuring a new restart policy.
      max_retries:
        type: int
        description:
          - Maximum restart attempts (only for C(on-failure) policy).
          - Must not be negative.
  metadata:
    type: dict
    description:
      - Metadata key-value pairs attached to the Machine.
      - Keys must not be empty.
  statics:
    type: list
    elements: dict
    description:
      - Static files served by Fly Proxy and passed to the Fly.io API.
    suboptions:
      guest_path:
        type: str
        required: true
        description:
          - Path containing the static files.
          - Must not be empty.
      url_prefix:
        type: str
        required: true
        description:
          - URL prefix from which files are served.
          - Must not be empty.
      tigris_bucket:
        type: str
        description:
          - Tigris bucket containing the static files.
      index_document:
        type: str
        description:
          - Index document served for directory requests.
  wait:
    type: bool
    default: true
    description:
      - Wait for the Machine to reach the target state.
      - For O(state=present), wait until the Machine reaches a stable state.
  wait_timeout:
    type: int
    default: 60
    description:
      - Timeout in seconds when waiting for Machine state.
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
      - C(present) creates or updates the Machine.
      - C(started) ensures the Machine is running.
      - C(stopped) ensures the Machine is stopped.
      - C(absent) destroys the Machine.
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
        interval: 15s
        timeout: 2s
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

- name: Stop a Machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: stopped

- name: Destroy a Machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: absent
"""

RETURN = r"""
---
machine:
  description: Fly.io Machine.
  returned: when available
  type: dict
  contains:
    id:
      description: Machine identifier.
      returned: always
      type: str
    name:
      description: Machine name.
      returned: when available
      type: str
    region:
      description: Region code.
      returned: when available
      type: str
    state:
      description: Current Machine state.
      returned: when available
      type: str
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

import base64
import binascii

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    api_request,
    delete_result,
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    post_result,
    require_positive,
    sanitize_machine,
    valid_machine,
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
CHECK_STRING_FIELDS = (
    "method",
    "path",
    "protocol",
    "tls_server_name",
    "type",
)
CHECK_INTEGER_FIELDS = ("port",)
CHECK_DURATION_FIELDS = ("grace_period", "interval", "timeout")
CHECK_BOOLEAN_FIELDS = ("tls_skip_verify",)
CHECK_FIELDS = set(
    CHECK_STRING_FIELDS
    + CHECK_INTEGER_FIELDS
    + CHECK_DURATION_FIELDS
    + CHECK_BOOLEAN_FIELDS
    + ("headers",)
)
LIST_ITEM_KEYS = (
    "guest_path",
    "internal_port",
    "port",
    "start_port",
    "end_port",
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
PRESENT_STATES = {"created", "started", "stopped", "suspended"}


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
            flyio_path("apps", app_name, "machines", machine_id),
            ok_statuses=[404],
            required_field="id",
            expected_value=machine_id,
            required_fields=("state",),
        )

    machines = list_all(
        client,
        flyio_path("apps", app_name, "machines"),
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

    config = clean(config)
    for service in config.get("services", []):
        if service.get("autostop") == "off":
            service["autostop"] = False
        elif service.get("autostop") == "stop":
            service["autostop"] = True
    return config


def validate_integer_range(module, value, name, minimum, maximum=None):
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        module.fail_json(msg=f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            module.fail_json(msg=f"{name} must be at least {minimum}")
        else:
            module.fail_json(msg=f"{name} must be between {minimum} and {maximum}")


def validate_string_mappings(module, config):
    for field in ("env", "metadata"):
        value = config.get(field)
        if value is not None and not all(
            isinstance(key, str) and key.strip() and isinstance(item, str)
            for key, item in value.items()
        ):
            module.fail_json(
                msg=f"{field} must use non-empty string keys and string values"
            )


def validate_check_strings(module, name, check):
    for field in CHECK_STRING_FIELDS:
        if field not in check:
            continue
        if not isinstance(check[field], str):
            module.fail_json(msg=f"checks.{name}.{field} must be a string")
        if not check[field].strip():
            module.fail_json(msg=f"checks.{name}.{field} must not be empty")


def validate_check_fields(module, name, check):
    if not all(isinstance(field, str) for field in check):
        module.fail_json(msg=f"checks.{name} field names must be strings")
    unsupported = check.keys() - CHECK_FIELDS
    if unsupported:
        module.fail_json(
            msg="check '{}' contains unsupported fields: {}".format(
                name,
                ", ".join(sorted(unsupported)),
            )
        )
    validate_check_strings(module, name, check)
    for field in CHECK_INTEGER_FIELDS:
        if field in check:
            validate_integer_range(
                module,
                check[field],
                f"checks.{name}.{field}",
                1,
                65535,
            )
    for field in CHECK_BOOLEAN_FIELDS:
        if field in check and not isinstance(check[field], bool):
            module.fail_json(msg=f"checks.{name}.{field} must be a boolean")


def validate_check_protocols(module, name, check):
    if check.get("type") not in (None, "http", "tcp"):
        module.fail_json(msg=f"checks.{name}.type must be http or tcp")
    if check.get("protocol") not in (None, "http", "https"):
        module.fail_json(msg=f"checks.{name}.protocol must be http or https")


def validate_check_durations(module, name, check):
    for field in CHECK_DURATION_FIELDS:
        if field not in check:
            continue
        value = check[field]
        if not (
            (isinstance(value, int) and not isinstance(value, bool))
            or (isinstance(value, str) and value.strip())
        ):
            module.fail_json(
                msg=f"checks.{name}.{field} must be an integer or duration string"
            )
        if isinstance(value, int) and not isinstance(value, bool):
            validate_integer_range(module, value, f"checks.{name}.{field}", 1)


def validate_check_headers(module, name, headers):
    if headers is not None and (
        not isinstance(headers, list)
        or not all(
            isinstance(header, dict)
            and set(header) == {"name", "values"}
            and isinstance(header.get("name"), str)
            and header["name"].strip()
            and isinstance(header.get("values"), list)
            and all(isinstance(value, str) for value in header["values"])
            for header in headers
        )
    ):
        module.fail_json(
            msg=f"checks.{name}.headers must contain name and string values"
        )


def validate_checks(module, checks):
    if checks is None:
        return
    if not isinstance(checks, dict) or not all(
        isinstance(name, str) and name.strip() and isinstance(check, dict)
        for name, check in checks.items()
    ):
        module.fail_json(msg="checks must map names to configuration dictionaries")

    for name, check in checks.items():
        validate_check_fields(module, name, check)
        validate_check_protocols(module, name, check)
        validate_check_durations(module, name, check)
        validate_check_headers(module, name, check.get("headers"))


def validate_paths(module, config):
    for option, field in (("files", "guest_path"), ("mounts", "path")):
        if any(
            not isinstance(item.get(field), str) or not item[field].startswith("/")
            for item in config.get(option) or []
        ):
            module.fail_json(msg=f"{option}[].{field} must be an absolute path")
    for field in ("guest_path", "url_prefix"):
        if any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for item in config.get("statics") or []
        ):
            module.fail_json(msg=f"statics[].{field} must not be empty")


def validate_files(module, files):
    for file in files:
        secret_name = file.get("secret_name")
        if secret_name is not None and not secret_name.strip():
            module.fail_json(msg="files[].secret_name must not be empty")
        raw_value = file.get("raw_value")
        if raw_value is None:
            continue
        try:
            base64.b64decode(raw_value, validate=True)
        except (binascii.Error, TypeError, ValueError):
            module.fail_json(msg="files[].raw_value must be valid Base64")


def validate_services(module, services):
    for service in services:
        validate_integer_range(
            module,
            service.get("internal_port"),
            "services[].internal_port",
            1,
            65535,
        )
        validate_integer_range(
            module,
            service.get("min_machines_running"),
            "services[].min_machines_running",
            0,
        )
        concurrency = service.get("concurrency") or {}
        for field in ("soft_limit", "hard_limit"):
            validate_integer_range(
                module,
                concurrency.get(field),
                f"services[].concurrency.{field}",
                0,
            )
        if (
            concurrency.get("soft_limit") is not None
            and concurrency.get("hard_limit") is not None
            and concurrency["soft_limit"] > concurrency["hard_limit"]
        ):
            module.fail_json(
                msg="services[].concurrency.soft_limit must not exceed hard_limit"
            )
        autostop = service.get("autostop")
        if autostop is not None and not (
            isinstance(autostop, bool) or autostop in ("off", "stop", "suspend")
        ):
            module.fail_json(
                msg="service autostop must be off, stop, suspend, true, or false"
            )
        for port in service.get("ports") or []:
            for field in ("port", "start_port", "end_port"):
                validate_integer_range(
                    module,
                    port.get(field),
                    f"services[].ports[].{field}",
                    1,
                    65535,
                )
            if (
                port.get("start_port") is not None
                and port.get("end_port") is not None
                and port["start_port"] > port["end_port"]
            ):
                module.fail_json(
                    msg="services[].ports[].start_port must not exceed end_port"
                )
            http_options = port.get("http_options") or {}
            response = http_options.get("response") or {}
            headers = response.get("headers")
            if headers is not None and (
                not isinstance(headers, dict)
                or not all(
                    isinstance(header, str)
                    and header.strip()
                    and (
                        value is False
                        or isinstance(value, str)
                        or (
                            isinstance(value, list)
                            and all(isinstance(item, str) for item in value)
                        )
                    )
                    for header, value in headers.items()
                )
            ):
                module.fail_json(
                    msg=(
                        "service HTTP response headers must map non-empty strings "
                        "to strings, string lists, or false"
                    )
                )


def validate_guest(module, guest):
    if guest is None:
        return
    for field in ("cpus", "gpus", "memory_mb"):
        validate_integer_range(module, guest.get(field), f"guest.{field}", 1)
    memory_mb = guest.get("memory_mb")
    if memory_mb is not None and memory_mb % 256:
        module.fail_json(msg="guest.memory_mb must be a multiple of 256")


def validate_mounts(module, mounts):
    for mount in mounts:
        if not isinstance(mount.get("volume"), str) or not mount["volume"].strip():
            module.fail_json(msg="mounts[].volume must not be empty")
        validate_integer_range(
            module,
            mount.get("extend_threshold_percent"),
            "mounts[].extend_threshold_percent",
            0,
            100,
        )
        for field in ("add_size_gb", "size_gb_limit"):
            validate_integer_range(
                module,
                mount.get(field),
                f"mounts[].{field}",
                0,
            )


def validate_restart(module, restart):
    if restart is None:
        return
    validate_integer_range(
        module,
        restart.get("max_retries"),
        "restart.max_retries",
        0,
    )


def validate_config(module, config):
    validate_string_mappings(module, config)
    validate_checks(module, config.get("checks"))
    validate_files(module, config.get("files") or [])
    validate_guest(module, config.get("guest"))
    validate_mounts(module, config.get("mounts") or [])
    validate_paths(module, config)
    validate_restart(module, config.get("restart"))
    validate_services(module, config.get("services") or [])


def validate_complete_config(module, config, existing_checks=()):
    for name, check in config.get("checks", {}).items():
        if name in existing_checks:
            continue
        missing = {"port", "type"} - check.keys()
        if missing:
            module.fail_json(
                msg="check '{}' requires {}".format(
                    name,
                    " and ".join(sorted(missing)),
                )
            )
    if any("protocol" not in service for service in config.get("services", [])):
        module.fail_json(msg="each service requires protocol")
    restart = config.get("restart")
    if restart is not None:
        if "policy" not in restart:
            module.fail_json(msg="restart.policy is required")
        if "max_retries" in restart and restart["policy"] != "on-failure":
            module.fail_json(
                msg="restart.max_retries is valid only with policy=on-failure"
            )


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

    if isinstance(current, list) and isinstance(desired, list):
        if len(current) != len(desired):
            return True
        return any(
            config_values_differ(cur, want) for cur, want in zip(current, desired)
        )

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return current != desired

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

    result = {**current, **desired}
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


def matching_mount(current, desired):
    current_mounts = current.get("mounts", [])
    desired_mounts = desired.get("mounts", [])
    if not current_mounts or not desired_mounts:
        return None

    mount = desired_mounts[0]
    identifiers = {mount.get(key) for key in ("volume", "name") if mount.get(key)}
    current_identifiers = {
        current_mounts[0].get(key)
        for key in ("volume", "name")
        if current_mounts[0].get(key)
    }
    return (
        current_mounts[0]
        if identifiers and identifiers <= current_identifiers
        else None
    )


def mounts_differ(current, desired):
    current_mounts = current.get("mounts", [])
    if not isinstance(current_mounts, list) or not all(
        isinstance(mount, dict) for mount in current_mounts
    ):
        return True
    if len(current_mounts) != len(desired.get("mounts", [])):
        return True
    return bool(current_mounts) and matching_mount(current, desired) is None


def mount_values_differ(current, desired):
    desired_mounts = desired.get("mounts", [])
    if not desired_mounts:
        return False
    values = {
        key: value
        for key, value in desired_mounts[0].items()
        if key not in ("volume", "name")
    }
    match = matching_mount(current, desired)
    return match is None or config_values_differ(match, values)


def validate_machine_data(module, machine):
    if machine is not None and not valid_machine(machine):
        module.fail_json(
            msg=(
                "Fly.io API returned malformed Machine data for app "
                f"'{module.params['app_name']}'"
            ),
            machine=sanitize_machine(machine),
        )
    return machine


def validate_waited_machine(module, machine_id, current, expected_state):
    validate_machine_data(module, current)
    if expected_state == "destroyed":
        reached = current is None or current.get("state") == "destroyed"
    elif expected_state == "settled":
        reached = current is not None and current.get("state") in PRESENT_STATES
    else:
        reached = current is not None and current.get("state") == expected_state
    if not reached:
        module.fail_json(
            msg=(
                f"Machine '{machine_id}' in app '{module.params['app_name']}' "
                f"did not reach state '{expected_state}'"
            ),
            machine=sanitize_machine(current),
        )


def machine_instance_id(module, machine):
    instance_id = machine.get("instance_id")
    if not isinstance(instance_id, str) or not instance_id.strip():
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data for Machine '{machine['id']}' "
                f"in app '{module.params['app_name']}': expected an instance ID"
            ),
            machine=sanitize_machine(machine),
        )
    return instance_id


def settle_machine(module, client, current, desired_state):
    app_name = module.params["app_name"]
    machine_id = current["id"]
    state = current.get("state")
    if state in TERMINAL_STATES:
        module.fail_json(
            msg=(
                f"Machine '{machine_id}' in app '{app_name}' is in terminal "
                f"state '{state}'"
            ),
            machine=sanitize_machine(current),
        )

    target = TRANSITION_TARGETS.get(state)
    if target is None:
        if state in AMBIGUOUS_TRANSITIONS:
            if not module.params["wait"]:
                module.fail_json(
                    msg=(
                        f"Machine '{machine_id}' in app '{app_name}' is currently "
                        f"{state}; enable wait or retry"
                    ),
                    machine=sanitize_machine(current),
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
    elif target == desired_state and (module.check_mode or not module.params["wait"]):
        module.exit_json(
            changed=False,
            message=f"Machine already transitioning to {desired_state}",
            machine=sanitize_machine(current),
        )
    elif not module.params["wait"]:
        module.fail_json(
            msg=(
                f"Machine '{machine_id}' in app '{app_name}' is currently "
                f"{state}; enable wait or retry"
            ),
            machine=sanitize_machine(current),
        )
    else:
        wait_state = "settled" if desired_state == "present" else target
        wait_for_machine(
            client,
            module.params["app_name"],
            current["id"],
            wait_state,
            module.params["wait_timeout"],
            instance_id=(
                machine_instance_id(module, current)
                if wait_state == "stopped"
                else None
            ),
        )
        current = get_resource(
            client,
            flyio_path("apps", module.params["app_name"], "machines", current["id"]),
            ok_statuses=[404],
            required_field="id",
            expected_value=current["id"],
            required_fields=("state",),
        )
        validate_waited_machine(module, machine_id, current, wait_state)
    if current is None or current.get("state") in TERMINAL_STATES:
        module.fail_json(
            msg=f"Machine '{machine_id}' in app '{app_name}' is no longer available",
            machine=sanitize_machine(current),
        )
    if current.get("state") in TRANSITIONAL_STATES:
        module.fail_json(
            msg=f"Transition of Machine '{machine_id}' in app '{app_name}' timed out",
            machine=sanitize_machine(current),
        )
    return current


def validate_machine_update(module, current, desired_config):
    app_name = module.params["app_name"]
    current_config = current.get("config")
    if not isinstance(current_config, dict):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed configuration for Machine "
                f"'{current['id']}' in app '{app_name}'"
            ),
            machine=sanitize_machine(current),
        )

    current_region = current.get("region")
    if module.params.get("region") is not None:
        if not isinstance(current_region, str) or not current_region:
            module.fail_json(
                msg=(
                    f"Fly.io API returned malformed region data for Machine "
                    f"'{current['id']}' in app '{app_name}'"
                ),
                machine=sanitize_machine(current),
            )
        if module.params["region"] != current_region:
            module.fail_json(
                msg=(
                    f"Region cannot be changed for Machine '{current['id']}' "
                    f"in app '{app_name}'"
                )
            )
    if "mounts" in desired_config and mounts_differ(current_config, desired_config):
        module.fail_json(
            msg=(
                f"Attached volume cannot be changed for Machine '{current['id']}' "
                f"in app '{app_name}'"
            )
        )
    return current_config


def machine_config_changed(current_config, desired_config):
    if current_config.get("image") != desired_config["image"]:
        return True

    for field, value in desired_config.items():
        if field == "image":
            continue
        if field == "mounts":
            if mount_values_differ(current_config, desired_config):
                return True
        elif config_values_differ(
            current_config.get(field),
            value,
            purge=field in PURGE_CONFIG_FIELDS,
        ):
            return True
    return False


def validate_machine_postcondition(
    module,
    machine,
    desired_config,
    expected_name=None,
    expected_region=None,
):
    validate_machine_data(module, machine)
    config = machine.get("config") if machine is not None else None
    machine_id = (
        machine.get("id")
        if isinstance(machine, dict)
        else module.params.get("id") or module.params.get("name")
    )
    if (
        not isinstance(config, dict)
        or machine_config_changed(config, desired_config)
        or (expected_name is not None and machine.get("name") != expected_name)
        or (expected_region is not None and machine.get("region") != expected_region)
    ):
        module.fail_json(
            msg=(
                f"Fly.io API did not apply the requested configuration to Machine "
                f"'{machine_id}' in app '{module.params['app_name']}'"
            ),
            machine=sanitize_machine(machine),
        )
    return machine


def update_machine(module, client, current, desired_config):
    params = module.params
    app_name = params["app_name"]
    current = settle_machine(module, client, current, "present")
    current_config = validate_machine_update(module, current, desired_config)

    config = merge_config(current_config, desired_config)
    existing_checks = current_config.get("checks")
    if not isinstance(existing_checks, dict):
        existing_checks = {}
    validate_complete_config(
        module,
        {
            field: config[field]
            for field in ("checks", "services", "restart")
            if field in desired_config
        },
        existing_checks,
    )

    if not machine_config_changed(current_config, desired_config):
        module.exit_json(
            changed=False,
            message="Machine already present",
            machine=sanitize_machine(current),
        )
    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be updated",
            machine=sanitize_machine(current),
        )

    body = {"config": config}
    if current.get("instance_id") is not None:
        body["current_version"] = machine_instance_id(module, current)
    if current.get("state") in ("created", "failed", "stopped", "suspended"):
        body["skip_launch"] = True

    result = post_result(
        client,
        flyio_path("apps", app_name, "machines", current["id"]),
        body,
    )
    if not valid_machine(result) or result["id"] != current["id"]:
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while updating Machine "
                f"'{current['id']}' in app '{app_name}'"
            ),
            machine=sanitize_machine(result),
        )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            result["id"],
            "settled",
            params["wait_timeout"],
        )
        result = get_resource(
            client,
            flyio_path("apps", app_name, "machines", result["id"]),
            required_field="id",
            expected_value=result["id"],
            required_fields=("state",),
        )
        validate_waited_machine(module, result["id"], result, "settled")

    validate_machine_postcondition(module, result, desired_config)

    module.exit_json(
        changed=True,
        message="Machine updated",
        machine=sanitize_machine(result),
    )


def create_machine(module, client, desired_config):
    params = module.params
    app_name = params["app_name"]
    if params.get("id") is not None:
        module.fail_json(msg=f"Machine '{params['id']}' not found in app '{app_name}'")

    validate_complete_config(module, desired_config)
    if module.check_mode:
        module.exit_json(changed=True, message="Machine would be created")

    body = {"config": desired_config}
    if params.get("name") is not None:
        body["name"] = params["name"]
    if params.get("region") is not None:
        body["region"] = params["region"]

    result = post_result(client, flyio_path("apps", app_name, "machines"), body)
    if not valid_machine(result):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while creating Machine "
                f"'{params['name']}' in app '{app_name}'"
            ),
            machine=sanitize_machine(result),
        )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            result["id"],
            "settled",
            params["wait_timeout"],
        )
        result = get_resource(
            client,
            flyio_path("apps", app_name, "machines", result["id"]),
            required_field="id",
            expected_value=result["id"],
            required_fields=("state",),
        )
        validate_waited_machine(module, result["id"], result, "settled")

    validate_machine_postcondition(
        module,
        result,
        desired_config,
        expected_name=params["name"],
        expected_region=params.get("region"),
    )

    module.exit_json(
        changed=True,
        message="Machine created",
        machine=sanitize_machine(result),
    )


def ensure_present(module, client):
    params = module.params
    if not params["image"].strip():
        module.fail_json(msg="image must not be empty")
    if params.get("region") is not None and not params["region"].strip():
        module.fail_json(msg="region must not be empty")
    if params["wait"]:
        require_positive(module, "wait_timeout")
    if len(params.get("mounts") or []) > 1:
        module.fail_json(msg="only one volume can be mounted to a Machine")

    validate_config(module, params)
    desired_config = build_config(params)
    current = validate_machine_data(
        module,
        find_machine(
            client,
            params["app_name"],
            name=params.get("name"),
            machine_id=params.get("id"),
        ),
    )
    if current is not None:
        return update_machine(module, client, current, desired_config)
    return create_machine(module, client, desired_config)


def wait_until_machine_destroyed(module, client, machine):
    app_name = module.params["app_name"]
    machine_id = machine["id"]
    wait_for_machine(
        client,
        app_name,
        machine_id,
        "destroyed",
        module.params["wait_timeout"],
    )
    current = get_resource(
        client,
        flyio_path("apps", app_name, "machines", machine_id),
        ok_statuses=[404],
        required_field="id",
        expected_value=machine_id,
        required_fields=("state",),
    )
    validate_waited_machine(module, machine_id, current, "destroyed")
    return current


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = validate_machine_data(
        module,
        find_machine(
            client,
            app_name,
            name=params.get("name"),
            machine_id=params.get("id"),
            missing_ok=True,
        ),
    )

    if current is None or current.get("state") == "destroyed":
        module.exit_json(changed=False, message="Machine already absent")

    machine_id = current["id"]
    if current.get("state") == "destroying":
        if params["wait"] and not module.check_mode:
            current = wait_until_machine_destroyed(module, client, current)
        values = {"changed": False, "message": "Machine already being destroyed"}
        if current is not None:
            values["machine"] = sanitize_machine(current)
        module.exit_json(**values)

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be destroyed",
            machine=sanitize_machine(current),
        )

    result = delete_result(
        client,
        f"{flyio_path('apps', app_name, 'machines', current['id'])}?force=true",
        ok_statuses=[404],
    )
    if result is not None and (
        not isinstance(result, dict) or result.get("ok") is not True
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while destroying Machine "
                f"'{machine_id}' in app '{app_name}'"
            ),
            response=result,
        )

    if params["wait"]:
        current = wait_until_machine_destroyed(module, client, current)
    else:
        current = None

    message = "Machine destroyed" if params["wait"] else "Machine destruction requested"
    values = {"changed": True, "message": message}
    if current is not None:
        values["machine"] = sanitize_machine(current)
    module.exit_json(**values)


def ensure_started(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = validate_machine_data(
        module,
        find_machine(
            client,
            app_name,
            name=params.get("name"),
            machine_id=params.get("id"),
        ),
    )

    if current is None:
        identifier = params.get("id") or params.get("name")
        module.fail_json(msg=f"Machine '{identifier}' not found in app '{app_name}'")

    current = settle_machine(module, client, current, "started")

    if current.get("state") == "started":
        module.exit_json(
            changed=False,
            message="Machine already started",
            machine=sanitize_machine(current),
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be started",
            machine=sanitize_machine(current),
        )

    result = api_request(
        client,
        "post",
        flyio_path("apps", app_name, "machines", current["id"], "start"),
    )
    if result is not None and (
        not isinstance(result, dict)
        or not isinstance(result.get("previous_state"), str)
        or not result["previous_state"]
        or not isinstance(result.get("migrated"), bool)
        or not isinstance(result.get("new_host"), str)
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while starting Machine "
                f"'{current['id']}' in app '{app_name}'"
            ),
            response=result,
        )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            current["id"],
            "started",
            params["wait_timeout"],
        )

    current = get_resource(
        client,
        flyio_path("apps", app_name, "machines", current["id"]),
        required_field="id",
        expected_value=current["id"],
        required_fields=("state",),
    )
    validate_machine_data(module, current)
    if params["wait"]:
        validate_waited_machine(module, current["id"], current, "started")

    message = "Machine started" if params["wait"] else "Machine start requested"
    module.exit_json(
        changed=True,
        message=message,
        machine=sanitize_machine(current),
    )


def ensure_stopped(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    current = validate_machine_data(
        module,
        find_machine(
            client,
            app_name,
            name=params.get("name"),
            machine_id=params.get("id"),
        ),
    )

    if current is None:
        identifier = params.get("id") or params.get("name")
        module.fail_json(msg=f"Machine '{identifier}' not found in app '{app_name}'")

    current = settle_machine(module, client, current, "stopped")

    if current.get("state") == "created":
        module.exit_json(
            changed=False,
            message="Machine has not been started",
            machine=sanitize_machine(current),
        )

    if current.get("state") == "stopped":
        module.exit_json(
            changed=False,
            message="Machine already stopped",
            machine=sanitize_machine(current),
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be stopped",
            machine=sanitize_machine(current),
        )

    instance_id = machine_instance_id(module, current) if params["wait"] else None
    result = api_request(
        client,
        "post",
        flyio_path("apps", app_name, "machines", current["id"], "stop"),
    )
    if result is not None and (
        not isinstance(result, dict) or result.get("ok") is not True
    ):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data while stopping Machine "
                f"'{current['id']}' in app '{app_name}'"
            ),
            response=result,
        )

    if params["wait"]:
        wait_for_machine(
            client,
            app_name,
            current["id"],
            "stopped",
            params["wait_timeout"],
            instance_id=instance_id,
        )

    current = get_resource(
        client,
        flyio_path("apps", app_name, "machines", current["id"]),
        required_field="id",
        expected_value=current["id"],
        required_fields=("state",),
    )
    validate_machine_data(module, current)
    if params["wait"]:
        validate_waited_machine(module, current["id"], current, "stopped")

    message = "Machine stopped" if params["wait"] else "Machine stop requested"
    module.exit_json(
        changed=True,
        message=message,
        machine=sanitize_machine(current),
    )


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
            "guest": {
                "type": "dict",
                "options": {
                    "cpu_kind": {"type": "str"},
                    "gpu_kind": {"type": "str"},
                    "host_dedication_id": {"type": "str"},
                    "cpus": {"type": "int"},
                    "gpus": {"type": "int"},
                    "memory_mb": {"type": "int"},
                    "kernel_args": {"type": "list", "elements": "str"},
                    "persist_rootfs": {
                        "type": "str",
                        "choices": ["never", "restart", "always"],
                    },
                },
            },
            "services": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "protocol": {"type": "str", "choices": ["tcp", "udp"]},
                    "internal_port": {"type": "int", "required": True},
                    "autostart": {"type": "bool"},
                    "autostop": {"type": "raw"},
                    "min_machines_running": {"type": "int"},
                    "concurrency": {
                        "type": "dict",
                        "options": {
                            "type": {
                                "type": "str",
                                "choices": ["connections", "requests"],
                            },
                            "soft_limit": {"type": "int"},
                            "hard_limit": {"type": "int"},
                        },
                    },
                    "ports": {
                        "type": "list",
                        "elements": "dict",
                        "options": {
                            "port": {"type": "int"},
                            "start_port": {"type": "int"},
                            "end_port": {"type": "int"},
                            "handlers": {"type": "list", "elements": "str"},
                            "force_https": {"type": "bool"},
                            "http_options": {
                                "type": "dict",
                                "options": {
                                    "compress": {"type": "bool"},
                                    "h2_backend": {"type": "bool"},
                                    "response": {
                                        "type": "dict",
                                        "options": {
                                            "headers": {
                                                "type": "dict",
                                                "no_log": True,
                                            },
                                            "pristine": {"type": "bool"},
                                        },
                                    },
                                },
                            },
                            "tls_options": {
                                "type": "dict",
                                "options": {
                                    "alpn": {"type": "list", "elements": "str"},
                                    "default_self_signed": {"type": "bool"},
                                    "versions": {
                                        "type": "list",
                                        "elements": "str",
                                    },
                                },
                            },
                            "proxy_proto_options": {
                                "type": "dict",
                                "options": {
                                    "version": {"type": "str"},
                                },
                            },
                        },
                        "mutually_exclusive": [
                            ("port", "start_port"),
                            ("port", "end_port"),
                        ],
                        "required_one_of": [("port", "start_port")],
                        "required_together": [("start_port", "end_port")],
                    },
                },
            },
            "checks": {"type": "dict", "no_log": True},
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
            "mounts": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "volume": {"type": "str", "required": True},
                    "path": {"type": "str", "required": True},
                    "name": {"type": "str"},
                    "extend_threshold_percent": {"type": "int"},
                    "add_size_gb": {"type": "int"},
                    "size_gb_limit": {"type": "int"},
                    "encrypted": {"type": "bool"},
                },
                "required_together": [
                    ("extend_threshold_percent", "add_size_gb"),
                ],
            },
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
            "statics": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "guest_path": {"type": "str", "required": True},
                    "url_prefix": {"type": "str", "required": True},
                    "tigris_bucket": {"type": "str"},
                    "index_document": {"type": "str"},
                },
            },
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
