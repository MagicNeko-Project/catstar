package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/runner"
)

const defaultExecutionTimeout = 12 * time.Hour

func main() {
	os.Exit(run())
}

func run() int {
	configPath := flag.String("config", "catstar-backup.yaml", "Path to the YAML configuration file")
	flag.Parse()

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
