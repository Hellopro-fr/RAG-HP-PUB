package ws

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"runtime/debug"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// stringOrNum extrait une chaine d'une valeur de map qui peut etre une chaine
// ou un nombre.
func stringOrNum(v any) string {
	switch val := v.(type) {
	case string:
		return val
	case float64:
		if val == float64(int64(val)) {
			return strconv.FormatInt(int64(val), 10)
		}
		return strconv.FormatFloat(val, 'f', -1, 64)
	case int64:
		return strconv.FormatInt(val, 10)
	}
	return ""
}

// defaultIdleTimeout : duree de silence au-dela de laquelle un abonnement est
// suspect si des crawls tournent (les heartbeats arrivent toutes les 2 s).
const defaultIdleTimeout = 120 * time.Second

type PubSub struct {
	rs       *redisstore.Client
	hub      *Hub
	channels []string
	// lastMessageAt : horodatage unix ms du dernier message recu sur les
	// canaux Redis, amorce a l'abonnement. Expose par /api/system/health
	// pour detecter un abonnement mort alors que des crawls tournent encore.
	lastMessageAt atomic.Int64
	// idleResubscribes : nombre de reabonnements declenches par le watchdog.
	idleResubscribes atomic.Int64
	idleTimeout      time.Duration
}

func NewPubSub(rs *redisstore.Client, hub *Hub, channels ...string) *PubSub {
	return &PubSub{rs: rs, hub: hub, channels: channels, idleTimeout: defaultIdleTimeout}
}

// LastMessageAt retourne l'horodatage unix ms du dernier message recu (0 si aucun).
func (p *PubSub) LastMessageAt() int64 { return p.lastMessageAt.Load() }

// SetIdleTimeoutForTest raccourcit le delai du watchdog. A appeler avant Run.
func (p *PubSub) SetIdleTimeoutForTest(d time.Duration) { p.idleTimeout = d }

// SetLastMessageAtForTest force l'horodatage du dernier message recu.
func (p *PubSub) SetLastMessageAtForTest(ms int64) { p.lastMessageAt.Store(ms) }

// IdleResubscribesForTest retourne le nombre de reabonnements du watchdog.
func (p *PubSub) IdleResubscribesForTest() int64 { return p.idleResubscribes.Load() }

func (p *PubSub) Run(ctx context.Context) {
	backoff := time.Second
	const maxBackoff = 30 * time.Second
	for {
		received, err := p.runOnce(ctx)
		// Un abonnement qui a effectivement servi n'est pas une boucle
		// d'echec : on repart du backoff minimal plutot que de garder le
		// palier atteint par les pannes precedentes.
		if received {
			backoff = time.Second
		}
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			slog.Warn("ws.pubsub.disconnect", "err", err, "backoff", backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return
			}
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
			continue
		}
		return
	}
}

// errChannelClosed : le canal de reception go-redis a ete ferme (perte de la
// connexion subscriber). On remonte une erreur pour que Run relance
// l'abonnement — retourner nil arreterait la diffusion definitivement.
var errChannelClosed = errors.New("pubsub channel closed")

// errPubSubIdle : plus aucun message alors que des crawls tournent. Le canal
// go-redis n'est pas ferme pour autant (connexion a demi-morte) : seul un
// reabonnement complet remet la diffusion en marche.
var errPubSubIdle = errors.New("pubsub idle while crawls are running")

// runOnce tient un abonnement jusqu'a sa perte. Le premier retour indique si au
// moins un message a ete recu, ce qui permet a Run de distinguer un abonnement
// sain qui vient de tomber d'une boucle d'echec.
func (p *PubSub) runOnce(ctx context.Context) (bool, error) {
	sub := p.rs.Subscribe(ctx, p.channels...)
	defer sub.Close()
	if _, err := sub.Receive(ctx); err != nil {
		return false, err
	}
	ch := sub.Channel()
	// Amorcer l'horodatage a l'abonnement : sans ca, /api/system/health ne
	// distingue pas "jamais abonne" de "abonne il y a une heure, muet depuis".
	p.lastMessageAt.Store(time.Now().UnixMilli())
	slog.Info("ws.pubsub.subscribed", "channels", p.channels)

	idle := time.NewTimer(p.idleTimeout)
	defer idle.Stop()
	received := false
	for {
		select {
		case <-ctx.Done():
			return received, nil
		case msg, ok := <-ch:
			if !ok {
				return received, errChannelClosed
			}
			received = true
			p.lastMessageAt.Store(time.Now().UnixMilli())
			// Diffuser d'abord : la latence WS du dashboard n'a pas a
			// attendre l'aller-retour Redis. Les deux etapes sont
			// independantes et chacune isolee dans son propre recover(),
			// donc un panic de l'une n'empeche pas l'autre.
			safe("broadcast", func() { p.broadcastTransformed(msg.Payload) })
			safe("persist", func() { p.persistAndNotify(ctx, msg.Payload) })
			resetTimer(idle, p.idleTimeout)
		case <-idle.C:
			// Silence prolonge : si des crawls tournent, des heartbeats
			// devraient arriver. L'abonnement est mort sans que go-redis
			// nous l'ait signale — on le reconstruit.
			if running, err := p.runningCount(ctx); err == nil && running > 0 {
				p.idleResubscribes.Add(1)
				slog.Warn("ws.pubsub.idle_resubscribe",
					"idle", p.idleTimeout, "running", running, "channels", p.channels)
				return received, errPubSubIdle
			}
			idle.Reset(p.idleTimeout)
		}
	}
}

