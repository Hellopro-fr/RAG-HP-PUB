import { useState, useEffect, useRef, useCallback } from 'react';
import { createEventStream } from './api';

/**
 * Hook: polls an async function at a given interval.
 */
export function usePolling(fetchFn, intervalMs = 5000) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchRef = useRef(fetchFn);
    fetchRef.current = fetchFn;

    const reload = useCallback(() => {
        fetchRef.current()
            .then(d => { setData(d); setError(null); })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        reload();
        const id = setInterval(reload, intervalMs);
        return () => clearInterval(id);
    }, [reload, intervalMs]);

    return { data, loading, error, reload };
}

/**
 * Hook: connects to SSE stream and accumulates events.
 * Keeps the last `maxEvents` in memory.
 */
export function useSSE(maxEvents = 500) {
    const [events, setEvents] = useState([]);
    const [connected, setConnected] = useState(false);
    const sourceRef = useRef(null);

    useEffect(() => {
        const src = createEventStream(
            (event) => {
                if (event.type === 'heartbeat') return;
                setEvents(prev => {
                    const next = [...prev, event];
                    return next.length > maxEvents ? next.slice(-maxEvents) : next;
                });
            },
            () => setConnected(false)
        );
        setConnected(true);
        sourceRef.current = src;

        return () => {
            src.close();
            sourceRef.current = null;
        };
    }, [maxEvents]);

    const clear = useCallback(() => setEvents([]), []);

    return { events, connected, clear };
}
