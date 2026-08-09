# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


import json
import time
import urllib.error
import urllib.parse
from contextlib import contextmanager

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


@contextmanager
def flyio_client(module):
    token = module.params.get("api_token")
    if not token:
        module.fail_json(msg="api_token is required")

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


def api_request(client, method, path, body=None, ok_statuses=None, timeout=30):
    ok_statuses = ok_statuses or []
    url = f"{MACHINES_API_URL}{path}"
    data = json.dumps(body) if body is not None else None

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

        response_body = None
        try:
            response_body = json.loads(exc.read())
        except (ValueError, AttributeError):
            response_body = None

        raise FlyioApiError(
            str(exc),
            status_code=status_code,
            response_body=response_body,
        )
    except urllib.error.URLError as exc:
        raise FlyioApiError(str(exc))
    except ValueError as exc:
        raise FlyioApiError(f"Invalid JSON in API response: {exc}")


def delete_result(client, path, timeout=30, ok_statuses=None):
    result = api_request(
        client,
        "delete",
        path,
        ok_statuses=ok_statuses,
        timeout=timeout,
    )
    return None if result is _MISSING else result


def get_ip_addresses(client, app_name, missing_ok=False):
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
        data = graphql_request(client, query, {"appName": app_name})
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
        raise FlyioApiError("Malformed GraphQL response: expected an app object")

    ip_addresses = app.get("ipAddresses")
    if not isinstance(ip_addresses, dict):
        raise FlyioApiError(
            "Malformed GraphQL response: expected an IP address connection"
        )

    addresses = ip_addresses.get("nodes")
    if not isinstance(addresses, list) or not all(
        isinstance(address, dict)
        and isinstance(address.get("address"), str)
        and address["address"]
        and isinstance(address.get("type"), str)
        and address["type"]
        and (address.get("region") is None or isinstance(address.get("region"), str))
        for address in addresses
    ):
        raise FlyioApiError("Malformed GraphQL response: expected an IP address list")

    addresses = list(addresses)

    shared = app.get("sharedIpAddress")
    if shared is not None and not isinstance(shared, str):
        raise FlyioApiError("Malformed GraphQL response: expected a shared IP address")
    if shared:
        addresses.append({"address": shared, "type": "shared_v4", "region": ""})

    return addresses


def graphql_request(client, query, variables=None, timeout=30):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        response = open_url(
            GRAPHQL_API_URL,
            method="POST",
            data=json.dumps(payload),
            headers=client["headers"],
            timeout=timeout,
        )
        result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        response_body = None
        try:
            response_body = json.loads(exc.read())
        except (ValueError, AttributeError):
            pass
        raise FlyioApiError(
            str(exc),
            status_code=exc.code,
            response_body=response_body,
        )
    except urllib.error.URLError as exc:
        raise FlyioApiError(str(exc))
    except ValueError as exc:
        raise FlyioApiError(f"Invalid JSON in GraphQL response: {exc}")

    if not isinstance(result, dict):
        raise FlyioApiError("Malformed GraphQL response: expected an object")

    if result.get("errors"):
        errors = result["errors"]
        message = (
            errors[0].get("message", "GraphQL error")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict)
            else "GraphQL error"
        )
        raise FlyioApiError(message)

    data = result.get("data")
    if not isinstance(data, dict):
        raise FlyioApiError("Malformed GraphQL response: expected a data object")

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
        isinstance(value.get(field), str) and value[field] for field in fields
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
        raise FlyioApiError("Malformed API response: expected a resource object")
    if not _valid_resource(result, required_field, required_fields) or (
        expected_value is not None and result[required_field] != expected_value
    ):
        raise FlyioApiError("Malformed API response: expected a resource object")
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
        raise FlyioApiError("Malformed API response: expected a resource list")
    if not isinstance(result, list) or not all(
        _valid_resource(item, required_field, required_fields) for item in result
    ):
        raise FlyioApiError("Malformed API response: expected a resource list")
    return result


def post_result(client, path, body):
    return api_request(client, "post", path, body=body)


def put_result(client, path, body):
    return api_request(client, "put", path, body=body)


def select_fields(value, fields):
    if not isinstance(value, dict):
        return {}
    return {field: value.get(field) for field in fields if field in value}


def require_positive(module, *names):
    for name in names:
        if module.params[name] <= 0:
            module.fail_json(msg=f"{name} must be greater than zero")


def values_differ(current, desired, purge=False):
    if isinstance(current, list) and isinstance(desired, list):
        if len(current) != len(desired):
            return True
        return any(values_differ(cur, want) for cur, want in zip(current, desired))

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return current != desired

    if purge and current.keys() != desired.keys():
        return True

    if not desired:
        return False

    for key, value in desired.items():
        if key not in current or values_differ(current[key], value):
            return True

    return False


def wait_for_machine(
    client, app_name, machine_id, state="started", timeout=60, instance_id=None
):
    if instance_id is not None and (
        not isinstance(instance_id, str) or not instance_id
    ):
        raise FlyioApiError("Malformed API response: expected a Machine instance ID")

    query = {"state": state, "timeout": timeout}
    if instance_id is not None:
        query["instance_id"] = instance_id

    path = (
        f"/apps/{app_name}/machines/{machine_id}/wait?{urllib.parse.urlencode(query)}"
    )
    ok_statuses = [404] if state == "destroyed" else None
    api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout + 10)


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
            f"/apps/{app_name}/machines/{machine_id}",
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
            f"/apps/{app_name}",
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
            f"/apps/{app_name}/volumes/{volume_id}",
            ok_statuses=ok_statuses,
            timeout=remaining,
            required_field="id",
            expected_value=volume_id,
            required_fields=("state",),
        )
        if volume is None:
            return volume

        if volume.get("state") in states:
            if size_gb is None:
                return volume

            current_size = volume.get("size_gb")
            if not isinstance(current_size, int) or isinstance(current_size, bool):
                raise FlyioApiError(
                    "Malformed API response: expected an integer volume size"
                )
            if current_size >= size_gb:
                return volume

        time.sleep(min(2, max(0, deadline - time.monotonic())))
