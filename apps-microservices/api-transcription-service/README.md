# API de Transcription en Streaming en Temps Réel

Ce projet est une API de transcription audio en temps réel construite avec FastAPI, WebSockets et Google Speech-to-Text. Il est conçu selon les principes de la Clean Architecture pour être robuste, maintenable et testable.

## Fonctionnalités

-   Transcription en temps réel via WebSockets.
-   Intégration avec l'API Google Cloud Speech-to-Text.
-   Gestion concurrente de plusieurs clients.
-   Interface de test simple en HTML/JavaScript avec visualiseur audio.
-   Architecture propre et découplée.
-   Configuration via variables d'environnement.
-   Prêt pour la conteneurisation avec Docker.

## Structure du Projet

Le projet suit une structure inspirée de la Clean Architecture :

-   `app/main.py`: Point d'entrée de l'application FastAPI.
-   `app/api/`: Contient les endpoints de l'API (WebSockets).
-   `app/core/`: Contient la logique métier (`services`) et les modèles de données (`models`).
-   `app/infrastructure/`: Gère les aspects techniques comme la gestion des WebSockets.
-   `config/`: Gère la configuration de l'application.
-   `static/`: Contient les fichiers frontend (HTML, JS, CSS).
-   `tests/`: Contient les tests unitaires et fonctionnels.

## Prérequis

-   Python 3.9+
-   Un compte Google Cloud avec l'API Speech-to-Text activée.
-   Un fichier de clés de service Google Cloud (JSON).

## Installation

1.  **Clonez le dépôt ou utilisez le script de génération.**

2.  **Naviguez dans le répertoire du projet :**
    ```bash
    cd api-transcription-service
    ```

3.  **Créez un environnement virtuel et activez-le :**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # Sur Windows: venv\Scripts\activate
    ```

4.  **Installez les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configurez les variables d'environnement :**
    -   Copiez le fichier `.env.example` en `.env`.
        ```bash
        cp .env.example .env
        ```
    -   Modifiez le fichier `.env` :
        -   `JSON_KEY`: Spécifiez le chemin **absolu** vers votre fichier de clés de service Google Cloud.
        -   `AUTH_TOKEN`: Définissez un token secret pour sécuriser l'accès au WebSocket.

## Lancement de l'Application

Pour lancer le serveur de développement :

```bash
uvicorn main:app --host 0.0.0.0 --port 8515 --reload
