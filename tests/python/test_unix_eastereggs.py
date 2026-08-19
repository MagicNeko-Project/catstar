"""Unit test suite for the Unix Easter Eggs collection and command runner."""

import curses
import io
import unittest
from unittest.mock import MagicMock, patch

from scripts.unix_eastereggs import (
    APT_BUILD_COW_ART,
    APT_COW_ART,
    APTITUDE_COW_LEVELS,
    FORTUNE_COOKIES,
    TRIVIA_QUESTIONS,
    AptMoo,
    Cowsay,
    DoctorEliza,
    EasterEggRegistry,
    MakeLove,
    MatrixDigitalRain,
    NyanCat,
    PlumbingPipes,
    PythonEggs,
    SecretFireworks,
    SteamLocomotive,
    SudoInsults,
    TriviaQuiz,
    UnixFortune,
    VimHelp,
    build_default_registry,
    display_scrollable_text,
    main,
    run_tui_menu,
    safe_addstr,
)


class TestEasterEggRegistry(unittest.TestCase):
    """Unit tests for EasterEggRegistry and command resolution."""

    def setUp(self) -> None:
        self.registry: EasterEggRegistry = build_default_registry()

    def test_default_registry_contains_all_core_eggs(self) -> None:
        """Verifies standard catalog includes all expected easter eggs."""
        catalog = self.registry.get_catalog()
        egg_names = [egg.name for egg in catalog]

        expected_names = [
            "Steam Locomotive (sl)",
            "Matrix Digital Rain",
            "Terminal Pipes",
            "Nyan Cat",
            "APT / Aptitude Moo",
            "The Zen of Python",
            "Sudo Insults",
            "Make Love",
            "Emacs M-x doctor",
            "Vim Easter Eggs",
            "Cowsay / Cowthink",
            "Unix Fortune",
            "Vim & Unix Quiz",
        ]
        for name in expected_names:
            self.assertIn(name, egg_names)

    def test_resolve_single_alias_commands(self) -> None:
        """Verifies direct resolution of single-word trigger aliases."""
        test_cases = [
            (["sl"], SteamLocomotive),
            (["LS"], SteamLocomotive),
            (["cmatrix"], MatrixDigitalRain),
            (["pipes"], PlumbingPipes),
            (["pipes.sh"], PlumbingPipes),
            (["nyancat"], NyanCat),
            (["apt"], AptMoo),
            (["apt-get"], AptMoo),
            (["aptitude"], AptMoo),
            (["this"], PythonEggs),
            (["sudo"], SudoInsults),
            (["make"], MakeLove),
            (["doctor"], DoctorEliza),
            (["vim"], VimHelp),
            (["cowsay"], Cowsay),
            (["fortune"], UnixFortune),
            (["quiz"], TriviaQuiz),
        ]
        for tokens, expected_class in test_cases:
            egg, _ = self.registry.resolve(tokens)
            self.assertIsNotNone(egg, f"Failed to resolve {tokens}")
            self.assertIsInstance(egg, expected_class)

    def test_resolve_multi_token_combinations(self) -> None:
        """Verifies resolution of multi-word command invocations."""
        egg, _ = self.registry.resolve(["apt-get", "moo"])
        self.assertIsInstance(egg, AptMoo)

        egg, _ = self.registry.resolve(["aptitude", "-vvv", "moo"])
        self.assertIsInstance(egg, AptMoo)

        egg, _ = self.registry.resolve(["python", "-m", "this"])
        self.assertIsInstance(egg, PythonEggs)

        egg, _ = self.registry.resolve(["python", "-c", "import __hello__"])
        self.assertIsInstance(egg, PythonEggs)

        egg, _ = self.registry.resolve(["python", "-m", "antigravity"])
        self.assertIsInstance(egg, PythonEggs)

        egg, _ = self.registry.resolve(["make", "love"])
        self.assertIsInstance(egg, MakeLove)

    def test_resolve_secret_aliases(self) -> None:
        """Verifies resolution of secret easter egg keywords."""
        for secret_cmd in ["xyzzy", "magic", "42", "secret", "fireworks"]:
            egg, _ = self.registry.resolve([secret_cmd])
            self.assertIsInstance(egg, SecretFireworks)

    def test_resolve_empty_or_unknown(self) -> None:
        """Verifies behavior for empty or unrecognized command arguments."""
        egg, remaining = self.registry.resolve([])
        self.assertIsNone(egg)
        self.assertEqual(remaining, [])

        egg, remaining = self.registry.resolve(["nonexistent_egg_command_12345"])
        self.assertIsNone(egg)
        self.assertEqual(remaining, ["nonexistent_egg_command_12345"])


