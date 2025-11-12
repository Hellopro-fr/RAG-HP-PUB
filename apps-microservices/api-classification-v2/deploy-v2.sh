#!/bin/bash
# Script de déploiement pour API Classification V2

echo "🚀 Déploiement de API Classification V2..."

# Vérifier que Docker est démarré
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker n'est pas démarré. Veuillez démarrer Docker Desktop."
    exit 1
fi

# Build des images
echo "📦 Build de l'image api-classification-v2-service..."
docker-compose build api-classification-v2-service

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du build de api-classification-v2-service"
    exit 1
fi

echo "📦 Build de l'image api-classification-v2-lb..."
docker-compose build api-classification-v2-lb

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du build de api-classification-v2-lb"
    exit 1
fi

# Démarrer les services
echo "▶️  Démarrage des services..."
docker-compose up -d api-classification-v2-service api-classification-v2-lb

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du démarrage des services"
    exit 1
fi

# Attendre que les services soient prêts
echo "⏳ Attente du démarrage des services (30 secondes)..."
sleep 30

# Vérifier le health check
echo "🔍 Vérification du health check..."
HEALTH_RESPONSE=$(curl -s http://localhost:8578/health)

if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✅ API Classification V2 est opérationnelle !"
    echo "📍 URL: http://localhost:8578"
    echo ""
    echo "🧪 Tests disponibles :"
    echo "  - Health: curl http://localhost:8578/health"
    echo "  - Status: curl http://localhost:8578/classification/status"
    echo "  - Version: curl http://localhost:8578/"
    echo ""
    echo "📊 Voir les logs:"
    echo "  docker-compose logs -f api-classification-v2-service"
else
    echo "⚠️  Service démarré mais health check échoué"
    echo "Réponse: $HEALTH_RESPONSE"
    echo ""
    echo "Vérifiez les logs:"
    echo "  docker-compose logs api-classification-v2-service"
fi

# Afficher les replicas actifs
echo ""
echo "📈 Replicas actifs:"
docker-compose ps api-classification-v2-service
