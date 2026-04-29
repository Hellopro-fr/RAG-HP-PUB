package ws

import (
	"sync"
	"sync/atomic"
)

type Client struct {
	send   chan []byte
	closed atomic.Bool
}

func newClient() *Client {
	return &Client{send: make(chan []byte, 256)}
}

func NewClientForTest() *Client { return newClient() }

func (c *Client) SendForTest() <-chan []byte { return c.send }

type Hub struct {
	mu      sync.RWMutex
	clients map[*Client]struct{}
	count   atomic.Int64
}

func NewHub() *Hub {
	return &Hub{clients: make(map[*Client]struct{})}
}

func (h *Hub) Register(c *Client) {
	h.mu.Lock()
	h.clients[c] = struct{}{}
	h.mu.Unlock()
	h.count.Add(1)
}

func (h *Hub) Unregister(c *Client) {
	h.mu.Lock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
		h.mu.Unlock()
		if c.closed.CompareAndSwap(false, true) {
			close(c.send)
		}
		h.count.Add(-1)
		return
	}
	h.mu.Unlock()
}

func (h *Hub) Broadcast(msg []byte) {
	h.mu.RLock()
	clients := make([]*Client, 0, len(h.clients))
	for c := range h.clients {
		clients = append(clients, c)
	}
	h.mu.RUnlock()
	for _, c := range clients {
		select {
		case c.send <- msg:
		default:
			h.Unregister(c)
		}
	}
}

func (h *Hub) Count() int64 { return h.count.Load() }

func (h *Hub) Close() {
	h.mu.Lock()
	for c := range h.clients {
		if c.closed.CompareAndSwap(false, true) {
			close(c.send)
		}
		delete(h.clients, c)
	}
	h.mu.Unlock()
	h.count.Store(0)
}
