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

// Register inscrit le client et incremente le compteur SOUS LE MEME VERROU que
// l'insertion : sinon Count() peut renvoyer une valeur qui ne correspond a
// aucun etat de la map (Unregister decremente deja sous le verrou).
func (h *Hub) Register(c *Client) {
	h.mu.Lock()
	h.clients[c] = struct{}{}
	h.count.Add(1)
	h.mu.Unlock()
}

// Unregister retire le client et ferme son canal SOUS LE MEME VERROU que la
// suppression : Broadcast emet sous RLock, donc le canal ne peut pas etre
// ferme pendant qu'un envoi est en cours (plus de "send on closed channel").
func (h *Hub) Unregister(c *Client) {
	h.mu.Lock()
	if _, ok := h.clients[c]; ok {
		delete(h.clients, c)
		if c.closed.CompareAndSwap(false, true) {
			close(c.send)
		}
		h.count.Add(-1)
	}
	h.mu.Unlock()
}

// Broadcast envoie le message a tous les clients sous RLock, collecte les
// clients dont le buffer est plein, puis les desinscrit APRES avoir relache
// le verrou (Unregister prend le Lock exclusif).
func (h *Hub) Broadcast(msg []byte) {
	var dropped []*Client
	h.mu.RLock()
	for c := range h.clients {
		select {
		case c.send <- msg:
		default:
			dropped = append(dropped, c)
		}
	}
	h.mu.RUnlock()
	for _, c := range dropped {
		h.Unregister(c)
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
