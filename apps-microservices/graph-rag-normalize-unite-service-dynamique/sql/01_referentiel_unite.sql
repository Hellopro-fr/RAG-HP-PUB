-- =====================================================================
-- Référentiel de normalisation d'unités (dynamique, SQL-driven)
-- Base : HELLOPRO_IA
-- Remplace les dictionnaires hardcodés de
--   graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py
--   (UNIT_TO_DIMENSION, LABEL_TO_DIMENSION, CANONICAL_UNITS + pint define()).
--
-- Colonnes transverses (apprentissage / revue) :
--   est_auto      : 1 = ligne apprise par le learner LLM, 0 = seed/manuel
--   confiance     : score LLM (NULL si seed/manuel)
--   statut_revue  : 0 = validé/actif, 1 = à valider humainement (confiance < seuil)
--   actif         : 1 = chargé par le service, 0 = ignoré (en attente de revue)
--   origine       : 'seed' | 'learner' | 'manual'
--
-- ⚠ Suffixes de colonnes proposés (convention projet à valider) :
--   _udfi / _udi / _ldi / _dci / _uai
-- =====================================================================

-- 1. pint define() bruts — rejoués DANS L'ORDRE (ordre_udfi) car certaines
--    définitions dépendent d'une précédente (ex. "CV = cheval_vapeur").
CREATE TABLE IF NOT EXISTS unite_definition_ia (
    id_udfi            INT AUTO_INCREMENT PRIMARY KEY,
    definition_udfi    VARCHAR(255) NOT NULL,                 -- ex. "KW = 1000 * watt"
    ordre_udfi         INT          NOT NULL DEFAULT 0,
    est_auto_udfi      TINYINT      NOT NULL DEFAULT 0,
    confiance_udfi     FLOAT                 DEFAULT NULL,
    statut_revue_udfi  TINYINT      NOT NULL DEFAULT 0,
    actif_udfi         TINYINT      NOT NULL DEFAULT 1,
    origine_udfi       VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_udfi DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_definition_udfi (definition_udfi),   -- anti-doublon au re-save (UPSERT)
    KEY idx_udfi_actif_ordre (actif_udfi, ordre_udfi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. UNIT_TO_DIMENSION — lookup EXACT par clé minuscule (unicité de clé).
CREATE TABLE IF NOT EXISTS unite_dimension_ia (
    id_udi             INT AUTO_INCREMENT PRIMARY KEY,
    unite_udi          VARCHAR(100) NOT NULL,                 -- stocké en minuscules
    dimension_udi      VARCHAR(50)  NOT NULL,
    est_auto_udi       TINYINT      NOT NULL DEFAULT 0,
    confiance_udi      FLOAT                 DEFAULT NULL,
    statut_revue_udi   TINYINT      NOT NULL DEFAULT 0,
    actif_udi          TINYINT      NOT NULL DEFAULT 1,
    origine_udi        VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_udi  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_unite_udi (unite_udi),
    KEY idx_udi_actif (actif_udi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. LABEL_TO_DIMENSION — match par SOUS-CHAÎNE, ORDONNÉ (priorite_ldi).
--    Le spécifique DOIT précéder le générique ("capacité d'accueil" avant "capacité").
CREATE TABLE IF NOT EXISTS label_dimension_ia (
    id_ldi             INT AUTO_INCREMENT PRIMARY KEY,
    label_ldi          VARCHAR(150) NOT NULL,                 -- mot-clé recherché dans le label
    dimension_ldi      VARCHAR(50)  NOT NULL,
    priorite_ldi       INT          NOT NULL DEFAULT 0,       -- ordre d'évaluation croissant
    est_auto_ldi       TINYINT      NOT NULL DEFAULT 0,
    confiance_ldi      FLOAT                 DEFAULT NULL,
    statut_revue_ldi   TINYINT      NOT NULL DEFAULT 0,
    actif_ldi          TINYINT      NOT NULL DEFAULT 1,
    origine_ldi        VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_ldi  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_label_ldi (label_ldi),               -- 1 label = 1 dimension (anti-doublon, UPSERT)
    KEY idx_ldi_actif_prio (actif_ldi, priorite_ldi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. CANONICAL_UNITS — dimension -> unité canonique (unicité par dimension).
CREATE TABLE IF NOT EXISTS dimension_canonique_ia (
    id_dci               INT AUTO_INCREMENT PRIMARY KEY,
    dimension_dci        VARCHAR(50)  NOT NULL,
    unite_canonique_dci  VARCHAR(100) NOT NULL,               -- ex. "kilogram", "meter ** 2 / hour"
    est_auto_dci         TINYINT      NOT NULL DEFAULT 0,
    confiance_dci        FLOAT                 DEFAULT NULL,
    statut_revue_dci     TINYINT      NOT NULL DEFAULT 0,
    actif_dci            TINYINT      NOT NULL DEFAULT 1,
    origine_dci          VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_dci    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_dimension_dci (dimension_dci),
    KEY idx_dci_actif (actif_dci)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
