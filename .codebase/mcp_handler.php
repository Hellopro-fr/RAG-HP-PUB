<?php
/**
 * MCPHandler — Serveur MCP HelloPro (MySQL lecture seule)
 *
 * 11 couches de sécurité :
 *  1. Token Bearer          2. Pas de GRANT nécessaire (filtrage logiciel)
 *  3. SESSION READ ONLY     4. Whitelist de tables
 *  5. Regex SELECT only     6. Mots-clés dangereux bloqués
 *  7. LIMIT auto (100)      8. Timeout MySQL (10s)
 *  9. HTTPS (.htaccess)    10. config.php inaccessible
 * 11. Anonymisation emails/téléphones dans les résultats
 */
declare(strict_types=1);

class MCPHandler
{
    private array $config;
    /** @var mysqli|null */
    private $mysqli = null;

    private const SERVER_NAME     = 'hellopro-mysql-mcp';
    private const SERVER_VERSION  = '1.0.0';
    private const PROTOCOL_VERSION = '2024-11-05';

    // ── Couche 6 : mots-clés interdits ──
    private const FORBIDDEN_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'REPLACE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'LOAD_FILE', 'BENCHMARK', 'SLEEP', 'OUTFILE', 'DUMPFILE',
        'LOCK\s+TABLES', 'UNLOCK\s+TABLES', 'CALL', 'SET\s',
    ];

    public function __construct(array $config)
    {
        $this->config = $config;
    }

    // ═══════════════════════════════════════════
    //  DISPATCHER JSON-RPC
    // ═══════════════════════════════════════════

    public function handle(array $request): array
    {
        $method = $request['method'] ?? '';
        $id     = $request['id'] ?? null;
        $params = $request['params'] ?? [];

        $this->log("method={$method}");

        try {
            switch ($method) {
                case 'initialize':  $result = $this->initialize(); break;
                case 'initialized': $result = new \stdClass();     break;
                case 'tools/list':  $result = $this->toolsList();  break;
                case 'tools/call':  $result = $this->toolsCall($params); break;
                case 'ping':        $result = ['status' => 'pong']; break;
                default:
                    throw new \RuntimeException("Method not found: {$method}", -32601);
            }
            return ['jsonrpc' => '2.0', 'result' => $result, 'id' => $id];
        } catch (\Throwable $e) {
            $this->log("ERREUR: {$e->getMessage()}");
            return [
                'jsonrpc' => '2.0',
                'error'   => ['code' => $e->getCode() ?: -32603, 'message' => $e->getMessage()],
                'id'      => $id,
            ];
        }
    }

    // ═══════════════════════════════════════════
    //  MCP PROTOCOL
    // ═══════════════════════════════════════════

    private function initialize(): array
    {
        return [
            'protocolVersion' => self::PROTOCOL_VERSION,
            'capabilities'    => ['tools' => new \stdClass()],
            'serverInfo'      => ['name' => self::SERVER_NAME, 'version' => self::SERVER_VERSION],
        ];
    }

    private function toolsList(): array
    {
        $maxRows = $this->config['max_rows'];
        return ['tools' => [
            $this->defTool('list_tables',
                'Liste les tables accessibles avec leur nombre de lignes.',
                []),
            $this->defTool('describe_table',
                'Structure d\'une table (colonnes, types, clés, index).',
                ['table_name' => ['type' => 'string', 'description' => 'Nom de la table']],
                ['table_name']),
            $this->defTool('query_readonly',
                "Exécute un SELECT en lecture seule. Max {$maxRows} lignes. Seuls les SELECT sont autorisés. Bonne pratique : appeler get_table_doc AVANT pour connaitre la structure et le champ default_order_by. Si la table a un default_order_by, l'utiliser dans ORDER BY. Sinon, trier par cle primaire DESC pour les donnees les plus recentes.",
                ['sql' => ['type' => 'string', 'description' => 'Requête SELECT à exécuter']],
                ['sql']),
            $this->defTool('sample_data',
                'Retourne 5 lignes d\'exemple d\'une table.',
                ['table_name' => ['type' => 'string', 'description' => 'Nom de la table']],
                ['table_name']),
            $this->defTool('search_columns',
                'Recherche des colonnes par nom dans toutes les tables (ex: "price", "email").',
                ['column_pattern' => ['type' => 'string', 'description' => 'Motif de recherche']],
                ['column_pattern']),
            $this->defTool('get_table_doc',
                'Documentation metier d\'une table : description, role de chaque colonne, relations et notes. Appeler AVANT d\'ecrire une requete pour comprendre le sens des colonnes. Sans parametre = liste toutes les tables documentees.',
                ['table_name' => ['type' => 'string', 'description' => 'Nom de la table (optionnel, sans = liste toutes)']],
                []),
        ]];
    }

    private function defTool(string $name, string $desc, array $props, array $required = []): array
    {
        return [
            'name'        => $name,
            'description' => $desc,
            'inputSchema' => [
                'type'       => 'object',
                'properties' => empty($props) ? new \stdClass() : $props,
                'required'   => $required,
            ],
        ];
    }

    private function toolsCall(array $params): array
    {
        $name = $params['name'] ?? '';
        $args = $params['arguments'] ?? [];

        try {
            switch ($name) {
                case 'list_tables':    $result = $this->toolListTables();          break;
                case 'describe_table': $result = $this->toolDescribeTable($args);  break;
                case 'query_readonly': $result = $this->toolQueryReadonly($args);   break;
                case 'sample_data':    $result = $this->toolSampleData($args);      break;
                case 'search_columns': $result = $this->toolSearchColumns($args);   break;
                case 'get_table_doc': $result = $this->toolGetTableDoc($args);    break;
                default:
                    throw new \RuntimeException("Unknown tool: {$name}");
            }
            $text = is_string($result) ? $result : json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
            return ['content' => [['type' => 'text', 'text' => $text]], 'isError' => false];
        } catch (\Throwable $e) {
            return ['content' => [['type' => 'text', 'text' => "Erreur: {$e->getMessage()}"]], 'isError' => true];
        }
    }

    // ═══════════════════════════════════════════
    //  6 TOOLS
    // ═══════════════════════════════════════════

    private function toolListTables(): array
    {
        $tables = [];
        foreach ($this->config['allowed_tables'] as $t) {
            try {
                $cnt = $this->queryScalar("SELECT COUNT(*) FROM `{$this->safeId($t)}`");
                $tables[] = ['table' => $t, 'rows' => (int)$cnt];
            } catch (\Throwable $e) {
                $tables[] = ['table' => $t, 'rows' => null, 'error' => 'inaccessible'];
            }
        }
        return [
            'server_date' => date('Y-m-d'),
            'server_time' => date('H:i:s'),
            'timezone'    => date_default_timezone_get(),
            'database'    => $this->config['mysql']['dbname'],
            'tables'      => $tables,
            'tip'         => 'Appeler get_table_doc pour connaitre le default_order_by de chaque table. Si absent, trier par clé primaire DESC.',
        ];
    }

    private function toolDescribeTable(array $a): array
    {
        $t   = $a['table_name'] ?? '';
        $this->assertAllowed($t);
        $safe = $this->safeId($t);
        return [
            'table'   => $t,
            'rows'    => (int)$this->queryScalar("SELECT COUNT(*) FROM `{$safe}`"),
            'columns' => $this->query("DESCRIBE `{$safe}`"),
            'indexes' => $this->query("SHOW INDEX FROM `{$safe}`"),
        ];
    }

    private function toolQueryReadonly(array $a): array
    {
        $sql = trim($a['sql'] ?? '');
        if ($sql === '') throw new \RuntimeException('Requête SQL vide.');

        // ── Couches 5 + 6 : validation ──
        $this->assertSelectOnly($sql);
        $this->assertAllowedTablesInQuery($sql);

        // ── Couche 7 : LIMIT auto ──
        $max = $this->config['max_rows'];
        if (!preg_match('/\bLIMIT\b/i', $sql)) {
            $sql = rtrim($sql, '; ') . " LIMIT {$max}";
        }

        $this->log("SQL: {$sql}");
        $rows = $this->query($sql);

        // ── Couche 11 : anonymisation des données personnelles ──
        $rows = $this->anonymizeRows($rows);

        return [
            'server_date' => date('Y-m-d H:i:s'),
            'sql'         => $sql,
            'row_count'   => count($rows),
            'rows'        => $rows,
            'truncated'   => count($rows) >= $max,
        ];
    }

    private function toolSampleData(array $a): array
    {
        $t = $a['table_name'] ?? '';
        $this->assertAllowed($t);
        $rows = $this->query("SELECT * FROM `{$this->safeId($t)}` LIMIT 5");
        $rows = $this->anonymizeRows($rows);
        return ['table' => $t, 'rows' => $rows];
    }

    private function toolSearchColumns(array $a): array
    {
        $pattern = $a['column_pattern'] ?? '';
        if ($pattern === '') throw new \RuntimeException('Motif vide.');

        $matches = [];
        foreach ($this->config['allowed_tables'] as $t) {
            try {
                $cols = $this->query("DESCRIBE `{$this->safeId($t)}`");
                foreach ($cols as $c) {
                    if (stripos($c['Field'], $pattern) !== false) {
                        $matches[] = ['table' => $t, 'column' => $c['Field'], 'type' => $c['Type'], 'key' => $c['Key']];
                    }
                }
            } catch (\Throwable $e) { /* skip */ }
        }
        return ['pattern' => $pattern, 'matches' => count($matches), 'columns' => $matches];
    }

    /**
     * Tool: get_table_doc — Documentation métier depuis schema_doc.json
     */
    private function toolGetTableDoc(array $a): array
    {
        $docFile = __DIR__ . '/schema_doc.json';
        if (!file_exists($docFile)) {
            throw new \RuntimeException('schema_doc.json non trouvé sur le serveur.');
        }
        $doc = json_decode(file_get_contents($docFile), true);
        if (!$doc) {
            throw new \RuntimeException('schema_doc.json invalide (JSON parse error).');
        }

        $tableName = trim($a['table_name'] ?? '');

        // Sans paramètre = liste toutes les tables documentées avec leur description
        if ($tableName === '') {
            $summary = [];
            foreach ($doc as $key => $val) {
                if ($key === '_meta') continue;
                $summary[] = [
                    'table'       => $key,
                    'description' => $val['description'] ?? '',
                    'rows'        => $val['rows'] ?? null,
                    'columns_doc' => count($val['columns'] ?? []),
                ];
            }
            return [
                'info' => 'Liste des tables documentées. Appeler get_table_doc avec table_name pour le détail.',
                'tables' => $summary,
            ];
        }

        // Avec paramètre = doc complète d'une table
        if (!isset($doc[$tableName])) {
            $available = array_diff(array_keys($doc), ['_meta']);
            throw new \RuntimeException(
                "Pas de documentation pour '{$tableName}'. Tables documentées : " . implode(', ', $available)
            );
        }

        return [
            'table' => $tableName,
            'doc'   => $doc[$tableName],
        ];
    }

    // ═══════════════════════════════════════════
    //  SÉCURITÉ (couches 2, 3, 4, 5, 6)
    // ═══════════════════════════════════════════

    /** Couche 5 : seuls SELECT / WITH autorisés */
    private function assertSelectOnly(string $sql): void
    {
        $up = strtoupper(trim($sql));
        if (!preg_match('/^(SELECT|WITH)\b/', $up)) {
            throw new \RuntimeException('Seules les requêtes SELECT sont autorisées.');
        }
        // Couche 6 : mots-clés dangereux
        foreach (self::FORBIDDEN_KEYWORDS as $kw) {
            if (preg_match('/\b' . $kw . '\b/i', $sql)) {
                throw new \RuntimeException("Mot-clé interdit : {$kw}");
            }
        }
    }

    /** Couche 4 : whitelist de tables dans la requête */
    private function assertAllowedTablesInQuery(string $sql): void
    {
        preg_match_all('/\b(?:FROM|JOIN)\s+`?(\w+)`?/i', $sql, $m);
        $allowed = array_map('strtolower', $this->config['allowed_tables']);
        foreach (($m[1] ?? []) as $table) {
            if (!in_array(strtolower($table), $allowed, true)) {
                throw new \RuntimeException("Table non autorisée : {$table}");
            }
        }
    }

    /** Couche 4 : whitelist pour les tools directs */
    private function assertAllowed(string $t): void
    {
        $allowed = array_map('strtolower', $this->config['allowed_tables']);
        if (!in_array(strtolower($t), $allowed, true)) {
            throw new \RuntimeException("Table non autorisée : {$t}");
        }
    }

    /** Nettoyer un identifiant SQL */
    private function safeId(string $id): string
    {
        if (!preg_match('/^[a-zA-Z_][a-zA-Z0-9_]*$/', $id)) {
            throw new \RuntimeException("Identifiant invalide : {$id}");
        }
        return $id;
    }

    // ═══════════════════════════════════════════
    //  ANONYMISATION (couche 11)
    // ═══════════════════════════════════════════

    /**
     * Anonymise les données personnelles (emails, téléphones) dans les résultats
     */
    private function anonymizeRows(array $rows): array
    {
        foreach ($rows as &$row) {
            foreach ($row as $key => &$value) {
                if (!is_string($value) || $value === '') continue;
                $value = $this->anonymizeValue($value);
            }
            unset($value);
        }
        unset($row);
        return $rows;
    }

    private function anonymizeValue(string $value): string
    {
        // ── Emails ──
        // user@domain.com, prénom.nom@entreprise.co.uk, etc.
        $value = preg_replace(
            '/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/',
            '[email_masque]',
            $value
        );

        // ── Téléphones français ──
        // +33 6 12 34 56 78 | 0033612345678 | 06 12 34 56 78 | 06.12.34.56.78 | 06-12-34-56-78
        $value = preg_replace(
            '/(?:\+33|0033|0)\s*[1-9](?:[\s.\-]?\d{2}){4}/',
            '[tel_masque]',
            $value
        );

        // ── Téléphones internationaux ──
        // +1 555 123 4567 | +44 20 7946 0958 | +49 30 123456
        $value = preg_replace(
            '/\+\d{1,3}[\s.\-]?\d[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{2,6}/',
            '[tel_masque]',
            $value
        );

        // ── Numéros bruts 10 chiffres (FR sans indicatif) ──
        // 0612345678 collé sans séparateurs
        $value = preg_replace(
            '/\b0[1-9]\d{8}\b/',
            '[tel_masque]',
            $value
        );

        return $value;
    }

    // ═══════════════════════════════════════════
    //  CONNEXION MySQL via mysqli (couches 2, 3, 8)
    //  On utilise mysqli comme le reste du site hellopro.fr
    // ═══════════════════════════════════════════

    private function db(): mysqli
    {
        if ($this->mysqli === null) {
            $c = $this->config['mysql'];
            $timeout = (int)(($this->config['mysql_timeout_ms'] ?? 10000) / 1000);

            $this->mysqli = new mysqli($c['host'], $c['username'], $c['password'], $c['dbname'], (int)$c['port']);
            if ($this->mysqli->connect_error) {
                throw new \RuntimeException('MySQL connect error: ' . $this->mysqli->connect_error);
            }
            $this->mysqli->set_charset($c['charset']);
            // Couche 8 : timeout
            $this->mysqli->options(MYSQLI_OPT_READ_TIMEOUT, $timeout);
            // Couche 3 : session read-only
            $this->mysqli->query("SET SESSION TRANSACTION READ ONLY");
            $this->mysqli->query("SET SESSION MAX_EXECUTION_TIME=" . ($this->config['mysql_timeout_ms'] ?? 10000));
        }
        return $this->mysqli;
    }

    /**
     * Exécute un SELECT et retourne un tableau associatif
     */
    private function query(string $sql): array
    {
        $result = $this->db()->query($sql);
        if ($result === false) {
            throw new \RuntimeException('MySQL error: ' . $this->db()->error);
        }
        $rows = [];
        while ($row = $result->fetch_assoc()) {
            $rows[] = $row;
        }
        $result->free();
        return $rows;
    }

    /**
     * Exécute un SELECT et retourne la première colonne de la première ligne
     */
    private function queryScalar(string $sql)
    {
        $result = $this->db()->query($sql);
        if ($result === false) {
            throw new \RuntimeException('MySQL error: ' . $this->db()->error);
        }
        $row = $result->fetch_row();
        $result->free();
        return $row ? $row[0] : null;
    }

    // ═══════════════════════════════════════════
    //  LOGGING
    // ═══════════════════════════════════════════

    private function log(string $msg): void
    {
        $f = __DIR__ . '/logs/mcp.log';
        @file_put_contents($f, '[' . date('Y-m-d H:i:s') . "] {$msg}\n", FILE_APPEND | LOCK_EX);
    }
}
