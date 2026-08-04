# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import machines
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
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
        expected = {"id": "machine-one", "name": "worker"}

        with patch.object(machines, "list_all", return_value=[expected]):
            result = machines.find_machine({}, "example", name="worker")

        self.assertEqual(result, expected)

    def test_image_registry_prefix_is_equivalent(self):
        self.assertFalse(
            machines.image_changed(
                "registry.example/library/example:latest",
                "example:latest",
            )
        )
        self.assertTrue(machines.image_changed("example:old", "example:latest"))

    def test_builds_config_without_none_values(self):
        config = machines.build_config(
            {
                "checks": {"health": {"port": 8080}},
                "env": None,
                "image": "example:latest",
                "restart": {"policy": "on-failure"},
            }
        )

        self.assertEqual(
            config,
            {
                "checks": {"health": {"port": 8080}},
                "image": "example:latest",
                "restart": {"policy": "on-failure"},
            },
        )

    def test_equivalent_machine_is_unchanged(self):
        current = {
            "config": {"image": "registry.example/library/example:latest"},
            "id": "machine-one",
        }
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_updates_machine_and_waits(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
        }
        updated = {"id": "machine-one", "state": "started"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            patch.object(machines, "wait_for_machine") as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            {"config": {"image": "example:latest"}, "region": "ord"},
        )
        wait.assert_called_once_with({}, "example", "machine-one", "started", 60)
        self.assertEqual(raised.exception.values["machine"], updated)

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

    def test_destroy_stops_running_machine_first(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "delete_result") as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/stop"
        )
        wait.assert_called_once_with({}, "example", "machine-one", "stopped", 60)
        delete.assert_called_once_with(
            {}, "/apps/example/machines/machine-one?force=true"
        )
        self.assertTrue(raised.exception.values["changed"])

    def test_starts_machine(self):
        current = {"id": "machine-one", "state": "stopped"}
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_result", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/start"
        )
        wait.assert_called_once_with({}, "example", "machine-one", "started", 60)
        self.assertEqual(raised.exception.values["machine"], started)

    def test_stops_machine(self):
        current = {"id": "machine-one", "state": "started"}
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_result", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/stop"
        )
        wait.assert_called_once_with({}, "example", "machine-one", "stopped", 60)
        self.assertEqual(raised.exception.values["machine"], stopped)
