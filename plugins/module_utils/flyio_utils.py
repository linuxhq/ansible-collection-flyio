# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


import ipaddress
import json
import time
import urllib.error
import urllib.parse
from contextlib import contextmanager

from ansible.module_utils.urls import ConnectionError as AnsibleConnectionError
from ansible.module_utils.urls import open_url

GRAPHQL_API_URL = "https://api.fly.io/graphql"
MACHINES_API_URL = "https://api.machines.dev/v1"
_MISSING = object()


def authorization_header(token):
    if token.startswith(("Bearer ", "FlyV1 ")):
        return token
    if any(part.partition("_")[0] in ("fm1r", "fm2") for part in token.split(",")):
        return f"FlyV1 {token}"
    return f"Bearer {token}"


def flyio_path(*parts):
    return "/" + "/".join(urllib.parse.quote(part, safe="") for part in parts)


@contextmanager
def flyio_client(module):
    token = module.params.get("api_token")
    if not isinstance(token, str) or not token.strip():
        module.fail_json(msg="api_token is required")
    if "\r" in token or "\n" in token:
        module.fail_json(msg="api_token must not contain line breaks")
    if any(ord(character) < 32 or ord(character) == 127 for character in token):
        module.fail_json(msg="api_token must not contain control characters")
    token = token.strip()
    if token in ("Bearer", "FlyV1"):
        module.fail_json(msg="api_token credential must not be empty")

    for name in ("address", "app_name", "id", "name", "network", "org_slug"):
        value = module.params.get(name)
        if isinstance(value, str) and not value.strip():
            module.fail_json(msg=f"{name} must not be empty")

    client = {
        "headers": {
            "Authorization": authorization_header(token),
            "Content-Type": "application/json",
        },
    }

    try:
        yield client
    except FlyioApiError as exc:
        fail_from_flyio_error(module, str(exc), exc)


class FlyioApiError(Exception):
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _error_response(exc):
    try:
        content = exc.read()
    except (AttributeError, OSError):
        return None
    if not content:
        return None
    try:
        return json.loads(content)
    except ValueError:
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return str(content)


def api_request(client, method, path, body=None, ok_statuses=None, timeout=30):
    ok_statuses = ok_statuses or []
    operation = f"{method.upper()} {path}"
    url = f"{MACHINES_API_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None

    try:
        response = open_url(
            url,
            method=method.upper(),
            data=data,
            headers=client["headers"],
            timeout=timeout,
        )
        content = response.read()
        if content:
            return json.loads(content)
        return None
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        if status_code in ok_statuses:
            return _MISSING

        raise FlyioApiError(
            f"{operation} failed: {exc}",
            status_code=status_code,
            response_body=_error_response(exc),
        ) from exc
    except (OSError, AnsibleConnectionError) as exc:
        raise FlyioApiError(f"{operation} failed: {exc}") from exc
    except ValueError as exc:
        raise FlyioApiError(f"{operation} returned invalid JSON: {exc}") from exc


def delete_result(client, path, timeout=30, ok_statuses=None):
    result = api_request(
        client,
        "delete",
        path,
        ok_statuses=ok_statuses,
        timeout=timeout,
    )
    return None if result is _MISSING else result


def valid_machine(machine):
    return (
        isinstance(machine, dict)
        and isinstance(machine.get("id"), str)
        and bool(machine["id"].strip())
        and all(
            field not in machine
            or (isinstance(machine[field], str) and machine[field].strip())
            for field in ("name", "region", "state")
        )
    )


def valid_volume(volume):
    return (
        isinstance(volume, dict)
        and isinstance(volume.get("id"), str)
        and bool(volume["id"].strip())
        and all(
            field not in volume
            or (isinstance(volume[field], str) and volume[field].strip())
            for field in ("name", "region", "state")
        )
        and (
            "size_gb" not in volume
            or (
                isinstance(volume["size_gb"], int)
                and not isinstance(volume["size_gb"], bool)
                and volume["size_gb"] > 0
            )
        )
        and ("encrypted" not in volume or isinstance(volume["encrypted"], bool))
    )


def valid_secret_metadata(secret):
    return (
        isinstance(secret, dict)
        and isinstance(secret.get("name"), str)
        and bool(secret["name"].strip())
        and isinstance(secret.get("digest"), str)
        and bool(secret["digest"].strip())
        and all(
            field not in secret
            or (isinstance(secret[field], str) and bool(secret[field].strip()))
            for field in ("created_at", "updated_at")
        )
    )


