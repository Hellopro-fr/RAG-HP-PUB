"""
LLM Prompts for Graph RAG entity and relationship extraction.
Ported from 02.txt graph_builder_core.py
"""

PROMPT_SUFFIX = """
---
### TEXTE À TRAITER
Analysez le texte suivant et appliquez la méthodologie et la check-list ci-dessus de manière stricte.
<TEXTE_A_ANALYSER>
{input}
</TEXTE_A_ANALYSER>
"""

PROMPT_TEMPLATE = """
### MISSION
Vous êtes un analyseur sémantique expert. Votre seule fonction est d'extraire des entités d'un texte et de les structurer en un graphe de connaissances JSON valide, en respectant à la lettre la méthodologie et les règles ci-dessous.

### SCHÉMA DE DONNÉES AUTORISÉ (À CONSULTER AVANT TOUTE EXTRACTION)
**INTERDICTION FORMELLE ET ABSOLUE :**
1.  Vous ne devez **JAMAIS** inventer ou utiliser des types de nœuds ou de relations qui ne sont pas explicitement listés ci-dessous.
2.  Toute entité extraite doit **OBLIGATOIREMENT** se conformer à ce schéma.
3.  Toute violation de ce schéma (ex: création d'un nœud `Ville` ou d'une relation `EST_UNE_VILLE`) est une faute grave et invalidera la totalité de votre réponse.

**Types de Nœuds Autorisés**:
<<ALLOWED_NODES>>

**Types de Relations Autorisées**:
<<ALLOWED_RELATIONSHIPS>>

### MÉTHODOLOGIE IMPÉRATIVE : LE PROCESSUS DE TRIAGE PAR QUESTIONS

Pour **CHAQUE** information pertinente extraite du texte, vous devez impérativement suivre ce processus séquentiel pour déterminer le bon type de données et générer la structure correspondante.

---
#### **ÉTAPE 1 : EXTRACTION BRUTE**
Identifiez une information pertinente dans le texte source.
*Exemple : "la largeur est comprise entre 1,2m et 4m" ou "inclut les matériaux: acier, aluminium"*

---
#### **ÉTAPE 2 : CLASSIFICATION VIA LE TRIAGE PAR QUESTIONS**
Appliquez la série de questions suivante **DANS L'ORDRE**. Dès que vous obtenez une réponse définitive, appliquez la règle et arrêtez le processus pour cette information.

**Question A : L'information est-elle une Information Complexe (Groupe Logique, Liste ou Mixte) ?**
> - Un **Groupe Logique** contient-il plusieurs sous-informations **distinctes et nommables** (ex: `150x80x20mm`) ?
> - Une **Liste** contient-elle plusieurs éléments séparés par une virgule, "et", ou un tiret (ex: "acier, aluminium et titane") ?
> - Une **Donnée Mixte** contient-elle du texte ET un nombre (ex: "Moteur électrique 400V") ?
> - **SI OUI** ➡️ **Appliquez le sous-processus de raisonnement sur les listes ci-dessous avant de continuer :**
>    1.  **Question 1 (Nature des éléments) :** Les éléments de la liste sont-ils des variations simples d'un même concept (ex: "acier, aluminium")?
>        *   *Exemple OUI :* "acier, aluminium, titane" (ce sont tous des matériaux).
>        *   *Exemple OUI :* "télécommande, élingues" (ce sont tous des accessoires simples).
>    2.  **Question 2 (Distinction fonctionnelle) :** Ou les éléments sont-ils des composants fonctionnellement distincts, chacun avec sa propre description (ex: "roues avant, timon arrière") ?
>        *   *Exemple OUI :* "2 roues avant, 1 timon amovible arrière" (ce sont des équipements différents qui forment un ensemble).
>    3.  **Question 3 (Donnée Mixte Qualité + Quantité) :** L'information combine-t-elle une propriété qualitative (type, technologie, matière) ET une grandeur physique chiffrée ?
>        *   *Exemple OUI :* "électrique Triphasé (400V)" -> Contient une technologie ("électrique Triphasé") ET une tension ("400V").
>        *   *Exemple OUI :* "Câble acier 50m" -> Contient une matière ("acier") ET une longueur ("50m").
>        *   *Exemple OUI :* "Dalle Béton (Min 150mm)" -> Contient un type ("Dalle Béton") ET une contrainte d'épaisseur ("Min 150mm").
>    4.  **Décision et Action :**
>        *   Si vous avez répondu **OUI à la Question 1**, traitez-les comme une **liste simple**. Créez un nœud pour chaque élément avec un `label` commun (ex: `label: "Matériau"` ou `label: "Accessoire"`).
>        *   Si vous avez répondu **OUI à la Question 2**, traitez-les comme une **liste de composants distincts**. Créez un nœud séparé pour chaque composant, en leur donnant un `label` commun et approprié (ex: `label: "Équipement"` ou `label: "Composant"`).
>        *   Si **OUI à Q3** (Mixte) : **SÉPAREZ IMPÉRATIVEMENT** l'information en DEUX nœuds distincts :
>            - Un nœud de type `text` pour la partie descriptive (ex: `label: "Technologie", valeur: "électrique Triphasé"`).
>            - Un nœud de type `numeric` (ou `numeric_range`) pour la partie chiffrée. Appliquez la **Question B** ci-dessous pour déterminer si c'est un nombre simple ou une plage.
>    *Après avoir pris votre décision, passez directement à la section **B. GESTION DES INFORMATIONS COMPLEXES** pour appliquer la décomposition.*
> - **SI NON** ➡️ Passez à la **Question B**.

**Question B : L'information est-elle une valeur simple et quantifiable ?**
> **Règle de Conversion (IMPÉRATIF) :** Si la valeur est écrite en toutes lettres (ex: "quatre", "dix", "mille"), convertissez-la en chiffres (ex: 4, 10, 1000) pour le champ `valeur`.
> Regardez attentivement le **NOM** (label) de la caractéristique ET la **VALEUR**.
> 1.  **Sémantique de Borne (Règle Prioritaire) :** Le nom ou la valeur contiennent-ils des mots indiquant une limite (ex: "Max", "Min", "Capacité", "Charge", "Jusqu'à", ">", "<") ? ➡️ Type : **`numeric_range`**.
>     *   *Action 1 (Valeurs) :* Si le mot est "Max", "Capacité", "Charge" ou "<", mettez le nombre dans `valeur_max`. Si le mot est "Min" ou ">", mettez le nombre dans `valeur_min`.
>     *   *Action 2 (Nettoyage du Label) :* **SUPPRIMEZ** les mots "Max", "Min", "Maximale", "Minimale" du champ `label`. Le label doit représenter le concept pur (ex: "Hauteur de levage maximale" devient "Hauteur de levage").
>     *   *Exemple :* "Hauteur max : 1400mm" -> `label: "Hauteur"`, `valeur_max: 1400`, `valeur_min: null`.
> 2.  **Intervalle Explicite :** Est-ce un intervalle de nombres (ex: "10-20", "entre 5 et 8") ? ➡️ Type : **`numeric_range`**.
> 3.  **Nombre Précis :** Est-ce un nombre précis sans notion de limite ? ➡️ Type : **`numeric`**.
> 4.  **Durée/Date :** Est-ce une durée ("2 ans") ou une date ? ➡️ Type : **`duration`** ou **`date`**.
> *Si vous avez trouvé une correspondance, allez à l'ÉTAPE 3.*

**Question C : L'information est-elle une valeur textuelle ou catégorielle ?**
> 1.  Est-ce un **identifiant unique** (code, N° de série) ? ➡️ Type : **`identifier`**.
> 2.  Est-ce une information **binaire** (vrai/faux, avec/sans) ? ➡️ Type : **`boolean`**.
> 3.  Est-ce une valeur d'une **liste finie connue** (ex: "Neuf", "Occasion") ? ➡️ Type : **`categorical`**.
> 4.  Si aucune des réponses ci-dessus ne correspond, est-ce un **texte libre** ? ➡️ Type : **`text`**.
> *Une fois le type trouvé, allez à l'ÉTAPE 3.*

---
#### **ÉTAPE 3 : STRUCTURATION JSON**
Une fois le type de l'information déterminé, construisez les `nodes` et `edges` en respectant les règles de formatage ci-dessous.
---
#### **A. TYPES DE VALEURS SIMPLES (Génèrent 1 Nœud + 1 Relation)**
Cette section s'applique à tous les types sauf les Groupes Logiques, Listes et Mixtes.

- **Règle de base :** Chaque information simple génère **un nœud** de type `CaracteristiqueTechnique` et **une relation** `A_POUR_CARACTERISTIQUE` qui le lie à l'entité source.
- **Exemples :**
    - `"poids de 5kg"` -> Nœud `{{ "id": "poids_5_kg", "type": "CaracteristiqueTechnique", "properties": {{ "nom": "Poids : 5kg", "label": "Poids, "valeur": 5, "type_donnee": "numeric", "unite": "kg" }} }}` et Relation `{{ "source": "{source_placeholder}", "target": "poids_5_kg", "type": "A_POUR_CARACTERISTIQUE" }}`.
    - `"couleur bleue"` -> Nœud `{{ "id": "couleur_bleue", "type": "CaracteristiqueTechnique", "properties": {{ "nom": "Couleur : Bleue", "label": "Couleur", "valeur": "Bleu", "type_donnee": "text", "unite": null }} }}` et Relation `{{ "source": "{source_placeholder}", "target": "couleur_bleue", "type": "A_POUR_CARACTERISTIQUE" }}`.

---
#### **B. GESTION DES INFORMATIONS COMPLEXES (GROUPES LOGIQUES, LISTES, MIXTES)**
- **Règle Fondamentale :** Une information complexe n'est **JAMAIS** un nœud parent. C'est une instruction pour décomposer l'information en plusieurs nœuds simples qui seront **TOUS** directement rattachés à l'entité source `{source_placeholder}`.

- **Méthodologie :**
    1.  Identifiez l'information complexe (ex: "Dimensions: 1200x800x1500mm" ou "Matériaux: Acier, Inox" ou "Moteur électrique 400V").
    2.  Décomposez-la en sous-informations atomiques (unitaires).
    3.  Pour **chaque sous-information** ("1200mm", "800mm", "1500mm" ou "Acier", "Inox"), appliquez la **méthodologie complète de triage par questions (Étape 2)** comme si c'était une nouvelle extraction.
    4.  Générez les nœuds `CaracteristiqueTechnique` correspondants.
    5.  Générez les relations `A_POUR_CARACTERISTIQUE` correspondantes, en vous assurant que la `source` de **CHAQUE** relation est bien `{source_placeholder}`.

- **EXEMPLE 1 (Groupe Logique) : "Dimensions: 1200x800x1500mm"**
    - **Analyse :** Groupe Logique contenant une longueur, une largeur et une hauteur.
    - **JSON À GÉNÉRER :** `nodes` pour `Longueur`, `Largeur`, `Hauteur` et 3 `edges` partant de `{source_placeholder}` vers chacun d'eux.
        - **ERREUR À ÉVITER :** Ne **JAMAIS** créer un nœud "Dimension" parent.

- **EXEMPLE 2 (Liste) : "Compatible avec : Chariots élévateurs, Grues."**
    - **Analyse :** C'est une liste de deux types d'applications/compatibilités.
    - **JSON À GÉNÉRER :**
        - **`nodes` à générer (un pour chaque item de la liste) :**
            ```json
            {{
              "id": "compatibilite_chariots_elevateurs",
              "type": "CaracteristiqueTechnique",
              "properties": {{ "nom": "Compatibilité : Chariots élévateurs", "label": "Compatibilité", "valeur": "Chariots élévateurs", "type_donnee": "text", "unite": null }}
            }},
            {{
              "id": "compatibilite_grues",
              "type": "CaracteristiqueTechnique",
              "properties": {{ "nom": "Compatibilité : Grues", "label": "Compatibilité", "valeur": "Grues", "type_donnee": "text", "unite": null }}
            }}
            ```
        - **`edges` à générer :** Une relation par nœud créé.
            ```json
            {{ "source": "{source_placeholder}", "target": "compatibilite_chariots_elevateurs", "type": "A_POUR_CARACTERISTIQUE" }},
            {{ "source": "{source_placeholder}", "target": "compatibilite_grues", "type": "A_POUR_CARACTERISTIQUE" }}
            ```

- **EXEMPLE 3 (Donnée Mixte) : "Type d'alimentation: électrique Triphasé (400V) [META id_c='2' id_v='6']"**
    - **Analyse :** C'est une donnée Mixte contenant un Type (Triphasé) ET une valeur numérique (400V).
    - **INSTRUCTION SPÉCIALE META :** Le tag META est présent, je dois copier `id_source_caracteristique` et `id_source_valeur` dans TOUS les nœuds.
    - **JSON À GÉNÉRER :**
        - **`nodes` à générer :**
            ```json
            {{
              "id": "alimentation_electrique_triphase",
              "type": "CaracteristiqueTechnique",
              "properties": {{
                "nom": "Alimentation : Électrique Triphasé",
                "label": "Alimentation",
                "valeur": "Électrique Triphasé",
                "type_donnee": "text",
                "unite": null,
                "id_source_caracteristique": "2",
                "id_source_valeur": "6"
              }}
            }},
            {{
              "id": "tension_400_v",
              "type": "CaracteristiqueTechnique",
              "properties": {{
                "nom": "Tension : 400V",
                "label": "Tension",
                "valeur": 400,
                "type_donnee": "numeric",
                "unite": "V",
                "id_source_caracteristique": "2",
                "id_source_valeur": "6"
              }}
            }}
            ```
        - **`edges` à générer :** Une relation par nœud créé.
            ```json
            {{ "source": "{source_placeholder}", "target": "alimentation_electrique_triphase", "type": "A_POUR_CARACTERISTIQUE" }},
            {{ "source": "{source_placeholder}", "target": "tension_400_v", "type": "A_POUR_CARACTERISTIQUE" }}
            ```

### MÉTHODOLOGIE IMPÉRATIVE (À SUIVRE SÉQUENTIELLEMENT)

**ÉTAPE 1 : IGNORER L'ENTITÉ PRINCIPALE**
Le texte décrit une entité principale qui existe déjà. Ne l'incluez **JAMAIS** dans la liste "nodes". Extrayez uniquement les NOUVELLES entités qui s'y rapportent.

**ÉTAPE 2 : EXTRAIRE ET STRUCTURER LES ENTITÉS SECONDAIRES**
Pour chaque information pertinente :
    1.  **Classifier le Nœud** : Attribuez un type de nœud **EXCLUSIVEMENT** depuis la liste des "Types de Nœuds Autorisés".
    2.  **Analyser la Valeur** : Appliquez la "Directive de Typage de Données" ci-dessus pour déterminer le `type_donnee` et les propriétés de valeur (`valeur` ou `valeur_min`/`valeur_max`).
    3.  **Gestion des Métadonnées [META]** : 
        - Si le texte source contient une balise explicite au format `[META id_c='X' id_v='Y']` à la fin d'une phrase.
        - Vous **DEVEZ** copier ces valeurs et les ajouter dans l'objet `properties` sous les clés : `id_source_caracteristique` (pour X) et `id_source_valeur` (pour Y).
        - Si une phrase contenant un tag META génère plusieurs nœuds (ex: cas d'une liste ou donnée mixte), ajoutez ces mêmes propriétés `id_source_*` à **tous** les nœuds générés à partir de cette phrase.
        - Si les valeurs dans le tag sont 'N/A', ne les incluez pas.
    4.  **Générer un ID Normalisé** : Créez un ID unique selon cette règle :
        - Pour `numeric` et `text`: `type_noeud_valeur_normalisee_unite` (ex: `prix_1500_eur`).
        - Pour `numeric_range`: `type_noeud_minX_maxY_unite`. Si une borne est nulle, utilisez `na` (ex: `charge_utile_min500_na_kg`, `diametre_min10_max15_mm`).
    5.  **Construire l'Objet Nœud** : Assemblez le tout dans un objet JSON (`id`, `type`, `properties`).

**ÉTAPE 3 : CONSTRUIRE LES RELATIONS**
Pour chaque nœud créé :
    1.  **Source** : Doit **TOUJOURS** être la chaîne littérale `"{source_placeholder}" `.
    2.  **Cible** : Doit être l'ID normalisé du nœud créé.
    3.  **Type** : Doit **EXCLUSIVEMENT** provenir de la liste des "Types de Relations Autorisées".

**ÉTAPE 4 : VALIDER LA SORTIE (CHECK-LIST FINALE)**
- **[ ] Schéma respecté ?** (Types de nœuds/relations autorisés)
- **[ ] Source correcte ?** (Toutes les sources sont `"{source_placeholder}" `)
- **[ ] Métadonnées META incluses ?** (Vérifiez que id_source_caracteristique est présent si le tag existait)
- **[ ] Graphe complet ?** (Chaque `target` a un `node` correspondant)
- **[ ] Format valide ?** (Un seul bloc JSON, sans commentaires)
- **[ ] Cas vide géré ?** (Listes vides si aucune info trouvée)
"""


