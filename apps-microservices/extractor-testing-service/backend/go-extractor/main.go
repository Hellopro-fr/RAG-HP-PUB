package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	nurl "net/url"
	"os"

	"github.com/markusmobius/go-trafilatura"
	"golang.org/x/net/html"
)

type InputJSON struct {
	URL  string `json:"url"`
	HTML string `json:"html"`
}

type OutputJSON struct {
	HTML  string  `json:"html"`
	Error *string `json:"error"`
}

func main() {
	// Configure logging to stderr to avoid polluting stdout
	log.SetOutput(os.Stderr)

	// Read input from stdin
	inputBytes, err := io.ReadAll(os.Stdin)
	if err != nil {
		outputError(fmt.Sprintf("failed to read stdin: %v", err))
		return
	}

	// Parse input JSON
	var input InputJSON
	if err := json.Unmarshal(inputBytes, &input); err != nil {
		outputError(fmt.Sprintf("failed to parse input JSON: %v", err))
		return
	}

	// Extract content
	result, err := extractContent(input.URL, input.HTML)
	if err != nil {
		outputError(err.Error())
		return
	}

	// Output result as JSON
	output := OutputJSON{
		HTML:  result,
		Error: nil,
	}

	outputBytes, err := json.Marshal(output)
	if err != nil {
		outputError(fmt.Sprintf("failed to marshal output JSON: %v", err))
		return
	}

	fmt.Println(string(outputBytes))
}

func extractContent(urlStr, htmlContent string) (string, error) {
	if htmlContent == "" {
		log.Printf("[%s] - Empty HTML content", urlStr)
		return "", nil
	}

	// Parse URL
	var parsedURL *nurl.URL
	var err error
	if urlStr != "" {
		parsedURL, err = nurl.ParseRequestURI(urlStr)
		if err != nil {
			log.Printf("[%s] - Warning: failed to parse URL: %v", urlStr, err)
			// Continue with nil URL instead of failing
			parsedURL = nil
		}
	}

	// Size thresholds to attempt
	sizes := []int{10, 25, 50, 100, 150, 200, 300, 500, 750, 1000}
	results := make(map[int]string)

	// Multi-pass extraction
	for _, size := range sizes {
		config := trafilatura.Config{
			MinExtractedSize: size,
		}

		opts := trafilatura.Options{
			IncludeImages:    true,
			IncludeLinks:     true,
			OriginalURL:      parsedURL,
			PruneSelector:    ".d-none, footer, nav, script, noscript, style",
			Deduplicate:      true,
			Config:           &config,
		}

		result, err := trafilatura.Extract(bytes.NewReader([]byte(htmlContent)), opts)
		if err != nil {
			log.Printf("[%s] - Error extracting with size attempt %d: %v", urlStr, size, err)
			continue
		}

		if result == nil {
			continue
		}

		extractedText := result.ContentText

		// Render HTML content
		var htmlBuf bytes.Buffer
		if result.ContentNode != nil {
			if err := html.Render(&htmlBuf, result.ContentNode); err != nil {
				log.Printf("[%s] - Error rendering HTML for size %d: %v", urlStr, size, err)
				continue
			}
		}

		if htmlBuf.Len() > 0 {
			results[len(extractedText)] = htmlBuf.String()
		}
	}

	// Find the result with the longest text
	var finalContent string
	if len(results) > 0 {
		var maxTextLen int
		for textLen, content := range results {
			if textLen > maxTextLen {
				maxTextLen = textLen
				finalContent = content
			}
		}
		log.Printf("[%s] - Best extraction found with text length: %d chars", urlStr, maxTextLen)
	} else {
		log.Printf("[%s] - No valid extraction after all attempts", urlStr)
	}

	return finalContent, nil
}

func outputError(errMsg string) {
	log.Printf("ERROR: %s", errMsg)
	output := OutputJSON{
		HTML:  "",
		Error: &errMsg,
	}
	outputBytes, _ := json.Marshal(output)
	fmt.Println(string(outputBytes))
}
