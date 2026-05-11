# syntax=docker/dockerfile:1.6
FROM golang:1.25-alpine AS build
WORKDIR /src
COPY apps-microservices/api-catalog-service/go.mod apps-microservices/api-catalog-service/go.sum ./
RUN go mod download
COPY apps-microservices/api-catalog-service/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/server ./cmd/server

FROM alpine:3.20
RUN adduser -D -H -u 10001 catalog && apk add --no-cache ca-certificates wget
USER catalog
COPY --from=build /out/server /usr/local/bin/server
EXPOSE 9100 9101
ENTRYPOINT ["/usr/local/bin/server"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:9101/healthz >/dev/null 2>&1 || exit 1