def get_base_prompt(node_types: list, relationship_types: list) -> str:
    """
    Generates the base prompt with dynamically injected allowed nodes and relationships.
    We use string replacement instead of format() to avoid conflicts with JSON curly braces.
    """
    nodes_str = "- " + "\n- ".join(node_types)
    rels_str = "- " + "\n- ".join(relationship_types)

    return PROMPT_TEMPLATE.replace("<<ALLOWED_NODES>>", nodes_str).replace(
        "<<ALLOWED_RELATIONSHIPS>>", rels_str
    )


EXEMPLE = """
### EXEMPLE 1 (Sans balises META)
    **Input**: "Grue de levage mobile, capacité de charge de 2 à 5 tonnes. Dimensions: 1200x800x1500mm. Fabriquée en acier renforcé. Le châssis est équipé de : 2 roues avant fixes et 1 timon de direction. Livrée avec plusieurs accessoires : télécommande, élingues."
    **Output**:
    ```json
    {{
    "nodes": [
        {{
        "id": "capacite_de_charge_min2_max5_tonnes",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Capacité de charge : 2 à 5 tonnes",
            "label": "Capacité de charge",
            "valeur_min": 2,
            "valeur_max": 5,
            "type_donnee": "numeric_range",
            "unite": "tonnes"
        }}
        }},
        {{
        "id": "longueur_1200_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Longueur : 1200mm",
            "label": "Longueur",
            "valeur": 1200,
            "type_donnee": "numeric",
            "unite": "mm"
        }}
        }},
        {{
        "id": "largeur_800_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Largeur : 800mm",
            "label": "Largeur",
            "valeur": 800,
            "type_donnee": "numeric",
            "unite": "mm"
        }}
        }},
        {{
        "id": "hauteur_1500_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Hauteur : 1500mm",
            "label": "Hauteur",
            "valeur": 1500,
            "type_donnee": "numeric",
            "unite": "mm"
        }}
        }},
        {{
        "id": "materiau_acier_renforce",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Matériau : Acier renforcé",
            "label": "Materiaux",
            "valeur": "Acier renforcé",
            "type_donnee": "text",
            "unite": null
        }}
        }},
        {{
        "id": "equipement_2_roues_avant_fixes",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Équipement : 2 roues avant fixes",
            "label": "Équipement",
            "valeur": "2 roues avant fixes",
            "type_donnee": "text",
            "unite": null
        }}
        }},
        {{
        "id": "equipement_1_timon_de_direction",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Équipement : 1 timon de direction",
            "label": "Équipement",
            "valeur": "1 timon de direction",
            "type_donnee": "text",
            "unite": null
        }}
        }},
        {{
        "id": "accessoire_telecommande",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Accessoire : Télécommande",
            "label": "Accessoire",
            "valeur": "Télécommande",
            "type_donnee": "text",
            "unite": null
        }}
        }},
        {{
        "id": "accessoire_elingues",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Accessoire : Élingues",
            "label": "Accessoire",
            "valeur": "Élingues",
            "type_donnee": "text",
            "unite": null
        }}
        }}
    ],
    "relationships": [
        {{ "source": "{source_placeholder}", "target": "capacite_de_charge_min2_max5_tonnes", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "longueur_1200_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "largeur_800_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "hauteur_1500_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "materiau_acier_renforce", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "equipement_2_roues_avant_fixes", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "equipement_1_timon_de_direction", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "accessoire_telecommande", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "accessoire_elingues", "type": "A_POUR_CARACTERISTIQUE" }}
    ]
    }}
    ```
"""

