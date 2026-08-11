#!/usr/bin/env python3
"""Unix Easter Eggs Collection.

A self-contained terminal utility providing interactive access to well-known
Unix and Linux terminal easter eggs.
"""

import argparse
import curses
import math
import random
import sys
import time
from collections.abc import Callable

# -----------------------------------------------------------------------------
# 1. ASCII Art Data Definitions
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

APT_COW_ART: str = r"""
         (__) 
         (oo) 
   /------\/ 
  / |    ||  
 *  ||---||  
    ~~   ~~  
"Have you mooed today?"
"""

APTITUDE_COW_LEVEL_1: str = r"""
 There are no Easter Eggs in this program.
"""

APTITUDE_COW_LEVEL_2: str = r"""
 Really, there are no Easter Eggs in this program.
"""

APTITUDE_COW_LEVEL_3: str = r"""
 Didn't I already tell you that there are no Easter Eggs in this program?
"""

APTITUDE_COW_LEVEL_4: str = r"""
 Stop it!
"""

APTITUDE_COW_LEVEL_5: str = r"""
 OK, ok, if I give you an Easter Egg, will you go away?
"""

APTITUDE_COW_LEVEL_6: str = r"""
 All right, you win.

                               User-friendly..o
                              /
                     .---.   .
                    /     \  |
                   | () () |/
                    \  ^  /
                     |||||
                     |||||
"""

SUDO_INSULTS_LIST: list[str] = [
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
]

ZEN_OF_PYTHON_TEXT: list[str] = [
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

VIM_TRIVIA_TEXT: list[str] = [
    "Vim & Unix Documentation Easter Eggs Trivia",
    "=" * 45,
    "",
    "1. Vim ':help 42'",
    "   Output: '42 - The Answer to Life, the Universe, and Everything.'",
    "   (Douglas Adams' Hitchhiker's Guide to the Galaxy reference)",
    "",
    "2. Vim ':help holy-wars'",
    "   Explains the longstanding rivalry between Vi and Emacs.",
    "",
    "3. Vim ':help quotes'",
    "   Displays humorous quotes collected throughout Vim's development history.",
    "",
    "4. Python 'import antigravity'",
    "   Opens xkcd comic #353 ('Python') in a browser window.",
    "",
    "5. Python 'import __hello__'",
    "   Prints 'Hello world!' directly from frozen bytecode.",
    "",
    "6. Emacs 'M-x butterfly'",
    "   Reference to xkcd #378 ('Real Programmers' flip bits using butterflies).",
]

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


# -----------------------------------------------------------------------------
# 2. Curses Rendering Helpers & Easter Egg Implementation Functions
# -----------------------------------------------------------------------------


def safe_addstr(
    stdscr: curses.window, y: int, x: int, text: str, attr: int = 0
) -> None:
    """Safely write text string to curses window preventing _curses.error on boundaries."""
    try:
        height, width = stdscr.getmaxyx()
        if 0 <= y < height and 0 <= x < width:
            max_len: int = max(0, width - x - (1 if y == height - 1 else 0))
            if max_len > 0:
                stdscr.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def run_sl_animation(stdscr: curses.window) -> None:
    """Run the steam locomotive (sl) ASCII animation across the screen."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    try:
        height, width = stdscr.getmaxyx()
        train_width: int = max(len(line) for line in SL_LOCOMOTIVE_FRAME_1)
        train_height: int = len(SL_LOCOMOTIVE_FRAME_1)

        start_y: int = max(0, (height - train_height) // 2)
        start_x: int = width - 1

        frame_toggle: bool = False

        while start_x > -train_width:
            stdscr.clear()

            # Handle user exit key
            key: int = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break

            current_frame: list[str] = (
                SL_LOCOMOTIVE_FRAME_1 if frame_toggle else SL_LOCOMOTIVE_FRAME_2
            )
            frame_toggle = not frame_toggle

            for row_index, line in enumerate(current_frame):
                target_y: int = start_y + row_index
                if 0 <= target_y < height:
                    for col_index, char in enumerate(line):
                        target_x: int = start_x + col_index
                        if 0 <= target_x < width:
                            try:
                                stdscr.addch(target_y, target_x, char)
                            except curses.error:
                                pass

            stdscr.refresh()
            time.sleep(0.04)
            start_x -= 2
    finally:
        stdscr.nodelay(False)


def run_cmatrix_animation(stdscr: curses.window) -> None:
    """Run falling Matrix digital rain animation."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    try:
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)

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
                    attr = (
                        curses.color_pair(2) if curses.has_colors() else curses.A_BOLD
                    )
                    try:
                        stdscr.addch(y_pos, col, char, attr)
                    except curses.error:
                        pass

                trail_y: int = y_pos - 1
                if 0 <= trail_y < height:
                    char: str = random.choice(characters)
                    attr = (
                        curses.color_pair(1) if curses.has_colors() else curses.A_NORMAL
                    )
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


