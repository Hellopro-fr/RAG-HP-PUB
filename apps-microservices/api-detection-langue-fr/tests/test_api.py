import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestAPIEndpoints:
    """Tests d'intégration pour les endpoints API"""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test endpoint /health"""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    @pytest.mark.asyncio
    async def test_check_url_fr_tld(self, client):
        """Test endpoint /check-url avec TLD .fr"""
        response = await client.get("/api/v1/check-url?url=https://www.example.fr")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["method"] == "direct_match"
    
    @pytest.mark.asyncio
    async def test_check_url_no_fr(self, client):
        """Test endpoint /check-url sans indicateur FR"""
        response = await client.get("/api/v1/check-url?url=https://www.example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
    
    @pytest.mark.asyncio
    async def test_detect_with_html_content(self, client):
        """Test endpoint /detect avec contenu HTML fourni"""
        html = '<html lang="fr"><body>Contenu français</body></html>'
        response = await client.post("/api/v1/detect", json={
            "url": "https://www.example.com",
            "mode": "simple",
            "html_content": html
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["method"] == "langHtml"
    
    @pytest.mark.asyncio
    async def test_detect_batch_validation(self, client):
        """Test validation endpoint /detect-batch avec liste vide"""
        response = await client.post("/api/v1/detect-batch", json={
            "urls": [],
            "mode": "simple"
        })
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Test endpoint racine /"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "documentation" in data


class TestAPIModesComparison:
    """Tests comparant les modes simple et complete"""
    
    @pytest.mark.asyncio
    async def test_mode_simple_no_hreflang_detection(self, client):
        """Mode simple ne doit pas détecter les liens hreflang"""
        html = '''
        <html>
        <head>
            <link rel="alternate" hreflang="fr" href="https://example.com/fr/">
        </head>
        <body>English content here</body>
        </html>
        '''
        response = await client.post("/api/v1/detect", json={
            "url": "https://www.example.com",
            "mode": "simple",
            "html_content": html,
            "use_nlp_detection": False
        })
        data = response.json()
        # En mode simple, sans lang HTML ni NLP, devrait échouer
        assert data["ok"] is False
    
    @pytest.mark.asyncio  
    async def test_mode_complete_with_hreflang(self, client):
        """Mode complete doit détecter les liens hreflang"""
        html = '''
        <html>
        <head>
            <link rel="alternate" hreflang="fr" href="https://example.com/fr/">
        </head>
        <body>English content</body>
        </html>
        '''
        response = await client.post("/api/v1/detect", json={
            "url": "https://example.com",
            "mode": "complete",
            "html_content": html,
            "use_nlp_detection": False
        })
        data = response.json()
        assert data["ok"] is True
        assert "alternative_link" in data["method"] or "fr" in data.get("url", "")