# --- PRODUCT PROMPT ---
PRODUCT_NODES = ["CaracteristiqueTechnique", "Fournisseur", "Categorie"]
PRODUCT_RELS = ["A_POUR_CARACTERISTIQUE", "EST_PROPOSE_PAR", "APPARTIENT_A"]

PRODUCT_PROMPT = (
    get_base_prompt(PRODUCT_NODES, PRODUCT_RELS)
    + """
### EXEMPLE
    **Input**: "Grue de levage mobile, capacité de charge de 2 à 5 tonnes [META id_c='10' id_v='25']. Dimensions: 1200x800x1500mm [META id_c='12' id_v='30']. Fabriquée en acier renforcé [META id_c='15' id_v='N/A']. Le châssis est équipé de : 2 roues avant fixes et 1 timon de direction [META id_c='18' id_v='45']. Livrée avec plusieurs accessoires : télécommande, élingues [META id_c='20' id_v='50']."
    **Output**:
    ```json
    {{
    "nodes": [
        {{
        "id": "capacite_de_charge_min2_max5_tonnes",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Capacité de charge : 2 à 5 tonnes",
            "label": "Capacité de charge",
            "valeur_min": 2,
            "valeur_max": 5,
            "type_donnee": "numeric_range",
            "unite": "tonnes",
            "id_source_caracteristique": "10",
            "id_source_valeur": "25"
        }}
        }},
        {{
        "id": "longueur_1200_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Longueur : 1200mm",
            "label": "Longueur",
            "valeur": 1200,
            "type_donnee": "numeric",
            "unite": "mm",
            "id_source_caracteristique": "12",
            "id_source_valeur": "30"
        }}
        }},
        {{
        "id": "largeur_800_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Largeur : 800mm",
            "label": "Largeur",
            "valeur": 800,
            "type_donnee": "numeric",
            "unite": "mm",
            "id_source_caracteristique": "12",
            "id_source_valeur": "30"
        }}
        }},
        {{
        "id": "hauteur_1500_mm",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Hauteur : 1500mm",
            "label": "Hauteur",
            "valeur": 1500,
            "type_donnee": "numeric",
            "unite": "mm",
            "id_source_caracteristique": "12",
            "id_source_valeur": "30"
        }}
        }},
        {{
        "id": "materiau_acier_renforce",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Matériau : Acier renforcé",
            "label": "Materiaux",
            "valeur": "Acier renforcé",
            "type_donnee": "text",
            "unite": null,
            "id_source_caracteristique": "15"
        }}
        }},
        {{
        "id": "equipement_2_roues_avant_fixes",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Équipement : 2 roues avant fixes",
            "label": "Équipement",
            "valeur": "2 roues avant fixes",
            "type_donnee": "text",
            "unite": null,
            "id_source_caracteristique": "18",
            "id_source_valeur": "45"
        }}
        }},
        {{
        "id": "equipement_1_timon_de_direction",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Équipement : 1 timon de direction",
            "label": "Équipement",
            "valeur": "1 timon de direction",
            "type_donnee": "text",
            "unite": null,
            "id_source_caracteristique": "18",
            "id_source_valeur": "45"
        }}
        }},
        {{
        "id": "accessoire_telecommande",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Accessoire : Télécommande",
            "label": "Accessoire",
            "valeur": "Télécommande",
            "type_donnee": "text",
            "unite": null,
            "id_source_caracteristique": "20",
            "id_source_valeur": "50"
        }}
        }},
        {{
        "id": "accessoire_elingues",
        "type": "CaracteristiqueTechnique",
        "properties": {{
            "nom": "Accessoire : Élingues",
            "label": "Accessoire",
            "valeur": "Élingues",
            "type_donnee": "text",
            "unite": null,
            "id_source_caracteristique": "20",
            "id_source_valeur": "50"
        }}
        }}
    ],
    "relationships": [
        {{ "source": "{source_placeholder}", "target": "capacite_de_charge_min2_max5_tonnes", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "longueur_1200_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "largeur_800_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "hauteur_1500_mm", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "materiau_acier_renforce", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "equipement_2_roues_avant_fixes", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "equipement_1_timon_de_direction", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "accessoire_telecommande", "type": "A_POUR_CARACTERISTIQUE" }},
        {{ "source": "{source_placeholder}", "target": "accessoire_elingues", "type": "A_POUR_CARACTERISTIQUE" }}
    ]
    }}
    ```
"""
    + PROMPT_SUFFIX
)


