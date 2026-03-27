<?php
/**
 * Configuration MCP HelloPro — NE JAMAIS COMMITTER CE FICHIER
 */

// Charger les credentials depuis le fichier de connexion existant
require $_SERVER['DOCUMENT_ROOT'] . '/no_read_access/connexion_base_mcp.php';

return [
    'mysql' => [
        'host'     => $host_bo,
        'port'     => 3306,
        'dbname'   => $db_bo,
        'username' => $user_bo,
        'password' => $pass_bo,
        'charset'  => 'utf8mb4',
    ],

    // Token Bearer — générer avec : openssl rand -hex 32
    'mcp_auth_token' => '7bd1733957a4935d053358500f917e6acb534b32ac9a534f65e7955fa86e14b4',

    // Whitelist de tables exposées (couche 4)
    'allowed_tables' => [        
        'rubrique',
        'demande_information',
        'rubrique_2',
        'produit_front',
        'page_conseil',
        'page_filtre_maillage',
        'page_filtre',
        'mon_compte_demo_recherche_leads',
        'marche_lead_categorie',
        'marche_lead',
        'societe'
        // Ajouter ici les tables à exposer
    ],

    // Limite max de lignes retournées (couche 7)
    'max_rows' => 100,

    // Timeout MySQL en ms (couche 8)
    'mysql_timeout_ms' => 10000,
];