// runningCount lit le nombre de crawls actifs (best effort).
func (p *PubSub) runningCount(ctx context.Context) (int, error) {
	running, _, err := p.rs.GetCapacity(ctx)
	return running, err
}

// resetTimer redemarre un timer deja arme sans laisser de tick en attente.
func resetTimer(t *time.Timer, d time.Duration) {
	if !t.Stop() {
		select {
		case <-t.C:
		default:
		}
	}
	t.Reset(d)
}

// safe execute fn en isolant les panics et en les tracant.
func safe(op string, fn func()) {
	defer func() {
		if r := recover(); r != nil {
			slog.Error("ws.pubsub.panic", "op", op, "err", r, "stack", string(debug.Stack()))
		}
	}()
	fn()
}

// broadcastTransformed convertit un heartbeat brut Redis en enveloppe
// replica_heartbeat attendue par le frontend React :
//
//	{ type: "replica_heartbeat", data: { replicaId, cpu, ram, … } }
//
// Les job_update ne sont PAS emis a chaque heartbeat (tempete de requetes
// React Query) : ils viennent des messages crawl_updates publies par
// crawler-service lors d'un changement de statut.
func (p *PubSub) broadcastTransformed(payload string) {
	var raw map[string]any
	if err := json.Unmarshal([]byte(payload), &raw); err != nil {
		p.hub.Broadcast([]byte(payload))
		return
	}

	msgType, _ := raw["type"].(string)
	if msgType != "heartbeat" {
		// crawler-service publie les changements de statut sur crawl_updates
		// au format {crawl_id, status, timestamp} sans champ type. Le frontend
		// React ne reagit qu aux messages {type:job_update, crawl_id}. On les
		// traduit donc en job_update type : sans ca, les transitions de statut
		// (finished/failed/archived/stopping/restarting_oom) n atteignent jamais
		// le dashboard (aucun polling REST de secours n existe).
		if cid := stringOrNum(raw["crawl_id"]); cid != "" {
			p.emitJobUpdate(cid)
			return
		}
		p.hub.Broadcast([]byte(payload))
		return
	}

	replicaEnvelope := map[string]any{
		"type": "replica_heartbeat",
		"data": raw,
	}
	if b, err := json.Marshal(replicaEnvelope); err == nil {
		p.hub.Broadcast(b)
	}
}

// emitJobUpdate envoie { type: "job_update", crawl_id } a tous les clients
// WebSocket, ce qui declenche l'invalidation du cache React Query.
func (p *PubSub) emitJobUpdate(jobID string) {
	envelope := map[string]any{
		"type":     "job_update",
		"crawl_id": jobID,
	}
	if b, err := json.Marshal(envelope); err == nil {
		p.hub.Broadcast(b)
	}
}

// persistAndNotify persiste les series temporelles issues des heartbeats.
// La cle crawl_job:<id> n'est PLUS reecrite ici : elle appartient a
// crawler-service (Python), qui y ecrit deja status/replica_id/dates.
func (p *PubSub) persistAndNotify(ctx context.Context, payload string) {
	var msg map[string]any
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		return
	}
	replicaID := stringOrNum(msg["replicaId"])
	jobID := stringOrNum(msg["jobId"])
	if replicaID == "" && jobID == "" {
		return
	}

	ts := time.Now().UnixMilli()
	if v, ok := msg["timestamp"].(float64); ok {
		ts = int64(v)
	}
	cpu, _ := msg["cpu"].(float64)
	ram, _ := msg["ram"].(float64)
	totalRAM, _ := msg["totalRam"].(float64)

	var jobIDPtr *string
	if jobID != "" {
		jobIDPtr = &jobID
	}
	p.rs.PersistHeartbeat(ctx, replicaID, ts, cpu, ram, totalRAM, jobIDPtr)

	// Meme forme de membre que l'implementation Express, pour que le
	// chargeur de capacity planning la decode sans changement.
	sample := map[string]any{
		"ts":       ts,
		"cpu":      cpu,
		"ram":      ram,
		"totalRam": totalRAM,
		"jobId":    jobID,
	}
	if replicaID != "" {
		sample["replicaId"] = replicaID
	}
	p.rs.PersistJobPerfSample(ctx, jobID, ts, sample)
}
