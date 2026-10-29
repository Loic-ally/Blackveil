package main

import (
	"blackveil/aether/internal/platform"
	"log"
)

func main() {
	if err := platform.Run(); err != nil {
		log.Fatal(err)
	}
}
