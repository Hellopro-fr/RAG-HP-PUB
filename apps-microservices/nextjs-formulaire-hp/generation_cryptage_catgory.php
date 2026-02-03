<?php
/**
 * Génération de tokens sécurisés pour les liens de catégorie
 * Compatible avec le middleware Next.js
 * Utilise AES-256-CBC pour un chiffrement complet du token
 */

class CategoryTokenGenerator
{
    private string $secret;
    private string $encryptionKey;

    public function __construct(string $secret = 'hellofr2k26')
    {
        $this->secret = $secret;
        // Dériver une clé de 32 bytes pour AES-256
        $this->encryptionKey = hash('sha256', $secret, true);
    }

    /**
     * Encode en Base64 URL-safe (sans padding)
     */
    private function base64UrlEncode(string $data): string
    {
        return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
    }

    /**
     * Décode depuis Base64 URL-safe
     */
    private function base64UrlDecode(string $data): string
    {
        $padding = 4 - (strlen($data) % 4);
        if ($padding !== 4) {
            $data .= str_repeat('=', $padding);
        }
        return base64_decode(strtr($data, '-_', '+/'));
    }

    /**
     * Chiffre les données avec AES-256-CBC
     * L'IV aléatoire garantit que chaque chiffrement est unique
     */
    private function encrypt(string $data): string
    {
        $iv = random_bytes(16); // IV aléatoire de 16 bytes
        $encrypted = openssl_encrypt($data, 'aes-256-cbc', $this->encryptionKey, OPENSSL_RAW_DATA, $iv);

        // Concaténer IV + données chiffrées
        return $iv . $encrypted;
    }

    /**
     * Déchiffre les données
     */
    private function decrypt(string $data): string|false
    {
        $iv = substr($data, 0, 16);
        $encrypted = substr($data, 16);

        return openssl_decrypt($encrypted, 'aes-256-cbc', $this->encryptionKey, OPENSSL_RAW_DATA, $iv);
    }

    /**
     * Génère un token sécurisé pour une catégorie
     * Le token entier change à chaque génération grâce à l'IV aléatoire
     *
     * @param int $categoryId L'ID de la catégorie
     * @return string Le token URL-safe (complètement différent à chaque appel)
     */
    public function generateToken(int $categoryId): string
    {
        $payload = json_encode([
            'c' => $categoryId,           // id_categorie
            'd' => date('Y-m-d'),         // date du jour
            't' => time()                 // timestamp pour encore plus d'unicité
        ], JSON_UNESCAPED_SLASHES);

        // Chiffrer tout le payload (l'IV aléatoire rend le résultat unique)
        $encrypted = $this->encrypt($payload);

        // Encoder en Base64 URL-safe
        return $this->base64UrlEncode($encrypted);
    }

    /**
     * Décode et vérifie un token
     *
     * @param string $token Le token à décoder
     * @return array|false Les données décodées ou false si invalide
     */
    public function decodeToken(string $token): array|false
    {
        try {
            $encrypted = $this->base64UrlDecode($token);
            $decrypted = $this->decrypt($encrypted);

            if ($decrypted === false) {
                return false;
            }

            $data = json_decode($decrypted, true);

            if (!isset($data['c']) || !isset($data['d'])) {
                return false;
            }

            return [
                'categoryId' => $data['c'],
                'date' => $data['d'],
                'timestamp' => $data['t'] ?? null
            ];
        } catch (Exception $e) {
            return false;
        }
    }

    /**
     * Génère l'URL complète pour le questionnaire
     *
     * @param int $categoryId L'ID de la catégorie
     * @param string $baseUrl L'URL de base (ex: https://dev-www.hellopro.fr/formulaire)
     * @return string L'URL complète
     */
    public function generateQuestionnaireUrl(int $categoryId, string $baseUrl = '/formulaire'): string
    {
        $token = $this->generateToken($categoryId);
        return rtrim($baseUrl, '/') . '/questionnaire/' . $token;
    }

