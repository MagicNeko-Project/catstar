#!/usr/bin/env python3
"""Unix Easter Eggs Collection.

A terminal utility replicating authentic Unix easter egg behaviors for direct
command execution (such as `sl`, `apt-get moo`, `make love`, `cmatrix`, `sudo`)
while providing an interactive TUI menu and trivia quiz.
"""

from __future__ import annotations

import curses
import getpass
import math
import os
import random
import sys
import textwrap
import time
import webbrowser
from dataclasses import dataclass
from typing import ClassVar

# -----------------------------------------------------------------------------
# 1. ASCII Art & Data Assets
# -----------------------------------------------------------------------------

SL_LOCOMOTIVE_FRAME_1: list[str] = [
    "      ======  _____    _________ ",
    "  ========  _  | [] |  |  ___   |",
    " ========  (_) |____|  | |   |  |",
    "====  _________________|_|___|__|",
    " |___/   [O] [O] [O] [O]   \\____|",
    "   \\(o)-----------------(o)/     ",
]

SL_LOCOMOTIVE_FRAME_2: list[str] = [
    "      ======  _____    _________ ",
    "  ========  _  | [] |  |  ___   |",
    " ========  (_) |____|  | |   |  |",
    "====  _________________|_|___|__|",
    " |___/   (O) (O) (O) (O)   \\____|",
    "   /(o)-----------------(o)\\     ",
]

SL_LITTLE_FRAME_1: list[str] = [
    "    ==== _____ ",
    "  === _  |[]| |",
    "==  ___|_|__|_|",
    " | / [O] [O] \\|",
]

SL_LITTLE_FRAME_2: list[str] = [
    "    ==== _____ ",
    "  === _  |[]| |",
    "==  ___|_|__|_|",
    " | / (O) (O) \\|",
]

APT_COW_ART: str = r"""         (__) 
         (oo) 
   /------\/ 
  / |    ||  
 *  ||---||  
    ~~   ~~  
"Have you mooed today?"
"""

APT_BUILD_COW_ART: str = r"""                    ____ 
          (__)    /     \
          (oo)   |  ~~~  |
    /------\/    |  ~~~  |
   / |    ||      \_____/
  *  ||---||
     ~~   ~~
"Have you spapped today?"
"""

APTITUDE_COW_LEVELS: list[str] = [
    "There are no Easter Eggs in this program.",
    "Really, there are no Easter Eggs in this program.",
    "Didn't I already tell you that there are no Easter Eggs in this program?",
    "Stop it!",
    "OK, ok, if I give you an Easter Egg, will you go away?",
    r"""All right, you win.

                               User-friendly..o
                              /
                     .---.   .
                    /     \  |
                   | () () |/
                    \  ^  /
                     |||||
                     |||||""",
    "What is it?  It's an elephant being eaten by a snake, of course.",
]

SUDO_INSULTS: list[str] = [
    "Just what do you think you're doing Dave?",
    "It can only be attributed to human error.",
    "That's something I cannot allow to happen.",
    "My brain is going. I can feel it.",
    "Listen, hackette, back off before I drop your core.",
    "Take a stress pill and think it over.",
    "Maybe computer programming isn't for you.",
    "Wrong! You stupid mortal.",
    "I've seen pets with more talent.",
    "If I had a brain cell for every bad command you typed, I'd have... one.",
    "Speak English, user! We don't speak your dialect.",
    "Are you typing with your elbows?",
    "You have the terminal velocity of a dead penguin.",
]

ZEN_OF_PYTHON: list[str] = [
    "The Zen of Python, by Tim Peters",
    "",
    "Beautiful is better than ugly.",
    "Explicit is better than implicit.",
    "Simple is better than complex.",
    "Complex is better than complicated.",
    "Flat is better than nested.",
    "Sparse is better than dense.",
    "Readability counts.",
    "Special cases aren't special enough to break the rules.",
    "Although practicality beats purity.",
    "Errors should never pass silently.",
    "Unless explicitly silenced.",
    "In the face of ambiguity, refuse the temptation to guess.",
    "There should be one-- and preferably only one --obvious way to do it.",
    "Although that way may not be obvious at first unless you're Dutch.",
    "Now is better than never.",
    "Although never is often better than *right* now.",
    "If the implementation is hard to explain, it's a bad idea.",
    "If the implementation is easy to explain, it may be a good idea.",
    "Namespaces are one honking great idea -- let's do more of those!",
]

VIM_HELP_ENTRIES: dict[str, list[str]] = {
    "42": [
        "*42* The Answer",
        "",
        "42",
        "",
        "What is the meaning of life, the universe, and everything?",
        "  -> 42",
        "",
        "Douglas Adams, the only person who figured out this question,",
        "now rests in peace.  Let's keep his memory alive.",
    ],
    "holy-wars": [
        "*holy-wars*",
        "",
        "The religious wars between Vi and Emacs supporters have raged for decades.",
        "Vi is lightweight, modal, and ubiquitous across every Unix terminal.",
        "Emacs is an operating system masquerading as a text editor.",
        "Both agree that nano is just a visitor.",
    ],
    "quotes": [
        "*quotes*",
        "",
        "\"Vim is like a piano. When you're good, you make music; when you're not,",
        ' you make terrible noise."',
        "",
        '"To exit Vim, simply reboot your computer, or buy a new laptop."',
    ],
}

NYAN_CAT_FRAMES: list[str] = [
    r"""
+------->  =^.^=  ~*~*~*~*~*~*~*
|  ~*~*~   (____)____)  ~*~*~*~
""",
    r"""
+------->   =^.^= ~*~*~*~*~*~*~*
|  *~*~*   (____)____)   *~*~*~
""",
]

FORTUNE_COOKIES: list[str] = [
    "You will inherit a large git repository with zero merge conflicts.",
    "A computer will do what you tell it to do, not what you want it to do.",
    "There are only 10 types of people: those who understand binary and those who don't.",
    "Never let your computer know you are in a rush.",
    "In Unix, everything is a file; in Linux, everything is a process trying to open that file.",
    "Don't worry if it doesn't work right. If everything did, you'd be out of a job.",
    "Real programmers count from 0.",
]