def run_pipes_animation(stdscr: curses.window) -> None:
    """Run animated terminal plumbing pipes."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    try:
        if curses.has_colors():
            curses.start_color()
            for idx in range(1, 7):
                curses.init_pair(idx, idx, curses.COLOR_BLACK)

        height, width = stdscr.getmaxyx()
        x_pos: int = width // 2
        y_pos: int = height // 2

        # Directions: 0: up, 1: right, 2: down, 3: left
        direction: int = random.randint(0, 3)
        pipe_chars: dict[tuple[int, int], str] = {
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

        color_idx: int = random.randint(1, 6)

        while True:
            key: int = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break

            new_dir: int = direction
            if random.random() < 0.2:
                new_dir = (direction + random.choice([-1, 1])) % 4
                color_idx = random.randint(1, 6)

            char: str = pipe_chars.get((direction, new_dir), "╬")
            direction = new_dir

            attr = (
                curses.color_pair(color_idx) if curses.has_colors() else curses.A_NORMAL
            )
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

            if x_pos <= 0 or x_pos >= width - 1 or y_pos <= 0 or y_pos >= height - 1:
                x_pos = random.randint(2, max(2, width - 3))
                y_pos = random.randint(2, max(2, height - 3))
                direction = random.randint(0, 3)

            stdscr.refresh()
            time.sleep(0.04)
    finally:
        stdscr.nodelay(False)


def run_nyancat_animation(stdscr: curses.window) -> None:
    """Run animated ASCII Nyan Cat."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    try:
        height, width = stdscr.getmaxyx()
        frame_index: int = 0
        cat_x: int = 2

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
            for line_offset, line in enumerate(current_frame.strip("\n").split("\n")):
                try:
                    stdscr.addstr(
                        center_y + line_offset, cat_x, line[: max(0, width - cat_x - 1)]
                    )
                except curses.error:
                    pass

            try:
                stdscr.addstr(height - 1, 2, "Press 'q' or 'ESC' to exit Nyan Cat.")
            except curses.error:
                pass

            stdscr.refresh()
            time.sleep(0.1)

            frame_index += 1
            cat_x += 1
            if cat_x > width - 30:
                cat_x = 2
    finally:
        stdscr.nodelay(False)


def run_apt_moo_interactive(stdscr: curses.window) -> None:
    """Interactive APT cow dialogue."""
    curses.curs_set(1)
    stdscr.nodelay(False)

    levels: list[str] = [
        APTITUDE_COW_LEVEL_1,
        APTITUDE_COW_LEVEL_2,
        APTITUDE_COW_LEVEL_3,
        APTITUDE_COW_LEVEL_4,
        APTITUDE_COW_LEVEL_5,
        APTITUDE_COW_LEVEL_6,
    ]

    current_level: int = 0

    while True:
        stdscr.clear()
        safe_addstr(stdscr, 0, 0, "=== APT / Aptitude Moo Easter Egg Dialogue ===")
        for idx, line in enumerate(APT_COW_ART.strip("\n").split("\n")):
            safe_addstr(stdscr, 2 + idx, 0, line)

        if current_level > 0:
            safe_addstr(stdscr, 12, 0, f"Aptitude -{'v' * current_level} moo response:")
            for idx, line in enumerate(
                levels[min(current_level - 1, len(levels) - 1)].strip("\n").split("\n")
            ):
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
            if current_level > len(levels):
                current_level = 0


def display_text_viewer(stdscr: curses.window, title: str, lines: list[str]) -> None:
    """Display paginated or scrollable text viewer."""
    curses.curs_set(0)
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


def run_sudo_insults_viewer(stdscr: curses.window) -> None:
    """Display random sudo insults."""
    curses.curs_set(0)
    stdscr.nodelay(False)

    current_insult: str = random.choice(SUDO_INSULTS_LIST)

    while True:
        stdscr.clear()
        safe_addstr(stdscr, 0, 0, "=== Sudo Insults Generator ===", curses.A_BOLD)
        safe_addstr(stdscr, 3, 2, "[sudo] password for user: *******")
        safe_addstr(stdscr, 5, 2, f"sudo: {current_insult}", curses.A_BOLD)

        safe_addstr(
            stdscr, 10, 0, "Press [Space] for another insult, or 'q' to return."
        )
        stdscr.refresh()

        key: int = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            break
        elif key == ord(" "):
            current_insult = random.choice(SUDO_INSULTS_LIST)


