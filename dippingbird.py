import time
import os
import threading
import pygame
from pywinauto import Application, Desktop
from PIL import Image, ImageSequence
import signal
import sys
import re
import random
import atexit
import subprocess
import hashlib

# Environment helpers
def _get_env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default

APP_TITLE = os.environ.get("APP_TITLE", "Administrator: Command Prompt")
APP_TITLE_CONTAINS = os.environ.get("APP_TITLE_CONTAINS", "")
ALWAYS_SEND_Y = _get_env_bool("ALWAYS_SEND_Y", True)
RUN_EVERY = _get_env_int("RUN_EVERY", 3)  # seconds
TARGET_HANDLE_ENV = os.environ.get("TARGET_HANDLE")
PERSISTENT = _get_env_bool("PERSISTENT", False)
STALE_SECONDS = _get_env_int("STALE_SECONDS", 60)
REEVALUATION_ENABLED = _get_env_bool("REEVALUATION_ENABLED", False)

REEVALUATION_MESSAGE = "Let's take a step back and re-evaluate if what we're doing makes sense. We might be getting in a loop here. Let's do something a little more out of left field instead."
REEVALUATION_CHANCE = 0.1

FORCE_EXIT_DELAY = 5  # seconds

GIF_PATH = 'dippingbird.gif'
DISABLE_GIF = False  # Set to True to disable the GIF display
WINDOW_SIZE = (300, 300)
FRAME_RATE = 60


# Event to manage thread termination
stop_event = threading.Event()

# Global flag for stopping
should_exit = False
SELECTED_HANDLE = None  # Preferred target window handle for this run

def list_open_windows():
    print("Listing all open windows (win32 backend):")
    try:
        windows = Desktop(backend="win32").windows()
        for w in windows:
            try:
                print(f"[{w.class_name()}] '{w.window_text()}' (pid={w.process_id()}, handle={hex(w.handle)})")
            except Exception:
                pass
    except Exception as e:
        print(f"Error listing win32 windows: {e}")
    print("Listing all open windows (uia backend):")
    try:
        windows = Desktop(backend="uia").windows()
        for w in windows:
            try:
                print(f"[{w.class_name()}] '{w.window_text()}' (pid={w.process_id()}, handle={hex(w.handle)})")
            except Exception:
                pass
    except Exception as e:
        print(f"Error listing uia windows: {e}")

# Connect to the command prompt window
def inspect_controls():
    try:
        print("Listing relevant windows:")
        windows = Desktop(backend="win32").windows()
        search_terms = ["administrator", "command", "prompt", "cmd", "aider"]
        
        filtered_windows = [
            w for w in windows
            if any(term.lower() in w.window_text().lower() for term in search_terms)
        ]
        
        for w in filtered_windows:
            print(f"[{w.class_name()}] '{w.window_text()}' (pid={w.process_id()}, handle={hex(w.handle)})")

    except Exception as e:
        print(f"Error listing windows: {e}")

def force_exit_now():
    print("\nForce exiting the script...")
    os._exit(1)

def handle_sigint(signum, frame):
    print("\nCTRL+C detected! Stopping the script...")
    cleanup()
    # Force exit after FORCE_EXIT_DELAY seconds (Windows-safe)
    threading.Timer(FORCE_EXIT_DELAY, force_exit_now).start()
    sys.exit(0)

# Check if the cmd output matches either the "> " or "[Yes]:"
def check_cmd_output():
    try:
        # Connect to the window
        app = Application().connect(title_re=f"^{re.escape(APP_TITLE)}.*")
        window = app.window(title_re=f"^{re.escape(APP_TITLE)}.*")
        
        # Access the text control inside the command prompt window
        text_control = window.child_window(control_type="Edit")  # The command prompt text area is usually an "Edit" control
        
        # Get the window text
        window_text = text_control.wrapper_object().texts()
        
        # Join all the window text lines into one string
        cmd_output = "\n".join(window_text).strip()
        
        # Print the last 20 lines for debugging
        print("\n".join(window_text[-20:]).strip())
        
        # Check if the command ends with "> " or "[Yes]:"
        if re.search(r"> *$", cmd_output) or cmd_output.endswith("[Yes]:"):
            return True
    except Exception as e:
        print(f"Error reading window: {e}")
    return False


