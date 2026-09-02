package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"runtime/debug"
	"syscall"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/runner"
)

var (
	version   = "dev"
	gitCommit = ""
	buildDate = ""
)

func init() {
	if buildInformation, isAvailable := debug.ReadBuildInfo(); isAvailable {
		if version == "dev" && buildInformation.Main.Version != "" && buildInformation.Main.Version != "(devel)" {
			version = buildInformation.Main.Version
		}
		for _, setting := range buildInformation.Settings {
			switch setting.Key {
			case "vcs.revision":
				if gitCommit == "" {
					gitCommit = setting.Value
				}
			case "vcs.time":
				if buildDate == "" {
					buildDate = setting.Value
				}
			}
		}
	}

	if version == "" {
		version = "dev"
	}
	if gitCommit == "" {
		gitCommit = "none"
	}
	if buildDate == "" {
		buildDate = "unknown"
	}
}

const defaultExecutionTimeout = 12 * time.Hour

func main() {
	os.Exit(run())
}

func run() int {
	configPath := flag.String("config", "catstar-backup.yaml", "Path to the YAML configuration file")
	showVersion := flag.Bool("version", false, "Display version information and exit")
	flag.Parse()

	if *showVersion {
		binaryName := filepath.Base(os.Args[0])
		fmt.Printf("%s %s (commit: %s, built: %s)\n", binaryName, version, gitCommit, buildDate)
		return 0
	}

	loadedConfig, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		return 1
	}

	appInstance, err := runner.NewApp(loadedConfig, os.Stdout, clock.NewRealClock())
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize application: %v\n", err)
		return 1
	}

	signalContext, stopSignals := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopSignals()

	timeoutContext, cancelTimeout := context.WithTimeout(signalContext, defaultExecutionTimeout)
	defer cancelTimeout()

	return appInstance.Run(timeoutContext)
}
