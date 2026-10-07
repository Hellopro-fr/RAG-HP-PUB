FROM golang:1.24-alpine AS builder
WORKDIR /build
COPY apps-microservices/mcp-hellodata-service/go.mod ./
RUN go mod download
COPY apps-microservices/mcp-hellodata-service/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /bin/mcp-hellodata ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates \
 && adduser -D -u 10001 nonroot
COPY --from=builder /bin/mcp-hellodata /bin/mcp-hellodata
USER nonroot
EXPOSE 8597
ENTRYPOINT ["/bin/mcp-hellodata"]
