user_id - Identifiant utilisateur
Stockage : localStorage (persistant)

Durée de vie : Permanent (jusqu'à ce que l'utilisateur vide son cache navigateur)

Génération : UUID v4 généré au premier accès, stocké dans localStorage sous la clé hp_user_id

Utilité :

Identifier un visiteur unique à travers plusieurs sessions/visites
Permet de suivre un utilisateur qui revient sur le site à J+1, J+7, etc.
Utile pour calculer le nombre de visiteurs uniques, le taux de retour, etc.
session_id - Identifiant de session
Stockage : sessionStorage (temporaire)

Durée de vie : Jusqu'à la fermeture de l'onglet/navigateur

Génération : UUID v4 généré à chaque nouvelle session, stocké dans sessionStorage sous la clé hp_session_id

Utilité :

Identifier une session de navigation unique
Permet de regrouper toutes les actions d'un utilisateur dans une même visite
Utile pour analyser le parcours complet d'une session, calculer le taux d'abandon par session, etc.