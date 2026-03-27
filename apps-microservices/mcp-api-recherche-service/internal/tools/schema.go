package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
)

const schemaDescription = "Récupérer le schéma (noms et types des champs) d'une collection Milvus. " +
	"Utilisez cet outil pour découvrir les champs disponibles pour le filtrage et les output_fields pouvant être demandés lors d'une recherche. " +
	"Collections disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs)."

const schemaInputSchema = `{
	"type": "object",
	"properties": {
		"collection": {
			"type": "string",
			"description": "Nom de la collection Milvus (ex. produits_3, siteweb_2, devis, echanges, prix)"
		}
	},
	"required": ["collection"]
}`

// milvusTypeNames maps Milvus DataType enum integer strings to human-readable type names.
var milvusTypeNames = map[string]string{
	"1":   "BOOL",
	"2":   "INT8",
	"3":   "INT16",
	"4":   "INT32",
	"5":   "INT64",
	"10":  "FLOAT",
	"11":  "DOUBLE",
	"21":  "VARCHAR",
	"22":  "ARRAY",
	"23":  "JSON",
	"100": "BINARY_VECTOR",
	"101": "FLOAT_VECTOR",
	"102": "FLOAT16_VECTOR",
	"103": "BFLOAT16_VECTOR",
	"104": "SPARSE_FLOAT_VECTOR",
}

// fieldInfo holds rich metadata for a single field.
type fieldInfo struct {
	Type        string `json:"type"`
	Description string `json:"description"`
	Filterable  bool   `json:"filterable"`
	Internal    bool   `json:"internal,omitempty"`
}