    /**
     * Génère toutes les URLs pour une catégorie
     *
     * @param int $categoryId L'ID de la catégorie
     * @param string $baseUrl L'URL de base
     * @return array Les URLs générées
     */
    public function generateAllUrls(int $categoryId, string $baseUrl = '/formulaire'): array
    {
        $token = $this->generateToken($categoryId);
        $base = rtrim($baseUrl, '/');

        return [
            'token' => $token,
            'questionnaire' => $base . '/questionnaire/' . $token,
            'selection' => $base . '/selection/' . $token,
            'formulaire' => $base . '/formulaire/' . $token,
        ];
    }
}

// =============================================================================
// EXEMPLE D'UTILISATION
// =============================================================================

/* $generator = new CategoryTokenGenerator('hellofr2k26');

$categoryId = 200500;

echo "=== Démonstration: tokens différents pour le même ID ===\n\n";

// Générer 3 tokens pour la même catégorie
for ($i = 1; $i <= 3; $i++) {
    $token = $generator->generateToken($categoryId);
    echo "Token $i: " . $token . "\n";

    // Vérifier que le décodage fonctionne
    $decoded = $generator->decodeToken($token);
    echo "Décodé: categoryId=" . $decoded['categoryId'] . ", date=" . $decoded['date'] . "\n\n";
}

echo "=== URL complète ===\n";
$url = $generator->generateQuestionnaireUrl($categoryId, 'https://dev-www.hellopro.fr/formulaire');
echo "URL: " . $url . "\n\n";

echo "=== Toutes les URLs ===\n";
$urls = $generator->generateAllUrls($categoryId, 'https://dev-www.hellopro.fr/formulaire');
print_r($urls);
 */
// =============================================================================
// FONCTION STANDALONE
// =============================================================================

/**
 * Génère un token sécurisé chiffré pour une catégorie
 *
 * @param int $categoryId L'ID de la catégorie
 * @param string $secret Le secret (doit correspondre à CATEGORY_TOKEN_SECRET)
 * @return string Le token URL-safe (complètement différent à chaque appel)
 */
function generateCategoryToken(int $categoryId, string $secret = 'hellofr2k26'): string
{
    $encryptionKey = hash('sha256', $secret, true);

    $payload = json_encode([
        'c' => $categoryId,
        'd' => date('Y-m-d'),
        't' => time()
    ], JSON_UNESCAPED_SLASHES);

    // Chiffrer avec AES-256-CBC et IV aléatoire
    $iv = random_bytes(16);
    $encrypted = openssl_encrypt($payload, 'aes-256-cbc', $encryptionKey, OPENSSL_RAW_DATA, $iv);

    // Encoder IV + données chiffrées en Base64 URL-safe
    return rtrim(strtr(base64_encode($iv . $encrypted), '+/', '-_'), '=');
}

/**
 * Décode un token chiffré
 *
 * @param string $token Le token à décoder
 * @param string $secret Le secret
 * @return array|false Les données décodées ou false si invalide
 */
function decodeCategoryToken(string $token, string $secret = 'hellofr2k26'): array|false
{
    $encryptionKey = hash('sha256', $secret, true);

    // Décoder Base64 URL-safe
    $padding = 4 - (strlen($token) % 4);
    if ($padding !== 4) {
        $token .= str_repeat('=', $padding);
    }
    $data = base64_decode(strtr($token, '-_', '+/'));

    // Extraire IV et données chiffrées
    $iv = substr($data, 0, 16);
    $encrypted = substr($data, 16);

    // Déchiffrer
    $decrypted = openssl_decrypt($encrypted, 'aes-256-cbc', $encryptionKey, OPENSSL_RAW_DATA, $iv);

    if ($decrypted === false) {
        return false;
    }

    $payload = json_decode($decrypted, true);

    if (!isset($payload['c'])) {
        return false;
    }

    return [
        'categoryId' => $payload['c'],
        'date' => $payload['d'] ?? null,
        'timestamp' => $payload['t'] ?? null
    ];
}
