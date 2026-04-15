package api

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
)

// handleListIcons returns all icon files in the uploads/icons directory.
func (h *Handler) handleListIcons(w http.ResponseWriter, r *http.Request) {
	iconsDir := filepath.Join(h.uploadDir, "icons")

	entries, err := os.ReadDir(iconsDir)
	if err != nil {
		// Directory doesn't exist yet — return empty list
		writeJSON(w, http.StatusOK, map[string]interface{}{"icons": []string{}})
		return
	}

	icons := make([]string, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(e.Name()))
		if ext == ".svg" || ext == ".png" || ext == ".jpg" || ext == ".jpeg" || ext == ".webp" {
			icons = append(icons, "/uploads/icons/"+e.Name())
		}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{"icons": icons})
}

// handleUploadIcon accepts a multipart form upload and saves the icon to the uploads/icons directory.
func (h *Handler) handleUploadIcon(w http.ResponseWriter, r *http.Request) {
	const maxBytes = 2 << 20 // 2 MB

	r.Body = http.MaxBytesReader(w, r.Body, maxBytes)

	if err := r.ParseMultipartForm(1 << 20); err != nil {
		if strings.Contains(err.Error(), "request body too large") {
			writeJSON(w, http.StatusRequestEntityTooLarge, ErrorResponse{Error: "file too large (max 2 MB)"})
		} else {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid multipart form: " + err.Error()})
		}
		return
	}

	file, header, err := r.FormFile("icon")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing icon file in request"})
		return
	}
	defer file.Close()

	// Validate file extension
	ext := strings.ToLower(filepath.Ext(header.Filename))
	allowedExts := map[string]bool{".svg": true, ".png": true, ".jpg": true, ".jpeg": true, ".webp": true}
	if !allowedExts[ext] {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid file type — allowed: svg, png, jpg, jpeg, webp"})
		return
	}

	// Ensure icons directory exists
	iconsDir := filepath.Join(h.uploadDir, "icons")
	if err := os.MkdirAll(iconsDir, 0755); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to create icons directory"})
		return
	}

	// Generate unique filename
	filename := uuid.New().String() + ext
	destPath := filepath.Join(iconsDir, filename)

	dest, err := os.Create(destPath)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to save icon"})
		return
	}
	defer dest.Close()

	if _, err := io.Copy(dest, file); err != nil {
		os.Remove(destPath)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to write icon file"})
		return
	}

	iconPath := fmt.Sprintf("/uploads/icons/%s", filename)
	writeJSON(w, http.StatusCreated, map[string]string{"icon": iconPath})
}

// handleUploadImage accepts a multipart form upload and saves the image to uploads/images.
// Used by the documentation builder for inline image elements.
func (h *Handler) handleUploadImage(w http.ResponseWriter, r *http.Request) {
	const maxBytes = 5 << 20 // 5 MB

	// Cap the request body to maxBytes — exceeding triggers a "http: request body too large" error.
	r.Body = http.MaxBytesReader(w, r.Body, maxBytes)

	// ParseMultipartForm's argument is the in-memory threshold, not the size limit.
	// Use a small in-memory buffer (1 MB) so larger files spill to a temp file.
	if err := r.ParseMultipartForm(1 << 20); err != nil {
		if strings.Contains(err.Error(), "request body too large") {
			writeJSON(w, http.StatusRequestEntityTooLarge, ErrorResponse{Error: "file too large (max 5 MB)"})
		} else {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid multipart form: " + err.Error()})
		}
		return
	}

	file, header, err := r.FormFile("image")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing image file in request"})
		return
	}
	defer file.Close()

	ext := strings.ToLower(filepath.Ext(header.Filename))
	allowedExts := map[string]bool{".svg": true, ".png": true, ".jpg": true, ".jpeg": true, ".webp": true, ".gif": true}
	if !allowedExts[ext] {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid file type — allowed: svg, png, jpg, jpeg, webp, gif"})
		return
	}

	imagesDir := filepath.Join(h.uploadDir, "images")
	if err := os.MkdirAll(imagesDir, 0755); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to create images directory"})
		return
	}

	filename := uuid.New().String() + ext
	destPath := filepath.Join(imagesDir, filename)

	dest, err := os.Create(destPath)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to save image"})
		return
	}
	defer dest.Close()

	if _, err := io.Copy(dest, file); err != nil {
		os.Remove(destPath)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to write image file"})
		return
	}

	imagePath := fmt.Sprintf("/uploads/images/%s", filename)
	writeJSON(w, http.StatusCreated, map[string]string{"image": imagePath})
}
