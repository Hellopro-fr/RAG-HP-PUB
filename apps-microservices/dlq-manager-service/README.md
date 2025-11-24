# DLQ Manager Service

This service manages the Dead Letter Queue (DLQ) messages stored in Elasticsearch. It provides a dashboard for monitoring failed messages and tools to search, view, edit, and re-queue them.

## Features

- **Dashboard**: Overview of failed messages by service and error type.
- **Search**: Advanced search capabilities to find specific messages.
- **Message Details**: View full payload and metadata of failed messages.
- **Re-queue**: Send messages back to RabbitMQ for processing.
- **Edit & Re-queue**: Modify the payload before re-queuing.

## Search Syntax

The "Search Term" field in the application supports the Elasticsearch `query_string` syntax, allowing for powerful queries.

### Basic Search
- **Simple text**: `connection` (finds messages containing "connection")
- **Exact phrase**: `"connection refused"`

### Wildcards
- **`*`**: Matches any character sequence.
  - `*timeout*` (finds "timeout", "connection_timeout", etc.)
  - `serv*` (finds "service", "server", etc.)
- **`?`**: Matches a single character.

### Boolean Operators
- **`AND`**: Both terms must be present.
  - `timeout AND database`
- **`OR`**: At least one term must be present (default behavior).
  - `timeout OR error`
- **`NOT`**: Exclude documents containing the term.
  - `timeout NOT database`

### Field-Specific Search
You can search within specific fields:

- **`service_name`**: The name of the service that failed.
  - `service_name:embedding-service`
- **`error_reason`**: The error message.
  - `error_reason:*timeout*`
- **`original_payload`**: Search within the message content.
  - `original_payload.product_id:12345`
  - `original_payload.email:*@example.com`

### Examples

1. **Find all timeout errors in the embedding service:**
   ```
   service_name:embedding-service AND error_reason:*timeout*
   ```

2. **Find messages related to a specific product ID:**
   ```
   original_payload.product_id:98765
   ```

3. **Find errors that are NOT related to network issues:**
   ```
   NOT error_reason:*network*
   ```
