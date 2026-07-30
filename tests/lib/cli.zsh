# CLI argument parsing routines for ztest.

ztest_parse_cli() {
  setopt localoptions noksharrays

  typeset -g ZTEST_FILTER="*"
  typeset -g ZTEST_LIST_TESTS=false
  typeset -g ZTEST_BREAK_ON_FAILURE=false
  typeset -g ZTEST_USE_COLOR="auto"
  typeset -g ZTEST_CUSTOM_BOOTSTRAP=""
  typeset -ga ZTEST_TARGET_FILES=()

  while (( $# > 0 )); do
    case "$1" in
      --bootstrap=*)
        ZTEST_CUSTOM_BOOTSTRAP="${1#*=}"
        shift
        ;;
      --bootstrap)
        ZTEST_CUSTOM_BOOTSTRAP="$2"
        shift 2
        ;;
      --filter=*|-f=*)
        ZTEST_FILTER="${1#*=}"
        shift
        ;;
      --filter|-f)
        ZTEST_FILTER="$2"
        shift 2
        ;;
      --list|-l)
        ZTEST_LIST_TESTS=true
        shift
        ;;
      --break-on-failure|-b)
        ZTEST_BREAK_ON_FAILURE=true
        shift
        ;;
      --color=*)
        ZTEST_USE_COLOR="${1#*=}"
        shift
        ;;
      --color)
        ZTEST_USE_COLOR="$2"
        shift 2
        ;;
      --help|-h)
        print "Usage: ./run_tests.zsh [options] [test_files...]"
        print "Options:"
        print "  -f, --filter PATTERN        Run only tests matching PATTERN"
        print "  -l, --list                  List discovered tests without running"
        print "  -b, --break-on-failure      Stop execution on first failed test"
        print "      --bootstrap PATH        Specify a bootstrap script to load environment"
        print "      --color=yes|no|auto    Control ANSI colored output"
        print "  -h, --help                  Show this help menu"
        return 10
        ;;
      *)
        if [[ -f "$1" ]]; then
          ZTEST_TARGET_FILES+=("${1:a}")
        fi
        shift
        ;;
    esac
  done

  return 0
}