class TestAptMoo(unittest.TestCase):
    """Unit tests for APT and Aptitude cow easter egg dialogues."""

    def setUp(self) -> None:
        self.apt_egg = AptMoo()

    def test_apt_get_moo_output(self) -> None:
        """Verifies apt-get moo prints classic Debian cow to stdout."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["apt-get", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue(), APT_COW_ART)

    def test_apt_moo_output(self) -> None:
        """Verifies apt moo prints standard cow dialogue."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["apt", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue(), APT_COW_ART)

    def test_apt_build_moo_output(self) -> None:
        """Verifies apt-build moo prints spapped cow to stdout."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["apt-build", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue(), APT_BUILD_COW_ART)

    def test_aptitude_verbosity_levels(self) -> None:
        """Verifies aptitude moo output for various -v verbosity levels."""
        # Level 0 (no -v)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[0])

        # Level 1 (-v)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-v", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[1])

        # Level 2 (-vv)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-vv", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[2])

        # Level 3 (-vvv)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-vvv", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[3])

        # Level 4 (-vvvv)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-vvvv", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[4])

        # Level 5 (-vvvvv) - The secret animal cow
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-vvvvv", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[5].strip()
            )

        # Level 6 (-vvvvvv) - The elephant inside snake
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-vvvvvv", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[6])

    def test_aptitude_separate_v_flags(self) -> None:
        """Verifies aptitude with multiple separate -v flags."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.apt_egg.execute(["aptitude", "-v", "-v", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), APTITUDE_COW_LEVELS[2])

    def test_apt_interactive(self) -> None:
        """Verifies interactive TUI handler for AptMoo."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (30, 100)
        # Simulate pressing space once then 'q' to quit
        mock_stdscr.getch.side_effect = [ord(" "), ord("q")]

        self.apt_egg.interactive(mock_stdscr)
        self.assertGreaterEqual(mock_stdscr.refresh.call_count, 2)


class TestMakeLove(unittest.TestCase):
    """Unit tests for Make target 'make love' simulation."""

    def setUp(self) -> None:
        self.make_egg = MakeLove()

    def test_make_love_error_output(self) -> None:
        """Verifies make love prints error to stderr and returns exit code 2."""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            exit_code = self.make_egg.execute(["make", "love"])
            self.assertEqual(exit_code, 2)
            self.assertIn(
                "make: *** No rule to make target 'love'.  Stop.",
                mock_stderr.getvalue(),
            )

    def test_make_custom_target_error_output(self) -> None:
        """Verifies make with other target returns exit code 2."""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            exit_code = self.make_egg.execute(["make", "war"])
            self.assertEqual(exit_code, 2)
            self.assertIn(
                "make: *** No rule to make target 'war'.  Stop.", mock_stderr.getvalue()
            )

    def test_make_interactive(self) -> None:
        """Verifies interactive viewer for Make lore."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        self.make_egg.interactive(mock_stdscr)
        mock_stdscr.clear.assert_called()


class TestPythonEggs(unittest.TestCase):
    """Unit tests for Python easter eggs."""

    def setUp(self) -> None:
        self.py_egg = PythonEggs()

    def test_zen_of_python_output(self) -> None:
        """Verifies python -m this prints the Zen of Python aphorisms."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.py_egg.execute(["python", "-m", "this"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("The Zen of Python, by Tim Peters", output)
            self.assertIn("Beautiful is better than ugly.", output)
            self.assertIn("Namespaces are one honking great idea", output)

    def test_hello_world_frozen_module(self) -> None:
        """Verifies python -c 'import __hello__' prints Hello world!."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.py_egg.execute(["python", "-c", "import __hello__"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue().strip(), "Hello world!")

    @patch("webbrowser.open")
    def test_antigravity_opens_xkcd_comic(
        self, mock_webbrowser_open: MagicMock
    ) -> None:
        """Verifies import antigravity attempts to open XKCD comic #353."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = self.py_egg.execute(["import", "antigravity"])
            self.assertEqual(exit_code, 0)
            self.assertIn("https://xkcd.com/353/", mock_stdout.getvalue())
            mock_webbrowser_open.assert_called_once_with("https://xkcd.com/353/")


class TestSudoInsults(unittest.TestCase):
    """Unit tests for Sudo password prompt and insults."""

    def setUp(self) -> None:
        self.sudo_egg = SudoInsults()

    def test_sudo_non_interactive_prints_insult(self) -> None:
        """Verifies non-interactive execution prints insult to stderr and exits with 1."""
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            exit_code = self.sudo_egg.execute(["sudo"])
            self.assertEqual(exit_code, 1)
            output = mock_stderr.getvalue()
            self.assertTrue(output.startswith("sudo: "))

    def test_sudo_interactive_wrong_password_retries(self) -> None:
        """Verifies interactive sudo prompts for password up to 3 times before failing."""
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("getpass.getpass", return_value="wrong_password") as mock_getpass,
            patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        ):
            exit_code = self.sudo_egg.execute(["sudo"])
            self.assertEqual(exit_code, 1)
            self.assertEqual(mock_getpass.call_count, 3)
            output = mock_stderr.getvalue()
            self.assertIn("Sorry, try again.", output)
            self.assertIn("sudo: 3 incorrect password attempts", output)

    def test_sudo_interactive_interrupted(self) -> None:
        """Verifies interactive sudo handles KeyboardInterrupt gracefully."""
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("getpass.getpass", side_effect=KeyboardInterrupt),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            exit_code = self.sudo_egg.execute(["sudo"])
            self.assertEqual(exit_code, 1)

    def test_sudo_interactive_menu_mode(self) -> None:
        """Verifies interactive TUI mode for SudoInsults."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [ord(" "), ord("q")]

        self.sudo_egg.interactive(mock_stdscr)
        self.assertGreaterEqual(mock_stdscr.refresh.call_count, 2)