def _window_title_matches(title: str) -> bool:
    if not title:
        return False
    title_lower = title.lower()
    # Allow explicit APP_TITLE prefix match
    if APP_TITLE and title.startswith(APP_TITLE):
        return True
    # Allow partial contains
    if APP_TITLE_CONTAINS and APP_TITLE_CONTAINS.lower() in title_lower:
        return True
    # Default heuristic: Elevated Command Prompt
    return title_lower.startswith("administrator:") and ("command prompt" in title_lower or "cmd" in title_lower)

def _find_target_window_win32():
    try:
        candidates = []
        for w in Desktop(backend="win32").windows():
            try:
                if w.class_name() == "ConsoleWindowClass" and _window_title_matches(w.window_text()):
                    candidates.append(w)
            except Exception:
                continue
        return candidates
    except Exception:
        return []

def _find_target_window_uia():
    try:
        candidates = []
        for w in Desktop(backend="uia").windows():
            try:
                if _window_title_matches(w.window_text()):
                    candidates.append(w)
            except Exception:
                continue
        return candidates
    except Exception:
        return []

def _parse_handle(value: str):
    if value is None:
        return None
    v = value.strip().lower()
    try:
        if v.startswith("0x"):
            return int(v, 16)
        return int(v)
    except Exception:
        return None

def _connect_window_by_handle(handle: int):
    if handle is None:
        return None
    # Try win32 first
    try:
        app = Application(backend="win32").connect(handle=handle)
        return app.window(handle=handle)
    except Exception:
        pass
    # Fallback UIA
    try:
        app = Application(backend="uia").connect(handle=handle)
        return app.window(handle=handle)
    except Exception:
        return None

def find_target_window():
    # 1) Prefer explicitly selected handle
    if SELECTED_HANDLE is not None:
        wnd = _connect_window_by_handle(SELECTED_HANDLE)
        if wnd is not None:
            return wnd
    # 2) Prefer TARGET_HANDLE env var
    env_handle = _parse_handle(TARGET_HANDLE_ENV)
    if env_handle is not None:
        wnd = _connect_window_by_handle(env_handle)
        if wnd is not None:
            return wnd
    # Prefer exact/regex via Application if APP_TITLE is provided
    try:
        if APP_TITLE:
            try:
                app = Application(backend="win32").connect(title_re=f"^{re.escape(APP_TITLE)}.*")
                return app.window(title_re=f"^{re.escape(APP_TITLE)}.*")
            except Exception:
                pass
    except Exception:
        pass

    # Heuristic search
    win32_candidates = _find_target_window_win32()
    if win32_candidates:
        return win32_candidates[0]
    uia_candidates = _find_target_window_uia()
    if uia_candidates:
        return uia_candidates[0]
    return None

def _gather_candidate_windows():
    seen = set()
    candidates = []
    # win32
    try:
        for w in Desktop(backend="win32").windows():
            try:
                title = w.window_text()
                cls = w.class_name()
                handle = w.handle
                if handle in seen:
                    continue
                if _window_title_matches(title) or cls == "ConsoleWindowClass":
                    seen.add(handle)
                    candidates.append((handle, cls, title, "win32"))
            except Exception:
                continue
    except Exception:
        pass
    # uia
    try:
        for w in Desktop(backend="uia").windows():
            try:
                title = w.window_text()
                cls = w.class_name()
                handle = w.handle
                if handle in seen:
                    continue
                if _window_title_matches(title):
                    seen.add(handle)
                    candidates.append((handle, cls, title, "uia"))
            except Exception:
                continue
    except Exception:
        pass
    return candidates

def list_candidates():
    print("Candidate windows (best guess first):")
    candidates = _gather_candidate_windows()
    if not candidates:
        print("  <none>")
        return
    for idx, (handle, cls, title, backend) in enumerate(candidates):
        print(f"[{idx}] handle={hex(handle)} class={cls} backend={backend} title='{title}'")

def interactive_select():
    global SELECTED_HANDLE
    candidates = _gather_candidate_windows()
    if not candidates:
        print("No candidate windows found.")
        return
    print("Select a window to target with dippingbird:")
    for idx, (handle, cls, title, backend) in enumerate(candidates):
        print(f"[{idx}] handle={hex(handle)} class={cls} backend={backend} title='{title}'")
    while True:
        try:
            raw = input("Enter number (or 'q' to cancel): ").strip()
            if raw.lower() in {"q", "quit", "exit"}:
                print("Selection cancelled.")
                return
            sel = int(raw)
            if 0 <= sel < len(candidates):
                SELECTED_HANDLE = candidates[sel][0]
                print(f"Selected handle {hex(SELECTED_HANDLE)}")
                return
            else:
                print("Out of range, try again.")
        except ValueError:
            print("Invalid input, enter a number.")

