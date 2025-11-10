import time
import asyncio
import functools
import logging
from threading import Thread
from prometheus_client import start_http_server, Histogram, REGISTRY, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

# Define a Histogram metric. Histograms are ideal for measuring durations.
# We will label it by the service name and the outcome (status).
PROCESSING_TIME_SECONDS = Histogram(
    'pipeline_processing_duration_seconds',
    'Time spent processing a message or request in a service',
    ['service_name', 'status']
)

def start_metrics_server_in_thread(port: int = 8000):
    """
    Starts a Prometheus metrics HTTP server in a separate thread.
    This is essential for services that are not already web servers (e.g., RabbitMQ consumers).
    """
    def run_server():
        app = make_wsgi_app()
        # Using run_simple from werkzeug for a more production-ready simple server
        httpd = run_simple('0.0.0.0', port, app)
        httpd.serve_forever()

    metrics_thread = Thread(target=run_server, daemon=True)
    metrics_thread.start()
    logging.info(f"✅ Prometheus metrics server started on port {port} in a background thread.")

def get_metrics_app():
    """
    Returns a WSGI app for serving Prometheus metrics.
    Useful for embedding into existing web frameworks like FastAPI.
    """
    return make_wsgi_app()


def measure_processing_time(service_name: str):
    """
    A decorator that measures the execution time of a function (sync or async)
    and records it in the PROCESSING_TIME_SECONDS histogram.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.monotonic()
            status = 'success'
            try:
                # Handle both async and sync functions
                if asyncio.iscoroutinefunction(func):
                    # For async functions, we need an awaitable wrapper
                    async def async_wrapper():
                        nonlocal status
                        try:
                            return await func(*args, **kwargs)
                        except Exception:
                            status = 'failure'
                            raise
                        finally:
                            duration = time.monotonic() - start_time
                            PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status).observe(duration)
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
                    PROCESSING_TIME_SECONDS.labels(service_name=service_name, status=status).observe(duration)
                    logging.debug(f"[{service_name}] Finished '{func.__name__}'. Status: {status}. Duration: {duration:.4f}s")
        return wrapper
    return decorator