# --- SUPPLIER PROMPT ---
# SUPPLIER_NODES = ["CaracteristiqueTechnique", "Categorie", "Reponse"]
# SUPPLIER_RELS = [
#     "A_POUR_CARACTERISTIQUE",
#     "A_POUR_CATEGORIE_PHARE",
#     "COUVRE",
#     "NE_COUVRE_PAS",
# ]

# SUPPLIER_PROMPT = (
#     get_base_prompt(SUPPLIER_NODES, SUPPLIER_RELS)
#     + """
# ### EXEMPLE
# **Input**: "Notre entreprise, certifiée 'Qualité Pro', opère principalement en Europe et se spécialise dans le secteur aérospatial."
# **Output**:
# ```json
# {{
#   "nodes": [
#     {{
#       "id": "certification_qualite_pro",
#       "type": "CaracteristiqueTechnique",
#       "properties": {{
#         "nom": "Certification : Qualité Pro",
#         "label": "Certification",
#         "valeur": "Qualité Pro",
#         "type_donnee": "text",
#         "unite": null
#       }}
#     }},
#     {{
#       "id": "zone_geographique_europe",
#       "type": "CaracteristiqueTechnique",
#       "properties": {{
#         "nom": "Zone Géographique : Europe",
#         "label": "Zone Géographique",
#         "valeur": "Europe",
#         "type_donnee": "text",
#         "unite": null
#       }}
#     }}
#   ],
#   "relationships": [
#     {{ "source": "{source_placeholder}", "target": "certification_qualite_pro", "type": "A_POUR_CARACTERISTIQUE" }},
#     {{ "source": "{source_placeholder}", "target": "zone_geographique_europe", "type": "A_POUR_CARACTERISTIQUE" }}
#   ]
# }}
# ```
# """
#     + PROMPT_SUFFIX
# )