def ip_version(value):
    if not isinstance(value, str) or "%" in value:
        return None
    try:
        return ipaddress.ip_address(value).version
    except ValueError:
        return None


def valid_ip_address(address):
    if not isinstance(address, dict):
        return False
    address_version = ip_version(address.get("address"))
    expected_version = {
        "private_v6": 6,
        "shared_v4": 4,
        "v4": 4,
        "v6": 6,
    }.get(address.get("type"))
    return (
        address_version == expected_version
        and all(
            address.get(field) is None
            or (isinstance(address[field], str) and address[field].strip())
            for field in ("id", "created_at")
        )
        and (address.get("region") is None or isinstance(address.get("region"), str))
    )


def get_ip_addresses(client, app_name, missing_ok=False):
    operation = f"List IP addresses for app '{app_name}'"
    query = """
        query($appName: String!) {
            app(name: $appName) {
                sharedIpAddress
                ipAddresses {
                    nodes {
                        id
                        address
                        type
                        region
                        created_at: createdAt
                    }
                }
            }
        }
    """
    try:
        data = graphql_request(
            client,
            query,
            {"appName": app_name},
            operation=operation,
        )
    except FlyioApiError as exc:
        if missing_ok and "could not find app" in str(exc).lower():
            return []
        raise
    app = data.get("app")
    if app is None:
        if missing_ok:
            return []
        raise FlyioApiError(f"App '{app_name}' not found")
    if not isinstance(app, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected an app")

    ip_addresses = app.get("ipAddresses")
    if not isinstance(ip_addresses, dict):
        raise FlyioApiError(
            f"{operation} returned malformed data: expected an address connection"
        )

    addresses = ip_addresses.get("nodes")
    if not isinstance(addresses, list) or not all(
        valid_ip_address(address) for address in addresses
    ):
        raise FlyioApiError(f"{operation} returned malformed data: expected a list")

    addresses = [
        {field: value for field, value in address.items() if value is not None}
        for address in addresses
    ]

    shared = app.get("sharedIpAddress")
    if shared is not None:
        shared_address = {"address": shared, "type": "shared_v4", "region": ""}
        if not valid_ip_address(shared_address):
            raise FlyioApiError(
                f"{operation} returned malformed data: expected a shared address"
            )
        addresses.append(shared_address)

    return addresses


def graphql_request(
    client, query, variables=None, timeout=30, operation="GraphQL request"
):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        response = open_url(
            GRAPHQL_API_URL,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=client["headers"],
            timeout=timeout,
        )
        result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise FlyioApiError(
            f"{operation} failed: {exc}",
            status_code=exc.code,
            response_body=_error_response(exc),
        ) from exc
    except (OSError, AnsibleConnectionError) as exc:
        raise FlyioApiError(f"{operation} failed: {exc}") from exc
    except ValueError as exc:
        raise FlyioApiError(f"{operation} returned invalid JSON: {exc}") from exc

    if not isinstance(result, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected an object")

    if result.get("errors"):
        errors = result["errors"]
        message = (
            errors[0].get("message", "GraphQL error")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict)
            else "GraphQL error"
        )
        raise FlyioApiError(
            f"{operation} failed: {message}",
            response_body=errors,
        )

    data = result.get("data")
    if not isinstance(data, dict):
        raise FlyioApiError(
            f"{operation} returned malformed data: expected a data object"
        )

    return data


def fail_from_flyio_error(module, message, exc):
    status_code = getattr(exc, "status_code", None)
    response_body = getattr(exc, "response_body", None)

    module.fail_json(
        msg=message,
        error=str(exc),
        status_code=status_code,
        response=response_body,
    )


def get_result(client, path, default=None, ok_statuses=None, timeout=30):
    result = api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout)
    if result is _MISSING:
        return default
    return result


def _valid_resource(value, required_field=None, required_fields=None):
    fields = tuple(required_fields or ())
    if required_field is not None:
        fields = (required_field, *fields)
    return isinstance(value, dict) and all(
        isinstance(value.get(field), str) and value[field].strip() for field in fields
    )


def get_resource(
    client,
    path,
    ok_statuses=None,
    timeout=30,
    required_field=None,
    expected_value=None,
    required_fields=None,
):
    result = api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout)
    if result is _MISSING:
        return None
    if result is None:
        raise FlyioApiError(f"GET {path} returned malformed data: expected an object")
    if not _valid_resource(result, required_field, required_fields) or (
        expected_value is not None and result[required_field] != expected_value
    ):
        raise FlyioApiError(f"GET {path} returned malformed data: expected an object")
    return result


