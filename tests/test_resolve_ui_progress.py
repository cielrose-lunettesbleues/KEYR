from __future__ import annotations

import unittest

from resolve_integration.resolve_app.ui_progress import (
    estimate_remaining_seconds,
    format_elapsed,
    heartbeat_text,
    progress_fill_x,
    progress_metrics_text,
    progress_percent,
    realtime_speed,
)


class ResolveUiProgressTests(unittest.TestCase):
    def test_progress_percent_clamps_and_handles_zero_total(self) -> None:
        self.assertEqual(progress_percent(0, 0), 0)
        self.assertEqual(progress_percent(1, 4), 25)
        self.assertEqual(progress_percent(10, 4), 100)
        self.assertEqual(progress_percent(-1, 4), 0)

    def test_progress_fill_x_scales_inside_bar(self) -> None:
        self.assertEqual(progress_fill_x(0, 360), 3)
        self.assertEqual(progress_fill_x(100, 360), 358)
        self.assertEqual(progress_fill_x(150, 360), 358)

    def test_heartbeat_text_adds_elapsed_when_stale(self) -> None:
        self.assertEqual(format_elapsed(7), "7s")
        self.assertEqual(format_elapsed(125), "2m05s")
        self.assertEqual(heartbeat_text("Transcription", 10, 15), "Transcription")
        self.assertEqual(heartbeat_text("Transcription", 75, 15), "Transcription\nToujours en cours depuis 1m15s...")

    def test_eta_helpers_compute_speed_and_remaining(self) -> None:
        self.assertEqual(realtime_speed(120, 60), 2.0)
        self.assertEqual(estimate_remaining_seconds(120, 300, 60), 90.0)
        self.assertIsNone(estimate_remaining_seconds(0, 300, 60))

    def test_progress_metrics_text_reports_eta_when_stable(self) -> None:
        self.assertEqual(progress_metrics_text(None, None, 42), "Écoulé: 42s")
        self.assertIn("estimation en cours", progress_metrics_text(10, 300, 10))
        text = progress_metrics_text(120, 300, 60)
        self.assertIn("Écoulé: 1m00s", text)
        self.assertIn("Vitesse: 2.0x temps réel", text)
        self.assertIn("Restant: ~1m30s restantes", text)


if __name__ == "__main__":
    unittest.main()
