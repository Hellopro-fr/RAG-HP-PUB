FROM golang:1.25-alpine AS builder
WORKDIR /build
COPY apps-microservices/mcp-leexi-service/ /build/
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-leexi ./cmd/server/

FROM alpine:3.21
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apk upgrade --no-cache
RUN apk add --no-cache ca-certificates
COPY --from=builder /bin/mcp-leexi /bin/mcp-leexi
EXPOSE 8589
ENTRYPOINT ["/bin/mcp-leexi"]