TRIVIA_QUESTIONS: list[dict[str, object]] = [
    {
        "question": "What happens when you execute ':help 42' in Vim?",
        "options": [
            "A) Displays '42 - The Answer to Life, the Universe, and Everything.'",
            "B) Replaces the active buffer with 42 spaces",
            "C) Immediately quits Vim with exit code 42",
            "D) Displays changelog for Vim version 4.2",
        ],
        "answer": 0,
        "explanation": "Reference to Douglas Adams' Hitchhiker's Guide to the Galaxy in Vim documentation.",
    },
    {
        "question": "What happens when you run 'apt-get moo' in Debian/Ubuntu systems?",
        "options": [
            "A) Installs the 'cowsay' package automatically",
            "B) Prints an ASCII cow asking 'Have you mooed today?'",
            "C) Throws a 'Permission Denied: Superuser access required' error",
            "D) Plays an audio sample of a cow mooing",
        ],
        "answer": 1,
        "explanation": "APT includes an ASCII cow easter egg responding to the 'moo' subcommand.",
    },
    {
        "question": "What occurs when you run 'import antigravity' in a Python 3 REPL?",
        "options": [
            "A) Disables physics calculations in math module",
            "B) Opens XKCD comic #353 ('Python') in your web browser",
            "C) Throws a ModuleNotFoundError exception",
            "D) Flips all terminal text upside down",
        ],
        "answer": 1,
        "explanation": "Standard Python module 'antigravity' opens XKCD comic #353 in a web browser.",
    },
    {
        "question": "What easter egg is triggered by typing 'M-x butterfly' in Emacs?",
        "options": [
            "A) Renders a colorful ASCII butterfly",
            "B) Opens the GNU Emacs bug tracker",
            "C) References XKCD #378: Real programmers flip bits using butterflies",
            "D) Launches a hidden Emacs flight simulator game",
        ],
        "answer": 2,
        "explanation": "Emacs 'M-x butterfly' flips a bit on disk by leveraging cosmic rays & butterflies.",
    },
    {
        "question": "What happens if you run 'aptitude -vvvvv moo'?",
        "options": [
            "A) Prints an ASCII cow carrying a user-friendly animal on its back",
            "B) Repeatedly prints 'Moo! Moo! Moo!' 5 times",
            "C) Reboots the machine",
            "D) Displays: 'There are REALLY no easter eggs!'",
        ],
        "answer": 0,
        "explanation": "Progressively adding '-v' flags to 'aptitude moo' eventually reveals the hidden cow egg.",
    },
    {
        "question": "Which Vim command opens documentation on the Vi vs Emacs editor rivalry?",
        "options": [
            "A) :help flame-wars",
            "B) :help holy-wars",
            "C) :help editor-fight",
            "D) :help emacs-vs-vim",
        ],
        "answer": 1,
        "explanation": "Vim's ':help holy-wars' provides a humorous history of the editor wars.",
    },
    {
        "question": "What message is produced when running 'make love' in GNU Make?",
        "options": [
            "A) 'make: *** No rule to make target 'love'.  Stop.'",
            "B) 'make: Love made successfully.'",
            "C) 'make: Permission denied.'",
            "D) Compiles 'love.c' if present",
        ],
        "answer": 0,
        "explanation": "GNU Make responds with standard error '*** No rule to make target 'love'.  Stop.'",
    },
    {
        "question": "Which Python module prints 'Hello world!' directly from frozen C bytecode?",
        "options": [
            "A) import hello",
            "B) import __hello__",
            "C) import print_hello",
            "D) import stdio",
        ],
        "answer": 1,
        "explanation": "Python includes a frozen module '__hello__' compiled into C bytecode.",
    },
]


# -----------------------------------------------------------------------------
# 2. Terminal & Curses Helpers
# -----------------------------------------------------------------------------


def safe_curs_set(visibility: int) -> None:
    """Safely set cursor visibility, ignoring curses errors when unsupported."""
    try:
        curses.curs_set(visibility)
    except curses.error:
        pass


def safe_echo(enable: bool) -> None:
    """Safely toggle echo mode."""
    try:
        if enable:
            curses.echo()
        else:
            curses.noecho()
    except curses.error:
        pass


def safe_init_colors(count: int = 7) -> bool:
    """Safely initialize curses color pairs if supported."""
    try:
        if curses.has_colors():
            curses.start_color()
            for idx in range(1, count):
                try:
                    curses.init_pair(idx, idx, curses.COLOR_BLACK)
                except curses.error:
                    pass
            return True
    except curses.error:
        pass
    return False


def safe_color_pair(pair_number: int, fallback_attr: int = curses.A_NORMAL) -> int:
    """Safely get a curses color pair attribute or return fallback."""
    try:
        if curses.has_colors():
            return curses.color_pair(pair_number)
    except curses.error:
        pass
    return fallback_attr


def safe_addstr(
    stdscr: curses.window, y: int, x: int, text: str, attr: int = 0
) -> None:
    """Write string to curses window safely without throwing boundary exceptions."""
    try:
        height, width = stdscr.getmaxyx()
        if 0 <= y < height and 0 <= x < width:
            max_len: int = max(0, width - x - (1 if y == height - 1 else 0))
            if max_len > 0:
                stdscr.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def display_scrollable_text(
    stdscr: curses.window, title: str, lines: list[str]
) -> None:
    """Display paginated or scrollable text viewer with vim/arrow navigation."""
    safe_curs_set(0)
    stdscr.nodelay(False)

    height, _ = stdscr.getmaxyx()
    scroll_offset: int = 0
    visible_height: int = max(1, height - 4)

    while True:
        stdscr.clear()
        height, _ = stdscr.getmaxyx()
        visible_height = max(1, height - 4)
        safe_addstr(stdscr, 0, 0, f"=== {title} ===", curses.A_BOLD)

        for idx in range(visible_height):
            line_idx: int = scroll_offset + idx
            if line_idx < len(lines):
                safe_addstr(stdscr, idx + 2, 0, lines[line_idx])

        status: str = "Use [Up/Down/j/k] to scroll. Press 'q' or 'ESC' to return."
        safe_addstr(stdscr, height - 1, 0, status, curses.A_REVERSE)

        stdscr.refresh()
        key: int = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k"), ord("K")) and scroll_offset > 0:
            scroll_offset -= 1
        elif key in (
            curses.KEY_DOWN,
            ord("j"),
            ord("J"),
        ) and scroll_offset + visible_height < len(lines):
            scroll_offset += 1


# -----------------------------------------------------------------------------
# 3. Base Easter Egg Definition
# -----------------------------------------------------------------------------


