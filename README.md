# Dipping Bird

![Dipping Bird](dippingbird.gif)

Fully-automated* coding for Aider (currently couched with asterisks)

- All entry is done in the background, you can keep your mouse and keyboard to yourself.
- Assumes Windows environment for now (Win 10 pro tested)
- Claude-3.5-sonnet recommended, only one that stays consistent long enough
  - but Aider supports local models too
- USE AT YOUR OWN RISK

```
# create your project repo
# init a venv or miniconda env
python -m venv venv
.\venv\Scripts\activate

# IDEALLY RUN THIS IN A SECURE VIRTUAL MACHINE AND NOT ON YOUR HOST LIKE A CRAZY PERSON

# install aider: https://aider.chat/
python -m pip install -U aider-chat
# set your env keys for anthropic and openai

# manually git init, Aider wont do it right afaik
git init

# copy /template folder into it and adjust/clean up GOALS.txt, ADVICE.txt, MODE.txt, STATUS.txt as needed (INSTRUCTIONS.txt can stay as is).  ADVICE.txt is your ongoing human feedback notes on the project

# ===== COPY/PASTE FROM HERE ON RERUNS:
.\venv\Scripts\activate

python -m aider --max-chat-history-tokens 100000 --no-gitignore --attribute-commit-message-author --sonnet

# add your files
/add INSTRUCTIONS.txt
  MODE.txt
  GOALS.txt
  README.md
  requirements.txt
  main.py
  STATUS.txt
  ADVICE.txt

# set INSTRUCTIONS.txt as read-only in aider if feeling paranoid
/read-only INSTRUCTIONS.txt
```

Then in a separate terminal, run:

```
python dippingbird.py
```
Though you'll likely have to adjust APP_TITLE to match your current aider session title.


## Admin Command Prompt auto-confirm (send "y")

This script can target an elevated Command Prompt window and periodically send a "y" followed by Enter. Detection was hardened:

- Prefers exact title matches, otherwise falls back to heuristics for elevated CMD (`ConsoleWindowClass`, titles starting with `Administrator:` and containing `Command Prompt`/`cmd`).
- Uses both `win32` and `uia` backends to find the window.
- Optionally tries to detect confirmation prompts via UI Automation before sending.

Environment variables you can set in the same CMD before running `python dippingbird.py`:

- `APP_TITLE`: Exact title prefix to match. Default: `Administrator: Command Prompt`.
- `APP_TITLE_CONTAINS`: Alternate substring to match in the title if not using `APP_TITLE`.
- `ALWAYS_SEND_Y`: If `true`, always sends `y` every interval. If `false`, attempt to detect Y/N prompts first. Default: `true`.
- `RUN_EVERY`: Interval in seconds between attempts. Default: `3`.
- `DISABLE_GIF`: If `true`, disables the GIF window. Default: `false`.
- `PERSISTENT`: If `true`, always sends based on base condition every interval (ignores staleness). Default: `false`.
- `STALE_SECONDS`: Consider the window stale after this many seconds of no text change via UIA snapshot; will send when stale unless `PERSISTENT=true`. Default: `60`.
- `REEVALUATION_ENABLED`: If `true`, occasionally sends a re-evaluation line instead of 'y'. Default: `false`.

Examples (Windows CMD):

```
set APP_TITLE=Administrator: Command Prompt
set ALWAYS_SEND_Y=true
set RUN_EVERY=2
set REEVALUATION_ENABLED=true
python dippingbird.py
```

If you prefer conditional sending only when a prompt is detected:

```
set ALWAYS_SEND_Y=false
python dippingbird.py

Interactive selection and persistent mode:

```
python dippingbird.py --select
set PERSISTENT=true
python dippingbird.py
```

Minimal send behavior (default):

- Sends one initial 'y' immediately on start.
- Sends one 'y' after `STALE_SECONDS` of inactivity (resets when the console text changes).
- Does not repeat 'y' while the window remains stale; waits for change then re-arms.
```

If detection struggles, run the helper to list likely windows:

```
python dippingbird.py --help
```


# TODO

- [ ] get it to recursively define new module folders with their own fractal repeat of this template, so each module can be worked on independently and fit context restrictions (these do way better on smaller projects)
- [ ] have it setup unit tests in a procedural way
- [ ] have it setup inspection tests for the human user to peruse asynchronously and checkpoint progress (e.g. just browse the folder, run program, provide feedback, and Aider just adjusts to your feedback)
- [ ] get this more rigorous, minimal and tested lol - this was entirely just naive first-pass that worked