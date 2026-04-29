package queue

// ignoredExtensions est la liste des extensions de fichiers ignorées par le crawler.
// Traduit server.js:523-530.
const ignoredExtensions = "7z|7zip|bz2|rar|tar|tar\\.gz|xz|zip|" +
	"mng|pct|bmp|gif|jpg|jpeg|png|pst|psp|tif|tiff|ai|drw|dxf|eps|ps|svg|cdr|ico|webp|" +
	"mp3|wma|ogg|wav|ra|aac|mid|au|aiff|" +
	"3gp|asf|asx|avi|mov|mp4|mpg|qt|rm|swf|wmv|m4a|m4v|flv|webm|" +
	"xls|xlsx|ppt|pptx|pps|doc|docx|odt|ods|odg|odp|" +
	"css|pdf|exe|bin|rss|dmg|iso|apk|xml"

// BlockedPatterns est la liste des patterns d'exclusion utilisés pour catégoriser
// les URLs d'une request queue comme "bloquées".
// Reproduit exactement excludePatterns de server.js:532-585.
var BlockedPatterns = []string{
	// Extension pattern — traitée spécialement dans MatchesPattern via @(...)
	"**/*.@(" + ignoredExtensions + "){,\\?*}{,\\#*}",

	// === SPIDER TRAPS E-COMMERCE ===
	"**/*order=*", "**/*sort=*", "**/*dir=*", "**/*limit=*",
	"**/*resultsPerPage=*", "**/*filter=*", "**/*filters[*",
	"**/*price=*", "**/*price_min=*", "**/*price_max=*",
	"**/*id_category=*", "**/*categoryId=*", "**/*productListView=*",
	"**/*q=*", "**/*search=*", "**/*query=*",
	"**/*page=*/**/*page=*", "**/*offset=*", "**/*start=*",
	"**/*view=*", "**/*mode=*", "**/*display=*", "**/*per_page=*", "**/*items=*",

	// === AUTH & ACCOUNT ===
	"**/connexion**", "**/login**", "**/signin**", "**/log-in**",
	"**/register**", "**/signup**", "**/inscription**",
	"**/account**", "**/mon-compte**", "**/my-account**",
	"**/profile**", "**/profil**",
	"**/password**", "**/mot-de-passe**", "**/reset-password**",
	"**/logout**", "**/deconnexion**",
	"**/forgot-password**", "**/oubli-mot-de-passe**",
	"**/customer/account/**", "**/customer/**",

	// === SHOPPING ===
	"**/panier**", "**/cart**", "**/basket**",
	"**/checkout**", "**/commande**", "**/order**",
	"**/add-to-cart**", "**/addtocart**",
	"**/payment**", "**/paiement**",
	"**/shipping**", "**/livraison**",
	"**/confirmation**",
	"**/quotation/**", "**/devis/**",

	// === USER ACTIONS ===
	"**/wishlist**", "**/liste-envies**", "**/favoris**",
	"**/compare**", "**/comparateur**",
	"**/sendtoafriend**", "**/send-to-friend**",

	// === CALENDAR ===
	"**/*year=*", "**/*month=*", "**/*day=*",
	"**/*date=*", "**/*from=*", "**/*to=*",
	"**/calendrier/**", "**/calendar/**",

	// === SOCIAL ===
	"**/*facebook*", "**/*twitter*", "**/*linkedin*",
	"**/*instagram*", "**/*youtube*", "**/*pinterest*",
	"**/*tiktok*", "**/*whatsapp*",
	"**/*share*", "**/*partager*",
	"**/mailto:*", "**/tel:*", "**/*://t.me/*",

	// === TRACKING ===
	"**/*redirect*", "**/*track*", "**/*click*",
	"**/*ref=*", "**/*referrer=*", "**/*source=*",

	// === API ===
	"**/api/**", "**/wp-json/**", "**/rest/**",
	"**/feed/**", "**/feeds/**", "**/rss/**",
	"**/PBCPPlayer.asp**", "**/popup/**",

	// === SPECIFIC SITE EXCLUDES (promodis.fr) ===
	"**/download.php*", "**/dhtml/download.php*",
	"**/*imp=1*",

	// === SHOPIFY TRAPS ===
	"**/collections/all*", "**/collections/vendors*", "**/collections/types*",
}
