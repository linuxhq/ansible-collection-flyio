# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils import flyio_utils
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import FlyioApiError
from ansible_collections.linuxhq.flyio.plugins.modules import volumes
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)

# Volumes Fly.io is deleting; fly-go's destroyedVolumeStates without pending_destroy, which counts as gone.
DELETING_STATES = ("destroying", "fork_cleanup", "scheduling_destroy", "waiting_for_detach")


class FindVolumeTests(TestCase):
    def test_deleting_states_match_fly(self):
        self.assertEqual(volumes.DELETING_STATES, set(DELETING_STATES))
        self.assertEqual(volumes.DEAD_STATES, {"destroyed", "pending_destroy"})

    def setUp(self):
        clock = patch.object(volumes, "wait_deadline", return_value=60)
        clock.start()
        self.addCleanup(clock.stop)
        left = patch.object(volumes, "seconds_left", side_effect=lambda deadline: deadline)
        left.start()
        self.addCleanup(left.stop)

    def test_rejects_empty_region_for_id_lookup(self):
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": " ",
                "wait": False,
                "wait_timeout": 60,
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
            volumes.require_matching_volume(module, volume)

        self.assertEqual(
            raised.exception.values["msg"],
            "Volume 'vol_one' in app 'example' is in region 'ord', not 'iad'",
        )

    def test_rejects_empty_region_for_name_lookup(self):
        module = FakeModule(
            {
                "app_name": "example",
                "name": "data",
                "region": " ",
                "size_gb": None,
                "wait": False,
                "wait_timeout": 60,
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
            "region must not be empty",
        )

    def test_missing_parent_is_tolerated_only_when_requested(self):
        with patch.object(volumes, "list_all", return_value=[]) as list_all:
            volumes.find_volume(FakeModule({}), {}, "example", name="data")
            list_all.assert_called_once_with(
                {},
                "/apps/example/volumes",
                ok_statuses=None,
            )

            list_all.reset_mock()
            volumes.find_volume(FakeModule({}), {}, "example", name="data", missing_ok=True)
            list_all.assert_called_once_with(
                {},
                "/apps/example/volumes",
                ok_statuses=[404],
            )

    def test_leaves_missing_size_to_fly_when_creating(self):
        module = FakeModule(
            {
                "api_token": "token",
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": None,
                "wait": False,
                "wait_timeout": 60,
            }
        )
        error = FlyioApiError("POST /apps/example/volumes failed: HTTP Error 400: size_gb must be set", status_code=400)

        # Fly.io rejects the create before changing anything, so the failure reports no change.
        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", side_effect=error) as post,
            self.assertRaises(ModuleFail) as raised,
            volumes.flyio_client(module) as client,
        ):
            volumes.ensure_present(module, client)

        post.assert_called_once_with(client, "/apps/example/volumes", {"name": "data", "region": "ord"})
        self.assertNotIn("changed", raised.exception.values)
        self.assertEqual(raised.exception.values["status_code"], 400)

    def test_check_mode_predicts_fly_rejection_without_size(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": None,
                "wait": False,
                "wait_timeout": 60,
            },
            check_mode=True,
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
            "Fly.io would reject the request to create volume 'data' in app 'example': size_gb must be set",
        )
        self.assertNotIn("changed", raised.exception.values)

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
            result = volumes.find_volume(FakeModule({}), {}, "example", name="data", region="ord")

        self.assertEqual(result, created)

    def test_name_lookup_matches_only_the_requested_region(self):
        ams = {"id": "vol_ams", "name": "data", "region": "ams", "state": "created"}
        ord_volume = {"id": "vol_ord", "name": "data", "region": "ord", "state": "created"}

        with patch.object(volumes, "list_all", return_value=[ams, ord_volume]):
            self.assertEqual(
                volumes.find_volume(FakeModule({}), {}, "example", name="data", region="ord"),
                ord_volume,
            )
            self.assertIsNone(volumes.find_volume(FakeModule({}), {}, "example", name="data", region="iad"))

    def test_destroyed_id_is_absent(self):
        destroyed = {"id": "vol_old", "state": "destroyed"}

        with patch.object(flyio_utils, "get_resource", return_value=destroyed):
            result = volumes.find_volume(FakeModule({}), {}, "example", volume_id="vol_old")

        self.assertIsNone(result)

    def test_includes_deleting_volume_only_when_requested(self):
        for state in DELETING_STATES:
            with self.subTest(state=state):
                deleting = {"id": "vol_old", "state": state}

                with patch.object(flyio_utils, "get_resource", return_value=deleting):
                    self.assertIsNone(volumes.find_volume(FakeModule({}), {}, "example", volume_id="vol_old"))
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
            volumes.find_volume(FakeModule({}), {}, "example", name="data", region="ord")

        self.assertEqual(
            raised.exception.values["msg"],
            "Multiple volumes named 'data' in region 'ord' match in app 'example'; specify id",
        )
        self.assertEqual(raised.exception.values["volume_ids"], ["vol_one", "vol_two"])

    def test_deleting_volumes_are_not_ambiguous(self):
        for state in DELETING_STATES:
            with self.subTest(state=state):
                deleting = {"id": "vol_old", "name": "data", "region": "ord", "state": state}
                created = {"id": "vol_new", "name": "data", "region": "ord", "state": "created"}

                # A live volume is preferred, including for an absent lookup.
                with patch.object(volumes, "list_all", return_value=[deleting, created]):
                    self.assertEqual(
                        volumes.find_volume(FakeModule({}), {}, "example", name="data", region="ord"), created
                    )
                    found = volumes.find_volume(
                        FakeModule({}), {}, "example", name="data", region="ord", include_deleting=True
                    )

                self.assertEqual(found, created)

                with patch.object(volumes, "list_all", return_value=[deleting]):
                    found = volumes.find_volume(
                        FakeModule({}), {}, "example", name="data", region="ord", include_deleting=True
                    )

                self.assertEqual(found, deleting)

                # Several deleting volumes are not ambiguous; any one satisfies an absent lookup.
                with patch.object(volumes, "list_all", return_value=[deleting, {**deleting, "id": "vol_two"}]):
                    self.assertIsNone(volumes.find_volume(FakeModule({}), {}, "example", name="data", region="ord"))
                    found = volumes.find_volume(
                        FakeModule({}), {}, "example", name="data", region="ord", include_deleting=True
                    )

                self.assertEqual(found["id"], "vol_old")

    def test_detaching_and_fork_cleanup_volumes_are_not_deleted_again(self):
        for state in ("fork_cleanup", "waiting_for_detach"):
            with self.subTest(state=state):
                current = {"id": "vol_one", "state": state}
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
                    patch.object(flyio_utils, "get_resource", return_value=current),
                    patch.object(volumes, "delete_result") as delete,
                    self.assertRaises(ModuleExit) as raised,
                ):
                    volumes.ensure_absent(module, {})

                delete.assert_not_called()
                self.assertFalse(raised.exception.values["changed"])
                self.assertEqual(raised.exception.values["message"], "Volume already being deleted")

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
            "size_gb": 1,
            "state": "created",
        }
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": False,
                "wait_timeout": 60,
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
            {"name": "data", "region": "ord", "size_gb": 1},
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
                "wait_timeout": 60,
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

    def test_volume_deleted_elsewhere_after_read_is_unchanged(self):
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
            patch.object(flyio_utils, "get_resource", return_value={"id": "vol_one", "state": "created"}),
            patch.object(volumes, "delete_result", side_effect=FlyioApiError("gone", status_code=404)),
            patch.object(volumes, "wait_for_volume") as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        wait.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["message"], "Volume already absent")

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
            patch.object(flyio_utils, "get_resource", return_value=current),
            patch.object(
                volumes,
                "delete_result",
                return_value={"id": "vol_one", "state": "destroyed"},
            ) as delete,
            patch.object(volumes, "wait_for_volume", return_value=deleted) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example/volumes/vol_one")
        wait.assert_called_once_with(
            {},
            "example",
            "vol_one",
            60,
            states=volumes.DEAD_STATES,
            ok_statuses=[404],
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], current)

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
            patch.object(volumes, "wait_until_volume_deleted", return_value=None) as wait,
            self.assertRaises(ModuleExit),
        ):
            volumes.ensure_absent(module, {})

        wait.assert_called_once_with(module, {}, current, 60)

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

        self.assertEqual(raised.exception.values["message"], "Volume deletion requested")
        self.assertEqual(raised.exception.values["volume"], current)

    def test_deleted_volume_keeps_last_known_snapshot(self):
        current = {"id": "vol_one", "state": "destroying"}
        module = FakeModule(
            {"app_name": "example", "id": "vol_one", "name": None, "region": None, "wait": True, "wait_timeout": 60}
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "wait_until_volume_deleted", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], current)

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

    def test_attached_volume_fails_in_check_mode(self):
        current = {"id": "vol_one", "state": "created", "attached_machine_id": "machine_one"}
        module = FakeModule(
            {"app_name": "example", "id": "vol_one", "name": None, "region": None, "wait": True, "wait_timeout": 60},
            check_mode=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result") as delete,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Volume 'vol_one' in app 'example' is attached to Machine 'machine_one'; "
            "destroy the Machine before deleting the volume",
        )
        self.assertEqual(raised.exception.values["volume"], current)

    def test_detached_volume_would_be_deleted_in_check_mode(self):
        for attached in ({"attached_machine_id": None}, {"attached_machine_id": ""}, {}):
            with self.subTest(attached=attached):
                current = {"id": "vol_one", "state": "created", **attached}
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
                    self.assertRaises(ModuleExit) as raised,
                ):
                    volumes.ensure_absent(module, {})

                delete.assert_not_called()
                self.assertTrue(raised.exception.values["changed"])
                self.assertEqual(raised.exception.values["message"], "Volume would be deleted")

    def test_attached_volume_delete_reaches_api(self):
        current = {"id": "vol_one", "state": "created", "attached_machine_id": "machine_one"}
        module = FakeModule(
            {"app_name": "example", "id": "vol_one", "name": None, "region": None, "wait": True, "wait_timeout": 60}
        )
        rejected = FlyioApiError("failed_precondition", status_code=412)

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result", side_effect=rejected) as delete,
            self.assertRaises(FlyioApiError) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example/volumes/vol_one")
        self.assertIs(raised.exception, rejected)

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
                "api_request",
                return_value={"needs_restart": True, "volume": extended},
            ) as put,
            patch.object(volumes, "wait_for_volume", return_value=extended) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        put.assert_called_once_with({}, "put", "/apps/example/volumes/vol_one/extend", body={"size_gb": 2})
        wait.assert_called_once_with(
            {}, "example", "vol_one", 60, stop_states=volumes.DEAD_STATES | volumes.DELETING_STATES, size_gb=2
        )
        self.assertEqual(raised.exception.values["volume"], extended)
        self.assertTrue(raised.exception.values["needs_restart"])

    def test_extension_wait_rejects_stale_or_missing_size(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 10,
            "state": "created",
        }
        extended = {**current, "size_gb": 20}

        for reported, waited in (
            (extended, current),
            (extended, {"id": "vol_one", "state": "extending"}),
            (current, current),
        ):
            # A fresh module per case, since a sent write wraps fail_json to report a change.
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

            with self.subTest(reported=reported, waited=waited):
                with (
                    patch.object(volumes, "find_volume", return_value=current),
                    patch.object(volumes, "api_request", return_value={"needs_restart": False, "volume": reported}),
                    patch.object(volumes, "wait_for_volume", return_value=waited),
                    self.assertRaises(ModuleFail) as raised,
                ):
                    volumes.ensure_present(module, {})

                self.assertEqual(
                    raised.exception.values["msg"],
                    "Extension of volume 'vol_one' in app 'example' timed out",
                )
                self.assertTrue(raised.exception.values["changed"])

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
            patch.object(volumes, "api_request") as put,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        wait.assert_called_once_with(
            {}, "example", "vol_one", 60, stop_states=volumes.DEAD_STATES | volumes.DELETING_STATES
        )
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
                "wait_timeout": 60,
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
                "wait_timeout": 60,
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

    def test_omitted_encryption_accepts_missing_provider_field(self):
        current = {
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
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_omitted_size_accepts_missing_provider_size(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
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
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_leaves_volume_shrink_to_fly(self):
        current = {
            "encrypted": True,
            "id": "vol_one",
            "size_gb": 10,
            "state": "created",
        }
        module = FakeModule(
            {
                "api_token": "token",
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 5,
                "wait": False,
                "wait_timeout": 60,
            }
        )
        error = FlyioApiError(
            "PUT /apps/example/volumes/vol_one/extend failed: HTTP Error 400: Invalid volume size - Specified volume size must be greater than 10",
            status_code=400,
        )

        # Fly.io rejects the smaller size and leaves the volume unchanged, so the failure reports no change.
        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "api_request", side_effect=error) as request,
            self.assertRaises(ModuleFail) as raised,
            volumes.flyio_client(module) as client,
        ):
            volumes.ensure_present(module, client)

        request.assert_called_once_with(client, "put", "/apps/example/volumes/vol_one/extend", body={"size_gb": 5})
        self.assertNotIn("changed", raised.exception.values)
        self.assertEqual(raised.exception.values["status_code"], 400)
        self.assertEqual(raised.exception.values["volume"], current)

    def test_check_mode_predicts_fly_rejection_of_shrink(self):
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
                "wait_timeout": 60,
            },
            check_mode=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        request.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io would reject the request to extend volume 'vol_one' in app 'example': Invalid volume size - Specified volume size must be greater than 10",
        )
        self.assertNotIn("changed", raised.exception.values)
        self.assertEqual(raised.exception.values["volume"], current)

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

    def test_failed_volume_is_rejected(self):
        module = FakeModule({"app_name": "example", "wait": True, "wait_timeout": 60})

        with self.assertRaises(ModuleFail) as raised:
            volumes.settle_volume(module, {}, {"id": "vol_one", "state": "failed"}, 60)

        self.assertEqual(raised.exception.values["msg"], "Volume 'vol_one' in app 'example' is in failed state")

    def test_wait_reports_volume_that_fails_while_waiting(self):
        module = FakeModule({"app_name": "example", "wait": True, "wait_timeout": 60})
        failed = {"id": "vol_one", "state": "failed"}

        with (
            patch.object(volumes, "wait_for_volume", return_value=failed),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.settle_volume(module, {}, {"id": "vol_one", "state": "creating"}, 60)

        self.assertEqual(raised.exception.values["msg"], "Volume 'vol_one' in app 'example' is in failed state")

    def test_rejects_region_groups(self):
        module = FakeModule(
            {"app_name": "example", "name": "data", "region": "us", "size_gb": 1, "wait": False, "wait_timeout": 60}
        )

        with (
            patch.object(volumes, "find_volume") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "region must be a single region code; region lists and groups are not supported",
        )

    def test_unchanged_transitioning_volume_without_wait_is_unchanged(self):
        module = FakeModule({"app_name": "example", "encrypted": None, "size_gb": 1, "wait": False, "wait_timeout": 60})
        current = {"id": "vol_one", "size_gb": 1, "state": "creating"}

        with self.assertRaises(ModuleExit) as raised:
            volumes.update_volume(module, {}, current, 60)

        self.assertFalse(raised.exception.values["changed"])

    def test_diff_mode_reports_extension(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 1, "state": "created"}
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
            },
            check_mode=True,
            diff=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(raised.exception.values["diff"], {"before": {"size_gb": 1}, "after": {"size_gb": 2}})

    def test_diff_mode_reports_applied_extension_size(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 1, "state": "created"}
        extended = {"id": "vol_one", "size_gb": 3, "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "encrypted": True,
                "size_gb": 2,
                "wait": False,
                "wait_timeout": 60,
            },
            diff=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "api_request", return_value={"needs_restart": False, "volume": extended}),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(raised.exception.values["volume"]["size_gb"], 3)
        self.assertEqual(raised.exception.values["diff"], {"before": {"size_gb": 1}, "after": {"size_gb": 3}})

    def test_transitioning_volume_without_wait_reports_shrink_as_change(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 3, "state": "extending"}
        for check_mode in (True, False):
            module = FakeModule(
                {
                    "app_name": "example",
                    "id": "vol_one",
                    "name": None,
                    "region": None,
                    "encrypted": True,
                    "size_gb": 2,
                    "wait": False,
                    "wait_timeout": 60,
                },
                check_mode=check_mode,
            )

            # A smaller size is a requested change, so it fails like any change to a transitioning volume.
            with (
                self.subTest(check_mode=check_mode),
                patch.object(volumes, "find_volume", return_value=current),
                patch.object(volumes, "api_request") as request,
                self.assertRaises(ModuleFail) as raised,
            ):
                volumes.ensure_present(module, {})

            request.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                "Volume 'vol_one' in app 'example' is transitioning; enable wait or retry",
            )

    def test_diff_mode_reports_deleted_volume_fields(self):
        current = {
            "id": "vol_one",
            "name": "data",
            "region": "ord",
            "size_gb": 1,
            "encrypted": True,
            "state": "created",
            "created_at": "2026-01-01T00:00:00Z",
        }
        module = FakeModule(
            {"app_name": "example", "id": "vol_one", "name": None, "region": None, "wait": True, "wait_timeout": 60},
            check_mode=True,
            diff=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["diff"],
            {
                "before": {"id": "vol_one", "name": "data", "region": "ord", "size_gb": 1, "encrypted": True},
                "after": {},
            },
        )

    def test_diff_mode_reports_created_volume(self):
        module = FakeModule(
            {
                "app_name": "example",
                "id": None,
                "name": "data",
                "region": "ord",
                "encrypted": True,
                "size_gb": 1,
                "wait": True,
                "wait_timeout": 60,
            },
            check_mode=True,
            diff=True,
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["diff"],
            {"before": {}, "after": {"name": "data", "region": "ord", "size_gb": 1, "encrypted": True}},
        )

    def test_volume_deleted_while_waiting_for_extension_fails(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 1, "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
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
            patch.object(
                volumes,
                "api_request",
                return_value={"needs_restart": False, "volume": {**current, "size_gb": 2}},
            ),
            patch.object(volumes, "wait_for_volume", return_value={**current, "state": "pending_destroy"}),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(raised.exception.values["msg"], "Volume 'vol_one' in app 'example' was deleted while waiting")
        self.assertTrue(raised.exception.values["changed"])

    def test_volume_deleted_while_settling_fails(self):
        module = FakeModule({"app_name": "example", "wait": True, "wait_timeout": 60})
        deleting = {"id": "vol_one", "state": "scheduling_destroy"}

        with (
            patch.object(volumes, "wait_for_volume", return_value=deleting),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.settle_volume(module, {}, {"id": "vol_one", "state": "creating"}, 60)

        self.assertEqual(raised.exception.values["msg"], "Volume 'vol_one' in app 'example' was deleted while waiting")
        self.assertNotIn("changed", raised.exception.values)

    def test_volume_deleted_while_waiting_for_creation_fails(self):
        created = {"id": "vol_new", "name": "data", "region": "ord", "size_gb": 1, "state": "creating"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", return_value=created),
            patch.object(volumes, "wait_for_volume", return_value={**created, "state": "destroying"}) as wait,
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        wait.assert_called_once_with(
            {}, "example", "vol_new", 60, stop_states=volumes.DEAD_STATES | volumes.DELETING_STATES
        )
        self.assertEqual(raised.exception.values["msg"], "Volume 'vol_new' in app 'example' was deleted while waiting")
        self.assertTrue(raised.exception.values["changed"])

    def test_creation_wait_timeout_reports_change(self):
        created = {"id": "vol_new", "name": "data", "region": "ord", "size_gb": 1, "state": "creating"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", return_value=created),
            patch.object(volumes, "wait_for_volume", return_value=created),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertEqual(raised.exception.values["msg"], "Creation of volume 'vol_new' in app 'example' timed out")
        self.assertTrue(raised.exception.values["changed"])

    def test_transition_wait_timeout_reports_no_change(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 1, "state": "extending"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
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
            patch.object(volumes, "api_request") as put,
            patch.object(volumes, "wait_for_volume", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes.ensure_present(module, {})

        put.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "Transition of volume 'vol_one' in app 'example' timed out")
        self.assertNotIn("changed", raised.exception.values)

    def test_sends_nonpositive_size_to_fly(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 0,
                "wait": False,
                "wait_timeout": 60,
            }
        )
        error = FlyioApiError("POST /apps/example/volumes failed: HTTP Error 400: Bad Request", status_code=400)

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", side_effect=error) as post,
            self.assertRaises(FlyioApiError),
        ):
            volumes.ensure_present(module, {})

        post.assert_called_once_with({}, "/apps/example/volumes", {"name": "data", "region": "ord", "size_gb": 0})

    def test_create_returns_volume_as_reported(self):
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": False,
                "wait_timeout": 60,
            }
        )
        created = {"encrypted": False, "id": "vol_one", "name": "data", "region": "ord", "size_gb": 2, "state": 1}

        with (
            patch.object(volumes, "find_volume", return_value=None),
            patch.object(volumes, "post_result", return_value=created),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], created)

    def test_extension_returns_response_as_reported(self):
        current = {"encrypted": True, "id": "vol_one", "size_gb": 1, "state": "created"}
        extended = {"id": "vol_one", "size_gb": 2, "state": False}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": None,
                "id": "vol_one",
                "name": None,
                "region": None,
                "size_gb": 2,
                "wait": False,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "api_request", return_value={"needs_restart": "yes", "volume": extended}),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], extended)
        self.assertEqual(raised.exception.values["needs_restart"], "yes")

    def test_delete_reports_change_for_any_response(self):
        current = {"id": "vol_one", "state": "created"}
        response = {"id": "vol_two", "state": "created"}
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
            patch.object(volumes, "delete_result", return_value=response),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["volume"], response)

    def test_delete_wait_failure_reports_change(self):
        current = {"id": "vol_one", "state": "created"}
        module = FakeModule(
            {
                "api_token": "token",
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        # The client boundary turns API errors after the delete into failures that report the change.
        with (
            patch.object(volumes, "find_volume", return_value=current),
            patch.object(volumes, "delete_result", return_value=None),
            patch.object(volumes, "wait_for_volume", side_effect=FlyioApiError("GET failed", status_code=500)),
            self.assertRaises(ModuleFail) as raised,
            volumes.flyio_client(module) as client,
        ):
            volumes.ensure_absent(module, client)

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["status_code"], 500)
