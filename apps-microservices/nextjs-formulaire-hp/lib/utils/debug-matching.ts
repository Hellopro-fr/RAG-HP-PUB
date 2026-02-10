/**
 * Debug Matching - Affiche les infos de debug sur les cartes produit et modals
 * Usage: Appeler debugInfo() dans la console du navigateur
 */

interface CharacteristicDebug {
  id_caracteristique: number;
  bareme: number;
  poids?: number;
  poids_question?: number;
  coeff_caracteristique?: number;
  coeff_etat_score?: number;
}

interface ProductDebugInfo {
  coeff_geo?: number;
  coeff_type_frns?: number;
  coeff_caracteristique?: number;
  coeff_etat_score?: number;
  characteristics_debug?: CharacteristicDebug[];
}

interface MatchingProduct {
  id: string;
  productName: string;
  matchScore: number;
  isRecommended: boolean;
  debugInfo?: ProductDebugInfo;
}

interface UserQuestionAnswer {
  questionId: number | string;
  questionCode?: string;
  questionLabel?: string;
  answerId: string | string[];
  answerLabel?: string | string[];
  equivalences?: any[];
  timestamp: number;
}

interface FlowStorage {
  state: {
    matchingResults?: {
      recommended?: MatchingProduct[];
      others?: MatchingProduct[];
    };
    characteristicsMap?: Record<string, { nom?: string }>;
    userQuestionAnswers?: UserQuestionAnswer[];
  };
}

