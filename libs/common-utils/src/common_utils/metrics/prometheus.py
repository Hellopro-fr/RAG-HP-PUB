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


def measure_processing_time(service_name: str, payload_arg_name: str = None, collection_field_name: str = 'collection', label_arg_name: str = None):
    """
    A decorator that measures the execution time of a function (sync or async)
    and records it in the PROCESSING_TIME_SECONDS histogram.

    It can optionally extract a 'collection_type' label from a payload argument
    or directly from a named argument.
    """
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)

        # --- FIX: Return an async wrapper for async functions ---
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                collection_value = 'unknown'
                try:
                    sig = inspect.signature(func)
                    arg_names = list(sig.parameters.keys())

                    if label_arg_name and label_arg_name in kwargs:
                        collection_value = kwargs[label_arg_name]
                    elif label_arg_name and label_arg_name in arg_names:
                        label_index = arg_names.index(label_arg_name)
                        if label_index < len(args):
                            collection_value = args[label_index]
                    
                    elif payload_arg_name:
                        payload = None
                        if payload_arg_name in kwargs:
                            payload = kwargs[payload_arg_name]
                        elif payload_arg_name in arg_names:
                            payload_index = arg_names.index(payload_arg_name)
                            if payload_index < len(args):
                                payload = args[payload_index]
                        
                        if payload is not None:
                            if isinstance(payload, list):
                                collection_value = 'empty_batch' if not payload else getattr(payload[0], collection_field_name, 'unknown_batch_item')
                            elif isinstance(payload, dict):
                                collection_value = payload.get(collection_field_name, 'unknown')
                            else:
                                val = getattr(payload, collection_field_name, 'unknown')
                                collection_value = val if val is not None else 'Default'

                except Exception:
                    collection_value = 'error_extracting_label'

                start_time = time.monotonic()
                status = 'success'
                try:
                    # Await the actual async function
                    result = await func(*args, **kwargs)
                    return result
                except Exception:
                    status = 'failure'
                    raise
                finally:
                    duration = time.monotonic() - start_time
                    PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status, collection_type=str(collection_value)).observe(duration)
                    logging.debug(f"[{service_name}] Finished '{func.__name__}'. Status: {status}. Duration: {duration:.4f}s")
            return async_wrapper
        
        # --- FIX: Return a sync wrapper for sync functions ---
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                collection_value = 'unknown'
                try:
                    sig = inspect.signature(func)
                    arg_names = list(sig.parameters.keys())

                    if label_arg_name and label_arg_name in kwargs:
                        collection_value = kwargs[label_arg_name]
                    elif label_arg_name and label_arg_name in arg_names:
                        label_index = arg_names.index(label_arg_name)
                        if label_index < len(args):
                            collection_value = args[label_index]

                    elif payload_arg_name:
                        payload = None
                        if payload_arg_name in kwargs:
                            payload = kwargs[payload_arg_name]
                        elif payload_arg_name in arg_names:
                            payload_index = arg_names.index(payload_arg_name)
                            if payload_index < len(args):
                                payload = args[payload_index]
                        
                        if payload is not None:
                            if isinstance(payload, list):
                                collection_value = 'empty_batch' if not payload else getattr(payload[0], collection_field_name, 'unknown_batch_item')
                            elif isinstance(payload, dict):
                                collection_value = payload.get(collection_field_name, 'unknown')
                            else:
                                val = getattr(payload, collection_field_name, 'unknown')
                                collection_value = val if val is not None else 'Default'
                except Exception:
                    collection_value = 'error_extracting_label'

                start_time = time.monotonic()
                status = 'success'
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception:
                    status = 'failure'
                    raise
                finally:
                    duration = time.monotonic() - start_time
                    PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status, collection_type=str(collection_value)).observe(duration)
                    logging.debug(f"[{service_name}] Finished '{func.__name__}'. Status: {status}. Duration: {duration:.4f}s")
            return sync_wrapper
    return decorator