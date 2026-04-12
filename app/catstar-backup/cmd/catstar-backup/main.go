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

func main() {
	configPath := flag.String("config", "catstar-backup.yaml", "Path to the YAML configuration file")
	flag.Parse()

	// Load Configuration
	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// Initialize the Application Kernel
	app, err := runner.NewApp(cfg, os.Stdout, clock.NewRealClock())
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize application: %v\n", err)
		os.Exit(1)
	}

	// Global context bound to OS signals for graceful shutdown
	ctx, cancelSignal := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelSignal()

	// Wrap the signal context with a safety timeout
	ctx, cancelTimeout := context.WithTimeout(ctx, 12*time.Hour)
	defer cancelTimeout()

	// Execute the application kernel
	exitCode := app.Run(ctx)

	os.Exit(exitCode)
}
