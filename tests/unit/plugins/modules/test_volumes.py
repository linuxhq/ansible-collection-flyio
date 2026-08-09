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
    def test_rejects_empty_region_for_id_lookup(self):
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": " ",
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_absent(module, {})

        find.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "region must not be empty")

    def test_rejects_region_mismatch_for_id_lookup(self):
        module = FakeModule({"app_name": "example", "region": "iad"})
        volume = {"id": "vol_one", "region": "ord", "state": "created"}

        with self.assertRaises(ModuleFail) as raised:
            volumes.validate_volume_data(module, volume)

        self.assertEqual(
            raised.exception.values["msg"],
            "Volume 'vol_one' in app 'example' is in region 'ord', not 'iad'",
        )

    def test_rejects_name_mismatch(self):
        module = FakeModule({"app_name": "example", "name": "data", "region": "ord"})
        volume = {
            "id": "vol_one",
            "name": "other",
            "region": "ord",
            "state": "created",
        }

        with self.assertRaises(ModuleFail) as raised:
            volumes.validate_volume_data(module, volume)

        self.assertEqual(
            raised.exception.values["msg"],
            "Volume 'vol_one' in app 'example' does not match requested name 'data'",
        )

    def test_rejects_unapplied_create_options(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "name": "data",
                "region": "ord",
                "size_gb": 2,
            }
        )
        volume = {
            "encrypted": True,
            "id": "vol_one",
            "name": "data",
            "region": "ord",
            "size_gb": 2,
            "state": "created",
        }

        for field, value in (("size_gb", 1), ("encrypted", False)):
            with self.subTest(field=field), self.assertRaises(ModuleFail) as raised:
                volumes.validate_created_volume(module, {**volume, field: value})

            self.assertEqual(
                raised.exception.values["msg"],
                f"Fly.io API did not apply requested {field} to volume "
                "'vol_one' in app 'example'",
            )

    def test_rejects_empty_region_for_name_lookup(self):
        module = FakeModule(
            {
                "app_name": "example",
                "name": "data",
                "region": " ",
                "size_gb": None,
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
            raised.exception.values["msg"],
            "region must not be empty when name is specified",
        )

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

    def test_rejects_size_above_provider_limit(self):
        module = FakeModule(
            {
                "app_name": "example",
                "size_gb": 501,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        find.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "size_gb must not exceed 500")

    def test_skips_pending_destroy(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {
            "encrypted": False,
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "size_gb": 1,
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
            "Multiple volumes named 'data' in region 'ord' match in app "
            "'example'; specify id",
        )
        self.assertEqual(raised.exception.values["volume_ids"], ["vol_one", "vol_two"])

    def test_creates_replacement_for_pending_volume(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {
            "encrypted": False,
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": False,
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
            {"encrypted": False, "name": "data", "region": "ord", "size_gb": 1},
        )
        self.assertEqual(raised.exception.values["volume"], created)

    def test_omits_unset_provider_defaults_when_creating(self):
        created = {
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": None,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", return_value=created) as post,
            self.assertRaises(ModuleExit),
        ):
            volumes.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/volumes",
            {"name": "data", "region": "ord"},
        )

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
            "Fly.io API returned malformed data while creating volume "
            "'data' in app 'example'",
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
            raised.exception.values["msg"],
            "Volume 'vol_missing' not found in app 'example'",
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
        deleted = None

        with (
            patch.object(volumes, "get_resource", return_value=current),
            patch.object(
                volumes,
                "delete_result",
                return_value={"id": "vol_one", "state": "destroyed"},
            ) as delete,
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
        self.assertNotIn("volume", raised.exception.values)

    def test_rejects_malformed_volume_deletion_response(self):
        current = {"id": "vol_one", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": False,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(
                volumes,
                "delete_result",
                return_value={"id": "vol_two", "state": "created"},
            ),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while deleting volume "
            "'vol_one' in app 'example'",
        )

    def test_delete_without_wait_returns_provider_state(self):
        current = {"id": "vol_one", "state": "created"}
        deleted = {"id": "vol_one", "state": "destroyed"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": False,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result", return_value=deleted),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertEqual(raised.exception.values["message"], "Volume deleted")
        self.assertEqual(raised.exception.values["volume"], deleted)

    def test_empty_delete_response_still_waits_for_volume(self):
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

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result", return_value=None),
            patch.object(
                volumes, "wait_until_volume_deleted", return_value=None
            ) as wait,
            self.assertRaises(ModuleExit),
        ):
            volumes.ensure_absent(module, {})

        wait.assert_called_once_with(module, {}, current)

    def test_empty_delete_response_without_wait_is_only_requested(self):
        current = {"id": "vol_one", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": False,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["message"], "Volume deletion requested"
        )
        self.assertNotIn("volume", raised.exception.values)

    def test_deleting_volume_does_not_wait_in_check_mode(self):
        current = {"id": "vol_one", "state": "scheduling_destroy"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": True,
                "wait_timeout": 60,
            },
            check_mode=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result") as delete,
            patch.object(volumes, "wait_for_volume") as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_not_called()
        wait.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], current)

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

    def test_extension_wait_rejects_stale_size(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 10,
            "state": "created",
        }
        response = {
            "needs_restart": False,
            "volume": {**current, "size_gb": 20},
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 20,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "put_result", return_value=response),
            patch.object(volumes, "wait_for_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Extension of volume 'vol_one' in app 'example' timed out",
        )

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
            "Fly.io API returned malformed data while extending volume "
            "'vol_one' in app 'example'",
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
            {
                "needs_restart": False,
                "volume": {"id": "vol_one", "size_gb": 2, "state": False},
            },
            {
                "needs_restart": False,
                "volume": {"id": "vol_one", "size_gb": 1},
            },
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
                "Fly.io API returned malformed data while extending volume "
                "'vol_one' in app 'example'",
            )

    def test_extension_requires_restart_flag(self):
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
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while extending volume "
            "'vol_one' in app 'example'",
        )

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
            "Volume 'vol_one' in app 'example' is transitioning; enable wait or retry",
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
            "Encryption cannot be changed for volume 'vol_one' in app 'example'",
        )

    def test_omitted_encryption_accepts_existing_unencrypted_volume(self):
        current = {
            "encrypted": False,
            "id": "vol_one",
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 1,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_omitted_size_accepts_larger_existing_volume(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 10,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": None,
                "wait": False,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_volume_shrink(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 10,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 5,
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
            "Volume 'vol_one' in app 'example' cannot be shrunk from 10 GB to 5 GB",
        )

    def test_rejects_malformed_current_volume(self):
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

        for current in (
            {"id": "vol_one", "size_gb": 1, "state": "created"},
            {
                "encrypted": True,
                "id": "vol_one",
                "size_gb": 0,
                "state": "created",
            },
        ):
            with (
                self.subTest(current=current),
                patch.object(volumes, "find_volume", return_value=current),
                self.assertRaises(ModuleFail) as raised,
            ):
                volumes.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data for volume "
                "'vol_one' in app 'example'",
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
        self.assertEqual(
            raised.exception.values["msg"],
            "Deletion of volume 'vol_one' in app 'example' timed out",
        )
