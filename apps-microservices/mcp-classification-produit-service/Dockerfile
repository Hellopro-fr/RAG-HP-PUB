# ── Stage 1: Build Go binary ─────────────────────────────────────────────────
FROM golang:1.24-alpine AS builder

WORKDIR /build
COPY apps-microservices/mcp-classification-produit-service/ /build/

RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-classification-produit ./cmd/server/

# ── Stage 2: Minimal runtime ────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates

COPY --from=builder /bin/mcp-classification-produit /bin/mcp-classification-produit

EXPOSE 8590

ENTRYPOINT ["/bin/mcp-classification-produit"]