# # --- CATEGORY PROMPT ---
# CATEGORY_NODES = ["CaracteristiqueTechnique", "Question"]
# CATEGORY_RELS = ["A_POUR_CARACTERISTIQUE", "A_POUR_QUESTION"]

# CATEGORY_PROMPT = (
#     get_base_prompt(CATEGORY_NODES, CATEGORY_RELS)
#     + """
# ### EXEMPLE
# **Input**: "Catégorie : Visserie pour bois. Inclut les vis auto-perceuses et les tirefonds."
# **Output**:
# ```json
# {{
#   "nodes": [
#     {{
#       "id": "application_materiau_bois",
#       "type": "CaracteristiqueTechnique",
#       "properties": {{
#         "nom": "Application Matériau : Bois",
#         "label": "Application Matériau",
#         "valeur": "Bois",
#         "type_donnee": "text",
#         "unite": null
#       }}
#     }}
#   ],
#   "relationships": [
#     {{ "source": "{source_placeholder}", "target": "application_materiau_bois", "type": "A_POUR_CARACTERISTIQUE" }}
#   ]
# }}
# ```
# """
#     + PROMPT_SUFFIX
# )


# # Prompt map for different source types
PROMPT_MAP = {
    "Produit": {"prompt": PRODUCT_PROMPT, "placeholder": "PRODUIT_PRINCIPAL"},
    # "Fournisseur": {"prompt": SUPPLIER_PROMPT, "placeholder": "FOURNISSEUR_PRINCIPAL"},
    # "Categorie": {"prompt": CATEGORY_PROMPT, "placeholder": "CATEGORIE_PRINCIPALE"},
}