// fieldDescriptions contains per-collection, per-field descriptions in French.
// Fields not listed here will get a generic description based on their type.
var fieldDescriptions = map[string]map[string]fieldMeta{
	"produits_3": {
		"id":                       {Desc: "Identifiant unique interne (clé primaire auto-générée)", Filterable: true, Internal: true},
		"id_produit":               {Desc: "Identifiant du produit HelloPro", Filterable: true},
		"url":                      {Desc: "URL de la page produit"},
		"nom_produit":              {Desc: "Nom commercial du produit"},
		"page_type":                {Desc: "Type de page source (ex. fiche_produit, listing_produit)", Filterable: true},
		"domaine":                  {Desc: "Nom de domaine du site source", Filterable: true},
		"fournisseur":              {Desc: "Nom du fournisseur", Filterable: true},
		"id_fournisseur":           {Desc: "Identifiant du fournisseur", Filterable: true},
		"categorie":                {Desc: "Nom de la catégorie produit", Filterable: true},
		"id_categorie":             {Desc: "Identifiant de la catégorie", Filterable: true},
		"source":                   {Desc: "Source d'import du produit (BO, SITEWEB, API)", Filterable: true},
		"fichier_source":           {Desc: "Nom du fichier source d'import"},
		"etat":                     {Desc: "État du produit (actif, inactif, etc.)", Filterable: true},
		"affichage":                {Desc: "Statut d'affichage sur HelloPro", Filterable: true},
		"date_ajout":               {Desc: "Date d'ajout au format ISO (ex. 2024-01-15)", Filterable: true},
		"date_maj":                 {Desc: "Date de dernière mise à jour au format ISO", Filterable: true},
		"text":                     {Desc: "Contenu textuel complet du produit (utilisé pour la recherche BM25)"},
		"sku":                      {Desc: "Référence SKU (Stock Keeping Unit)", Filterable: true},
		"ean":                      {Desc: "Code-barres EAN du produit", Filterable: true},
		"url_images":               {Desc: "URLs des images produit (peut être tronqué)"},
		"reference":                {Desc: "Référence interne du produit", Filterable: true},
		"prix_ht":                  {Desc: "Prix hors taxe"},
		"prix_ttc":                 {Desc: "Prix toutes taxes comprises"},
		"statut":                   {Desc: "Statut du produit", Filterable: true},
		"remise":                   {Desc: "Informations de remise/promotion"},
		"stock":                    {Desc: "Niveau de stock disponible"},
		"delai_livraison":          {Desc: "Délai de livraison estimé"},
		"marque":                   {Desc: "Marque du produit", Filterable: true},
		"fabricant":                {Desc: "Nom du fabricant", Filterable: true},
		"garantie":                 {Desc: "Informations de garantie"},
		"normes":                   {Desc: "Normes et certifications applicables"},
		"frais_de_port":            {Desc: "Frais de port / livraison"},
		"caracteristique":          {Desc: "Caractéristiques techniques du produit"},
		"type_produit":             {Desc: "Type de produit (bien, service, etc.)", Filterable: true},
		"montant_eco_participation": {Desc: "Montant de l'éco-participation"},
		"source_produits":          {Desc: "Source d'origine des données produit", Filterable: true},
		"chunk_id":                 {Desc: "Identifiant unique du chunk", Internal: true},
		"chunk_number":             {Desc: "Numéro de séquence du chunk (0, 1, 2...)", Internal: true},
		"total_chunks":             {Desc: "Nombre total de chunks pour ce produit", Internal: true},
		"embedding":                {Desc: "Vecteur dense CamemBERT-large (1024 dimensions)", Internal: true},
		"sparse_embedding":         {Desc: "Vecteur creux BM25 (calculé automatiquement depuis le champ text)", Internal: true},
	},
	"siteweb_2": {
		"id":             {Desc: "Identifiant unique interne (clé primaire auto-générée)", Filterable: true, Internal: true},
		"url":            {Desc: "URL de la page web crawlée"},
		"domaine":        {Desc: "Nom de domaine du site", Filterable: true},
		"fournisseur":    {Desc: "Nom du fournisseur propriétaire du site", Filterable: true},
		"id_fournisseur": {Desc: "Identifiant du fournisseur", Filterable: true},
		"categorie":      {Desc: "Catégorie associée à la page", Filterable: true},
		"id_categorie":   {Desc: "Identifiant de la catégorie", Filterable: true},
		"page_type":      {Desc: "Type de page web (home, fiche_produit, presentation_societe, article, contact, etc.)", Filterable: true},
		"source":         {Desc: "Source d'import de la page", Filterable: true},
		"fichier_source": {Desc: "Nom du fichier source"},
		"etat":           {Desc: "État de la page (active, supprimée, etc.)", Filterable: true},
		"affichage":      {Desc: "Statut d'affichage", Filterable: true},
		"date_ajout":     {Desc: "Date d'ajout au format ISO", Filterable: true},
		"date_maj":       {Desc: "Date de dernière mise à jour au format ISO", Filterable: true},
		"text":           {Desc: "Contenu textuel de la page web (utilisé pour la recherche BM25)"},
		"chunk_id":       {Desc: "Identifiant unique du chunk", Internal: true},
		"chunk_number":   {Desc: "Numéro de séquence du chunk", Internal: true},
		"total_chunks":   {Desc: "Nombre total de chunks pour cette page", Internal: true},
		"embedding":      {Desc: "Vecteur dense CamemBERT-large (1024 dimensions)", Internal: true},
	},
	"devis": {
		"id":                 {Desc: "Identifiant unique interne (clé primaire auto-générée)", Filterable: true, Internal: true},
		"lead_id":            {Desc: "Identifiant du lead (demande de devis)", Filterable: true},
		"date_du_lead":       {Desc: "Date du lead (timestamp entier)", Filterable: true},
		"categorie":          {Desc: "Catégorie du produit demandé", Filterable: true},
		"id_categorie":       {Desc: "Identifiant de la catégorie", Filterable: true},
		"id_produit":         {Desc: "Identifiant du produit demandé", Filterable: true},
		"message":            {Desc: "Message de demande de devis rédigé par l'acheteur"},
		"message_hellopro":   {Desc: "Message standard HelloPro accompagnant la demande"},
		"critere":            {Desc: "Critères de sélection spécifiés par l'acheteur"},
		"appreciation_lead":  {Desc: "Appréciation/qualité du lead", Filterable: true},
		"societe_acheteur":   {Desc: "Nom de la société de l'acheteur", Filterable: true},
		"siren":              {Desc: "Numéro SIREN de l'acheteur", Filterable: true},
		"siret":              {Desc: "Numéro SIRET de l'acheteur", Filterable: true},
		"naf2":               {Desc: "Code NAF niveau 2 de l'acheteur", Filterable: true},
		"naf5":               {Desc: "Code NAF niveau 5 de l'acheteur", Filterable: true},
		"effectif":           {Desc: "Tranche d'effectif de la société acheteuse", Filterable: true},
		"departement":        {Desc: "Département de l'acheteur", Filterable: true},
		"region":             {Desc: "Région de l'acheteur", Filterable: true},
		"pays":               {Desc: "Pays de l'acheteur", Filterable: true},
		"prof_ou_part":       {Desc: "Professionnel ou particulier", Filterable: true},
		"nb_mec":             {Desc: "Nombre de mises en concurrence", Filterable: true},
		"liste_frns":         {Desc: "Liste des fournisseurs mis en concurrence (tableau)"},
		"source":             {Desc: "Source du devis", Filterable: true},
		"date_ajout":         {Desc: "Date d'ajout au format ISO", Filterable: true},
		"date_maj":           {Desc: "Date de dernière mise à jour au format ISO", Filterable: true},
		"page_type":          {Desc: "Type de page source", Filterable: true},
		"text":               {Desc: "Contenu textuel complet du devis"},
		"chunk_id":           {Desc: "Identifiant unique du chunk", Internal: true},
		"chunk_number":       {Desc: "Numéro de séquence du chunk", Internal: true},
		"total_chunks":       {Desc: "Nombre total de chunks pour ce devis", Internal: true},
		"embedding":          {Desc: "Vecteur dense CamemBERT-large (1024 dimensions)", Internal: true},
	},
	"echanges": {
		"id":              {Desc: "Identifiant unique interne (clé primaire auto-générée)", Filterable: true, Internal: true},
		"conversation_id": {Desc: "Identifiant de la conversation", Filterable: true},
		"id_demande":      {Desc: "Identifiant de la demande liée", Filterable: true},
		"acheteur":        {Desc: "Nom de l'acheteur", Filterable: true},
		"id_acheteur":     {Desc: "Identifiant de l'acheteur", Filterable: true},
		"fournisseur":     {Desc: "Nom du fournisseur", Filterable: true},
		"id_fournisseur":  {Desc: "Identifiant du fournisseur", Filterable: true},
		"produit":         {Desc: "Nom du produit concerné"},
		"id_produit":      {Desc: "Identifiant du produit concerné", Filterable: true},
		"categorie":       {Desc: "Catégorie du produit", Filterable: true},
		"id_categorie":    {Desc: "Identifiant de la catégorie", Filterable: true},
		"etat":            {Desc: "État de la conversation (ouverte, fermée, etc.)", Filterable: true},
		"affichage":       {Desc: "Statut d'affichage", Filterable: true},
		"date_ajout":      {Desc: "Date d'ajout au format ISO", Filterable: true},
		"date_maj":        {Desc: "Date de dernière mise à jour au format ISO", Filterable: true},
		"text":            {Desc: "Contenu textuel de l'échange/conversation"},
		"chunk_id":        {Desc: "Identifiant unique du chunk", Internal: true},
		"chunk_number":    {Desc: "Numéro de séquence du chunk", Internal: true},
		"total_chunks":    {Desc: "Nombre total de chunks pour cet échange", Internal: true},
		"embedding":       {Desc: "Vecteur dense CamemBERT-large (1024 dimensions)", Internal: true},
	},
	"prix": {
		"id":                  {Desc: "Identifiant unique interne (clé primaire auto-générée)", Filterable: true, Internal: true},
		"id_produit":          {Desc: "Identifiant du produit", Filterable: true},
		"id_fournisseur":      {Desc: "Identifiant du fournisseur", Filterable: true},
		"id_lead":             {Desc: "Identifiant du lead associé", Filterable: true},
		"id_categorie":        {Desc: "Identifiant de la catégorie", Filterable: true},
		"id_societe_ia":       {Desc: "Identifiant de la société IA", Filterable: true},
		"nom_produit":         {Desc: "Nom du produit"},
		"nom_categorie":       {Desc: "Nom de la catégorie", Filterable: true},
		"description_produit": {Desc: "Description détaillée du produit"},
		"fournisseur":         {Desc: "Nom du fournisseur", Filterable: true},
		"domaine":             {Desc: "Nom de domaine du fournisseur", Filterable: true},
		"valeur_prix":         {Desc: "Valeur numérique du prix"},
		"prix_original":       {Desc: "Prix original tel que mentionné dans la source"},
		"devise":              {Desc: "Devise du prix (EUR, USD, etc.)", Filterable: true},
		"unite":               {Desc: "Unité de mesure du prix (pièce, kg, m², etc.)", Filterable: true},
		"taxe":                {Desc: "Type de taxe (HT, TTC)", Filterable: true},
		"structure_prix":      {Desc: "Structure tarifaire (unitaire, lot, dégressif, etc.)", Filterable: true},
		"type_transaction":    {Desc: "Type de transaction (achat, location, etc.)", Filterable: true},
		"date_prix":           {Desc: "Date du relevé de prix", Filterable: true},
		"source":              {Desc: "Source du prix (devis, catalogue, site web)", Filterable: true},
		"perimetre":           {Desc: "Périmètre géographique du prix", Filterable: true},
		"caracteristique":     {Desc: "Caractéristiques du produit liées au prix"},
		"valeur_reponse_q1":   {Desc: "Valeur de réponse au questionnaire qualité"},
		"date_ajout":          {Desc: "Date d'ajout au format ISO", Filterable: true},
		"date_maj":            {Desc: "Date de dernière mise à jour au format ISO", Filterable: true},
		"text":                {Desc: "Contenu textuel complet de l'entrée prix"},
		"source_chunk_id":     {Desc: "Identifiant du chunk source", Internal: true},
		"chunk_id":            {Desc: "Identifiant unique du chunk", Internal: true},
		"chunk_number":        {Desc: "Numéro de séquence du chunk", Internal: true},
		"total_chunks":        {Desc: "Nombre total de chunks pour cette entrée", Internal: true},
		"embedding":           {Desc: "Vecteur dense CamemBERT-large (1024 dimensions)", Internal: true},
		"sparse_embedding":    {Desc: "Vecteur creux BM25 (calculé automatiquement depuis le champ text)", Internal: true},
	},
}

