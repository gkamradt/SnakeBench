"""Offline browser regression for the Play AI turn loop. Run with Python Playwright."""
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ASSETS = Path(__file__).resolve().parent / "public"


class BrowserTickTest(unittest.TestCase):
    def test_corner_through_pending_step_and_late_plan(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.getenv("CHROME_CHANNEL"))
            page = browser.new_page()
            page.clock.install(time=datetime(2026, 1, 1, tzinfo=timezone.utc))
            page.clock.pause_at(datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc))
            human = dict(id="0", alive=True, score=0, direction="right", body=[[3, 7], [2, 7], [1, 7]])
            jev = dict(id="1", alive=True, score=0, direction="left", body=[[12, 4]])
            board = dict(width=16, height=12, snakes=[human, jev], apples=[], tick=0)
            game = dict(id="test", board=board, speeds={"Medium": 455}, roundLimit=450)
            steps, late_plans = [], []

            def respond(route):
                name = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
                if route.request.method == "GET":
                    route.fulfill(path=ASSETS / name)
                elif name in ("game", "state"):
                    route.fulfill(json=game)
                elif name == "plan" and board["tick"] == 2:
                    late_plans.append(route)
                elif name == "plan":
                    route.fulfill(json={"ready": True, "devCost": {"usd": 0.0012345, "partial": True}, "averageLatencyMs": 84.6})
                elif name == "step":
                    steps.append(route)
                else:
                    raise AssertionError(name)

            page.route("**/*", respond)
            page.goto("http://duel.test/duel/index.html")
            medium = page.get_by_role("button", name="Medium")
            medium.wait_for()
            plan_finished = lambda req: req.url.endswith("/plan")

            def wait_routes(routes, count):
                # The network event may arrive before its route handler runs.
                for _ in range(100):
                    if len(routes) >= count:
                        break
                    page.wait_for_timeout(10)
                self.assertEqual(len(routes), count)

            def accept(direction, head):
                wait_routes(steps, board["tick"] + 1)
                route = steps[-1]
                self.assertEqual(route.request.post_data_json["direction"], direction)
                human.update(direction=direction, body=[head, *human["body"][:-1]])
                board["tick"] += 1
                route.fulfill(json=game)

            def pixel():
                # Interior of the human's next head cell (3, 6).
                return page.locator("#board").evaluate(
                    "(c) => Array.from(c.getContext('2d').getImageData(210, 399, 1, 1).data)"
                )

            expect(page.locator("#latency")).to_have_text("—")
            empty = pixel()
            with page.expect_event("requestfinished", predicate=plan_finished):
                medium.dispatch_event("click")
            expect(page.locator("#latency")).to_have_text("85 ms")
            expect(page.locator("#cost")).to_have_text("$0.0012+")
            # All of these arrive before the first tick. Preserve Up, revise
            # its second turn from Right to Left, and ignore a reversal of Up.
            for key in ("ArrowUp", "ArrowRight", "ArrowLeft", "ArrowDown"):
                page.keyboard.press(key)
            page.clock.run_for(454)
            self.assertFalse(steps)
            page.clock.run_for(1)
            self.assertNotEqual(pixel(), empty)  # Visible before the step's HTTP response.
            # Left is still pending. It can be revised while Up is in flight.
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowLeft")
            page.dispatch_event("body", "keydown", {"key": "ArrowUp", "repeat": True})
            page.clock.run_for(100)
            with page.expect_event("requestfinished", predicate=plan_finished):
                accept("up", [3, 6])
            page.clock.run_for(354)
            self.assertEqual(len(steps), 1)
            with page.expect_request("**/step"):
                page.clock.run_for(1)
            with page.expect_request("**/plan"):
                accept("left", [2, 6])

            # A slow plan postpones one tick; the next gets a full interval.
            page.clock.run_for(700)
            self.assertEqual(len(steps), 2)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowLeft")
            wait_routes(late_plans, 1)
            with page.expect_request("**/step"):
                late_plans[0].fulfill(json={"ready": True})
            with page.expect_event("requestfinished", predicate=plan_finished):
                accept("down", [2, 7])
            page.clock.run_for(454)
            self.assertEqual(len(steps), 3)
            with page.expect_request("**/step"):
                page.clock.run_for(1)
            wait_routes(steps, 4)
            self.assertEqual(steps[-1].request.post_data_json["direction"], "left")
            page.locator("#pause").dispatch_event("click")
            with page.expect_event("requestfinished", predicate=lambda req: req.url.endswith("/state")):
                steps[-1].fulfill(status=503, json={"error": "Simulated network failure"})
            expect(page.get_by_role("button", name="Resume")).to_be_enabled()
            expect(page.locator("#round")).to_have_text("3")
            expect(page.locator("#message")).to_have_text("Simulated network failure")
            browser.close()


if __name__ == "__main__":
    unittest.main()