def list_all(
    client,
    path,
    ok_statuses=None,
    required_field=None,
    required_fields=None,
):
    result = api_request(client, "get", path, ok_statuses=ok_statuses)
    if result is _MISSING:
        return []
    if result is None:
        raise FlyioApiError(f"GET {path} returned malformed data: expected a list")
    if not isinstance(result, list) or not all(
        _valid_resource(item, required_field, required_fields) for item in result
    ):
        raise FlyioApiError(f"GET {path} returned malformed data: expected a list")
    return result


def post_result(client, path, body):
    return api_request(client, "post", path, body=body)


def put_result(client, path, body):
    return api_request(client, "put", path, body=body)


def select_fields(value, fields):
    if not isinstance(value, dict):
        return {}
    return {field: value.get(field) for field in fields if field in value}


def sanitize_machine(machine):
    if machine is None:
        return None
    if not isinstance(machine, dict):
        return {}

    def sanitize_config(value):
        if isinstance(value, list):
            return [sanitize_config(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: sanitize_config(item)
            for key, item in value.items()
            if key not in ("env", "headers", "raw_value")
        }

    result = dict(machine)
    for field in ("config", "incomplete_config"):
        if isinstance(result.get(field), dict):
            result[field] = sanitize_config(result[field])
        elif field in result:
            del result[field]
    return result


def require_positive(module, *names):
    for name in names:
        value = module.params[name]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            module.fail_json(msg=f"{name} must be greater than zero")


def wait_for_machine(
    client, app_name, machine_id, state="started", timeout=60, instance_id=None
):
    operation = (
        f"Wait for Machine '{machine_id}' in app '{app_name}' "
        f"to reach state '{state}'"
    )
    if instance_id is not None and (
        not isinstance(instance_id, str) or not instance_id.strip()
    ):
        raise FlyioApiError(f"{operation} received a malformed instance ID")
    if state == "stopped" and instance_id is None:
        raise FlyioApiError(f"{operation} requires an instance ID")

    query = {"state": state, "timeout": timeout}
    if instance_id is not None:
        query["version"] = instance_id

    path = "{}?{}".format(
        flyio_path("apps", app_name, "machines", machine_id, "wait"),
        urllib.parse.urlencode(query),
    )
    ok_statuses = [404] if state == "destroyed" else None
    result = api_request(
        client,
        "get",
        path,
        ok_statuses=ok_statuses,
        timeout=timeout + 10,
    )
    if result is _MISSING and state == "destroyed":
        return
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise FlyioApiError(f"{operation} returned malformed data: expected ok=true")


def wait_for_machine_settled(
    client, app_name, machine_id, transient_states, timeout=60
):
    deadline = time.monotonic() + timeout
    machine = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return machine

        machine = get_resource(
            client,
            flyio_path("apps", app_name, "machines", machine_id),
            ok_statuses=[404],
            timeout=remaining,
            required_field="id",
            expected_value=machine_id,
            required_fields=("state",),
        )
        if machine is None or machine["state"] not in transient_states:
            return machine

        time.sleep(min(2, max(0, deadline - time.monotonic())))


def wait_for_app_absent(client, app_name, timeout=60):
    deadline = time.monotonic() + timeout
    app = {}
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return app

        app = get_resource(
            client,
            flyio_path("apps", app_name),
            ok_statuses=[404],
            timeout=remaining,
            required_field="name",
            expected_value=app_name,
        )
        if app is None:
            return None

        time.sleep(min(2, max(0, deadline - time.monotonic())))


def wait_for_volume(
    client,
    app_name,
    volume_id,
    timeout=60,
    states=("created",),
    ok_statuses=None,
    size_gb=None,
):
    deadline = time.monotonic() + timeout
    volume = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return volume

        volume = get_resource(
            client,
            flyio_path("apps", app_name, "volumes", volume_id),
            ok_statuses=ok_statuses,
            timeout=remaining,
            required_field="id",
            expected_value=volume_id,
            required_fields=("state",),
        )
        if volume is None:
            return volume
        if not valid_volume(volume):
            raise FlyioApiError(
                f"Wait for volume '{volume_id}' in app '{app_name}' returned "
                "malformed data"
            )

        if volume.get("state") in states:
            if size_gb is None:
                return volume

            current_size = volume.get("size_gb")
            if not isinstance(current_size, int) or isinstance(current_size, bool):
                raise FlyioApiError(
                    f"Wait for volume '{volume_id}' in app '{app_name}' returned "
                    "malformed data: expected an integer size"
                )
            if current_size >= size_gb:
                return volume

        time.sleep(min(2, max(0, deadline - time.monotonic())))
