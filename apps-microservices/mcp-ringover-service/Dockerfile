FROM golang:1.26-alpine AS builder
WORKDIR /build
COPY apps-microservices/mcp-ringover-service/ /build/
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mcp-ringover ./cmd/server/

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=builder /bin/mcp-ringover /bin/mcp-ringover
EXPOSE 8586
ENTRYPOINT ["/bin/mcp-ringover"]