def run_doctor_eliza(stdscr: curses.window) -> None:
    """Run interactive Emacs M-x doctor ELIZA bot."""
    curses.curs_set(1)
    stdscr.nodelay(False)
    curses.echo()

    height, width = stdscr.getmaxyx()
    history: list[str] = [
        "Emacs Doctor (ELIZA Psychotherapist)",
        "I am the psychotherapist.  Please describe your problem.",
        "",
    ]

    responses: list[str] = [
        "Why do you say that?",
        "Does that trouble you?",
        "Tell me more about your computer workflow.",
        "How long have you felt this way?",
        "Can you elaborate on that?",
        "Do you think software development causes this?",
        "What does that suggest to you?",
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
        bot_response: str = random.choice(responses)
        history.append(f"Doctor: {bot_response}")
        history.append("")

    curses.noecho()


# -----------------------------------------------------------------------------
# 3. Interactive Quiz & Trivia Game
# -----------------------------------------------------------------------------

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
            "A) 'make: Don't know how to make love. Stop.'",
            "B) 'make: Love made successfully.'",
            "C) 'make: Permission denied.'",
            "D) Compiles 'love.c' if present",
        ],
        "answer": 0,
        "explanation": "GNU Make responds with standard error 'Don't know how to make love. Stop.'",
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


def run_interactive_trivia_game(stdscr: curses.window) -> None:
    """Run an interactive Unix & Vim Easter Egg Quiz game."""
    curses.curs_set(0)
    stdscr.nodelay(False)

    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)

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
                stdscr, 0, 0, header.center(width), curses.A_REVERSE | curses.A_BOLD
            )
            safe_addstr(
                stdscr, 1, 0, f" Current Score: {score}/{q_index}", curses.A_BOLD
            )

            safe_addstr(stdscr, 3, 2, f"Q{q_index + 1}: {question_text}", curses.A_BOLD)

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
                    stdscr, 0, 0, header.center(width), curses.A_REVERSE | curses.A_BOLD
                )

                if selected_option == correct_answer:
                    score += 1
                    green_attr = (
                        curses.color_pair(1) | curses.A_BOLD
                        if curses.has_colors()
                        else curses.A_BOLD
                    )
                    safe_addstr(stdscr, 3, 2, "CORRECT!", green_attr)
                else:
                    red_attr = (
                        curses.color_pair(2) | curses.A_BOLD
                        if curses.has_colors()
                        else curses.A_BOLD
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

    # Final Score & Rank Evaluation Screen
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    title_end: str = " QUIZ COMPLETE! FINAL RESULTS "
    safe_addstr(stdscr, 0, 0, title_end.center(width), curses.A_REVERSE | curses.A_BOLD)

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
    cyan_attr = (
        curses.color_pair(3) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
    )
    safe_addstr(stdscr, 5, 2, f"Awarded Rank: {rank}", cyan_attr)

    safe_addstr(stdscr, 8, 2, "Press any key to return to main menu...")
    stdscr.refresh()
    stdscr.getch()


def run_secret_fireworks_animation(stdscr: curses.window) -> None:
    """Secret Easter Egg: Animated ASCII Fireworks & Magic Mode."""
    curses.curs_set(0)
    stdscr.nodelay(True)

    if curses.has_colors():
        curses.start_color()
        for idx in range(1, 7):
            curses.init_pair(idx, idx, curses.COLOR_BLACK)

    particles: list[dict[str, float]] = []

    try:
        while True:
            key: int = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break

            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Spawn new firework burst
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
                            "life": random.randint(8, 20),
                            "color": color,
                            "char": random.choice(["*", "+", ".", "o", "O", "★", "@"]),
                        }
                    )

            # Update & render particles
            surviving_particles: list[dict[str, float]] = []
            for p in particles:
                px: int = int(p["x"])
                py: int = int(p["y"])
                attr = (
                    curses.color_pair(int(p["color"]))
                    if curses.has_colors()
                    else curses.A_BOLD
                )

                if 0 <= py < height and 0 <= px < width:
                    safe_addstr(stdscr, py, px, str(p["char"]), attr)

                p["x"] += p["vx"]
                p["y"] += p["vy"] + 0.1  # Gravity effect
                p["life"] -= 1

                if p["life"] > 0:
                    surviving_particles.append(p)

            particles = surviving_particles

            # Floating Banner
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
                " 'xyzzy': Nothing happens... Except ASCII Fireworks! ".center(width),
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


# -----------------------------------------------------------------------------
# 4. Interactive TUI Menu System
# -----------------------------------------------------------------------------

