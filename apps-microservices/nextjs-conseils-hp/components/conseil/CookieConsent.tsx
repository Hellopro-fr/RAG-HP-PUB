'use client';

import { useEffect, useState } from 'react';
import {
  getCookie,
  setRgpdCookie,
  storeConsentV2,
  pushConsentUpdate,
  fireConsentAuditPixel,
} from '@/lib/consent/cookies';

/**
 * Bandeau de consentement RGPD HelloPro — reconstruction React du CMP legacy
 * (cookie_consentement.php + handlers js_general_v1). Look et comportements identiques.
 *
 * Réutilisable : déposer <CookieConsent/> dans le layout. S'affiche uniquement si
 * le cookie `hp_consent` est absent (consentement partagé .hellopro.fr — cf. ticket GTM).
 *
 * Flux (identiques au legacy) :
 *   - Refuser tout / Continuer sans accepter → denied×4, hp_consent=1, pixel=1
 *   - Accepter tout / Accepter et fermer      → granted×4, hp_consent=3, pixel=3
 *   - Enregistrer préférences                 → hp_consent=2 + hp_consent_perso, pixel=2
 */

const LOGO = 'https://www.hellopro.fr/hellopro_fr/images/logo-hellopro-logo.jpg';

type Choice = 'none' | 'accept' | 'refuse';

const STYLE = `
#hp-cmp .cookie-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);display:flex;justify-content:center;align-items:center;z-index:3001}
#hp-cmp .cookie-popup{width:720px;max-width:720px;background:#fff;padding:30px;box-shadow:0 4px 6px rgba(0,0,0,.1);max-height:400px;overflow:auto;border-radius:4px}
#hp-cmp .cookie-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-direction:column}
#hp-cmp .cookie-logo-title{display:flex;align-items:center;gap:10px;justify-content:space-between;width:100%}
#hp-cmp .cookie-logo{height:20px}
#hp-cmp .cookie-header h2{margin:20px 0 0;font-size:18px;color:#FB5607;align-self:flex-start;display:block}
#hp-cmp .hp-cmp-link{font-size:12px;color:#888;text-decoration:underline;cursor:pointer;margin-left:auto;background:none;border:0;padding:0}
#hp-cmp .hp-cmp-link:hover{color:#000}
#hp-cmp .cookie-body p{font-size:14px;color:#333;line-height:1.6;margin:0 0 10px}
#hp-cmp .cookie-body p a{color:inherit;text-decoration:underline}
#hp-cmp .cookie-footer{display:flex;justify-content:center;margin-top:40px;gap:15px}
#hp-cmp .cookie-button{background:#fff;border:1px solid #ccc;color:#333;border-radius:24px;padding:10px 15px;font-size:14px;cursor:pointer;transition:background .3s ease}
#hp-cmp .cookie-button.accept{background:#FB5607;color:#fff;border:1px solid #FB5607}
#hp-cmp .cookie-button:hover{background:#f5f5f5}
#hp-cmp .cookie-button.accept:hover{background:#a83800}
#hp-cmp .cookie-option{padding:10px 0;border-bottom:1px solid #f0f0f0;position:relative;flex-wrap:wrap}
#hp-cmp .title-with-chevron{display:flex;align-items:center;gap:10px}
#hp-cmp .toggle-description{background:none;border:none;cursor:pointer;padding:5px;display:flex;align-items:center}
#hp-cmp .trigger-icon{width:15px;font-size:16px;display:inline-block;text-align:center}
#hp-cmp .trigger-icon::before{content:'+'}
#hp-cmp .trigger-icon.ouvert::before{content:'-'}
#hp-cmp .cookie-option span{font-size:14px;color:#333}
#hp-cmp .description{margin-top:10px;font-size:12px;color:#666;line-height:1.4;background:#f5f6f7;padding:15px 10px;border-radius:4px}
#hp-cmp .cookie_bloc_bouton{margin-top:10px}
#hp-cmp .cookie_boutons{display:flex;gap:6px;align-items:center}
#hp-cmp .btn_action_cookie{cursor:pointer;height:25px;box-shadow:1px 1px 0 0 rgba(0,0,0,.1);background:#fff;border:1px solid #eee;padding:0 20px;line-height:12px;font-size:12px;color:#757575;font-weight:700;transition:background-color .2s,border-color .2s;border-radius:4px;display:inline-flex;align-items:center;gap:6px}
#hp-cmp .refuser_cookie.choisi{background:#e60000;color:#fff;border:1px solid rgba(0,0,0,.3)}
#hp-cmp .accepter_cookie.choisi{background:#3d8548;color:#fff;border:1px solid rgba(0,0,0,.3)}
#hp-cmp .cookie_requis{display:flex;margin:5px 0;text-transform:uppercase;font-size:14px;color:#526e7a}
#hp-cmp .cookie-footer.params{flex-direction:column;align-items:flex-end;gap:12px}
#hp-cmp .bloc_btn_action_cookie_tout{display:flex;gap:15px}
#hp-cmp .text_param_cookie{margin-right:15px;font-style:italic;color:#757575;font-size:14px}
#hp-cmp .btn_save_param_cookie:disabled{background:#fff !important;color:#B1B5C0 !important;border:1px solid #ccc;cursor:not-allowed}
#hp-cmp .close_param_cookie{opacity:.5;font-size:30px;line-height:30px;color:#000;cursor:pointer;background:none;border:0}
#hp-cmp .close_param_cookie:hover{opacity:.7}
@media (max-width:768px){#hp-cmp .cookie-popup{width:99%;max-width:99%;padding:14px;max-height:95vh}#hp-cmp .cookie-footer{flex-direction:column}#hp-cmp .cookie-button{width:100%}#hp-cmp .bloc_btn_action_cookie_tout{flex-direction:column;width:100%}}
`;

