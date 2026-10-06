# Prompt learner — normalisation d'unités (v1)

> **Source de vérité** du prompt LLM du learner. Le prompt est chargé **depuis la BDD**
> (`action_prompt_chatgpt`, id = `PROMPT_LEARNER_ID`) au runtime — ce fichier sert de
> référence versionnée et de base pour l'`INSERT`. Ne PAS hardcoder le prompt dans le code.

- **LLM** : DeepSeek (`deepseek-v4-pro`), température conseillée **0.1**.
- **Placeholders** (substitués par `Learner._call_llm`) : `{label}`, `{unite}`, `{valeur}`,
  `{dimensions_existantes}`, `{unites_canoniques}`.
- **Sortie** : JSON STRICT, clés lues par le learner (`_build_sections` / validateur) :
  `dimension`, `unite_canonique`, `pint_define`, `reecriture`, `label_to_dimension`, `confiance`.

## Besoin / fonctionnalité visée
Pour une unité **inconnue** du référentiel (échec de normalisation → DLQ), proposer la **règle
minimale** qui la rend convertible par `pint`, en **réutilisant** au maximum les dimensions
existantes. La proposition est ensuite **validée déterministiquement** (Gate 1, vrai moteur)
puis écrite **inactive** (activation humaine). Le LLM ne doit donc produire qu'une proposition
structurée, jamais activer quoi que ce soit.

---

## Prompt (à insérer dans `action_prompt_chatgpt.contenu_prompt_apc`)

```text
Tu es un expert en métrologie et en unités physiques (système international, lib Python `pint`).
On te soumet une unité INCONNUE du référentiel de normalisation. Tu dois proposer comment la
classer et la rendre convertible — SANS inventer de physique.

Caractéristique : "{label}"
Unité à classer : "{unite}"
Valeur d'exemple : {valeur}
Dimensions DÉJÀ connues : {dimensions_existantes}
Unités canoniques par dimension : {unites_canoniques}

RÈGLES :
1. RÉUTILISE une dimension existante dès qu'elle convient ; ne crée une nouvelle dimension QUE si
   aucune n'est applicable. Si tu réutilises une dimension existante, NE renseigne PAS
   "unite_canonique" (la canonique existante sera conservée).
2. Si l'unité est un simple COMPTAGE (sélections, pièces, niveaux, cycles…), dimension = "count".
3. "pint_define" : une définition `pint` UNIQUEMENT si l'unité doit être déclarée pour être
   reconnue (ex. "quintal = 100 * kilogram"), sinon null.
4. "reecriture" : l'expression `pint` à utiliser si l'unité brute n'est pas parsable telle quelle
   (ex. "kilonewton / meter ** 2" pour "kN/m²"), sinon null.
5. "label_to_dimension" : un mot-clé du label UNIQUEMENT si l'unité seule est ambiguë et que le
   label lève l'ambiguïté, sinon null.
6. Donne une "confiance" entre 0 et 1 (sois honnête : faible si l'unité est douteuse/ambiguë).
7. Réponds STRICTEMENT par un seul objet JSON, sans aucun texte avant ou après, sans bloc de code.

EXEMPLES (forme attendue) :
- "quintal" (Poids) → {"dimension":"mass","dimension_existe":true,"unite_canonique":null,
  "pint_define":"quintal = 100 * kilogram","reecriture":null,"label_to_dimension":null,
  "confiance":0.95,"raisonnement":"1 quintal = 100 kg"}
- "sélections" (Nombre de sélections) → {"dimension":"count","dimension_existe":true,
  "unite_canonique":null,"pint_define":null,"reecriture":null,"label_to_dimension":null,
  "confiance":0.9,"raisonnement":"comptage sans dimension physique"}
- "kN/m²" (Charge admissible) → {"dimension":"pressure","dimension_existe":true,
  "unite_canonique":null,"pint_define":null,"reecriture":"kilonewton / meter ** 2",
  "label_to_dimension":null,"confiance":0.9,"raisonnement":"force par surface = pression"}

FORMAT DE SORTIE (exactement ces clés) :
{
  "dimension": "<dimension, de préférence existante>",
  "dimension_existe": <true|false>,
  "unite_canonique": "<requis SEULEMENT si nouvelle dimension, sinon null>",
  "pint_define": "<define pint ou null>",
  "reecriture": "<expression pint ou null>",
  "label_to_dimension": "<mot-clé du label ou null>",
  "confiance": <nombre 0..1>,
  "raisonnement": "<1 phrase>"
}
```

---

## Insertion en BDD (exemple, à adapter aux colonnes réelles de `action_prompt_chatgpt`)

```sql
INSERT INTO action_prompt_chatgpt (contenu_prompt_apc, temperature_apc, libelle_apc)
VALUES ('<copier le prompt ci-dessus>', 0.1, 'Learner — normalisation unités v1');
-- Récupérer l'id généré → renseigner PROMPT_LEARNER_ID (env du service learner).
```

## Changelog
- **v1** : version initiale — classification dimension + define/reecriture, réutilisation des
  dimensions existantes, sortie JSON stricte, 3 exemples d'ancrage.
