const GTM_ID = 'GTM-PBBSTMC';
const GA4_ID = 'G-J3925VE86T';
const MD5_EMPTY = 'd41d8cd98f00b204e9800998ecf8427e';

const GTM_LOADER = `(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','${GTM_ID}');`;

const GA4_CONFIG = `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${GA4_ID}');`;

const IMPRESSIONS_SCRIPT = `if(typeof prod_intern_gtm!='undefined'){window.dataLayer=window.dataLayer||[];dataLayer.push({"event":"eec.impressionView","ecommerce":{"currencyCode":"EUR","impressions":Object.keys(prod_intern_gtm).map(function(i){return prod_intern_gtm[i];})}});dataLayer.push({"event":"done"});}`;

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface GtmFooterScriptsProps {
  breadcrumb: BreadcrumbItem[];
}

function toGtmSlug(label: string): string {
  return label.replace(/\s+/g, '-');
}

function buildUserCategoryScript(breadcrumb: BreadcrumbItem[]): string {
  const items = breadcrumb.slice(1); // exclure "Accueil"
  const last = items[items.length - 1];
  const middle = items.slice(0, items.length - 1).slice(0, 4);
  const cat = {
    category1: toGtmSlug(middle[0]?.label ?? ''),
    category2: toGtmSlug(middle[1]?.label ?? ''),
    category3: toGtmSlug(middle[2]?.label ?? ''),
    category4: toGtmSlug(middle[3]?.label ?? ''),
    category5: toGtmSlug(last?.label ?? ''),
  };
  return `(function(){function getCookie(n){var c=document.cookie.split(';');for(var i=0;i<c.length;i++){var p=c[i].trim().split('=');if(p[0]===n)return decodeURIComponent(p.slice(1).join('='));}return '';}var email=getCookie('email_preremplissage_di');var logged=(email!==''&&email!=='${MD5_EMPTY}')||getCookie('id_societe')!=='';window.dataLayer=window.dataLayer||[];dataLayer.push({"user":{"visitorId":"","visitorLoginState":logged?"logged":"unlogged","visitorType":"","visitorCountry":"","visitorDepartment":"/","visitorJob":"/","visitorNewsletterSub":"","visitorCompanyStatus":"/"},"product":{"category1":${JSON.stringify(cat.category1)},"category2":${JSON.stringify(cat.category2)},"category3":${JSON.stringify(cat.category3)},"category4":${JSON.stringify(cat.category4)},"category5":${JSON.stringify(cat.category5)}}});})();`;
}

export function GtmFooterScripts({ breadcrumb }: GtmFooterScriptsProps) {
  const userCategoryScript = buildUserCategoryScript(breadcrumb);
  return (
    <>
      {/* Step 6 — page_template (en premier) */}
      <script dangerouslySetInnerHTML={{ __html: `window.dataLayer=window.dataLayer||[];dataLayer.push({"page_template":"conseils"});` }} />
      {/* Step 7 — user + catégories (détection session + fil d'ariane) */}
      <script dangerouslySetInnerHTML={{ __html: userCategoryScript }} />
      {/* Step 8 — chargement GTM (révèle la page via fin du async-hide) */}
      <script dangerouslySetInnerHTML={{ __html: GTM_LOADER }} />
      {/* Step 9 — GA4 */}
      <script async src={`https://www.googletagmanager.com/gtag/js?id=${GA4_ID}`} />
      <script dangerouslySetInnerHTML={{ __html: GA4_CONFIG }} />
      {/* Step 10 — impressions produits (en dernier) */}
      <script dangerouslySetInnerHTML={{ __html: IMPRESSIONS_SCRIPT }} />
    </>
  );
}
