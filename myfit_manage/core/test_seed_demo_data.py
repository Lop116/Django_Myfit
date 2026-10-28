import io

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.dashboard_services import get_dashboard_stats


class SeedDemoDataTests(TestCase):
    @override_settings(DEBUG=True)  # the test runner switches DEBUG off
    def test_seed_fills_every_dashboard_card_and_is_repeatable(self):
        call_command("seed_demo_data", stdout=io.StringIO())
        call_command("seed_demo_data", stdout=io.StringIO())  # second run must not duplicate or crash

        stats = get_dashboard_stats()

        self.assertEqual(stats["clients"]["total"], 5)
        self.assertEqual(stats["coaches"]["total"], 2)
        self.assertEqual(stats["branches"]["total"], 2)
        self.assertEqual(stats["memberships"]["active"], 2)
        self.assertEqual(stats["memberships"]["expired"], 1)
        self.assertEqual(stats["memberships"]["pending_requests"], 1)
        self.assertEqual(stats["classes"]["scheduled"], 3)
        self.assertEqual(stats["bookings"]["confirmed"], 2)
        self.assertEqual(stats["attendance"]["today"], 1)
        self.assertEqual(stats["support"]["open"], 1)

    @override_settings(DEBUG=False)
    def test_refuses_to_run_without_debug(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=io.StringIO())