def _detect_confirmation_prompt(uia_window) -> bool:
    try:
        # Try to scan text-like descendants for common Y/N prompts
        texts = []
        for ctrl in uia_window.descendants(control_type="Text"):
            try:
                t = ctrl.window_text()
                if t:
                    texts.append(t)
            except Exception:
                continue
        if not texts:
            # Fallback: sometimes the console exposes its whole buffer as name
            try:
                t = uia_window.window_text()
                if t:
                    texts.append(t)
            except Exception:
                pass
        haystack = "\n".join(texts)
        if not haystack:
            return False
        patterns = [
            r"\(y/n\)\s*\?*$",
            r"\[y/n\]\s*\?*$",
            r"\[yes\]:\s*$",
            r"are you sure.*\(y/n\).*?$",
        ]
        for pat in patterns:
            if re.search(pat, haystack, re.IGNORECASE | re.MULTILINE):
                return True
        return False
    except Exception:
        return False

def _read_console_text_snapshot_by_handle(handle: int) -> str:
    try:
        uia_app = Application(backend="uia").connect(handle=handle)
        uia_window = uia_app.window(handle=handle)
    except Exception:
        return ""
    try:
        texts = []
        for ctrl in uia_window.descendants(control_type="Text"):
            try:
                t = ctrl.window_text()
                if t:
                    texts.append(t)
            except Exception:
                continue
        if not texts:
            try:
                t = uia_window.window_text()
                if t:
                    texts.append(t)
            except Exception:
                pass
        return "\n".join(texts)
    except Exception:
        return ""

def send_keys_if_match():
    global should_exit
    start_time = time.time()
    interval = RUN_EVERY
    last_check = -interval
    last_snapshot_hash = None
    last_change_ts = time.time()
    initial_sent = False
    sent_during_current_stale = False
    while not should_exit and not stop_event.is_set():
        try:
            # Check the command output every second
            if stop_event.wait(1):  # Wait for 1 second or until stop_event is set
                break
            rounded_time = round(time.time() - start_time)
            if rounded_time > last_check + interval:
                window = find_target_window()
                if window is None:
                    print("No matching admin Command Prompt window found.")
                    last_check = rounded_time
                    continue

                # Update staleness based on UIA snapshot
                snapshot = _read_console_text_snapshot_by_handle(window.handle)
                if snapshot:
                    new_hash = hashlib.sha1(snapshot.encode("utf-8", errors="ignore")).hexdigest()
                    if new_hash != last_snapshot_hash:
                        last_snapshot_hash = new_hash
                        last_change_ts = time.time()
                        # Reset per-stale-cycle state on any change
                        sent_during_current_stale = False
                stale_secs = time.time() - last_change_ts

                # Minimal behavior:
                # 1) Send initial 'y' immediately once
                if not initial_sent:
                    if REEVALUATION_ENABLED and (random.random() < REEVALUATION_CHANCE):
                        window.send_keystrokes(REEVALUATION_MESSAGE + "{ENTER}")
                        print(f"{rounded_time}  sent re-eval (initial)")
                    else:
                        window.send_keystrokes("y{ENTER}")
                        print(f"{rounded_time}  sent 'y' (initial)")
                    initial_sent = True
                    last_check = rounded_time
                    continue

                # 2) After STALE_SECONDS of no changes, send one 'y' then wait for change or next stale window
                is_stale = stale_secs >= STALE_SECONDS
                should_send = False
                if PERSISTENT:
                    should_send = True
                else:
                    if is_stale and not sent_during_current_stale:
                        should_send = True

                if should_send:
                    if REEVALUATION_ENABLED and (random.random() < REEVALUATION_CHANCE):
                        window.send_keystrokes(REEVALUATION_MESSAGE + "{ENTER}")
                        print(f"{rounded_time}  sent re-eval")
                    else:
                        window.send_keystrokes("y{ENTER}")
                        if PERSISTENT:
                            print(f"{rounded_time}  sent 'y' (persistent mode)")
                        else:
                            sent_during_current_stale = True
                            print(f"{rounded_time}  sent 'y' (stale for ~{int(stale_secs)}s)")
                else:
                    reason = "active < stale threshold" if not PERSISTENT else "cond false"
                    print(f"{rounded_time}  skipping send ({reason})")
                last_check = rounded_time
            time.sleep(1)
        except Exception as e:
            print(f"Error sending keys: {e}")
            time.sleep(60)

