// Package acces decide qui peut utiliser ce service.
//
// Deux voies, et deux seulement : le role admin, ou la presence dans une
// liste statique. Le gateway n'applique qu'une barriere de role minimale
// (min_role = readonly) qui ecarte les chemins sans utilisateur ; la
// decision nominative se prend ici.
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

type Acces struct {
	autorises map[string]struct{}
}

// Nouveau construit la liste depuis HELLODATA_ALLOWED_EMAILS. Les entrees
// vides sont ignorees, ce qui rend inoffensive une virgule en trop et
// evite qu'une cle vide corresponde a un email vide.
func Nouveau(liste string) *Acces {
	a := &Acces{autorises: make(map[string]struct{})}
	for _, brut := range strings.Split(liste, ",") {
		if e := Normaliser(brut); e != "" {
			a.autorises[e] = struct{}{}
		}
	}
	return a
}

// Normaliser est appliquee des deux cotes — au chargement de la liste et a
// l'email entrant — pour qu'une difference de casse ne produise pas un
// refus silencieux.
func Normaliser(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

func (a *Acces) Autorise(email, role string) bool {
	if a == nil {
		return false
	}
	e := Normaliser(email)
	if e == "" {
		return false
	}
	if strings.TrimSpace(role) == RoleAdmin {
		return true
	}
	_, ok := a.autorises[e]
	return ok
}

// EstAdmin commande l'acces aux colonnes email et telephone, equivalent du
// $debloque_tel_mail du BO. Tant que la precondition 5 n'est pas tranchee,
// un autorise par liste n'y a pas droit.
func (a *Acces) EstAdmin(role string) bool {
	return strings.TrimSpace(role) == RoleAdmin
}
