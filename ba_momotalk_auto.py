import argparse
import io
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional acceleration only
    cv2 = None


BASE_W = 1920
BASE_H = 1080
DEFAULT_ADB = r"D:\MuMuPlayer-12.0\shell\adb.exe"
DEFAULT_SERIAL = "127.0.0.1:16384"


class StopAutomation(RuntimeError):
    pass


@dataclass
class Component:
    x: int
    y: int
    w: int
    h: int
    area: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


class BAAuto:
    def __init__(
        self,
        adb_path: str,
        serial: str,
        debug_dir: Path,
        max_rewards: int,
        max_steps: int,
        dry_run: bool = False,
    ) -> None:
        self.adb_path = adb_path
        self.serial = serial
        self.debug_dir = debug_dir
        self.max_rewards = max_rewards
        self.max_steps = max_steps
        self.dry_run = dry_run
        self.reward_count = 0
        self.step = 0
        self.blocked_rows: list[int] = []
        self.last_img: Image.Image | None = None
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        print(time.strftime("[%H:%M:%S]"), message, flush=True)

    def run_adb(self, args: list[str], *, capture: bool = False, timeout: int = 20) -> bytes:
        cmd = [self.adb_path]
        if args and args[0] not in {"connect", "devices", "start-server", "kill-server"}:
            cmd += ["-s", self.serial]
        cmd += args
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "ignore").strip()
            raise StopAutomation(f"adb failed: {' '.join(args)} :: {stderr}")
        return proc.stdout if capture else b""

    def connect(self) -> None:
        if not Path(self.adb_path).exists():
            raise StopAutomation(f"adb.exe not found: {self.adb_path}")
        self.log(f"connect adb {self.serial}")
        subprocess.run([self.adb_path, "connect", self.serial], check=False)

    def screenshot(self) -> Image.Image:
        raw = self.run_adb(["exec-out", "screencap", "-p"], capture=True, timeout=20)
        if len(raw) < 10000:
            raise StopAutomation("screenshot too small; MuMu/Blue Archive may not be ready")
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        self.last_img = img
        return img

    def save_debug(self, name: str = "last.png") -> None:
        if self.last_img is not None:
            self.last_img.save(self.debug_dir / name)

    def scale_xy(self, img: Image.Image, x: float, y: float) -> tuple[int, int]:
        w, h = img.size
        return round(x * w / BASE_W), round(y * h / BASE_H)

    def scale_rect(self, img: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        w, h = img.size
        x1, y1, x2, y2 = rect
        return (
            round(x1 * w / BASE_W),
            round(y1 * h / BASE_H),
            round(x2 * w / BASE_W),
            round(y2 * h / BASE_H),
        )

    def tap(self, img: Image.Image, x: float, y: float, label: str, delay: float = 1.0) -> None:
        tx, ty = self.scale_xy(img, x, y)
        self.log(f"tap {label} at {tx},{ty}")
        if not self.dry_run:
            self.run_adb(["shell", "input", "tap", str(tx), str(ty)], timeout=10)
        time.sleep(delay)

    def tap_abs(self, x: int, y: int, label: str, delay: float = 1.0) -> None:
        self.log(f"tap {label} at {x},{y}")
        if not self.dry_run:
            self.run_adb(["shell", "input", "tap", str(x), str(y)], timeout=10)
        time.sleep(delay)

    def swipe(self, img: Image.Image, x1: float, y1: float, x2: float, y2: float, label: str) -> None:
        ax, ay = self.scale_xy(img, x1, y1)
        bx, by = self.scale_xy(img, x2, y2)
        self.log(f"swipe {label} from {ax},{ay} to {bx},{by}")
        if not self.dry_run:
            self.run_adb(["shell", "input", "swipe", str(ax), str(ay), str(bx), str(by), "550"], timeout=10)
        time.sleep(1.2)

    def back(self, label: str, delay: float = 1.0) -> None:
        self.log(f"key BACK for {label}")
        if not self.dry_run:
            self.run_adb(["shell", "input", "keyevent", "4"], timeout=10)
        time.sleep(delay)

    def arr(self, img: Image.Image) -> np.ndarray:
        return np.asarray(img)

    def roi_mask_components(
        self,
        img: Image.Image,
        rect: tuple[int, int, int, int],
        mask_fn,
        min_area: int = 50,
    ) -> list[Component]:
        x1, y1, x2, y2 = self.scale_rect(img, rect)
        arr = self.arr(img)[y1:y2, x1:x2]
        if arr.size == 0:
            return []
        mask = mask_fn(arr)
        comps = self.components(mask, x1, y1)
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        return [c for c in comps if c.area >= int(min_area * scale * scale)]

    def components(self, mask: np.ndarray, x0: int, y0: int) -> list[Component]:
        mask_u8 = mask.astype(np.uint8)
        if cv2 is not None:
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, 8)
            comps: list[Component] = []
            for i in range(1, count):
                x, y, w, h, area = [int(v) for v in stats[i]]
                comps.append(Component(x0 + x, y0 + y, w, h, area))
            return comps

        height, width = mask_u8.shape
        visited = np.zeros_like(mask_u8, dtype=bool)
        comps = []
        ys, xs = np.nonzero(mask_u8)
        for sy, sx in zip(ys, xs):
            if visited[sy, sx]:
                continue
            stack = [(int(sx), int(sy))]
            visited[sy, sx] = True
            area = 0
            min_x = max_x = int(sx)
            min_y = max_y = int(sy)
            while stack:
                x, y = stack.pop()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for nx in (x - 1, x, x + 1):
                    for ny in (y - 1, y, y + 1):
                        if nx == x and ny == y:
                            continue
                        if 0 <= nx < width and 0 <= ny < height and mask_u8[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((nx, ny))
            comps.append(Component(x0 + min_x, y0 + min_y, max_x - min_x + 1, max_y - min_y + 1, area))
        return comps

    def is_momotalk(self, img: Image.Image) -> bool:
        x1, y1, x2, y2 = self.scale_rect(img, (170, 135, 1760, 265))
        part = self.arr(img)[y1:y2, x1:x2]
        if part.size == 0:
            return False
        r, g, b = part[..., 0], part[..., 1], part[..., 2]
        pink = (r > 235) & (g > 85) & (g < 190) & (b > 115) & (b < 215)
        return float(pink.mean()) > 0.20

    def is_story_screen(self, img: Image.Image) -> bool:
        comps = self.roi_mask_components(
            img,
            (1480, 15, 1905, 125),
            lambda a: (a[..., 0] > 225) & (a[..., 1] > 225) & (a[..., 2] > 225),
            min_area=2500,
        )
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        large_top_buttons = [
            c for c in comps if c.w >= 120 * scale and c.h >= 38 * scale and c.y < int(130 * img.size[1] / BASE_H)
        ]
        return len(large_top_buttons) >= 2

    def is_reward(self, img: Image.Image) -> bool:
        if self.is_story_screen(img):
            return False
        arr = self.arr(img)
        x1, y1, x2, y2 = self.scale_rect(img, (610, 185, 1310, 365))
        title = arr[y1:y2, x1:x2]
        tr, tg, tb = title[..., 0], title[..., 1], title[..., 2]
        yellow_title = (tr > 220) & (tg > 180) & (tb < 120)

        cx1, cy1, cx2, cy2 = self.scale_rect(img, (735, 350, 1215, 780))
        card = arr[cy1:cy2, cx1:cx2]
        cr, cg, cb = card[..., 0], card[..., 1], card[..., 2]
        reward_card = (cr > 215) & (cg > 215) & (cb > 215)

        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        return int(yellow_title.sum()) > int(8000 * scale * scale) and int(reward_card.sum()) > int(
            18000 * scale * scale
        )

    def find_unread_badges(self, img: Image.Image) -> list[Component]:
        comps = self.roi_mask_components(
            img,
            (440, 250, 1085, 980),
            lambda a: (a[..., 0] > 220) & (a[..., 1] < 105) & (a[..., 2] < 90),
            min_area=120,
        )
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        out = []
        for c in comps:
            if not (18 * scale <= c.w <= 72 * scale and 18 * scale <= c.h <= 72 * scale):
                continue
            if any(abs(c.cy - y) < 35 * scale for y in self.blocked_rows):
                continue
            out.append(c)
        out.sort(key=lambda c: (c.y, c.x))
        return out

    def find_reply_buttons(self, img: Image.Image) -> list[Component]:
        comps = self.roi_mask_components(
            img,
            (1110, 330, 1735, 945),
            lambda a: (a[..., 0] > 240) & (a[..., 1] > 240) & (a[..., 2] > 240),
            min_area=2500,
        )
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        buttons = []
        for c in comps:
            if 230 * scale <= c.w <= 620 * scale and 35 * scale <= c.h <= 120 * scale:
                if c.y > int(360 * img.size[1] / BASE_H):
                    buttons.append(c)
        buttons.sort(key=lambda c: (c.y, c.x))
        return buttons

    def find_cyan_buttons(self, img: Image.Image, rect: tuple[int, int, int, int]) -> list[Component]:
        comps = self.roi_mask_components(
            img,
            rect,
            lambda a: (a[..., 0] < 150) & (a[..., 1] > 170) & (a[..., 2] > 195),
            min_area=2500,
        )
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        buttons = []
        for c in comps:
            if c.w >= 170 * scale and c.h >= 35 * scale:
                buttons.append(c)
        buttons.sort(key=lambda c: (-c.area, c.y))
        return buttons

    def find_story_button(self, img: Image.Image) -> Component | None:
        buttons = self.find_cyan_buttons(img, (1010, 430, 1745, 980))
        pink_buttons = self.roi_mask_components(
            img,
            (1080, 330, 1745, 980),
            lambda a: (a[..., 0] > 225) & (a[..., 1] > 75) & (a[..., 1] < 180) & (a[..., 2] > 105) & (a[..., 2] < 220),
            min_area=1800,
        )
        scale = min(img.size[0] / BASE_W, img.size[1] / BASE_H)
        for c in pink_buttons:
            if c.w >= 170 * scale and c.h >= 35 * scale:
                buttons.append(c)
        if not buttons:
            return None
        buttons.sort(key=lambda c: (-c.area, c.y))
        return buttons[0]

    def find_confirm_button(self, img: Image.Image) -> Component | None:
        buttons = self.find_cyan_buttons(img, (760, 560, 1510, 900))
        if not buttons:
            return None
        buttons.sort(key=lambda c: (c.x, -c.area), reverse=True)
        return buttons[0]

    def open_momotalk(self) -> Image.Image:
        img = self.screenshot()
        if self.is_reward(img):
            self.collect_reward(img)
            img = self.screenshot()
            if self.is_momotalk(img):
                return img
        if self.is_momotalk(img):
            return img
        self.tap(img, 225, 225, "home MomoTalk", delay=1.4)
        img = self.screenshot()
        if self.is_momotalk(img):
            return img
        self.tap(img, 960, 540, "wake hidden home UI", delay=0.8)
        img = self.screenshot()
        if self.is_momotalk(img):
            return img
        self.tap(img, 225, 225, "home MomoTalk retry", delay=1.4)
        img = self.screenshot()
        if self.is_momotalk(img):
            return img

        self.log("MomoTalk did not open; trying story/reward recovery")
        recovered = self.skip_story()
        img = self.screenshot()
        if recovered and self.is_momotalk(img):
            return img
        if self.is_reward(img):
            self.collect_reward(img)
            img = self.screenshot()
            if self.is_momotalk(img):
                return img

        self.tap(img, 225, 225, "home MomoTalk after recovery", delay=1.4)
        img = self.screenshot()
        if not self.is_momotalk(img):
            raise StopAutomation("could not open MomoTalk from current screen")
        return img

    def ensure_unread_tab(self) -> Image.Image:
        img = self.screenshot()
        if not self.is_momotalk(img):
            return self.open_momotalk()
        self.tap(img, 260, 450, "unread tab", delay=0.9)
        return self.screenshot()

    def close_momotalk(self) -> None:
        img = self.screenshot()
        if self.is_momotalk(img):
            self.tap(img, 1685, 178, "MomoTalk close X", delay=1.0)

    def refresh_momotalk(self) -> Image.Image:
        self.close_momotalk()
        img = self.open_momotalk()
        self.blocked_rows = []
        return self.ensure_unread_tab()

    def process_current_chat(self) -> bool:
        for attempt in range(8):
            img = self.screenshot()
            if self.is_reward(img):
                self.collect_reward(img)
                return True
            if not self.is_momotalk(img):
                return self.skip_story()

            story = self.find_story_button(img)
            if story is not None:
                self.tap_abs(story.cx, story.cy, "story/enter bond button", delay=2.5)
                return self.after_story_button()

            replies = self.find_reply_buttons(img)
            if replies:
                reply = replies[0]
                self.tap_abs(reply.cx, reply.cy, "reply button", delay=1.5)
                return True

            if attempt == 3:
                self.swipe(img, 1450, 875, 1450, 500, "right chat area down")
            time.sleep(0.8)
        return False

    def after_story_button(self) -> bool:
        for _ in range(12):
            img = self.screenshot()
            if self.is_reward(img):
                self.collect_reward(img)
                return True
            if self.is_momotalk(img):
                story = self.find_story_button(img)
                if story is not None:
                    self.tap_abs(story.cx, story.cy, "story button second step", delay=2.5)
                    continue
                return True
            return self.skip_story()
        raise StopAutomation("story button did not lead to a recognizable story/reward state")

    def skip_story(self) -> bool:
        self.log("story state detected; attempting skip")
        time.sleep(1.5)
        for attempt in range(3):
            img = self.screenshot()
            if self.is_reward(img):
                self.collect_reward(img)
                return True
            if self.is_momotalk(img):
                return True
            self.back(f"story skip attempt {attempt + 1}", delay=1.0)
            img = self.screenshot()
            confirm = self.find_confirm_button(img)
            if confirm is not None:
                self.tap_abs(confirm.cx, confirm.cy, "confirm skip", delay=4.5)
                break
        for _ in range(30):
            img = self.screenshot()
            if self.is_reward(img):
                self.collect_reward(img)
                return True
            if self.is_momotalk(img):
                return True
            time.sleep(1.0)
        self.save_debug("stuck_after_skip.png")
        raise StopAutomation("story skip did not return to reward or MomoTalk")

    def collect_reward(self, img: Image.Image) -> None:
        self.reward_count += 1
        self.log(f"reward screen detected; total rewards={self.reward_count}")
        for i in range(4):
            self.tap(img, 960, 900, f"reward continue {i + 1}", delay=1.0)
            img = self.screenshot()
            if not self.is_reward(img):
                break
        self.refresh_momotalk()

    def select_next_unread(self) -> bool:
        img = self.screenshot()
        if not self.is_momotalk(img):
            img = self.open_momotalk()

        badges = self.find_unread_badges(img)
        empty_scrolls = 0
        while not badges and empty_scrolls < 5:
            self.log("no visible actionable unread red badge; scrolling unread list")
            self.swipe(img, 620, 900, 620, 390, "unread list down")
            self.blocked_rows = []
            img = self.screenshot()
            badges = self.find_unread_badges(img)
            empty_scrolls += 1
        if not badges:
            return False

        badge = badges[0]
        self.log(f"select unread row near y={badge.cy}")
        self.tap_abs(int(520 * img.size[0] / BASE_W), badge.cy, "unread student row", delay=1.4)
        if self.process_current_chat():
            return True

        self.log(f"row near y={badge.cy} had no actionable reply/story; skip this row for now")
        self.blocked_rows.append(badge.cy)
        return True

    def main_loop(self) -> None:
        self.connect()
        img = self.screenshot()
        if self.is_reward(img):
            self.collect_reward(img)
        img = self.open_momotalk()
        self.log(f"screenshot size {img.size[0]}x{img.size[1]}")
        self.ensure_unread_tab()

        no_progress = 0
        while self.step < self.max_steps and self.reward_count < self.max_rewards:
            self.step += 1
            self.log(f"step {self.step}")
            before_rewards = self.reward_count
            progressed = self.process_current_chat()
            if not progressed:
                progressed = self.select_next_unread()

            if not progressed:
                no_progress += 1
                self.log(f"no progress pass {no_progress}/4")
                if no_progress >= 4:
                    raise StopAutomation("no visible actionable unread rows after several refresh/scroll passes")
                self.blocked_rows = []
            else:
                no_progress = 0

            if self.reward_count > before_rewards:
                self.log(f"collected reward #{self.reward_count}")

        self.log(f"finished by limit: rewards={self.reward_count}, steps={self.step}")

    def self_test(self) -> None:
        self.connect()
        img = self.screenshot()
        img.save(self.debug_dir / "self_test.png")
        print(f"size={img.size[0]}x{img.size[1]}")
        print(f"is_momotalk={self.is_momotalk(img)}")
        print(f"is_reward={self.is_reward(img)}")
        print(f"unread_badges={[(c.x, c.y, c.w, c.h, c.area) for c in self.find_unread_badges(img)[:8]]}")
        print(f"reply_buttons={[(c.x, c.y, c.w, c.h, c.area) for c in self.find_reply_buttons(img)[:4]]}")
        story = self.find_story_button(img)
        print(f"story_button={(story.x, story.y, story.w, story.h, story.area) if story else None}")
        print(f"saved={self.debug_dir / 'self_test.png'}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blue Archive MomoTalk bond-story reward automation for MuMu.")
    parser.add_argument("--adb", default=DEFAULT_ADB)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--debug-dir", default="ba_momotalk_debug")
    parser.add_argument("--max-rewards", type=int, default=999)
    parser.add_argument("--max-steps", type=int, default=3000)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    bot = BAAuto(
        adb_path=args.adb,
        serial=args.serial,
        debug_dir=Path(args.debug_dir),
        max_rewards=args.max_rewards,
        max_steps=args.max_steps,
        dry_run=args.dry_run,
    )
    try:
        if args.self_test:
            bot.self_test()
        else:
            bot.main_loop()
        return 0
    except KeyboardInterrupt:
        bot.save_debug("interrupted.png")
        print("\nInterrupted by user. Last screenshot saved.", flush=True)
        return 130
    except StopAutomation as exc:
        bot.save_debug("stopped.png")
        print(f"\nSTOP: {exc}", flush=True)
        print(f"rewards={bot.reward_count}, steps={bot.step}", flush=True)
        print(f"last_screenshot={bot.debug_dir / 'stopped.png'}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
