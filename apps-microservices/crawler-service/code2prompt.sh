#!/bin/bash

# code2prompt.sh - Génère un prompt contextualisé pour LLM à partir d'un workspace
# Version finale : Robuste, optimisée, gestion intelligente des fichiers et auto-exclusion.
#
# Usage: ./code2prompt.sh [OPTIONS] [DIRECTORY]

# --- CONFIGURATION PAR DÉFAUT ---
DEFAULT_DIR="."
DEFAULT_OUTPUT="workspace_context.txt"
CHUNK_THRESHOLD=200000 
CHUNK_SIZE=150000
MAX_FILE_COUNT=500

# Extensions de fichiers à inclure
INCLUDE_EXTENSIONS=(
    "*.js" "*.jsx" "*.ts" "*.tsx" "*.py" "*.java" "*.c" "*.cpp" "*.h" "*.hpp"
    "*.go" "*.rs" "*.php" "*.rb" "*.swift" "*.html" "*.css" "*.scss" "*.sass"
    "*.json" "*.xml" "*.yaml" "*.yml" "*.md" "*.txt" "*.sh" "*.bat"
    "*.sql" "*.r" "*.scala" "*.kt" "Dockerfile" "Makefile" "*.toml" "*.ini"
    "*.vue" "*.svelte" "*.dart"
)

# Répertoires et fichiers à exclure par défaut
EXCLUDE_PATTERNS=(
    "*/node_modules/*" "*/.git/*" "*/.svn/*" "*/.hg/*" "*/__pycache__/*"
    "*/build/*" "*/dist/*" "*/target/*" "*/bin/*" "*/obj/*"
    "*/.vscode/*" "*/.idea/*" "*/vendor/*" "*/.next/*" "*/.nuxt/*"
    "*/coverage/*" "*/logs/*" "*.log" "package-lock.json" "yarn.lock"
    "*.min.js" "*.min.css" "*.exe" "*.dll" "*.so" "*.dylib"
    "*.jpg" "*.jpeg" "*.png" "*.gif" "*.ico" "*.pdf" "*.zip" "*.tar.gz" "*.rar"
)

# --- FONCTIONS ---
show_help() {
    echo "Usage: $0 [OPTIONS] [DIRECTORY] [OUTPUT_FILE]"
    echo ""
    echo "Génère un prompt contextualisé pour LLM à partir des fichiers d'un workspace."
    echo ""
    echo "Options:"
    echo "  -h, --help              Affiche cette aide."
    echo "  -o, --output FILE       Fichier de sortie (défaut: $DEFAULT_OUTPUT)."
    echo "  -d, --dir DIRECTORY     Répertoire à scanner (défaut: répertoire courant)."
    echo "  --chunk-threshold SIZE  Taille (en octets) à partir de laquelle découper les fichiers (défaut: $CHUNK_THRESHOLD)."
    echo "  --chunk-size SIZE       Taille (en octets) de chaque morceau (défaut: $CHUNK_SIZE)."
    echo "  --include-ext EXT       Extension supplémentaire à inclure."
    echo "  --exclude-pattern PTRN  Pattern d'exclusion supplémentaire."
    echo "  --no-content            Génère seulement l'arborescence et les stats."
}

# --- PARSE DES ARGUMENTS ---
WORK_DIR="$DEFAULT_DIR"
OUTPUT_FILE="$DEFAULT_OUTPUT"
NO_CONTENT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help; exit 0 ;;
        -o|--output) OUTPUT_FILE="$2"; shift 2 ;;
        -d|--dir) WORK_DIR="$2"; shift 2 ;;
        --chunk-threshold) CHUNK_THRESHOLD="$2"; shift 2 ;;
        --chunk-size) CHUNK_SIZE="$2"; shift 2 ;;
        --include-ext) INCLUDE_EXTENSIONS+=("$2"); shift 2 ;;
        --exclude-pattern) EXCLUDE_PATTERNS+=("$2"); shift 2 ;;
        --no-content) NO_CONTENT=true; shift ;;
        *) WORK_DIR="$1"; shift ;;
    esac
done

if [[ ! -d "$WORK_DIR" ]]; then
    echo "Erreur: Le répertoire '$WORK_DIR' n'existe pas." >&2
    exit 1
fi

get_file_lang() {
    local ext="${1##*.}"
    case "$ext" in
        js|jsx) echo "javascript" ;; ts|tsx) echo "typescript" ;;
        py) echo "python" ;; java) echo "java" ;; c|h) echo "c" ;;
        cpp|hpp) echo "cpp" ;; go) echo "go" ;; rs) echo "rust" ;;
        php) echo "php" ;; rb) echo "ruby" ;; swift) echo "swift" ;;
        html) echo "html" ;; css) echo "css" ;; scss|sass) echo "scss" ;;
        json) echo "json" ;; xml) echo "xml" ;; yaml|yml) echo "yaml" ;;
        md) echo "markdown" ;; sh) echo "bash" ;; sql) echo "sql" ;;
        Dockerfile) echo "dockerfile" ;; *) echo "text" ;;
    esac
}

# --- EXÉCUTION PRINCIPALE ---
echo "Génération du contexte du workspace..." >&2
echo "Répertoire : $WORK_DIR" >&2
echo "Sortie     : $OUTPUT_FILE" >&2

mkdir -p "$(dirname "$OUTPUT_FILE")"

exec > "$OUTPUT_FILE"