// fieldMeta holds static metadata for a known field.
type fieldMeta struct {
	Desc       string
	Filterable bool
	Internal   bool
}

func handleGetCollectionSchema(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	collection, ok := args["collection"].(string)
	if !ok || collection == "" {
		return errorResult("'collection' parameter is required and must be a string"), nil
	}

	resp, err := clients.Database.GetSchema(ctx, &databasepb.GetSchemaRequest{
		CollectionName: collection,
		SourceService:  strPtr("mcp-api-recherche"),
	})
	if err != nil {
		return nil, fmt.Errorf("GetSchema gRPC call failed: %w", err)
	}

	rawFields := resp.GetFields()
	collMeta := fieldDescriptions[collection]

	enrichedFields := make(map[string]fieldInfo, len(rawFields))
	for name, typeCode := range rawFields {
		typeName := milvusTypeNames[typeCode]
		if typeName == "" {
			typeName = "UNKNOWN(" + typeCode + ")"
		}

		info := fieldInfo{
			Type: typeName,
		}

		if meta, ok := collMeta[name]; ok {
			info.Description = meta.Desc
			info.Filterable = meta.Filterable
			info.Internal = meta.Internal
		}

		enrichedFields[name] = info
	}

	result := map[string]any{
		"collection": collection,
		"fields":     enrichedFields,
	}
	return jsonResult(result), nil
}

func strPtr(s string) *string {
	return &s
}
