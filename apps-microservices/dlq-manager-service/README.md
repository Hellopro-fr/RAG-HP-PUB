# Hellopro DLQ Manager Service

This service manages the Dead Letter Queue (DLQ) messages stored in Elasticsearch. It provides a fully responsive dashboard for monitoring failed messages and advanced tools to search, view, edit, and safely process millions of failed events.

## Features

- **Dashboard**: Overview of failed messages by service and error type, with time-series charts.
- **Search**: Advanced search capabilities to find specific messages using Elasticsearch `query_string` syntax.
- **Message Details**: View the full payload and metadata of failed messages, with the ability to copy or edit the payload.
- **Re-queue**: Send messages back to RabbitMQ for processing.
- **Edit & Re-queue**: Modify the payload before re-queuing to fix data formatting errors on the fly.
- **Auto-Archive Rules**: Save complex search queries as active rules. A background engine periodically scans for incoming "New" messages matching these rules and automatically routes them to an "Auto-Archived" state, effectively squelching expected noise and reducing alert fatigue.
- **Bulk Background Operations**: "Re-queue All Matching" and "Archive All Matching" allow you to process massive queues (100,000+ messages). These operations utilize FastAPI background tasks and highly optimized Elasticsearch scroll cursors (excluding heavy payloads when not needed) to prevent HTTP timeouts and protect the cluster from JVM Memory Circuit Breaker crashes.
- **Responsive UI**: A modern interface featuring a collapsible sidebar and mobile-friendly tables, ensuring the dashboard is usable on any device.

## Search Syntax

*Note: A quick-reference version of this guide is also available directly in the application UI by clicking the info (`?`) icon inside the search bar.*

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

## Architecture Note: Background Tasks
To guarantee stability, heavy operations do not block the main HTTP thread:
- **Auto-Archiving**: Runs periodically via an `asyncio.sleep` loop bound to the FastAPI lifecycle.
- **Bulk Archiving**: Fetches lightweight document IDs (`_source=False`) in batches of 500.
- **Bulk Re-queuing**: Fetches full payloads in smaller batches of 50 to respect memory constraints while publishing to RabbitMQ.