FROM golang:1.26-alpine AS builder
WORKDIR /build
COPY apps-microservices/mcp-leexi-service/ /build/
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-leexi ./cmd/server/

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=builder /bin/mcp-leexi /bin/mcp-leexi
EXPOSE 8589
ENTRYPOINT ["/bin/mcp-leexi"]
