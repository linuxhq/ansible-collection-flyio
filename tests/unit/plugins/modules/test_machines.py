# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import machines
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


def params(**updates):
    values = {
        "app_name": "example",
        "id": None,
        "image": "example:latest",
        "name": "worker",
        "region": "ord",
        "wait": True,
        "wait_timeout": 60,
    }
    values.update(updates)
    return values


class MachinesTests(TestCase):
    def test_finds_machine_by_name(self):
        listed = {
            "config": {"restart": {"policy": "on-failure"}},
            "id": "machine-one",
            "name": "worker",
        }

        with patch.object(machines, "list_all", return_value=[listed]):
            result = machines.find_machine({}, "example", name="worker")

        self.assertEqual(result, listed)

    def test_missing_parent_is_tolerated_only_when_requested(self):
        with patch.object(machines, "list_all", return_value=[]) as list_all:
            machines.find_machine({}, "example", name="worker")
            list_all.assert_called_once_with(
                {},
                "/apps/example/machines",
                ok_statuses=None,
                required_field="id",
                required_fields=("name", "state"),
            )

            list_all.reset_mock()
            machines.find_machine({}, "example", name="worker", missing_ok=True)
            list_all.assert_called_once_with(
                {},
                "/apps/example/machines",
                ok_statuses=[404],
                required_field="id",
                required_fields=("name", "state"),
            )

    def test_builds_config_without_none_values(self):
        config = machines.build_config(
            {
                "checks": {"health": {"port": 8080}},
                "env": None,
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                        "secret_name": None,
                    }
                ],
                "image": "example:latest",
                "init": {"entrypoint": ["/bin/sh"], "exec": None, "tty": None},
                "restart": {"policy": "on-failure"},
            }
        )

        self.assertEqual(
            config,
            {
                "checks": {"health": {"port": 8080}},
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                "image": "example:latest",
                "init": {"entrypoint": ["/bin/sh"]},
                "restart": {"policy": "on-failure"},
            },
        )

    def test_equivalent_machine_is_unchanged(self):
        current = {
            "config": {"image": "ghcr.io/example/app:latest"},
            "id": "machine-one",
        }
        module = FakeModule(params(image="ghcr.io/example/app:latest"))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_normalized_machine_is_unchanged(self):
        current = {
            "config": {
                "checks": {"health": {"port": 8080, "timeout": "2s", "type": "http"}},
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "mode": "0644",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
                "image": "example:latest",
                "init": {
                    "cmd": None,
                    "entrypoint": ["/bin/sh"],
                    "exec": None,
                    "tty": False,
                },
                "mounts": [
                    {
                        "encrypted": True,
                        "name": "data",
                        "path": "/data",
                        "size_gb": 1,
                        "volume": "vol-example",
                    }
                ],
                "restart": {"max_retries": 10, "policy": "on-failure"},
            },
            "id": "machine-one",
        }
        module = FakeModule(
            params(
                checks={"health": {"port": 8080, "type": "http"}},
                files=[
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                guest={"cpus": 1},
                init={"entrypoint": ["/bin/sh"]},
                mounts=[{"path": "/data", "volume": "vol-example"}],
                restart={"policy": "on-failure"},
            )
        )

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_present_rejects_terminal_machine(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "state": "destroyed",
        }
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine is in terminal state 'destroyed'",
        )

    def test_present_waits_for_existing_transition(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "stopping",
        }
        stopped = {**current, "state": "stopped"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            instance_id="instance-one",
        )
        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_updates_machine_and_waits(self):
        current = {
            "config": {
                "env": {"PRESERVED": "value"},
                "image": "ghcr.io/library/example:latest",
                "services": [{"internal_port": 8080}],
            },
            "id": "machine-one",
            "instance_id": "version-one",
            "region": "ord",
            "state": "started",
        }
        updated = {
            "id": "machine-one",
            "instance_id": "version-two",
            "state": "starting",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            {
                "config": {
                    "env": {"PRESERVED": "value"},
                    "image": "example:latest",
                    "services": [{"internal_port": 8080}],
                },
                "current_version": "version-one",
            },
        )
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            instance_id="version-two",
        )
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            required_field="id",
            expected_value="machine-one",
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_rejects_malformed_update_response(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "started",
        }
        module = FakeModule(params(wait=False))

        for response in ({}, {"id": "machine-two"}):
            with (
                self.subTest(response=response),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result", return_value=response),
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "fly.io API returned an empty or malformed response during update",
            )

    def test_rejects_malformed_current_configuration(self):
        current = {"config": None, "id": "machine-one", "state": "started"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "fly.io API returned a malformed machine configuration",
        )

    def test_preserves_unmanaged_nested_config_on_update(self):
        current = {
            "config": {
                "checks": {
                    "health": {"port": 8080, "timeout": "2s"},
                    "remove": {"port": 8081},
                },
                "guest": {"cpus": 1, "memory_mb": 2048},
                "image": "example:latest",
                "services": [
                    {
                        "internal_port": 8080,
                        "protocol": "tcp",
                        "ports": [{"force_https": True, "port": 80}],
                    }
                ],
            },
            "id": "machine-one",
        }
        module = FakeModule(
            params(
                checks={"health": {"port": 9090}},
                guest={"cpus": 2},
                services=[
                    {
                        "internal_port": 8080,
                        "ports": [{"handlers": ["http"], "port": 80}],
                    }
                ],
                wait=False,
            )
        )

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=current) as post,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        config = post.call_args.args[2]["config"]
        self.assertEqual(config["guest"], {"cpus": 2, "memory_mb": 2048})
        self.assertEqual(config["checks"], {"health": {"port": 9090, "timeout": "2s"}})
        self.assertEqual(
            config["services"],
            [
                {
                    "internal_port": 8080,
                    "protocol": "tcp",
                    "ports": [{"force_https": True, "handlers": ["http"], "port": 80}],
                }
            ],
        )

    def test_merges_reordered_list_items_by_identity(self):
        current = [
            {"internal_port": 8080, "protocol": "tcp"},
            {"internal_port": 9090, "protocol": "udp"},
        ]
        desired = [{"internal_port": 9090}, {"internal_port": 8080}]

        result = machines.merge_values(current, desired)

        self.assertFalse(machines.config_values_differ(current, desired))
        self.assertEqual(
            result,
            [
                {"internal_port": 9090, "protocol": "udp"},
                {"internal_port": 8080, "protocol": "tcp"},
            ],
        )

    def test_nested_list_items_are_compared_by_identity(self):
        current = [{"internal_port": 8080, "ports": [{"port": 80}, {"port": 443}]}]
        desired = [{"internal_port": 8080, "ports": [{"port": 443}, {"port": 80}]}]

        self.assertFalse(machines.config_values_differ(current, desired))

    def test_identityless_nested_items_preserve_defaults(self):
        current = [{"interval": "15s", "timeout": "2s", "type": "tcp"}]
        desired = [{"interval": "15s", "type": "tcp"}]

        self.assertFalse(machines.config_values_differ(current, desired))
        self.assertEqual(machines.merge_values(current, desired), current)

    def test_duplicate_desired_list_items_need_distinct_matches(self):
        current = [{"internal_port": 8080}, {"internal_port": 9090}]
        desired = [{"internal_port": 8080}, {"internal_port": 8080}]

        self.assertTrue(machines.config_values_differ(current, desired))

    def test_reordered_mounts_are_unchanged(self):
        current = {
            "config": {
                "image": "example:latest",
                "mounts": [
                    {"path": "/data", "volume": "vol-data"},
                    {"path": "/logs", "volume": "vol-logs"},
                ],
            },
            "id": "machine-one",
        }
        module = FakeModule(
            params(
                mounts=[
                    {"path": "/logs", "volume": "vol-logs"},
                    {"path": "/data", "volume": "vol-data"},
                ]
            )
        )

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_mount_name_and_id_are_equivalent(self):
        current = {
            "config": {
                "image": "example:latest",
                "mounts": [{"name": "data", "path": "/data", "volume": "vol-data"}],
            },
            "id": "machine-one",
        }
        module = FakeModule(params(mounts=[{"path": "/data", "volume": "data"}]))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_conflicting_mount_identifiers_are_different(self):
        current = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-old"}]}
        desired = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-new"}]}

        self.assertTrue(machines.mounts_differ(current, desired))

    def test_malformed_current_mounts_are_different(self):
        self.assertTrue(machines.mounts_differ({"mounts": None}, {"mounts": []}))

    def test_malformed_current_checks_do_not_crash_merge(self):
        desired = {"checks": {"health": {"port": 8080}}}

        self.assertEqual(machines.merge_config({"checks": None}, desired), desired)

    def test_merges_duplicate_ports_by_complete_identity(self):
        current = [
            {"internal_port": 53, "protocol": "tcp", "tcp_checks": ["preserve"]},
            {"internal_port": 53, "protocol": "udp", "udp_checks": ["preserve"]},
        ]

        result = machines.merge_values(
            current,
            [
                {"internal_port": 53, "protocol": "udp"},
                {"internal_port": 53, "protocol": "tcp"},
            ],
        )

        self.assertEqual(
            result,
            [
                {
                    "internal_port": 53,
                    "protocol": "udp",
                    "udp_checks": ["preserve"],
                },
                {
                    "internal_port": 53,
                    "protocol": "tcp",
                    "tcp_checks": ["preserve"],
                },
            ],
        )

    def test_rejects_changing_attached_volume(self):
        current = {
            "config": {
                "image": "example:latest",
                "mounts": [{"path": "/data", "volume": "vol-old"}],
            },
            "id": "machine-one",
        }
        module = FakeModule(params(mounts=[{"path": "/data", "volume": "vol-new"}]))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "attached volume cannot be changed for an existing machine",
        )

    def test_updates_stopped_machine_without_launching(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "instance_id": "version-one",
            "state": "stopped",
        }
        updated = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(wait=True))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            patch.object(machines, "wait_for_machine") as wait,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        self.assertTrue(post.call_args.args[2]["skip_launch"])
        self.assertEqual(post.call_args.args[2]["current_version"], "version-one")
        wait.assert_not_called()

    def test_removes_unspecified_environment_keys(self):
        current = {
            "config": {
                "env": {"KEEP": "value", "REMOVE": "value"},
                "image": "example:latest",
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(params(env={"KEEP": "value"}, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=current) as post,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            {
                "config": {
                    "env": {"KEEP": "value"},
                    "image": "example:latest",
                },
            },
        )

    def test_rejects_region_changes(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "region": "iad",
        }
        module = FakeModule(params(region="ord"))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "region cannot be changed for an existing machine",
        )

    def test_check_mode_does_not_create_machine(self):
        module = FakeModule(params(), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])

    def test_missing_machine_id_fails_instead_of_creating(self):
        module = FakeModule(params(id="missing", name=None))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "Machine 'missing' not found")

    def test_create_wait_returns_refreshed_machine(self):
        created = {"id": "machine-one", "state": "starting"}
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=started) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            required_field="id",
            expected_value="machine-one",
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_rejects_malformed_create_response(self):
        module = FakeModule(params(wait=False))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value={}),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "fly.io API returned an empty or malformed response during create",
        )

    def test_destroy_waits_for_destroyed_state(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "started",
        }
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "delete_result") as delete,
            patch.object(machines, "get_resource", return_value=None) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        wait.assert_called_once_with({}, "example", "machine-one", "destroyed", 60)
        delete.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one?force=true",
            ok_statuses=[404],
        )
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            ok_statuses=[404],
            required_field="id",
            expected_value="machine-one",
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertIsNone(raised.exception.values["machine"])

    def test_destroyed_machine_is_unchanged_in_check_mode(self):
        current = {"id": "machine-one", "state": "destroyed"}
        module = FakeModule(params(image=None), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_destroying_machine_waits_without_deleting_again(self):
        current = {"id": "machine-one", "state": "destroying"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result") as delete,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        delete.assert_not_called()
        wait.assert_called_once_with({}, "example", "machine-one", "destroyed", 60)
        self.assertFalse(raised.exception.values["changed"])

    def test_starts_machine(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "stopped",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/start"
        )
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            instance_id="instance-one",
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_starting_machine_waits_without_starting_again(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "starting",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            instance_id="instance-one",
        )
        self.assertFalse(raised.exception.values["changed"])

    def test_waits_for_ambiguous_machine_transition_to_settle(self):
        current = {"id": "machine-one", "state": "updating"}
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(
                machines, "wait_for_machine_settled", return_value=started
            ) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {}, "example", "machine-one", machines.TRANSITIONAL_STATES, 60
        )
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_ambiguous_machine_transition_without_wait(self):
        current = {"id": "machine-one", "state": "updating"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine is currently updating; enable wait or retry",
        )

    def test_rejects_timed_out_machine_transition(self):
        current = {"id": "machine-one", "state": "updating"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine_settled", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "Machine transition timed out")

    def test_rejects_terminal_machine_state(self):
        current = {"id": "machine-one", "state": "migrated"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine is in terminal state 'migrated'",
        )

    def test_stops_machine(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "started",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/stop"
        )
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            instance_id="instance-one",
        )
        self.assertEqual(raised.exception.values["machine"], stopped)

    def test_created_machine_is_already_not_running(self):
        current = {"id": "machine-one", "state": "created"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_nonpositive_wait_timeout(self):
        module = FakeModule(params(image=None, wait_timeout=0))

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "wait_timeout must be greater than zero",
        )

    def test_stopping_machine_waits_without_stopping_again(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "stopping",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            instance_id="instance-one",
        )
        self.assertFalse(raised.exception.values["changed"])
