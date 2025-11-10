import time
import asyncio
import functools
import logging
import inspect
from threading import Thread
from prometheus_client import start_http_server, Histogram, REGISTRY, make_wsgi_app
from waitress import serve

# 1. ADD a new label for the collection type.
PROCESSING_TIME_SECONDS = Histogram(
    'pipeline_processing_duration_seconds',
    'Time spent processing a message or request in a service',
    ['service_name', 'status', 'collection_type']
)

def start_metrics_server_in_thread(port: int = 8000):
    """
    Starts a Prometheus metrics HTTP server in a separate thread.
    This is essential for services that are not already web servers (e.g., RabbitMQ consumers).
    """
    def run_server():
        app = make_wsgi_app()
        # Using waitress for a production-ready simple server
        serve(app, host='0.0.0.0', port=port)

    metrics_thread = Thread(target=run_server, daemon=True)
    metrics_thread.start()
    logging.info(f"✅ Prometheus metrics server started on port {port} in a background thread.")

def get_metrics_app():
    """
    Returns a WSGI app for serving Prometheus metrics.
    Useful for embedding into existing web frameworks like FastAPI.
    """
    return make_wsgi_app()


def measure_processing_time(service_name: str, payload_arg_name: str = None, collection_field_name: str = 'collection'):
    """
    A decorator that measures the execution time of a function (sync or async)
    and records it in the PROCESSING_TIME_SECONDS histogram.

    It can optionally extract a 'collection_type' label from a payload argument.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            collection_value = 'unknown'
            # 2. Logic to inspect arguments and extract the collection type
            if payload_arg_name:
                try:
                    payload = None
                    if payload_arg_name in kwargs:
                        payload = kwargs[payload_arg_name]
                    else:
                        sig = inspect.signature(func)
                        arg_names = list(sig.parameters.keys())
                        if payload_arg_name in arg_names:
                            payload_index = arg_names.index(payload_arg_name)
                            if payload_index < len(args):
                                payload = args[payload_index]
                    
                    # Extract the collection value
                    if payload is not None:
                        if isinstance(payload, list):
                            if payload: # If the batch is not empty
                                first_item = payload[0]
                                if isinstance(first_item, dict):
                                    collection_value = first_item.get(collection_field_name, 'unknown_batch_item')
                                else:
                                    collection_value = getattr(first_item, collection_field_name, 'unknown_batch_item')
                            else:
                                collection_value = 'empty_batch'
                        elif isinstance(payload, dict):
                            collection_value = payload.get(collection_field_name, 'unknown')
                        else: # Assume it's an object/Pydantic model
                            collection_value = getattr(payload, collection_field_name, 'unknown')
                except Exception:
                    # If anything goes wrong, we default to 'unknown' and don't fail the request
                    collection_value = 'error_extracting_label'

            start_time = time.monotonic()
            status = 'success'
            try:
                # Handle both async and sync functions
                if asyncio.iscoroutinefunction(func):
                    # For async functions, we need an awaitable wrapper
                    async def async_wrapper():
                        nonlocal status, collection_value
                        try:
                            return await func(*args, **kwargs)
                        except Exception:
                            status = 'failure'
                            raise
                        finally:
                            duration = time.monotonic() - start_time
                            # 3. Use the new label when recording the metric
                            PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status, collection_type=str(collection_value)).observe(duration)
                            logging.debug(f"[{service_name}] Finished '{func.__name__}'. Status: {status}. Duration: {duration:.4f}s")
                    return async_wrapper()
                else:
                    # For sync functions
                    result = func(*args, **kwargs)
                    return result
            except Exception:
                status = 'failure'
                raise
            finally:
                # This block runs for sync functions, or if an async function
                # wasn't detected (which shouldn't happen with the check above).
                if not asyncio.iscoroutinefunction(func):
                    duration = time.monotonic() - start_time
                    # 3. Use the new label when recording the metric
                    PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status, collection_type=str(collection_value)).observe(duration)
                    logging.debug(f"[{service_name}] Finished '{func.__name__}'. Status: {status}. Duration: {duration:.4f}s")
        return wrapper
    return decorator