class DippingBirdGIF:
    def __init__(self):
        self.screen = None
        self.frames = []
        self.durations = []
        self.current_frame = 0
        self.frame_time = 0
        self.clock = pygame.time.Clock()

    def setup(self):
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Dipping Bird")

        if not os.path.exists(GIF_PATH):
            print(f"Error: '{GIF_PATH}' not found.")
            return False

        gif = Image.open(GIF_PATH)
        self.durations = [frame.info['duration'] for frame in ImageSequence.Iterator(gif)]
        self.frames = [pygame.image.fromstring(frame.convert("RGBA").tobytes(), frame.size, "RGBA") for frame in ImageSequence.Iterator(gif)]
        return True

    def update(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        self.screen.fill((255, 255, 255))

        frame = self.frames[self.current_frame]
        duration = self.durations[self.current_frame]

        frame_rect = frame.get_rect(center=(WINDOW_SIZE[0]//2, WINDOW_SIZE[1]//2))
        self.screen.blit(frame, frame_rect)

        pygame.display.flip()

        self.frame_time += self.clock.tick(FRAME_RATE)
        if self.frame_time > duration:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.frame_time = 0

        return True

def cleanup():
    global should_exit
    should_exit = True
    stop_event.set()
    pygame.quit()
    print("Cleanup complete.")

def main():
    global should_exit
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)
    atexit.register(cleanup)

    # Initialize pygame in the main thread
    if not DISABLE_GIF:
        pygame.init()

    key_thread = threading.Thread(target=send_keys_if_match, daemon=True)
    key_thread.start()

    if not DISABLE_GIF:
        dipping_bird = DippingBirdGIF()
        if not dipping_bird.setup():
            cleanup()
            return

    try:
        while not should_exit and not stop_event.is_set():
            if not DISABLE_GIF:
                if not dipping_bird.update():
                    break
                if stop_event.wait(1/60):  # Wait for 1/60 second or until stop_event is set
                    break
            else:
                if stop_event.wait(1):  # Wait for 1 second or until stop_event is set when GIF is disabled
                    break
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected, exiting...")
    finally:
        cleanup()
        key_thread.join(timeout=2)
        print("Key thread terminated.")
        # Force exit after cleanup
        os._exit(0)

def _apply_cli_overrides(argv):
    global REEVALUATION_ENABLED, PERSISTENT, STALE_SECONDS, RUN_EVERY, ALWAYS_SEND_Y
    global APP_TITLE, APP_TITLE_CONTAINS, SELECTED_HANDLE, TARGET_HANDLE_ENV
    # Recognized forms:
    # --no-reeval, --persistent, --stale=60, --interval=3, --always[=true|false]
    # --title=... --contains=... --handle=0x1234
    for arg in argv:
        if arg == "--no-reeval":
            REEVALUATION_ENABLED = False
        elif arg == "--persistent":
            PERSISTENT = True
        elif arg.startswith("--stale="):
            try:
                STALE_SECONDS = int(arg.split("=", 1)[1])
            except Exception:
                pass
        elif arg.startswith("--interval="):
            try:
                RUN_EVERY = int(arg.split("=", 1)[1])
            except Exception:
                pass
        elif arg == "--always":
            ALWAYS_SEND_Y = True
        elif arg.startswith("--always="):
            val = arg.split("=", 1)[1].strip().lower()
            ALWAYS_SEND_Y = val in {"1", "true", "yes", "y", "on"}
        elif arg.startswith("--title="):
            APP_TITLE = arg.split("=", 1)[1]
        elif arg.startswith("--contains="):
            APP_TITLE_CONTAINS = arg.split("=", 1)[1]
        elif arg.startswith("--handle="):
            val = arg.split("=", 1)[1]
            TARGET_HANDLE_ENV = val
        # --help/--list/--select are handled below


if __name__ == "__main__":
    # CLI: combine simple actions with overrides
    args = sys.argv[1:]
    if args:
        if "--help" in args:
            inspect_controls()
            sys.exit(0)
        if "--list" in args:
            list_candidates()
            sys.exit(0)
        if "--select" in args:
            interactive_select()
            # continue to main after selection
        _apply_cli_overrides(args)
    main()