function debugInfo(): void {
  const storageData = sessionStorage.getItem('flow-storage');
  if (!storageData) {
    console.error('Pas de flow-storage trouve');
    return;
  }

  const storage: FlowStorage = JSON.parse(storageData);
  if (!storage?.state) {
    console.error('Pas de state dans flow-storage');
    return;
  }

  const { matchingResults, characteristicsMap, userQuestionAnswers } = storage.state;

  // Afficher les questions/réponses de l'utilisateur
  if (userQuestionAnswers && userQuestionAnswers.length > 0) {
    console.log('--- QUESTIONS / REPONSES UTILISATEUR ---');
    console.table(userQuestionAnswers.map(qa => ({
      Question: qa.questionLabel || `Q${qa.questionId}`,
      Reponse: Array.isArray(qa.answerLabel) ? qa.answerLabel.join(', ') : qa.answerLabel || qa.answerId,
    })));

    // Créer un panel fixe draggable pour afficher les Q/R
    document.querySelectorAll('.debug-qa-panel').forEach(el => el.remove());

    const qaPanel = document.createElement('div');
    qaPanel.className = 'debug-qa-panel';
    qaPanel.style.cssText = `
      position: fixed; top: 10px; right: 10px; z-index: 99999;
      background: #1a1a2e; color: #0f0; font-size: 11px;
      font-family: monospace;
      border: 2px solid #0f0; border-radius: 8px;
      max-width: 400px; max-height: 350px;
      box-shadow: 0 4px 20px rgba(0,255,0,0.3);
      display: flex; flex-direction: column;
    `;

    const qaRows = userQuestionAnswers.map(qa => {
      const question = qa.questionLabel || `Question ${qa.questionId}`;
      const answer = Array.isArray(qa.answerLabel)
        ? qa.answerLabel.join(', ')
        : (qa.answerLabel || String(qa.answerId));
      return `
        <div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #333">
          <div style="color:#888;font-size:10px">Q: ${question}</div>
          <div style="color:#0ff;font-weight:bold">R: ${answer}</div>
        </div>
      `;
    }).join('');

    qaPanel.innerHTML = `
      <div class="debug-qa-header" style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#0f0;border-radius:6px 6px 0 0;cursor:move;user-select:none">
        <span style="color:#000;font-weight:bold;font-size:12px">Q/R (${userQuestionAnswers.length}) - Glisser pour deplacer</span>
        <button onclick="this.closest('.debug-qa-panel').remove()" style="background:#f00;color:#fff;border:none;padding:2px 8px;cursor:pointer;border-radius:4px;font-weight:bold">X</button>
      </div>
      <div style="padding:12px;overflow-y:auto;flex:1">
        ${qaRows}
      </div>
    `;

    document.body.appendChild(qaPanel);

    // Rendre le panel draggable
    const header = qaPanel.querySelector('.debug-qa-header') as HTMLElement;
    let isDragging = false;
    let offsetX = 0;
    let offsetY = 0;

    header.addEventListener('mousedown', (e: MouseEvent) => {
      isDragging = true;
      offsetX = e.clientX - qaPanel.getBoundingClientRect().left;
      offsetY = e.clientY - qaPanel.getBoundingClientRect().top;
      qaPanel.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e: MouseEvent) => {
      if (!isDragging) return;
      e.preventDefault();
      const x = e.clientX - offsetX;
      const y = e.clientY - offsetY;
      qaPanel.style.left = `${x}px`;
      qaPanel.style.top = `${y}px`;
      qaPanel.style.right = 'auto';
    });

    document.addEventListener('mouseup', () => {
      isDragging = false;
      qaPanel.style.cursor = '';
    });

    console.log('Panel Q/R affiche (draggable) - Glisser la barre verte pour deplacer');
  } else {
    console.log('Pas de userQuestionAnswers enregistrees');
  }

  if (!matchingResults) {
    console.error('Pas de matchingResults');
    return;
  }

  // Construire un map id_caracteristique -> nom depuis characteristicsMap
  const caracteristiquesMap: Record<string, string> = {};
  if (characteristicsMap) {
    Object.entries(characteristicsMap).forEach(([id, data]) => {
      if (data.nom) {
        caracteristiquesMap[id] = data.nom;
      }
    });
  }

  const { recommended = [], others = [] } = matchingResults;
  const allProducts = [...recommended, ...others];

  console.log('Produits trouves:', allProducts.length);
  console.log('Caracteristiques mappees:', Object.keys(caracteristiquesMap).length);

  // Map par productName -> toutes les infos
  const debugByName: Record<string, MatchingProduct> = {};
  allProducts.forEach(p => {
    debugByName[p.productName] = p;
  });

  // Supprimer les anciens overlays
  document.querySelectorAll('.debug-overlay').forEach(el => el.remove());

  let injected = 0;

  document.querySelectorAll('h4').forEach(h4 => {
    const name = h4.textContent?.trim();
    if (!name) return;

    const product = debugByName[name];
    if (!product) return;

    const card = h4.closest('div[class*="rounded-xl"][class*="border"]');
    if (!card || card.querySelector('.debug-overlay')) return;

    const debug = product.debugInfo || {};
    const chars = debug.characteristics_debug || [];

    const overlay = document.createElement('div');
    overlay.className = 'debug-overlay';
    overlay.style.cssText = `
      background: #111; color: #0f0; font-size: 9px;
      padding: 8px; font-family: monospace;
      border-top: 2px solid #0f0;
      max-height: 300px; overflow-y: auto;
      line-height: 1.4;
    `;

    const charRows = chars.map(c => {
      const libelle = caracteristiquesMap[c.id_caracteristique] || `ID:${c.id_caracteristique}`;
      const barColor = c.bareme >= 80 ? '#0f0' : c.bareme >= 50 ? '#ff0' : '#f80';
      return `
        <tr style="border-bottom:1px solid #222">
          <td style="color:#0ff" title="${c.id_caracteristique}">${c.id_caracteristique}</td>
          <td style="padding:2px;color:#0ff;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${libelle}">- ${libelle}</td>
          <td style="text-align:right;padding:2px;color:${barColor}">${c.bareme}</td>
          <td style="text-align:right;padding:2px">${c.poids_question ?? '-'}</td>
          <td style="text-align:right;padding:2px">${c.coeff_caracteristique ?? '-'}</td>
          <td style="text-align:right;padding:2px">${c.coeff_etat_score ?? '-'}</td>
        </tr>
      `;
    }).join('');

    overlay.innerHTML = `
      <div style="color:#fff;font-weight:bold;font-size:11px;margin-bottom:4px;border-bottom:1px solid #333;padding-bottom:4px">
        DEBUG - ID: ${product.id}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;margin-bottom:6px">
        <div><span style="color:#888">matchScore: </span><span style="color:#ff0">${product.matchScore}%</span></div>
        <div><span style="color:#888">isRecommended: </span>${product.isRecommended}</div>
        <div><span style="color:#888">coeff_geo: </span>${debug.coeff_geo ?? 'N/A'}</div>
        <div><span style="color:#888">coeff_type_frns: </span>${debug.coeff_type_frns ?? 'N/A'}</div>
      </div>
      <div style="color:#fff;font-weight:bold;margin:6px 0 4px;border-bottom:1px solid #333;padding-bottom:2px">
        Caracteristiques (${chars.length})
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:9px">
        <tr style="color:#888;border-bottom:1px solid #333">
          <th style="text-align:left">Id</th>
          <th style="text-align:left;padding:2px;width:35%">|Carac</th>
          <th style="text-align:right;padding:2px">|bareme</th>
          <th style="text-align:right;padding:2px">|poids_q</th>
          <th style="text-align:right;padding:2px">|coeff_car</th>
          <th style="text-align:right;padding:2px">|coeff_etat</th>
        </tr>
        ${charRows}
      </table>
      <div style="margin-top:6px;padding-top:4px;border-top:1px solid #333;color:#666;font-size:7px">
        Raw: ${JSON.stringify(debug).substring(0, 200)}...
      </div>
    `;

    card.appendChild(overlay);
    injected++;
  });

  console.log(`${injected} debug overlays injectes sur les cartes`);

  // ========================================
  // FONCTION: Injecter debug dans modal
  // ========================================
  function injectDebugInModal(modal: Element, productName: string): void {
    const product = allProducts.find(p => p.productName === productName);
    if (!product) {
      console.error('Produit non trouve:', productName);
      return;
    }

    const debug = product.debugInfo || {};
    const chars = debug.characteristics_debug || [];
    const charsMap = characteristicsMap || {};

    // Supprimer ancien panel si existe
    modal.querySelectorAll('.debug-panel').forEach(el => el.remove());

    const scrollContainer = modal.querySelector('.overflow-y-auto');
    if (!scrollContainer) {
      console.error('Conteneur modal non trouve');
      return;
    }

    const panel = document.createElement('div');
    panel.className = 'debug-panel';
    panel.style.cssText = `
      background: #0a0a0a; color: #0f0; font-size: 12px;
      padding: 12px; font-family: monospace;
      margin: 16px; border-radius: 8px;
      border: 2px solid #0f0;
    `;

    const modalCharRows = chars.map(c => {
      const charInfo = charsMap[c.id_caracteristique];
      const nom = charInfo?.nom || '?';
      const barColor = c.bareme >= 80 ? '#0f0' : c.bareme >= 50 ? '#ff0' : '#f80';
      return `
        <tr style="border-bottom:1px solid #1a1a1a">
          <td style="padding:4px;color:#0ff">${c.id_caracteristique}</td>
          <td style="padding:4px;color:#fff;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${nom}">${nom}</td>
          <td style="text-align:center;padding:4px;color:${barColor};font-weight:bold">${c.bareme}</td>
          <td style="text-align:center;padding:4px">${c.poids ?? '-'}</td>
          <td style="text-align:center;padding:4px">${c.poids_question ?? '-'}</td>
        </tr>
      `;
    }).join('');

    panel.innerHTML = `
      <div style="color:#fff;font-weight:bold;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:2px solid #0f0">
        DEBUG MATCHING
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px;padding:8px;background:#111;border-radius:4px">
        <div><span style="color:#888">ID:</span> <span style="color:#0ff">${product.id}</span></div>
        <div><span style="color:#888">matchScore:</span> <span style="color:#ff0;font-weight:bold">${product.matchScore}%</span></div>
        <div><span style="color:#888">coeff_geo:</span> <span style="color:#0f0">${debug.coeff_geo ?? 'N/A'}</span></div>
        <div><span style="color:#888">coeff_type_frns:</span> <span style="color:#0f0">${debug.coeff_type_frns ?? 'N/A'}</span></div>
        <div><span style="color:#888">isRecommended:</span> ${product.isRecommended ? '<span style="color:#0f0">true</span>' : '<span style="color:#f88">false</span>'}</div>
        <div><span style="color:#888">Coeff_Carac:</span> <span style="color:#0f0">${debug.coeff_caracteristique ?? 'N/A'}</span></div>
        <div><span style="color:#888">Nb caracteristiques:</span> <span style="color:#0ff">${chars.length}</span></div>
        <div><span style="color:#888">Coeff Etat Score:</span> <span style="color:#0f0">${debug.coeff_etat_score ?? 'N/A'}</span></div>
      </div>

      <div style="color:#fff;font-weight:bold;margin-bottom:6px">characteristics_debug (${chars.length})</div>

      <div style="max-height:200px;overflow-y:auto;background:#111;border-radius:4px">
        <table style="width:100%;border-collapse:collapse;font-size:11px">
          <thead style="position:sticky;top:0;background:#111">
            <tr style="color:#888">
              <th style="text-align:left;padding:4px;border-bottom:1px solid #333">Id</th>
              <th style="text-align:left;padding:4px;border-bottom:1px solid #333">Nom caracteristique</th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Bareme</th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Poids</th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Poids Q</th>
            </tr>
          </thead>
          <tbody>
            ${modalCharRows}
          </tbody>
        </table>
      </div>
    `;

    scrollContainer.prepend(panel);
    console.log('Debug modal injecte pour:', productName);
  }

  // ========================================
  // OBSERVER: Detecter l'ouverture des modaux
  // ========================================
  const productNames = new Set(allProducts.map(p => p.productName));

  // Supprimer l'ancien observer si existant
  const windowWithDebug = window as Window & { __debugMatchingObserver?: MutationObserver };
  if (windowWithDebug.__debugMatchingObserver) {
    windowWithDebug.__debugMatchingObserver.disconnect();
  }

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) {
          const element = node as Element;
          if (element.classList?.contains('fixed')) {
            const h2 = element.querySelector('h2');
            if (h2) {
              const pName = h2.textContent?.trim();
              if (pName && productNames.has(pName)) {
                console.log('Modal detecte pour:', pName);
                setTimeout(() => injectDebugInModal(element, pName), 100);
              }
            }
          }
        }
      });
    });
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });

  windowWithDebug.__debugMatchingObserver = observer;

  console.log('Observer actif - Les modaux seront automatiquement debugges');

  console.log('Donnees completes:', allProducts.map(p => ({
    id: p.id,
    name: p.productName,
    score: p.matchScore,
    debug: p.debugInfo
  })));
}

function clearDebugInfo(): void {
  document.querySelectorAll('.debug-overlay, .debug-panel, .debug-qa-panel').forEach(el => el.remove());

  const windowWithDebug = window as Window & { __debugMatchingObserver?: MutationObserver };
  if (windowWithDebug.__debugMatchingObserver) {
    windowWithDebug.__debugMatchingObserver.disconnect();
    delete windowWithDebug.__debugMatchingObserver;
  }

  console.log('Debug overlays supprimes');
}

export function initDebugMatching(): void {
  if (typeof window !== 'undefined') {
    const w = window as Window & { debugInfo?: typeof debugInfo; clearDebugInfo?: typeof clearDebugInfo };
    w.debugInfo = debugInfo;
    w.clearDebugInfo = clearDebugInfo;
    console.log('Debug matching initialise. Fonctions disponibles: debugInfo(), clearDebugInfo()');
  }
}

export { debugInfo, clearDebugInfo };
