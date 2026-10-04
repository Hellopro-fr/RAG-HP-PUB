// Package acces decide qui peut utiliser ce service.
//
// Deux voies, et deux seulement : le role admin, ou un grant
// server_authorizations sur le serveur hellodata. Le gateway decide le
// premier (Neo4jAccess : consentement, tools/list, tools/call) et transmet
// ce qu'il a constate en en-tetes ; ce service re-verifie en defense, sur
// ces seuls en-tetes. Spec :
// docs/superpowers/specs/2026-09-28-mcp-hellodata-server-authorizations-design.md.
//
// Toute absence refuse. Un appel sans identite n'est pas un appel interne
// de confiance, c'est un appel dont on ignore l'auteur.
package acces

import "strings"

// RoleAdmin est la valeur exacte de gateway_users.role pour un
// administrateur (internal/auth/role.go du gateway). La comparaison est
// stricte : ce service ne recoit pas la table des niveaux de role et n'a
// pas a la dupliquer, donc un role inconnu n'est pas admin.
const RoleAdmin = "admin"

// Autorise refuse sans identite. Autorise l'admin, ou l'appelant pour qui
// le gateway a constate un grant server_authorizations (granted).
func Autorise(email, role string, granted bool) bool {
	if strings.TrimSpace(email) == "" {
		return false
	}
	return EstAdmin(role) || granted
}

// EstAdmin commande l'acces aux colonnes email et telephone, equivalent du
// $debloque_tel_mail du BO. Tant que la precondition 5 n'est pas tranchee,
// un titulaire de grant n'y a pas droit.
func EstAdmin(role string) bool {
	return strings.TrimSpace(role) == RoleAdmin
}

// Source nomme le droit d'un appelant autorise, pour le journal : "admin"
// ou "grant".
func Source(role string) string {
	if EstAdmin(role) {
		return "admin"
	}
	return "grant"
}
