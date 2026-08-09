# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import volumes
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class FindVolumeTests(TestCase):
    def test_missing_parent_is_tolerated_only_when_requested(self):
        with patch.object(volumes, "list_all", return_value=[]) as list_all:
            volumes.find_volume(FakeModule({}), {}, "example", name="data")
            list_all.assert_called_once_with(
                {},
                "/apps/example/volumes",
                ok_statuses=None,
                required_field="id",
                required_fields=("name", "region", "state"),
            )

            list_all.reset_mock()
            volumes.find_volume(
                FakeModule({}), {}, "example", name="data", missing_ok=True
            )
            list_all.assert_called_once_with(
                {},
                "/apps/example/volumes",
                ok_statuses=[404],
                required_field="id",
                required_fields=("name", "region", "state"),
            )

    def test_rejects_nonpositive_size(self):
        module = FakeModule(
            {
                "app_name": "example",
                "size_gb": 0,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"], "size_gb must be greater than zero"
        )

    def test_skips_pending_destroy(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "state": "created",
        }

        with patch.object(volumes, "list_all", return_value=[pending, created]):
            result = volumes.find_volume(
                FakeModule({}), {}, "example", name="data", region="ord"
            )

        self.assertEqual(result, created)

    def test_destroyed_id_is_absent(self):
        destroyed = {"id": "vol_old", "state": "destroyed"}

        with patch.object(volumes, "get_resource", return_value=destroyed):
            result = volumes.find_volume(
                FakeModule({}), {}, "example", volume_id="vol_old"
            )

        self.assertIsNone(result)

    def test_includes_deleting_volume_only_when_requested(self):
        deleting = {"id": "vol_old", "state": "scheduling_destroy"}

        with patch.object(volumes, "get_resource", return_value=deleting):
            self.assertIsNone(
                volumes.find_volume(FakeModule({}), {}, "example", volume_id="vol_old")
            )
            self.assertEqual(
                volumes.find_volume(
                    FakeModule({}),
                    {},
                    "example",
                    volume_id="vol_old",
                    include_deleting=True,
                ),
                deleting,
            )

    def test_rejects_ambiguous_name_and_region(self):
        matches = [
            {"id": "vol_one", "name": "data", "region": "ord", "state": "created"},
            {"id": "vol_two", "name": "data", "region": "ord", "state": "created"},
        ]

        with (
            patch.object(volumes, "list_all", return_value=matches),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.find_volume(
                FakeModule({}), {}, "example", name="data", region="ord"
            )

        self.assertEqual(
            raised.exception.values["msg"],
            "Multiple volumes match name and region; specify id",
        )
        self.assertEqual(raised.exception.values["volume_ids"], ["vol_one", "vol_two"])

    def test_creates_replacement_for_pending_volume(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {"id": "vol_new", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "list_all", return_value=[pending]),
            patch.object(volumes, "post_result", return_value=created) as post,
            patch.object(volumes, "wait_for_volume", return_value=created),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/volumes",
            {"encrypted": True, "name": "data", "region": "ord", "size_gb": 1},
        )
        self.assertEqual(raised.exception.values["volume"], created)

    def test_rejects_malformed_create_response(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", return_value=["invalid"]),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "fly.io API returned an empty or malformed response during create",
        )

    def test_missing_volume_id_fails_instead_of_creating(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_missing",
                "name": None,
                "region": None,
                "size_gb": 1,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"], "Volume 'vol_missing' not found"
        )

    def test_deletes_volume(self):
        current = {"id": "vol_one", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": True,
                "wait_timeout": 60,
            }
        )
        deleted = {"id": "vol_one", "state": "pending_destroy"}

        with (
            patch.object(volumes, "get_resource", return_value=current),
            patch.object(volumes, "delete_result") as delete,
            patch.object(volumes, "wait_for_volume", return_value=deleted) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_called_once_with(
            {}, "/apps/example/volumes/vol_one", ok_statuses=[404]
        )
        wait.assert_called_once_with(
            {},
            "example",
            "vol_one",
            60,
            states=volumes.DEAD_STATES,
            ok_statuses=[404],
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], deleted)

    def test_extends_volume_and_waits(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        extended = {"id": "vol_one", "size_gb": 2, "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "encrypted": True,
                "size_gb": 2,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(
                volumes,
                "put_result",
                return_value={"needs_restart": True, "volume": extended},
            ) as put,
            patch.object(volumes, "wait_for_volume", return_value=extended) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        put.assert_called_once_with(
            {}, "/apps/example/volumes/vol_one/extend", {"size_gb": 2}
        )
        wait.assert_called_once_with({}, "example", "vol_one", 60, size_gb=2)
        self.assertEqual(raised.exception.values["volume"], extended)
        self.assertTrue(raised.exception.values["needs_restart"])

    def test_rejects_malformed_extension_response(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "put_result", return_value=["invalid"]),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "fly.io API returned a malformed response during extension",
        )

    def test_rejects_malformed_extension_fields(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": False,
            }
        )

        for result in (
            {"id": ["invalid"]},
            {"needs_restart": "yes", "volume": {"id": "vol_one"}},
            {"volume": {"id": "vol_two"}},
        ):
            with (
                self.subTest(result=result),
                patch.object(volumes, "find_volume", return_value=current),
                patch.object(volumes, "put_result", return_value=result),
                self.assertRaises(ModuleFail) as raised,
            ):
                volumes.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "fly.io API returned a malformed response during extension",
            )

    def test_omits_unavailable_extension_restart_flag(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        extended = {**current, "size_gb": 2}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "put_result", return_value={"volume": extended}),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertNotIn("needs_restart", raised.exception.values)

    def test_waits_for_existing_volume_transition(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 2,
            "state": "extending",
        }
        created = {**current, "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "wait_for_volume", return_value=created) as wait,
            patch.object(volumes, "put_result") as put,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        wait.assert_called_once_with({}, "example", "vol_one", 60)
        put.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_existing_volume_transition_without_wait(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 1,
            "state": "extending",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Volume transition already in progress; enable wait or retry",
        )

    def test_rejects_encryption_changes(self):
        current = {
            "encrypted": False,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 1,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "encryption cannot be changed for an existing volume",
        )

    def test_rejects_malformed_current_volume(self):
        current = {"id": "vol_one", "size_gb": 1, "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 1,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "fly.io API returned a malformed volume response",
        )

    def test_fails_when_volume_deletion_times_out(self):
        current = {"id": "vol_one", "state": "scheduling_destroy"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result") as delete,
            patch.object(volumes, "wait_for_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "Volume deletion timed out")