class TestCowsayAndFortune(unittest.TestCase):
    """Unit tests for Cowsay, Cowthink, and Unix Fortune."""

    def test_cowsay_single_line(self) -> None:
        """Verifies cowsay balloon and character rendering for single-line message."""
        cowsay = Cowsay()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = cowsay.execute(["cowsay", "Hello", "Unix"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("< Hello Unix >", output)
            self.assertIn("(oo)", output)
            self.assertIn("||----w |", output)

    def test_cowthink_single_line(self) -> None:
        """Verifies cowthink uses thought balloon and thought connectors."""
        cowsay = Cowsay()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = cowsay.execute(["cowthink", "Deep", "Thoughts"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("( Deep Thoughts )", output)
            self.assertIn("o   ^__^", output)

    def test_cowsay_multiline_balloon(self) -> None:
        """Verifies multi-line balloon wrapping logic."""
        balloon = Cowsay.format_balloon("Line 1 Line 2 Line 3 " * 10, is_think=False)
        lines = balloon.splitlines()
        self.assertTrue(lines[1].startswith("/ "))
        self.assertTrue(lines[-2].startswith("\\ "))

    def test_cowsay_interactive(self) -> None:
        """Verifies interactive Cowsay viewer."""
        cowsay = Cowsay()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        cowsay.interactive(mock_stdscr)
        mock_stdscr.clear.assert_called()

    def test_unix_fortune_prints_known_fortune(self) -> None:
        """Verifies fortune command outputs one of the known fortune cookies."""
        fortune_egg = UnixFortune()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = fortune_egg.execute(["fortune"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue().strip()
            self.assertIn(output, FORTUNE_COOKIES)

    def test_unix_fortune_interactive(self) -> None:
        """Verifies interactive fortune dispenser."""
        fortune_egg = UnixFortune()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        fortune_egg.interactive(mock_stdscr)
        mock_stdscr.clear.assert_called()


class TestVisualEasterEggs(unittest.TestCase):
    """Unit tests for visual/curses-based easter eggs (SL, CMatrix, Pipes, NyanCat, etc.)."""

    @patch("curses.wrapper")
    def test_steam_locomotive_execute_delegates_to_curses(
        self, mock_curses_wrapper: MagicMock
    ) -> None:
        """Verifies SteamLocomotive invokes curses.wrapper."""
        sl = SteamLocomotive()
        exit_code = sl.execute(["sl", "-a", "-F"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_steam_locomotive_animation_frames(self) -> None:
        """Verifies SteamLocomotive animation loop with mock stdscr."""
        sl = SteamLocomotive()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        sl._animate(mock_stdscr, accident=True, little=False, flying=True)
        mock_stdscr.clear.assert_called()
        mock_stdscr.refresh.assert_called()

    def test_steam_locomotive_little_train(self) -> None:
        """Verifies SteamLocomotive with -l option."""
        sl = SteamLocomotive()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        sl._animate(mock_stdscr, accident=False, little=True, flying=False)
        mock_stdscr.clear.assert_called()

    @patch("curses.wrapper")
    def test_cmatrix_execute_delegates_to_curses(
        self, mock_curses_wrapper: MagicMock
    ) -> None:
        """Verifies MatrixDigitalRain invokes curses.wrapper."""
        matrix = MatrixDigitalRain()
        exit_code = matrix.execute(["cmatrix"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_cmatrix_animation(self) -> None:
        """Verifies MatrixDigitalRain animation loop with mock stdscr."""
        matrix = MatrixDigitalRain()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        matrix._animate(mock_stdscr)
        mock_stdscr.refresh.assert_called()

    @patch("curses.wrapper")
    def test_pipes_execute_delegates_to_curses(
        self, mock_curses_wrapper: MagicMock
    ) -> None:
        """Verifies PlumbingPipes invokes curses.wrapper."""
        pipes = PlumbingPipes()
        exit_code = pipes.execute(["pipes"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_pipes_animation(self) -> None:
        """Verifies PlumbingPipes animation loop with mock stdscr."""
        pipes = PlumbingPipes()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        pipes._animate(mock_stdscr)
        mock_stdscr.refresh.assert_called()

    @patch("curses.wrapper")
    def test_nyancat_execute_delegates_to_curses(
        self, mock_curses_wrapper: MagicMock
    ) -> None:
        """Verifies NyanCat invokes curses.wrapper."""
        nyan = NyanCat()
        exit_code = nyan.execute(["nyancat"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_nyancat_animation(self) -> None:
        """Verifies NyanCat animation loop with mock stdscr."""
        nyan = NyanCat()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        nyan._animate(mock_stdscr)
        mock_stdscr.refresh.assert_called()

    @patch("curses.wrapper")
    def test_secret_fireworks_execute_delegates_to_curses(
        self, mock_curses_wrapper: MagicMock
    ) -> None:
        """Verifies SecretFireworks invokes curses.wrapper."""
        secret = SecretFireworks()
        exit_code = secret.execute(["xyzzy"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_secret_fireworks_animation(self) -> None:
        """Verifies SecretFireworks animation loop with mock stdscr."""
        secret = SecretFireworks()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [-1, ord("q")]

        secret._animate(mock_stdscr)
        mock_stdscr.refresh.assert_called()


class TestDoctorAndVimHelp(unittest.TestCase):
    """Unit tests for Emacs Doctor and Vim documentation easter eggs."""

    def test_doctor_eliza_cli_dialogue(self) -> None:
        """Verifies DoctorEliza CLI text session."""
        doctor = DoctorEliza()
        with (
            patch("builtins.input", side_effect=["Hello", "quit"]),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        ):
            exit_code = doctor.execute(["doctor"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Emacs Doctor (ELIZA Psychotherapist)", output)
            self.assertIn("Doctor: Farewell.", output)

    def test_doctor_eliza_interactive_curses(self) -> None:
        """Verifies DoctorEliza curses interactive interface."""
        doctor = DoctorEliza()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getstr.return_value = b"quit"

        doctor.interactive(mock_stdscr)
        mock_stdscr.refresh.assert_called()

    def test_vim_help_42(self) -> None:
        """Verifies vim :help 42 output."""
        vim = VimHelp()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = vim.execute(["vim", ":help", "42"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("*42* The Answer", output)
            self.assertIn("Douglas Adams", output)

    def test_vim_help_holy_wars(self) -> None:
        """Verifies vim :help holy-wars output."""
        vim = VimHelp()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = vim.execute(["vim", ":help", "holy-wars"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("*holy-wars*", output)
            self.assertIn("Vi and Emacs", output)

    def test_vim_help_quotes(self) -> None:
        """Verifies vim :help quotes output."""
        vim = VimHelp()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = vim.execute(["vim", ":help", "quotes"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("*quotes*", output)

    def test_vim_help_interactive(self) -> None:
        """Verifies interactive Vim help documentation viewer."""
        vim = VimHelp()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        vim.interactive(mock_stdscr)
        mock_stdscr.clear.assert_called()


class TestTriviaQuiz(unittest.TestCase):
    """Unit tests for TriviaQuiz questions and game logic."""

    def test_trivia_questions_integrity(self) -> None:
        """Verifies that all trivia questions have valid structure and answers."""
        for idx, q_data in enumerate(TRIVIA_QUESTIONS):
            self.assertIn("question", q_data)
            self.assertIn("options", q_data)
            self.assertIn("answer", q_data)
            self.assertIn("explanation", q_data)

            options = q_data["options"]
            answer = q_data["answer"]
            self.assertIsInstance(options, list)
            self.assertIsInstance(answer, int)
            self.assertTrue(
                0 <= answer < len(options), f"Invalid answer index in question {idx}"
            )

    def test_trivia_quiz_interactive_exit(self) -> None:
        """Verifies TriviaQuiz handles quick exit with 'q'."""
        quiz = TriviaQuiz()
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        quiz.interactive(mock_stdscr)
        mock_stdscr.refresh.assert_called()


class TestCursesHelpers(unittest.TestCase):
    """Unit tests for curses drawing and navigation helpers."""

    def test_safe_addstr_within_bounds(self) -> None:
        """Verifies safe_addstr draws text when coordinates are valid."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (20, 80)

        safe_addstr(mock_stdscr, 5, 10, "Valid Text")
        mock_stdscr.addstr.assert_called_once_with(5, 10, "Valid Text", 0)

    def test_safe_addstr_out_of_bounds_no_exception(self) -> None:
        """Verifies safe_addstr ignores out-of-bounds coordinates safely."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (20, 80)

        safe_addstr(mock_stdscr, 25, 90, "Out of bounds")
        mock_stdscr.addstr.assert_not_called()

    def test_display_scrollable_text(self) -> None:
        """Verifies display_scrollable_text renders and exits cleanly."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (20, 80)
        mock_stdscr.getch.side_effect = [ord("j"), ord("k"), ord("q")]

        lines = [f"Line {i}" for i in range(50)]
        display_scrollable_text(mock_stdscr, "Test Title", lines)
        self.assertGreaterEqual(mock_stdscr.refresh.call_count, 3)


class TestMainCliAndTui(unittest.TestCase):
    """Unit tests for main() entry point and CLI argument processing."""

    def test_main_list_flag(self) -> None:
        """Verifies main(["--list"]) prints available easter eggs and returns 0."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = main(["--list"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Available Unix Easter Eggs:", output)
            self.assertIn("Steam Locomotive (sl)", output)
            self.assertIn("APT / Aptitude Moo", output)

    def test_main_help_flag(self) -> None:
        """Verifies main(["--help"]) prints usage instructions."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = main(["--help"])
            self.assertEqual(exit_code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Usage: unix_eastereggs.py", output)
            self.assertIn("Direct Command Execution:", output)

    def test_main_direct_execution_success(self) -> None:
        """Verifies main() directly executes easter egg command."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = main(["apt-get", "moo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(mock_stdout.getvalue(), APT_COW_ART)

    def test_main_direct_execution_make_love(self) -> None:
        """Verifies main(["make", "love"]) returns 2."""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            exit_code = main(["make", "love"])
            self.assertEqual(exit_code, 2)
            self.assertIn(
                "make: *** No rule to make target 'love'.  Stop.",
                mock_stderr.getvalue(),
            )

    def test_main_unknown_command_returns_1(self) -> None:
        """Verifies main with unknown command prints error to stderr and returns 1."""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            exit_code = main(["invalid_command_xyz"])
            self.assertEqual(exit_code, 1)
            self.assertIn(
                "Error: Unknown command or easter egg", mock_stderr.getvalue()
            )

    @patch("curses.wrapper")
    def test_main_no_args_opens_tui(self, mock_curses_wrapper: MagicMock) -> None:
        """Verifies main([]) launches interactive TUI menu."""
        exit_code = main([])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    @patch("curses.wrapper")
    def test_main_menu_flag_opens_tui(self, mock_curses_wrapper: MagicMock) -> None:
        """Verifies main(["--menu"]) launches interactive TUI menu."""
        exit_code = main(["--menu"])
        self.assertEqual(exit_code, 0)
        mock_curses_wrapper.assert_called_once()

    def test_run_tui_menu_navigation(self) -> None:
        """Verifies run_tui_menu handles arrow keys and quit."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.side_effect = [
            curses.KEY_DOWN,
            curses.KEY_UP,
            ord("j"),
            ord("k"),
            ord("q"),
        ]

        registry = build_default_registry()
        run_tui_menu(mock_stdscr, registry)
        self.assertGreaterEqual(mock_stdscr.refresh.call_count, 5)

    def test_run_tui_menu_secret_sequence(self) -> None:
        """Verifies run_tui_menu triggers secret easter egg upon typing 'xyzzy'."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)

        # Send characters 'x', 'y', 'z', 'z', 'y' followed by 'q'
        key_sequence = [ord(c) for c in "xyzzy"] + [ord("q")]
        mock_stdscr.getch.side_effect = key_sequence

        registry = build_default_registry()
        with patch.object(
            registry.secret_egg, "interactive"
        ) as mock_secret_interactive:
            run_tui_menu(mock_stdscr, registry)
            mock_secret_interactive.assert_called_once()


if __name__ == "__main__":
    unittest.main()
