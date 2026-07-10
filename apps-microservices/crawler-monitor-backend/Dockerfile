FROM golang:1.25-alpine AS builder
WORKDIR /src
RUN apk add --no-cache git ca-certificates
COPY go.mod go.sum ./
RUN go mod download
COPY . .
# Trivy gate (politique Go, ≠ Python) : bump golang.org/x/crypto v0.50.0 -> v0.52.0
# 9 HIGH CVE dans x/crypto/ssh (non utilise ici : seuls scrypt+bcrypt le sont), mais gate ACTIVE.
# Fix applique au build : go.mod/go.sum du repo restent en v0.50.0 car pas de Docker/Go local
# cote dev (Windows). Aligne sur le pattern mcp-api-recherche / mcp-classification-produit.
RUN go get golang.org/x/crypto@v0.52.0 && go mod tidy
ENV CGO_ENABLED=0 GOOS=linux GOFLAGS="-trimpath"
ARG VERSION=dev
RUN go build -ldflags="-s -w -X main.version=${VERSION}" -o /out/server ./cmd/server

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=builder /out/server /app/server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER nonroot:nonroot
EXPOSE 3001
ENTRYPOINT ["/app/server"]
