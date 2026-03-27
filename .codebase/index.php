<?php
/**
 * Serveur MCP HelloPro — Point d'entrée HTTP
 * URL : https://bo.hellopro.fr/admin/mcp_hp
 *
 * Transport : Streamable HTTP (POST = JSON-RPC, GET = SSE endpoint)
 */
declare(strict_types=1);
error_reporting(0);
ini_set('display_errors', '0');

$config = require __DIR__ . '/config.php';
require __DIR__ . '/mcp_handler.php';

// ── Couche 1 : Token Bearer ──
// On utilise 403 (pas 401) pour éviter que mcp-remote déclenche un flow OAuth
$token = '';
$auth  = $_SERVER['HTTP_AUTHORIZATION']
    ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION']
    ?? $_SERVER['HTTP_X_MCP_TOKEN']
    ?? '';
if (preg_match('/^Bearer\s*(.+)$/i', $auth, $m)) {
    $token = $m[1];
}
if (!hash_equals($config['mcp_auth_token'], $token)) {
    http_response_code(403);
    header('Content-Type: application/json');
    die(json_encode([
        'jsonrpc' => '2.0',
        'error'   => ['code' => -32001, 'message' => 'Forbidden - invalid token'],
        'id'      => null,
    ]));
}

// ── Routing ──
$method = $_SERVER['REQUEST_METHOD'];

// GET → Répondre au protocole Streamable HTTP (pas de SSE persistant)
// Ecritel bloque le streaming SSE, donc on utilise le transport Streamable HTTP
if ($method === 'GET') {
    // Répondre 405 pour forcer mcp-remote à utiliser POST uniquement
    http_response_code(405);
    header('Content-Type: application/json');
    echo json_encode([
        'jsonrpc' => '2.0',
        'error'   => ['code' => -32601, 'message' => 'Use POST for MCP requests'],
        'id'      => null,
    ]);
    exit;
}

// POST → JSON-RPC
if ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!$body) {
        http_response_code(400);
        header('Content-Type: application/json');
        die(json_encode([
            'jsonrpc' => '2.0',
            'error'   => ['code' => -32700, 'message' => 'Parse error'],
            'id'      => null,
        ]));
    }

    // ── Mcp-Session-Id : requis par le spec Streamable HTTP ──
    // Réutiliser le session ID du client s'il en envoie un, sinon en générer un nouveau
    $mcpSessionId = $_SERVER['HTTP_MCP_SESSION_ID'] ?? bin2hex(random_bytes(16));
    header('Content-Type: application/json');
    header('Mcp-Session-Id: ' . $mcpSessionId);

    echo json_encode((new MCPHandler($config))->handle($body));
    exit;
}

// Autre → 405
http_response_code(405);
header('Content-Type: application/json');
echo json_encode([
    'jsonrpc' => '2.0',
    'error'   => ['code' => -32601, 'message' => 'Method not allowed'],
    'id'      => null,
]);
