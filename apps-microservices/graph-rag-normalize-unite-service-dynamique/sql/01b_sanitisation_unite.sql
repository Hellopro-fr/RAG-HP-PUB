-- =====================================================================
-- Dynamisation de la SANITISATION d'unités (remplace le if/elif hardcodé)
-- Base : HELLOPRO_IA
--
-- 2 tables qui remplacent la majorité de la chaîne if/elif de normalize() :
--   - unite_preprocessing_ia  : transforms universels ordonnés (NFKC, parens, ³→3…)
--   - unite_reecriture_ia     : réécritures exactes unité->expr pint, ou bypass->canonique
--
-- NB : la désambiguïsation contextuelle (nm / t/min / G) reste STATIQUE dans le code
--      (unit_normalization_service._STATIC_DISAMBIGUATIONS) — 3 cas seulement,
--      dynamisation en base injustifiée (schéma lourd, croissance quasi nulle).
-- =====================================================================

-- 1. Transforms universels appliqués à toute unité, DANS L'ORDRE (ordre_upi).
--    phase_upi : 'pre_snapshot' (avant snapshot original_unit, sert au lookup dimension)
--                'post_snapshot' (après, sert à l'expression pint finale)
--    type_upi  : 'nfkc' | 'regex_sub' | 'str_replace'
CREATE TABLE IF NOT EXISTS unite_preprocessing_ia (
    id_upi             INT AUTO_INCREMENT PRIMARY KEY,
    type_upi           VARCHAR(20)  NOT NULL,                 -- nfkc | regex_sub | str_replace
    phase_upi          VARCHAR(20)  NOT NULL DEFAULT 'pre_snapshot',
    pattern_upi        VARCHAR(255)          DEFAULT NULL,    -- regex (regex_sub) ou char source (str_replace) ; NULL si nfkc
    remplacement_upi   VARCHAR(255) NOT NULL DEFAULT '',
    ordre_upi          INT          NOT NULL DEFAULT 0,
    actif_upi          TINYINT      NOT NULL DEFAULT 1,
    origine_upi        VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_upi  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_upi_actif_ordre (actif_upi, ordre_upi)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Réécritures exactes (clé minuscule). kind_uri='rewrite' -> value_uri = expression pint ;
--    kind_uri='bypass' -> value_uri = unité canonique retournée directement (sans pint).
CREATE TABLE IF NOT EXISTS unite_reecriture_ia (
    id_uri             INT AUTO_INCREMENT PRIMARY KEY,
    unite_source_uri   VARCHAR(150) NOT NULL,                 -- clé minuscule (ex. "m3/h", "%")
    kind_uri           VARCHAR(20)  NOT NULL DEFAULT 'rewrite',
    value_uri          VARCHAR(150) NOT NULL,                 -- expr pint OU unité canonique (bypass)
    est_auto_uri       TINYINT      NOT NULL DEFAULT 0,
    confiance_uri      FLOAT                 DEFAULT NULL,
    statut_revue_uri   TINYINT      NOT NULL DEFAULT 0,
    actif_uri          TINYINT      NOT NULL DEFAULT 1,
    origine_uri        VARCHAR(20)  NOT NULL DEFAULT 'seed',
    date_creation_uri  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_unite_source_uri (unite_source_uri),
    KEY idx_uri_actif (actif_uri)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