EASTER_EGG_CATALOG: list[tuple[str, str, Callable[[curses.window], None]]] = [
    (
        "Steam Locomotive (sl)",
        "ASCII steam train running across screen",
        run_sl_animation,
    ),
    (
        "Matrix Digital Rain",
        "Falling green digital matrix characters",
        run_cmatrix_animation,
    ),
    ("Terminal Pipes", "Animated colorful growing plumbing pipes", run_pipes_animation),
    ("Nyan Cat", "Animated ASCII Nyan Cat with rainbow trail", run_nyancat_animation),
    (
        "APT / Aptitude Moo",
        "Have you mooed today? Cow dialogues",
        run_apt_moo_interactive,
    ),
    (
        "The Zen of Python",
        "Tim Peters' 19 aphorisms (import this)",
        lambda s: display_text_viewer(s, "The Zen of Python", ZEN_OF_PYTHON_TEXT),
    ),
    (
        "Sudo Insults",
        "Generator for classic sudo command insults",
        run_sudo_insults_viewer,
    ),
    ("Emacs M-x doctor", "Interactive ELIZA psychotherapist bot", run_doctor_eliza),
    (
        "Vim & Unix Quiz",
        "Interactive quiz game on Vim & Unix easter eggs",
        run_interactive_trivia_game,
    ),
]

SECRET_CATALOG_ITEM: tuple[str, str, Callable[[curses.window], None]] = (
    "★ Secret Fireworks",
    "Ancient Unix Magic & Fireworks (Unlocked!)",
    run_secret_fireworks_animation,
)


def run_tui_menu(stdscr: curses.window) -> None:
    """Run main interactive selection menu with secret key buffer tracking."""
    curses.curs_set(0)

    selected_index: int = 0
    active_catalog: list[tuple[str, str, Callable[[curses.window], None]]] = list(
        EASTER_EGG_CATALOG
    )
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

        for idx, (name, description, _) in enumerate(active_catalog):
            row_y: int = 4 + idx
            if row_y < height - 2:
                label: str = f"  [{'x' if idx == selected_index else ' '}] {name:<25} - {description}"
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

        # Secret key sequence tracking (silent background detector)
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
                    active_catalog.append(SECRET_CATALOG_ITEM)
                run_secret_fireworks_animation(stdscr)
                key_history = ""
                continue

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k"), ord("K")):
            selected_index = (selected_index - 1) % total_items
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            selected_index = (selected_index + 1) % total_items
        elif key in (10, 13, ord(" ")):
            _, _, egg_function = active_catalog[selected_index]
            egg_function(stdscr)


# -----------------------------------------------------------------------------
# 5. Command Line Entry Point
# -----------------------------------------------------------------------------


def build_cli_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Standalone Unix Easter Eggs Collection Utility."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available easter eggs and exit.",
    )
    parser.add_argument(
        "--egg",
        type=str,
        help="Directly run a specific easter egg by index or name.",
    )
    parser.add_argument(
        "--secret",
        "--xyzzy",
        "--42",
        action="store_true",
        dest="secret",
        help=argparse.SUPPRESS,
    )
    return parser


def main() -> None:
    """Main execution function."""
    parser: argparse.ArgumentParser = build_cli_parser()
    args: argparse.Namespace = parser.parse_args()

    if args.secret:
        curses.wrapper(run_secret_fireworks_animation)
        sys.exit(0)

    if args.list:
        print("Available Unix Easter Eggs:")
        for idx, (name, description, _) in enumerate(EASTER_EGG_CATALOG, 1):
            print(f"  {idx}. {name:<25} : {description}")
        sys.exit(0)

    if args.egg:
        target_egg: tuple[str, str, Callable[[curses.window], None]] | None = None
        if args.egg.isdigit():
            idx_val: int = int(args.egg) - 1
            if 0 <= idx_val < len(EASTER_EGG_CATALOG):
                target_egg = EASTER_EGG_CATALOG[idx_val]
        else:
            search_query: str = args.egg.lower()
            if search_query in ("secret", "xyzzy", "42", "fireworks"):
                target_egg = SECRET_CATALOG_ITEM
            else:
                for item in EASTER_EGG_CATALOG:
                    if search_query in item[0].lower():
                        target_egg = item
                        break

        if target_egg:
            _, _, handler = target_egg
            curses.wrapper(handler)
            sys.exit(0)
        else:
            print(
                f"Error: Unknown easter egg '{args.egg}'. Use --list to view options."
            )
            sys.exit(1)

    # Default to interactive TUI
    curses.wrapper(run_tui_menu)


if __name__ == "__main__":
    main()
