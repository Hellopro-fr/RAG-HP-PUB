-- =====================================================================
-- Journal + déduplication d'apprentissage du learner LLM.
-- Base : HELLOPRO_IA
--
-- Rôle :
--   - Dédoublonner les unités inconnues vues par le learner (1 appel LLM par
--     unité, pas par produit) → clé UNIQUE (unite, label_context).
--   - Tracer chaque décision (payload LLM, confiance, raison de rejet).
--   - Servir de "claim" atomique (statut=processing) pour éviter que 2 workers
--     traitent la même unité en parallèle.
--
-- statut_uai :
--   pending       : vue, pas encore traitée
--   processing    : claim posé par un worker (en cours LLM/validation)
--   learned       : apprise et appliquée (lignes référentiel actif=1)
--   needs_review  : confiance < seuil OU validation pint OK mais à valider → actif=0
--   rejected      : validation pint déterministe échouée (anti-hallucination)
--   -- batch manuel (learner) :
--   pending_activation  : Gate 1 OK, lignes écrites INACTIVES (actif=0) → activation manuelle requise
--   erreur_verification : Gate 1 NOK → vérification manuelle (aucune ligne écrite)
-- nb_requeue_uai : conservé pour compat ; non utilisé par le learner batch (plus de requeue auto).
-- =====================================================================

CREATE TABLE IF NOT EXISTS unite_apprentissage_ia (
    id_uai              INT AUTO_INCREMENT PRIMARY KEY,
    unite_uai           VARCHAR(150) NOT NULL,
    label_context_uai   VARCHAR(255) NOT NULL DEFAULT '',     -- '' si pas de contexte label
    statut_uai          VARCHAR(20)  NOT NULL DEFAULT 'pending',
    confiance_uai       FLOAT                 DEFAULT NULL,
    nb_occurrences_uai  INT          NOT NULL DEFAULT 1,
    nb_requeue_uai      INT          NOT NULL DEFAULT 0,    -- anti-boucle : nb de requeue d'une unité 'learned'
    payload_llm_uai     JSON                  DEFAULT NULL,
    raison_rejet_uai    VARCHAR(255)          DEFAULT NULL,
    date_creation_uai   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_maj_uai        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_unite_label_uai (unite_uai, label_context_uai),
    KEY idx_uai_statut (statut_uai)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