# --- PARTIE 1: Entête et Instructions ---
echo "# Contexte du Workspace pour LLM"
# ... (le reste de l'entête reste identique)
echo ""
echo "Ce document contient l'analyse complète d'un workspace de développement."
echo "Il a été généré pour fournir un contexte structuré à un Large Language Model."
echo "Les fichiers volumineux ont été découpés en morceaux (chunks) pour analyse."
echo ""
echo "**Date de génération**: $(date)"
echo "**Répertoire analysé**: $(realpath "$WORK_DIR")"
echo ""
echo "**Instructions pour le LLM**:"
echo "- Analyse la structure du projet, les dépendances et la logique métier à partir des fichiers fournis."
echo "- Pour les fichiers découpés (chunks), considère-les comme des parties séquentielles du même fichier."
echo "- Réponds aux questions en te basant sur l'intégralité de ce contexte."
echo ""

# --- PARTIE 2: Construction des commandes `find` ---
FIND_ARGS=()
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    FIND_ARGS+=(-path "$pattern" -prune -o)
done
FIND_ARGS+=(\( -false)
for ext in "${INCLUDE_EXTENSIONS[@]}"; do
    FIND_ARGS+=(-o -name "$ext")
done
FIND_ARGS+=(\))

# --- PARTIE 3: Boucle unique pour traiter les fichiers ---
file_paths=()
file_contents=""
total_size=0
file_count=0
processed_count=0

## NOUVEAU : Récupérer le nom de base du script et du fichier de sortie pour les exclure.
SCRIPT_NAME=$(basename "$0")
OUTPUT_BASENAME=$(basename "$OUTPUT_FILE")

spinner() {
    local i=0; local sp='/-\|';
    while true; do printf "\rTraitement... %s" "${sp:i++%${#sp}:1}"; sleep 0.1; done
}

spinner &
SPINNER_PID=$!
trap "kill $SPINNER_PID 2>/dev/null; printf '\rTraitement terminé.       \n' >&2; exit" INT TERM EXIT

while IFS= read -r -d '' file; do
    [[ -f "$file" && -r "$file" ]] || continue

    ## NOUVEAU : Condition d'auto-exclusion.
    # On compare le nom de base du fichier trouvé avec le nom du script et du fichier de sortie.
    current_basename=$(basename "$file")
    if [[ "$current_basename" == "$SCRIPT_NAME" || "$current_basename" == "$OUTPUT_BASENAME" ]]; then
        continue # On passe au fichier suivant
    fi

    relative_path="${file#$WORK_DIR/}"; file_paths+=("$relative_path")
    ((file_count++)); size=$(stat -c%s "$file"); ((total_size+=size))

    if [[ "$NO_CONTENT" == "false" ]]; then
        if file --mime-encoding "$file" | grep -qv "us-ascii\|utf-8"; then
            file_contents+="\n## $relative_path\n\n\`\`\`\n*Fichier binaire, contenu omis.*\n\`\`\`\n"
            continue
        fi

        if [[ $size -gt $CHUNK_THRESHOLD ]]; then
            num_chunks=$(( (size + CHUNK_SIZE - 1) / CHUNK_SIZE ))
            split -b "$CHUNK_SIZE" --numeric-suffixes=1 --additional-suffix=.chunk "$file" temp_chunk_
            chunk_num=1
            for chunk_file in temp_chunk_*; do
                file_contents+="\n## $relative_path (Partie $chunk_num/$num_chunks)\n"
                file_contents+="\n\`\`\`$(get_file_lang "$file")\n"
                file_contents+=$(<"$chunk_file"); file_contents+="\n\`\`\`\n"
                ((chunk_num++))
            done
            rm temp_chunk_*
        else
            file_contents+="\n## $relative_path\n"; file_contents+="\n\`\`\`$(get_file_lang "$file")\n"
            file_contents+=$(<"$file"); file_contents+="\n\`\`\`\n"
        fi
    fi

    ((processed_count++))
    printf "\rFichiers traités : %d" "$processed_count" >&2
    if [[ $processed_count -ge $MAX_FILE_COUNT ]]; then
        echo "*Limite de fichiers ($MAX_FILE_COUNT) atteinte, traitement interrompu.*" >&2
        break
    fi
done < <(find "$WORK_DIR" "${FIND_ARGS[@]}" -type f -print0 | sort -z)

kill $SPINNER_PID && wait $SPINNER_PID 2>/dev/null
trap - INT TERM EXIT
printf "\n" >&2

# --- PARTIE 4: Affichage final ---
TOKEN_ESTIMATE=$(( total_size / 3 ))
echo "# Statistiques et Arborescence"
echo ""
echo "- **Nombre de fichiers analysés**: $file_count"
echo "- **Taille totale du code**: $(( total_size / 1024 )) KB"
echo "- **Estimation grossière des tokens**: ~${TOKEN_ESTIMATE} tokens"
echo ""
echo "## Structure du projet"
echo "\`\`\`"
if command -v tree &> /dev/null; then
    EXCLUDE_TREE_ARGS=""
    for pattern in "node_modules" ".git" "build" "dist" "target"; do
        EXCLUDE_TREE_ARGS+=" -I $pattern"
    done
    tree "$WORK_DIR" $EXCLUDE_TREE_ARGS
else
    for path in "${file_paths[@]}"; do
        echo "$path"
    done | sort
fi
echo "\`\`\`"
echo ""

if [[ "$NO_CONTENT" == "false" ]]; then
    echo "# Contenu des fichiers"
    echo -e "$file_contents"
fi

# --- FIN ---
echo "---" >&2
echo "✅ Contexte généré avec succès dans: $OUTPUT_FILE" >&2
file_size=$(stat -c%s "$OUTPUT_FILE")
echo "📊 Taille du fichier de contexte : $(( file_size / 1024 )) KB" >&2

if [[ $TOKEN_ESTIMATE -gt 100000 ]]; then
    echo "⚠️  Attention : Le contexte généré est très volumineux (~${TOKEN_ESTIMATE} tokens). Il pourrait dépasser la limite de votre LLM." >&2
fi