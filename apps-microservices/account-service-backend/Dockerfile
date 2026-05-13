# syntax=docker/dockerfile:1.7

FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -buildvcs=false -ldflags="-s -w" -o /out/account-service ./cmd/server

FROM alpine:3.20
RUN addgroup -S app && adduser -S app -G app
RUN apk add --no-cache ca-certificates curl
USER app
COPY --from=build /out/account-service /app/account-service
EXPOSE 8600
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://localhost:8600/health || exit 1
ENTRYPOINT ["/app/account-service"]