@dataclass
class EasterEgg:
    """Base class for Unix Easter Eggs."""

    name: str
    aliases: list[str]
    description: str

    def execute(self, args: list[str]) -> int:
        """Run the easter egg directly simulating the command.

        Returns shell exit code.
        """
        raise NotImplementedError

    def interactive(self, stdscr: curses.window) -> None:
        """Run the interactive curses interface for TUI menu usage."""
        raise NotImplementedError


# -----------------------------------------------------------------------------
# 4. Domain Easter Egg Implementations
# -----------------------------------------------------------------------------


class SteamLocomotive(EasterEgg):
    """Steam Locomotive (sl) animation across terminal."""

    def __init__(self) -> None:
        super().__init__(
            name="Steam Locomotive (sl)",
            aliases=["sl", "LS", "lss"],
            description="ASCII steam train running across screen",
        )

    def execute(self, args: list[str]) -> int:
        accident: bool = "-a" in args
        little: bool = "-l" in args
        flying: bool = "-F" in args

        def run(stdscr: curses.window) -> None:
            self._animate(
                stdscr=stdscr, accident=accident, little=little, flying=flying
            )

        curses.wrapper(run)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        self._animate(stdscr=stdscr, accident=False, little=False, flying=False)

    def _animate(
        self,
        stdscr: curses.window,
        accident: bool = False,
        little: bool = False,
        flying: bool = False,
    ) -> None:
        safe_curs_set(0)
        stdscr.nodelay(True)

        try:
            height, width = stdscr.getmaxyx()

            frames: list[list[str]] = (
                [SL_LITTLE_FRAME_1, SL_LITTLE_FRAME_2]
                if little
                else [SL_LOCOMOTIVE_FRAME_1, SL_LOCOMOTIVE_FRAME_2]
            )

            train_width: int = max(len(line) for line in frames[0])
            train_height: int = len(frames[0])

            start_y: int = (
                height - train_height - 1
                if flying
                else max(0, (height - train_height) // 2)
            )
            start_x: int = width - 1

            frame_toggle: bool = False

            while start_x > -train_width:
                stdscr.clear()

                key: int = stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break

                current_frame: list[str] = frames[0] if frame_toggle else frames[1]
                frame_toggle = not frame_toggle

                cur_y: int = start_y
                if flying:
                    cur_y = max(
                        0,
                        int(
                            start_y * ((start_x + train_width) / (width + train_width))
                        ),
                    )

                for row_idx, line in enumerate(current_frame):
                    target_y: int = cur_y + row_idx
                    if 0 <= target_y < height:
                        for col_idx, char in enumerate(line):
                            target_x: int = start_x + col_idx
                            if 0 <= target_x < width:
                                try:
                                    stdscr.addch(target_y, target_x, char)
                                except curses.error:
                                    pass

                if accident:
                    safe_addstr(
                        stdscr,
                        max(0, cur_y - 1),
                        max(0, start_x + 5),
                        "HELP! HELP!",
                        curses.A_BOLD,
                    )

                stdscr.refresh()
                time.sleep(0.04)
                start_x -= 2
        finally:
            stdscr.nodelay(False)


class MatrixDigitalRain(EasterEgg):
    """Falling Matrix green digital rain animation."""

    def __init__(self) -> None:
        super().__init__(
            name="Matrix Digital Rain",
            aliases=["cmatrix", "matrix"],
            description="Falling green digital matrix characters",
        )

    def execute(self, args: list[str]) -> int:
        curses.wrapper(self._animate)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        self._animate(stdscr)

    def _animate(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(True)

        try:
            safe_init_colors(3)

            height, width = stdscr.getmaxyx()
            columns: list[int] = [random.randint(-height, 0) for _ in range(width)]
            characters: list[str] = [
                "a",
                "b",
                "c",
                "d",
                "e",
                "f",
                "0",
                "1",
                "2",
                "3",
                "@",
                "#",
                "$",
                "%",
                "&",
            ]

            while True:
                key: int = stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break

                for col in range(0, width, 2):
                    y_pos: int = columns[col]
                    if 0 <= y_pos < height:
                        char: str = random.choice(characters)
                        attr = safe_color_pair(2, fallback_attr=curses.A_BOLD)
                        try:
                            stdscr.addch(y_pos, col, char, attr)
                        except curses.error:
                            pass

                    trail_y: int = y_pos - 1
                    if 0 <= trail_y < height:
                        char = random.choice(characters)
                        attr = safe_color_pair(1, fallback_attr=curses.A_NORMAL)
                        try:
                            stdscr.addch(trail_y, col, char, attr)
                        except curses.error:
                            pass

                    erase_y: int = y_pos - random.randint(8, 18)
                    if 0 <= erase_y < height:
                        try:
                            stdscr.addch(erase_y, col, " ")
                        except curses.error:
                            pass

                    columns[col] += 1
                    if columns[col] - 18 > height:
                        columns[col] = random.randint(-10, 0)

                stdscr.refresh()
                time.sleep(0.05)
        finally:
            stdscr.nodelay(False)


class PlumbingPipes(EasterEgg):
    """Terminal animated plumbing pipes."""

    PIPE_CHARS: ClassVar[dict[tuple[int, int], str]] = {
        (0, 0): "║",
        (0, 1): "╔",
        (0, 3): "╗",
        (1, 1): "═",
        (1, 0): "╚",
        (1, 2): "╔",
        (2, 2): "║",
        (2, 1): "╝",
        (2, 3): "╚",
        (3, 3): "═",
        (3, 0): "╝",
        (3, 2): "╗",
    }

    def __init__(self) -> None:
        super().__init__(
            name="Terminal Pipes",
            aliases=["pipes", "pipes.sh"],
            description="Animated colorful growing plumbing pipes",
        )

    def execute(self, args: list[str]) -> int:
        curses.wrapper(self._animate)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        self._animate(stdscr)

    def _animate(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(True)

        try:
            safe_init_colors(7)

            height, width = stdscr.getmaxyx()
            x_pos: int = width // 2
            y_pos: int = height // 2

            # Directions: 0: up, 1: right, 2: down, 3: left
            direction: int = random.randint(0, 3)
            color_idx: int = random.randint(1, 6)

            while True:
                key: int = stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break

                new_dir: int = direction
                if random.random() < 0.2:
                    new_dir = (direction + random.choice([-1, 1])) % 4
                    color_idx = random.randint(1, 6)

                char: str = self.PIPE_CHARS.get((direction, new_dir), "╬")
                direction = new_dir

                attr = safe_color_pair(color_idx, fallback_attr=curses.A_NORMAL)
                try:
                    stdscr.addch(y_pos, x_pos, char, attr)
                except curses.error:
                    pass

                if direction == 0:
                    y_pos -= 1
                elif direction == 1:
                    x_pos += 1
                elif direction == 2:
                    y_pos += 1
                elif direction == 3:
                    x_pos -= 1

                if (
                    x_pos <= 0
                    or x_pos >= width - 1
                    or y_pos <= 0
                    or y_pos >= height - 1
                ):
                    x_pos = random.randint(2, max(2, width - 3))
                    y_pos = random.randint(2, max(2, height - 3))
                    direction = random.randint(0, 3)

                stdscr.refresh()
                time.sleep(0.04)
        finally:
            stdscr.nodelay(False)


class NyanCat(EasterEgg):
    """Animated ASCII Nyan Cat."""

    def __init__(self) -> None:
        super().__init__(
            name="Nyan Cat",
            aliases=["nyancat", "nyan"],
            description="Animated ASCII Nyan Cat with rainbow trail",
        )

    def execute(self, args: list[str]) -> int:
        curses.wrapper(self._animate)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        self._animate(stdscr)

    def _animate(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(True)

        try:
            height, width = stdscr.getmaxyx()
            frame_index: int = 0
            cat_x: int = 2
            start_time: float = time.time()
            rainbow_colors: list[str] = ["R", "O", "Y", "G", "B", "V"]

            while True:
                key: int = stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break

                stdscr.clear()
                center_y: int = max(0, height // 2 - 2)

                # Draw Rainbow Trail
                rainbow_line: str = "".join(
                    random.choice(rainbow_colors) for _ in range(cat_x)
                )
                try:
                    stdscr.addstr(center_y + 1, 0, rainbow_line[:cat_x])
                    stdscr.addstr(center_y + 2, 0, rainbow_line[:cat_x])
                except curses.error:
                    pass

                # Draw Cat Frame
                current_frame: str = NYAN_CAT_FRAMES[frame_index % len(NYAN_CAT_FRAMES)]
                for line_offset, line in enumerate(
                    current_frame.strip("\n").split("\n")
                ):
                    try:
                        stdscr.addstr(
                            center_y + line_offset,
                            cat_x,
                            line[: max(0, width - cat_x - 1)],
                        )
                    except curses.error:
                        pass

                elapsed_seconds: int = int(time.time() - start_time)
                status_line: str = (
                    f"You have nyaned for {elapsed_seconds} seconds! "
                    "[Press 'q' or 'ESC' to exit]"
                )
                safe_addstr(stdscr, height - 1, 2, status_line, curses.A_BOLD)

                stdscr.refresh()
                time.sleep(0.1)

                frame_index += 1
                cat_x += 1
                if cat_x > width - 30:
                    cat_x = 2
        finally:
            stdscr.nodelay(False)


class AptMoo(EasterEgg):
    """APT and Aptitude cow easter egg dialogues."""

    def __init__(self) -> None:
        super().__init__(
            name="APT / Aptitude Moo",
            aliases=["apt", "apt-get", "aptitude", "apt-build", "moo"],
            description="Have you mooed today? Cow dialogues",
        )

    def execute(self, args: list[str]) -> int:
        cmd_tokens: list[str] = [token.lower() for token in args]

        is_aptitude: bool = any("aptitude" in token for token in cmd_tokens)
        is_apt_build: bool = any("apt-build" in token for token in cmd_tokens)

        if is_apt_build:
            print(APT_BUILD_COW_ART, end="")
            return 0

        if is_aptitude:
            v_count: int = 0
            for token in cmd_tokens:
                if token.startswith("-v"):
                    v_count += token.count("v")
                elif token == "-v":
                    v_count += 1

            level_idx: int = min(v_count, len(APTITUDE_COW_LEVELS) - 1)
            print(APTITUDE_COW_LEVELS[level_idx])
            return 0

        # Standard apt / apt-get / moo
        print(APT_COW_ART, end="")
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        safe_curs_set(1)
        stdscr.nodelay(False)

        current_level: int = 0

        while True:
            stdscr.clear()
            safe_addstr(stdscr, 0, 0, "=== APT / Aptitude Moo Easter Egg Dialogue ===")
            for idx, line in enumerate(APT_COW_ART.strip("\n").split("\n")):
                safe_addstr(stdscr, 2 + idx, 0, line)

            if current_level > 0:
                safe_addstr(
                    stdscr,
                    12,
                    0,
                    f"Aptitude -{'v' * current_level} moo response:",
                )
                level_text: str = APTITUDE_COW_LEVELS[
                    min(current_level - 1, len(APTITUDE_COW_LEVELS) - 1)
                ]
                for idx, line in enumerate(level_text.strip("\n").split("\n")):
                    safe_addstr(stdscr, 13 + idx, 0, line)

            safe_addstr(
                stdscr,
                22,
                0,
                "Press [Space] to increase verbosity (aptitude -v moo), or 'q' to return.",
            )
            stdscr.refresh()

            key: int = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break
            elif key == ord(" "):
                current_level += 1
                if current_level > len(APTITUDE_COW_LEVELS):
                    current_level = 0


class PythonEggs(EasterEgg):
    """Python easter eggs (Zen of Python, Antigravity, and Hello)."""

    def __init__(self) -> None:
        super().__init__(
            name="The Zen of Python",
            aliases=["this", "antigravity", "__hello__", "python", "python3"],
            description="Tim Peters' 19 aphorisms (import this)",
        )

    def execute(self, args: list[str]) -> int:
        joined_args: str = " ".join(args).lower()

        if "antigravity" in joined_args:
            print("Opening https://xkcd.com/353/ (Python Antigravity)...")
            try:
                webbrowser.open("https://xkcd.com/353/")
            except webbrowser.Error:
                pass
            return 0

        if "__hello__" in joined_args:
            print("Hello world!")
            return 0

        # Default to Zen of Python
        for line in ZEN_OF_PYTHON:
            print(line)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        display_scrollable_text(stdscr, "The Zen of Python", ZEN_OF_PYTHON)


class SudoInsults(EasterEgg):
    """Sudo password prompt and insults generator."""

    def __init__(self) -> None:
        super().__init__(
            name="Sudo Insults",
            aliases=["sudo", "sudoers", "insults"],
            description="Generator for classic sudo command insults",
        )

    def execute(self, args: list[str]) -> int:
        user_name: str = os.getenv("USER", "user")

        if not sys.stdin.isatty():
            insult: str = random.choice(SUDO_INSULTS)
            print(f"sudo: {insult}", file=sys.stderr)
            return 1

        attempts: int = 0
        max_attempts: int = 3

        while attempts < max_attempts:
            prompt_label: str = f"[sudo] password for {user_name}: "
            try:
                _ = getpass.getpass(prompt_label)
            except (EOFError, KeyboardInterrupt):
                print(file=sys.stderr)
                return 1

            attempts += 1
            insult = random.choice(SUDO_INSULTS)
            print("Sorry, try again.", file=sys.stderr)
            print(f"sudo: {insult}", file=sys.stderr)

        print(f"sudo: {max_attempts} incorrect password attempts", file=sys.stderr)
        return 1

    def interactive(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(False)

        current_insult: str = random.choice(SUDO_INSULTS)

        while True:
            stdscr.clear()
            safe_addstr(stdscr, 0, 0, "=== Sudo Insults Generator ===", curses.A_BOLD)
            safe_addstr(stdscr, 3, 2, "[sudo] password for user: *******")
            safe_addstr(stdscr, 5, 2, f"sudo: {current_insult}", curses.A_BOLD)

            safe_addstr(
                stdscr,
                10,
                0,
                "Press [Space] for another insult, or 'q' to return.",
            )
            stdscr.refresh()

            key: int = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break
            elif key == ord(" "):
                current_insult = random.choice(SUDO_INSULTS)


class MakeLove(EasterEgg):
    """GNU Make love target error simulation."""

    def __init__(self) -> None:
        super().__init__(
            name="Make Love",
            aliases=["make"],
            description="GNU Make target 'make love' response",
        )

    def execute(self, args: list[str]) -> int:
        joined_args: str = " ".join(args).lower()
        if "love" in joined_args or len(args) <= 1:
            print(
                "make: *** No rule to make target 'love'.  Stop.",
                file=sys.stderr,
            )
            return 2

        target: str = args[1] if len(args) > 1 else "target"
        print(
            f"make: *** No rule to make target '{target}'.  Stop.",
            file=sys.stderr,
        )
        return 2

    def interactive(self, stdscr: curses.window) -> None:
        lore_lines: list[str] = [
            "GNU Make Easter Egg: 'make love'",
            "=" * 45,
            "",
            "Running 'make love' in Unix environments historically produced:",
            "  'make: Don't know how to make love. Stop.' (Classic Unix make)",
            "  'make: *** No rule to make target 'love'.  Stop.' (GNU Make)",
            "",
            "Other notable make targets:",
            "  - 'make war' -> 'make: *** No rule to make target 'war'.  Stop.'",
            "  - 'make money' -> 'make: *** No rule to make target 'money'.  Stop.'",
        ]
        display_scrollable_text(stdscr, "Make Lore & Trivia", lore_lines)


class DoctorEliza(EasterEgg):
    """Emacs M-x doctor ELIZA psychotherapist."""

    DOCTOR_RESPONSES: ClassVar[list[str]] = [
        "Why do you say that?",
        "Does that trouble you?",
        "Tell me more about your computer workflow.",
        "How long have you felt this way?",
        "Can you elaborate on that?",
        "Do you think software development causes this?",
        "What does that suggest to you?",
    ]

    def __init__(self) -> None:
        super().__init__(
            name="Emacs M-x doctor",
            aliases=["doctor", "eliza", "emacs"],
            description="Interactive ELIZA psychotherapist bot",
        )

    def execute(self, args: list[str]) -> int:
        print("Emacs Doctor (ELIZA Psychotherapist)")
        print("I am the psychotherapist.  Please describe your problem.")
        print("[Type 'quit' or 'exit' to end session]\n")

        while True:
            try:
                user_input: str = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nDoctor: Farewell.")
                break

            if not user_input or user_input.lower() in ("q", "quit", "exit"):
                print("Doctor: Farewell.")
                break

            response: str = random.choice(self.DOCTOR_RESPONSES)
            print(f"Doctor: {response}\n")

        return 0

    def interactive(self, stdscr: curses.window) -> None:
        safe_curs_set(1)
        stdscr.nodelay(False)
        safe_echo(True)

        height, width = stdscr.getmaxyx()
        history: list[str] = [
            "Emacs Doctor (ELIZA Psychotherapist)",
            "I am the psychotherapist.  Please describe your problem.",
            "",
        ]

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            start_row: int = max(0, len(history) - (height - 4))
            for idx, line in enumerate(history[start_row:]):
                safe_addstr(stdscr, idx, 0, line)

            safe_addstr(stdscr, max(0, height - 2), 0, "You: ")
            stdscr.refresh()

            input_y: int = max(0, height - 2)
            input_x: int = 5
            input_len: int = max(1, width - 10)

            user_input_bytes: bytes = stdscr.getstr(input_y, input_x, input_len)
            user_input: str = user_input_bytes.decode("utf-8", errors="ignore").strip()

            if not user_input or user_input.lower() in ("q", "quit", "exit"):
                break

            history.append(f"You: {user_input}")
            bot_response: str = random.choice(self.DOCTOR_RESPONSES)
            history.append(f"Doctor: {bot_response}")
            history.append("")

        safe_echo(False)


class VimHelp(EasterEgg):
    """Vim help documentation easter eggs (:help 42, :help holy-wars)."""

    def __init__(self) -> None:
        super().__init__(
            name="Vim Easter Eggs",
            aliases=["vim", "vi", "help42", "holy-wars"],
            description="Vim documentation easter eggs (:help 42, holy-wars)",
        )

    def execute(self, args: list[str]) -> int:
        joined: str = " ".join(args).lower()
        if "holy-wars" in joined or "holy_wars" in joined:
            for line in VIM_HELP_ENTRIES["holy-wars"]:
                print(line)
        elif "quotes" in joined:
            for line in VIM_HELP_ENTRIES["quotes"]:
                print(line)
        else:
            for line in VIM_HELP_ENTRIES["42"]:
                print(line)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        combined_lines: list[str] = [
            "Vim Documentation Easter Eggs",
            "=" * 45,
            "",
        ]
        for topic, entries in VIM_HELP_ENTRIES.items():
            combined_lines.append(f"[:help {topic}]")
            combined_lines.extend(entries)
            combined_lines.append("")
            combined_lines.append("-" * 45)
            combined_lines.append("")

        display_scrollable_text(stdscr, "Vim Documentation Easter Eggs", combined_lines)


class Cowsay(EasterEgg):
    """Cowsay and Cowthink configurable ASCII dialogue bubbles."""

    def __init__(self) -> None:
        super().__init__(
            name="Cowsay / Cowthink",
            aliases=["cowsay", "cowthink"],
            description="Generates ASCII cow with speech or thought bubble",
        )

    def execute(self, args: list[str]) -> int:
        is_think: bool = len(args) > 0 and "cowthink" in args[0].lower()
        text_tokens: list[str] = args[1:] if len(args) > 1 else []
        message: str = " ".join(text_tokens) if text_tokens else "Hello from Catstar!"

        balloon: str = self.format_balloon(message=message, is_think=is_think)
        thought_char: str = "o" if is_think else "\\"

        cow: str = rf"""{balloon}
        {thought_char}   ^__^
         {thought_char}  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
"""
        print(cow, end="")
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        balloon: str = self.format_balloon("Have you mooed today?", is_think=False)
        cow_preview: str = rf"""{balloon}
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
"""
        display_scrollable_text(stdscr, "Cowsay Viewer", cow_preview.splitlines())

    @staticmethod
    def format_balloon(message: str, is_think: bool = False) -> str:
        """Format text inside a classic ASCII speech or thought balloon."""
        lines: list[str] = textwrap.wrap(message, width=40)
        if not lines:
            lines = [""]

        max_len: int = max(len(line) for line in lines)
        border: str = " " + "_" * (max_len + 2)
        bottom: str = " " + "-" * (max_len + 2)

        formatted_lines: list[str] = [border]

        if is_think:
            for line in lines:
                formatted_lines.append(f"( {line.ljust(max_len)} )")
        elif len(lines) == 1:
            formatted_lines.append(f"< {lines[0].ljust(max_len)} >")
        else:
            for idx, line in enumerate(lines):
                if idx == 0:
                    formatted_lines.append(f"/ {line.ljust(max_len)} \\")
                elif idx == len(lines) - 1:
                    formatted_lines.append(f"\\ {line.ljust(max_len)} /")
                else:
                    formatted_lines.append(f"| {line.ljust(max_len)} |")

        formatted_lines.append(bottom)
        return "\n".join(formatted_lines)


class UnixFortune(EasterEgg):
    """Unix fortune cookies."""

    def __init__(self) -> None:
        super().__init__(
            name="Unix Fortune",
            aliases=["fortune"],
            description="Prints a random Unix fortune cookie",
        )

    def execute(self, args: list[str]) -> int:
        print(random.choice(FORTUNE_COOKIES))
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        fortune: str = random.choice(FORTUNE_COOKIES)
        wrapped: list[str] = textwrap.wrap(fortune, width=50)
        lines: list[str] = ["", "  " + "\n  ".join(wrapped), ""]
        display_scrollable_text(stdscr, "Unix Fortune Cookie", lines)


class SecretFireworks(EasterEgg):
    """Ancient Unix Magic & Fireworks animation."""

    def __init__(self) -> None:
        super().__init__(
            name="★ Secret Fireworks",
            aliases=["xyzzy", "magic", "42", "secret", "fireworks", "konami"],
            description="Ancient Unix Magic & Fireworks (Unlocked!)",
        )

    def execute(self, args: list[str]) -> int:
        curses.wrapper(self._animate)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        self._animate(stdscr)

    def _animate(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(True)

        try:
            safe_init_colors(7)
            particles: list[dict[str, float]] = []

            while True:
                key: int = stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break

                stdscr.clear()
                height, width = stdscr.getmaxyx()

                # Spawn firework bursts
                if random.random() < 0.3:
                    burst_x: float = float(random.randint(10, max(10, width - 10)))
                    burst_y: float = float(random.randint(4, max(4, height - 8)))
                    color: int = random.randint(1, 6)

                    for _ in range(24):
                        angle: float = random.uniform(0, 6.28)
                        speed: float = random.uniform(0.5, 2.5)
                        particles.append(
                            {
                                "x": burst_x,
                                "y": burst_y,
                                "vx": math.cos(angle) * speed,
                                "vy": math.sin(angle) * (speed * 0.5),
                                "life": float(random.randint(8, 20)),
                                "color": float(color),
                                "char": ord(
                                    random.choice(["*", "+", ".", "o", "O", "@"])
                                ),
                            }
                        )

                # Update particles
                surviving: list[dict[str, float]] = []
                for p in particles:
                    px: int = int(p["x"])
                    py: int = int(p["y"])
                    attr = safe_color_pair(int(p["color"]), fallback_attr=curses.A_BOLD)

                    if 0 <= py < height and 0 <= px < width:
                        safe_addstr(stdscr, py, px, chr(int(p["char"])), attr)

                    p["x"] += p["vx"]
                    p["y"] += p["vy"] + 0.1  # Gravity
                    p["life"] -= 1

                    if p["life"] > 0:
                        surviving.append(p)

                particles = surviving

                safe_addstr(
                    stdscr,
                    1,
                    0,
                    " ★ SECRET UNLOCKED: ANCIENT UNIX MAGIC ★ ".center(width),
                    curses.A_REVERSE | curses.A_BOLD,
                )
                safe_addstr(
                    stdscr,
                    height - 3,
                    0,
                    " 'xyzzy': Nothing happens... Except ASCII Fireworks! ".center(
                        width
                    ),
                    curses.A_BOLD,
                )
                safe_addstr(
                    stdscr,
                    height - 1,
                    0,
                    " Press 'q' or 'ESC' to exit Secret Mode ".center(width),
                    curses.A_REVERSE,
                )

                stdscr.refresh()
                time.sleep(0.04)
        finally:
            stdscr.nodelay(False)


class TriviaQuiz(EasterEgg):
    """Interactive Vim & Unix Easter Eggs Quiz Game."""

    def __init__(self) -> None:
        super().__init__(
            name="Vim & Unix Quiz",
            aliases=["quiz", "trivia", "game"],
            description="Interactive quiz game on Vim & Unix easter eggs",
        )

    def execute(self, args: list[str]) -> int:
        curses.wrapper(self.interactive)
        return 0

    def interactive(self, stdscr: curses.window) -> None:
        safe_curs_set(0)
        stdscr.nodelay(False)

        safe_init_colors(4)

        score: int = 0
        total_questions: int = len(TRIVIA_QUESTIONS)

        for q_index, q_data in enumerate(TRIVIA_QUESTIONS):
            selected_option: int = 0
            options: list[str] = q_data["options"]  # type: ignore
            question_text: str = q_data["question"]  # type: ignore
            correct_answer: int = q_data["answer"]  # type: ignore
            explanation_text: str = q_data["explanation"]  # type: ignore

            user_answered: bool = False

            while not user_answered:
                stdscr.clear()
                height, width = stdscr.getmaxyx()

                header: str = (
                    f" UNIX & VIM EASTER EGGS QUIZ ({q_index + 1}/{total_questions}) "
                )
                safe_addstr(
                    stdscr,
                    0,
                    0,
                    header.center(width),
                    curses.A_REVERSE | curses.A_BOLD,
                )
                safe_addstr(
                    stdscr,
                    1,
                    0,
                    f" Current Score: {score}/{q_index}",
                    curses.A_BOLD,
                )

                safe_addstr(
                    stdscr,
                    3,
                    2,
                    f"Q{q_index + 1}: {question_text}",
                    curses.A_BOLD,
                )

                for opt_idx, opt_str in enumerate(options):
                    opt_y: int = 6 + opt_idx
                    if opt_idx == selected_option:
                        attr = curses.A_BOLD | curses.A_REVERSE
                        safe_addstr(stdscr, opt_y, 4, f"> {opt_str}", attr)
                    else:
                        safe_addstr(stdscr, opt_y, 4, f"  {opt_str}")

                safe_addstr(
                    stdscr,
                    height - 1,
                    0,
                    " Nav: [↑/↓/j/k] | Select: [Enter/Space] | Quit: [q]".center(width),
                    curses.A_REVERSE,
                )
                stdscr.refresh()

                key: int = stdscr.getch()

                if key in (ord("q"), ord("Q"), 27):
                    return
                elif key in (curses.KEY_UP, ord("k"), ord("K")):
                    selected_option = (selected_option - 1) % len(options)
                elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
                    selected_option = (selected_option + 1) % len(options)
                elif key in (10, 13, ord(" ")):
                    user_answered = True
                    stdscr.clear()
                    safe_addstr(
                        stdscr,
                        0,
                        0,
                        header.center(width),
                        curses.A_REVERSE | curses.A_BOLD,
                    )

                    if selected_option == correct_answer:
                        score += 1
                        green_attr = (
                            safe_color_pair(1, fallback_attr=curses.A_BOLD)
                            | curses.A_BOLD
                        )
                        safe_addstr(stdscr, 3, 2, "CORRECT!", green_attr)
                    else:
                        red_attr = (
                            safe_color_pair(2, fallback_attr=curses.A_BOLD)
                            | curses.A_BOLD
                        )
                        safe_addstr(
                            stdscr,
                            3,
                            2,
                            f"INCORRECT! Correct answer was: {options[correct_answer]}",
                            red_attr,
                        )

                    safe_addstr(stdscr, 5, 2, f"Explanation: {explanation_text}")
                    safe_addstr(stdscr, 8, 2, "Press any key to continue...")
                    stdscr.refresh()
                    stdscr.getch()

        # Results screen
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        title_end: str = " QUIZ COMPLETE! FINAL RESULTS "
        safe_addstr(
            stdscr,
            0,
            0,
            title_end.center(width),
            curses.A_REVERSE | curses.A_BOLD,
        )

        percentage: float = (score / total_questions) * 100
        rank: str = "Script Kiddie"
        if percentage >= 100:
            rank = "Root Superuser / Unix Wizard 🧙‍♂️"
        elif percentage >= 75:
            rank = "Senior Sysadmin 💻"
        elif percentage >= 50:
            rank = "Terminal Hacker ⌨️"

        safe_addstr(
            stdscr,
            3,
            2,
            f"Final Score: {score} out of {total_questions} ({percentage:.0f}%)",
            curses.A_BOLD,
        )
        cyan_attr = safe_color_pair(3, fallback_attr=curses.A_BOLD) | curses.A_BOLD
        safe_addstr(stdscr, 5, 2, f"Awarded Rank: {rank}", cyan_attr)

        safe_addstr(stdscr, 8, 2, "Press any key to return to main menu...")
        stdscr.refresh()
        stdscr.getch()


# -----------------------------------------------------------------------------
# 5. Easter Egg Registry
# -----------------------------------------------------------------------------


class EasterEggRegistry:
    """Central registry managing easter egg resolution and dispatching."""

    def __init__(self) -> None:
        self._eggs: list[EasterEgg] = []
        self._alias_map: dict[str, EasterEgg] = {}
        self.secret_egg: EasterEgg = SecretFireworks()

    def register(self, egg: EasterEgg) -> None:
        """Register an easter egg instance and its command aliases."""
        self._eggs.append(egg)
        for alias in egg.aliases:
            self._alias_map[alias.lower()] = egg

    def get_catalog(self) -> list[EasterEgg]:
        """Return list of standard easter eggs for catalog display."""
        return list(self._eggs)

    def resolve(self, argv: list[str]) -> tuple[EasterEgg | None, list[str]]:
        """Resolve command tokens to a matching easter egg and remaining args."""
        if not argv:
            return None, []

        first_token: str = argv[0].lower()

        # Check single-token aliases
        if first_token in self._alias_map:
            return self._alias_map[first_token], argv

        # Check secret aliases
        if first_token in [alias.lower() for alias in self.secret_egg.aliases]:
            return self.secret_egg, argv

        # Check multi-token combinations (e.g. `apt-get moo`, `python -m this`)
        if len(argv) >= 2:
            combined_two: str = f"{argv[0]} {argv[1]}".lower()
            if "apt" in argv[0].lower() and "moo" in argv[1].lower():
                return self._alias_map.get("apt"), argv
            if "python" in argv[0].lower() and "this" in combined_two:
                return self._alias_map.get("this"), argv
            if "python" in argv[0].lower() and "antigravity" in combined_two:
                return self._alias_map.get("this"), argv
            if "python" in argv[0].lower() and "__hello__" in combined_two:
                return self._alias_map.get("this"), argv
            if "import" in argv[0].lower():
                return self._alias_map.get("this"), argv

        # Fuzzy / partial matching
        for egg in self._eggs:
            if first_token in egg.name.lower():
                return egg, argv

        return None, argv


def build_default_registry() -> EasterEggRegistry:
    """Create and initialize the standard EasterEggRegistry."""
    registry = EasterEggRegistry()
    registry.register(SteamLocomotive())
    registry.register(MatrixDigitalRain())
    registry.register(PlumbingPipes())
    registry.register(NyanCat())
    registry.register(AptMoo())
    registry.register(PythonEggs())
    registry.register(SudoInsults())
    registry.register(MakeLove())
    registry.register(DoctorEliza())
    registry.register(VimHelp())
    registry.register(Cowsay())
    registry.register(UnixFortune())
    registry.register(TriviaQuiz())
    return registry


# -----------------------------------------------------------------------------
# 6. Interactive Curses TUI Menu
# -----------------------------------------------------------------------------


def run_tui_menu(
    stdscr: curses.window, registry: EasterEggRegistry | None = None
) -> None:
    """Run full interactive TUI selection menu with secret code listener."""
    if registry is None:
        registry = build_default_registry()

    safe_curs_set(0)

    selected_index: int = 0
    active_catalog: list[EasterEgg] = registry.get_catalog()
    secret_unlocked: bool = False
    key_history: str = ""

    while True:
        stdscr.nodelay(False)
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        total_items: int = len(active_catalog)
        title: str = " UNIX EASTER EGGS COLLECTION "
        subtitle: str = "Select an easter egg to launch. Press 'q' to quit."

        safe_addstr(stdscr, 0, 0, title.center(width), curses.A_REVERSE | curses.A_BOLD)
        safe_addstr(stdscr, 1, 0, subtitle.center(width), curses.A_DIM)
        safe_addstr(stdscr, 2, 0, "-" * width, curses.A_DIM)

        for idx, egg in enumerate(active_catalog):
            row_y: int = 4 + idx
            if row_y < height - 2:
                label: str = f"  [{'x' if idx == selected_index else ' '}] {egg.name:<25} - {egg.description}"
                if idx == selected_index:
                    safe_addstr(
                        stdscr,
                        row_y,
                        2,
                        label[: width - 4],
                        curses.A_BOLD | curses.A_REVERSE,
                    )
                else:
                    safe_addstr(stdscr, row_y, 2, label[: width - 4])

        safe_addstr(
            stdscr,
            height - 1,
            0,
            " Nav: [↑/↓/j/k] | Select: [Enter/Space] | Exit: [q]".center(width),
            curses.A_REVERSE,
        )

        stdscr.refresh()

        key: int = stdscr.getch()

        # Secret keystroke sequence detection
        if 32 <= key <= 126:
            key_history += chr(key).lower()
            if len(key_history) > 10:
                key_history = key_history[-10:]

            if any(
                secret_code in key_history
                for secret_code in ("xyzzy", "42", "magic", "secret", "konami")
            ):
                if not secret_unlocked:
                    secret_unlocked = True
                    active_catalog.append(registry.secret_egg)
                registry.secret_egg.interactive(stdscr)
                key_history = ""
                continue

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k"), ord("K")):
            selected_index = (selected_index - 1) % total_items
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            selected_index = (selected_index + 1) % total_items
        elif key in (10, 13, ord(" ")):
            active_catalog[selected_index].interactive(stdscr)


# -----------------------------------------------------------------------------
# 7. Command Line Entry Point
# -----------------------------------------------------------------------------


def main(custom_argv: list[str] | None = None) -> int:
    """Main execution function handling direct command simulation and interactive TUI."""
    argv: list[str] = custom_argv if custom_argv is not None else sys.argv[1:]
    registry: EasterEggRegistry = build_default_registry()

    # Multi-call binary detection (if invoked as `sl`, `cmatrix`, etc.)
    prog_name: str = os.path.basename(sys.argv[0])
    if prog_name not in ("unix_eastereggs.py", "egg.py", "python", "python3", "pytest"):
        egg, _ = registry.resolve([prog_name] + argv)
        if egg is not None:
            return egg.execute([prog_name] + argv)

    # If no arguments provided, launch interactive TUI
    if not argv:
        curses.wrapper(lambda s: run_tui_menu(s, registry))
        return 0

    # Parse top-level CLI flags
    first_arg: str = argv[0].lower()

    if first_arg in ("--list", "-l"):
        print("Available Unix Easter Eggs:")
        for idx, egg in enumerate(registry.get_catalog(), 1):
            aliases_str: str = ", ".join(egg.aliases)
            print(f"  {idx:2d}. {egg.name:<25} ({aliases_str})")
            print(f"      {egg.description}")
        return 0

    if first_arg in ("--menu", "-i", "--interactive"):
        curses.wrapper(lambda s: run_tui_menu(s, registry))
        return 0

    if first_arg in ("--help", "-h"):
        print("Usage: unix_eastereggs.py [COMMAND | OPTIONS]")
        print("\nDirect Command Execution:")
        print("  unix_eastereggs.py sl [-a] [-l] [-F]")
        print("  unix_eastereggs.py apt-get moo")
        print("  unix_eastereggs.py aptitude [-v...] moo")
        print("  unix_eastereggs.py make love")
        print("  unix_eastereggs.py cmatrix")
        print("  unix_eastereggs.py pipes")
        print("  unix_eastereggs.py nyancat")
        print("  unix_eastereggs.py python -m this")
        print("  unix_eastereggs.py sudo")
        print("  unix_eastereggs.py cowsay <message>")
        print("  unix_eastereggs.py fortune")
        print("  unix_eastereggs.py quiz")
        print("\nOptions:")
        print("  --list, -l         List all available easter eggs and aliases")
        print("  --menu, -i         Open interactive curses selection menu")
        print("  --help, -h         Show this help message")
        return 0

    # Resolve and execute matching easter egg command
    egg, remaining_args = registry.resolve(argv)
    if egg is not None:
        return egg.execute(remaining_args)

    print(
        f"Error: Unknown command or easter egg '{' '.join(argv)}'.",
        file=sys.stderr,
    )
    print("Use --list to view available commands.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
