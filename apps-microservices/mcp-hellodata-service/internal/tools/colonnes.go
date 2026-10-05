package tools

import "strings"

// colonne est une colonne projetable du moteur. Nom est la cle attendue par
// requete.php (mcp_hd_sql_catalogue_colonnes) ; Libelle est le nom du champ
// tel que l'utilisateur le connait dans l'ecran d'extraction du BO
// (ca_extract_* de lancer_comptage_combine.php).
type colonne struct {
	Nom        string
	Libelle    string
	Restreinte bool // email / mobile : role admin, comme $debloque_tel_mail cote BO
}

// catalogueColonnes reflete requete.php, dans l'ordre de l'ecran d'extraction
// du BO. Ajouter une colonne ici sans l'ajouter au moteur la ferait refuser
// par le moteur (colonne_inconnue) : les deux listes vont ensemble.
var catalogueColonnes = []colonne{
	{"id_fiche", "ID societe", false},
	{"email", "Email", true},
	{"nom_commercial", "Nom commercial", false},
	{"raison_sociale", "Raison sociale", false},
	{"civilite", "Civilite (code)", false},
	{"nom", "Nom", false},
	{"prenom", "Prenom", false},
	{"adresse", "Adresse", false},
	{"code_postal", "Code postal", false},
	{"mobile", "Telephone mobile", true},
	{"ville", "Ville", false},
	{"region", "Region (code)", false},
	{"pays", "Pays (code)", false},
	{"siret", "Siret", false},
	{"annee_creation", "Annee de creation", false},
	{"effectif", "Effectif (code)", false},
	{"site_web", "Site web", false},
	{"statut", "Statut (code)", false},
	{"fonction", "Fonction (code)", false},
	{"service", "Service (code)", false},
	{"naf", "NAF (code)", false},
	{"id_acheteur", "ID acheteur", false},
	{"departement", "Departement", false},
	{"siren", "Siren", false},
	{"source", "Source", false},
	{"date_creation", "Date de creation de la fiche", false},
}

// nonDisponibles sont des champs de l'ecran BO que le moteur ne sait pas
// encore rendre : le LLM doit le dire au lieu de les promettre.
const nonDisponibles = "Validite email, telephone fixe / ligne directe, et les libelles " +
	"(civilite, region, pays, effectif, statut, fonction, service, NAF rendus en code)"

// colonnesRestreintes reflete requete.php cote moteur. Le refus se prend
// ici pour eviter un aller-retour reseau qui echouerait de toute facon.
var colonnesRestreintes = func() map[string]bool {
	m := map[string]bool{}
	for _, c := range catalogueColonnes {
		if c.Restreinte {
			m[c.Nom] = true
		}
	}
	return m
}()

func nomsColonnes() []string {
	out := make([]string, 0, len(catalogueColonnes))
	for _, c := range catalogueColonnes {
		out = append(out, c.Nom)
	}
	return out
}

// listeColonnes rend « Libelle (nom), ... » : la liste a montrer a
// l'utilisateur avant une extraction.
func listeColonnes() string {
	parts := make([]string, 0, len(catalogueColonnes))
	for _, c := range catalogueColonnes {
		p := c.Libelle + " (" + c.Nom
		if c.Restreinte {
			p += ", admin"
		}
		parts = append(parts, p+")")
	}
	return strings.Join(parts, ", ")
}

func colonneConnue(nom string) bool {
	for _, c := range catalogueColonnes {
		if c.Nom == nom {
			return true
		}
	}
	return false
}