const D = { ad_storage: 'denied', analytics_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' } as const;
const G = { ad_storage: 'granted', analytics_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted' } as const;

export function CookieConsent() {
  const [show, setShow] = useState(false);
  const [view, setView] = useState<'main' | 'param'>('main');
  const [open, setOpen] = useState<{ essential: boolean; stats: boolean; perso: boolean }>({
    essential: false, stats: false, perso: false,
  });
  const [stat, setStat] = useState<Choice>('none');
  const [perso, setPerso] = useState<Choice>('none');

  /* Affiché uniquement si aucun consentement enregistré (cookie lisible côté client). */
  useEffect(() => {
    if (getCookie('hp_consent') === '') setShow(true);
  }, []);

  /* Verrou scroll body tant que le bandeau est ouvert. */
  useEffect(() => {
    if (!show) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [show]);

  if (!show) return null;

  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'conseils.hellopro.fr';
  const saveEnabled = stat !== 'none' && perso !== 'none';

  function close() {
    setShow(false);
  }

  /* Refuser tout / Continuer sans accepter → hp_consent=1 */
  function refuseAll() {
    pushConsentUpdate(D);
    storeConsentV2(D);
    setRgpdCookie('hp_consent', '1', 365);
    fireConsentAuditPixel('1');
    close();
  }

  /* Accepter tout / Accepter et fermer → hp_consent=3 */
  function acceptAll() {
    pushConsentUpdate(G);
    storeConsentV2(G);
    setRgpdCookie('hp_consent', '3', 365);
    fireConsentAuditPixel('3');
    close();
  }

  /* Enregistrer préférences → hp_consent=2 + hp_consent_perso "<stats>,<perso>" */
  function savePrefs() {
    if (!saveEnabled) return;
    const s = stat === 'accept' ? 1 : 0;
    const p = perso === 'accept' ? 1 : 0;
    const choices = `${s},${p}`;
    const analytics = s === 1 ? 'granted' : 'denied';
    const personalization = p === 1 ? 'granted' : 'denied';
    const c = {
      ad_storage: personalization,
      analytics_storage: analytics,
      ad_user_data: personalization,
      ad_personalization: personalization,
    } as const;
    pushConsentUpdate(c);
    storeConsentV2(c);
    setRgpdCookie('hp_consent', '2', 365);
    setRgpdCookie('hp_consent_perso', choices, 365);
    fireConsentAuditPixel('2', choices);
    close();
  }

  function CatButtons({ value, onChange }: { value: Choice; onChange: (c: Choice) => void }) {
    return (
      <div className="cookie_bloc_bouton">
        <div className="cookie_boutons">
          <button
            type="button"
            className={`btn_action_cookie refuser_cookie${value === 'refuse' ? ' choisi' : ''}`}
            onClick={() => onChange('refuse')}
          >
            Refuser
          </button>
          <button
            type="button"
            className={`btn_action_cookie accepter_cookie${value === 'accept' ? ' choisi' : ''}`}
            onClick={() => onChange('accept')}
          >
            Accepter
          </button>
        </div>
      </div>
    );
  }

  return (
    <div id="hp-cmp">
      <style dangerouslySetInnerHTML={{ __html: STYLE }} />

      {/* ── Popup principal ── */}
      {view === 'main' && (
        <div className="cookie-overlay">
          <div className="cookie-popup">
            <div className="cookie-header">
              <div className="cookie-logo-title">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={LOGO} alt="HelloPro" className="cookie-logo" />
                <button type="button" className="hp-cmp-link" onClick={refuseAll}>
                  Continuer sans accepter
                </button>
              </div>
              <h2>Vos données, votre choix.</h2>
            </div>
            <div className="cookie-body">
              <p>
                Sur nos sites et nos applications, nous recueillons à chacune de vos visites des
                données vous concernant. Ces données nous permettent de vous proposer les offres et
                services les plus pertinents pour vous, et d&apos;adapter le contenu de nos sites à
                vos préférences.
              </p>
              <p>
                Pour en savoir plus sur l&apos;utilisation des cookies{' '}
                <a href={`https://${hostname}/gestion-cookie`} target="_blank" rel="nofollow noreferrer">
                  cliquez ici
                </a>.
              </p>
            </div>
            <div className="cookie-footer">
              <button type="button" className="cookie-button" onClick={() => setView('param')}>
                Paramétrer
              </button>
              <button type="button" className="cookie-button accept" onClick={acceptAll}>
                Accepter et fermer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Popup paramétrage ── */}
      {view === 'param' && (
        <div className="cookie-overlay">
          <div className="cookie-popup">
            <div className="cookie-header">
              <div className="cookie-logo-title">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={LOGO} alt="HelloPro" className="cookie-logo" />
                <button
                  type="button"
                  className="close_param_cookie"
                  aria-label="Fermer"
                  onClick={() => { setView('main'); setStat('none'); setPerso('none'); }}
                >
                  ×
                </button>
              </div>
              <h2>Vous autorisez</h2>
            </div>

            <div className="cookie-body">
              {/* Essentiels — REQUIS */}
              <div className="cookie-option">
                <div className="title-with-chevron">
                  <button
                    type="button"
                    className="toggle-description"
                    onClick={() => setOpen((o) => ({ ...o, essential: !o.essential }))}
                  >
                    <span className={`trigger-icon${open.essential ? ' ouvert' : ''}`} aria-hidden="true" />
                  </button>
                  <span>Essentiels au fonctionnement du site</span>
                  <span className="cookie_requis" style={{ marginLeft: 'auto' }}>Requis</span>
                </div>
                {open.essential && (
                  <div className="description">
                    Ces cookies sont indispensables pour assurer le bon fonctionnement de Hellopro.
                    Ils permettent, par exemple, de maintenir votre session active lors de votre
                    navigation ou de garantir l&apos;accès aux fonctionnalités principales du site.
                    Ces cookies ne peuvent pas être désactivés.
                  </div>
                )}
              </div>

              {/* Statistiques enrichies */}
              <div className="cookie-option">
                <div className="title-with-chevron">
                  <button
                    type="button"
                    className="toggle-description"
                    onClick={() => setOpen((o) => ({ ...o, stats: !o.stats }))}
                  >
                    <span className={`trigger-icon${open.stats ? ' ouvert' : ''}`} aria-hidden="true" />
                  </button>
                  <span>Statistiques enrichies</span>
                </div>
                {open.stats && (
                  <div className="description">
                    Ces cookies nous aident à analyser et améliorer la performance de Hellopro. Ils
                    permettent de comprendre quelles pages sont les plus consultées et d&apos;optimiser
                    votre expérience de navigation sur le site.
                  </div>
                )}
                <CatButtons value={stat} onChange={setStat} />
              </div>

              {/* Personnalisation de contenu */}
              <div className="cookie-option">
                <div className="title-with-chevron">
                  <button
                    type="button"
                    className="toggle-description"
                    onClick={() => setOpen((o) => ({ ...o, perso: !o.perso }))}
                  >
                    <span className={`trigger-icon${open.perso ? ' ouvert' : ''}`} aria-hidden="true" />
                  </button>
                  <span>Personnalisation de contenu</span>
                </div>
                {open.perso && (
                  <div className="description">
                    Ces cookies adaptent les contenus et recommandations en fonction de votre activité
                    sur le site. Par exemple, ils mettent en avant les solutions ou produits les plus
                    pertinents pour vos besoins professionnels.
                  </div>
                )}
                <CatButtons value={perso} onChange={setPerso} />
              </div>
            </div>

            <div className="cookie-footer params">
              {saveEnabled ? (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <span className="text_param_cookie">Enregistrer et continuer</span>
                  <button type="button" className="cookie-button accept btn_save_param_cookie" onClick={savePrefs}>
                    Enregistrer
                  </button>
                </div>
              ) : (
                <div className="bloc_btn_action_cookie_tout">
                  <button type="button" className="cookie-button" onClick={refuseAll}>Refuser tout</button>
                  <button type="button" className="cookie-button accept" onClick={acceptAll}>Accepter tout</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
