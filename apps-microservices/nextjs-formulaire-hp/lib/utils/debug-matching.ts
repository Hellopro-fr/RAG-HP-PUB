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

interface FournisseurPays {
  id_pays: number;
  nom_pays: string;
  couvre_partiel: boolean;
}

interface FournisseurDepartement {
  id_dept: string;
  nom_dept?: string;
}

interface FournisseurData {
  pays?: FournisseurPays[];
  departements?: FournisseurDepartement[];
}

/**
 * Récupère les informations du fournisseur via l'API
 */
async function getFournisseur(id_produit: string): Promise<FournisseurData | null> {
  try {
    console.log('Recuperation fournisseur pour ID:', id_produit);

    const response = await fetch(
      `/formulaire/api/matching_fournisseur/produit/${id_produit}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    console.log('Response status:', response.status);

    if (!response.ok) {
      throw new Error(`Erreur HTTP: ${response.status}`);
    }

    const data = await response.json();
    console.log('Donnees recues:', data);

    return data;
  } catch (error) {
    console.error("Erreur lors de l'appel API :", error);
    return null;
  }
}

function debugInfo(): void {
  // Activer le mode debug pour les boutons de copie dans les modals produit
  (window as any).__debugModeEnabled = true;
  window.dispatchEvent(new Event('enableDebugMode'));
  console.log('[DEBUG] Copy buttons enabled in product modals');

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

    const qaRows = userQuestionAnswers.map((qa, index) => {
      const questionNum = index + 1;
      const question = qa.questionLabel || `Question ${qa.questionId}`;
      const answer = Array.isArray(qa.answerLabel)
        ? qa.answerLabel.join(', ')
        : (qa.answerLabel || String(qa.answerId));
      return `
        <div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #333">
          <div style="color:#888;font-size:10px"><span style="color:#0f0;font-weight:bold">Q${questionNum}:</span> ${question}</div>
          <div style="color:#0ff;font-weight:bold">R${questionNum}: ${answer}</div>
        </div>
      `;
    }).join('');

    // Preparer le texte a copier
    const textToCopy = userQuestionAnswers.map((qa, index) => {
      const questionNum = index + 1;
      const question = qa.questionLabel || `Question ${qa.questionId}`;
      const answer = Array.isArray(qa.answerLabel)
        ? qa.answerLabel.join(', ')
        : (qa.answerLabel || String(qa.answerId));
      return `Q${questionNum}: ${question}\nR${questionNum}: ${answer}`;
    }).join('\n\n');

    // Stocker le texte a copier dans une variable globale temporaire
    const copyId = `__debugQACopy_${Date.now()}`;
    (window as any)[copyId] = textToCopy;

    qaPanel.innerHTML = `
      <div class="debug-qa-header" style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#0f0;border-radius:6px 6px 0 0;cursor:move;user-select:none">
        <span style="color:#000;font-weight:bold;font-size:12px">Q/R (${userQuestionAnswers.length}) - Glisser pour deplacer</span>
        <div style="display:flex;gap:4px;align-items:center">
          <button class="debug-copy-btn" title="Copier Q/R" style="background:#1a1a2e;color:#0f0;border:1px solid #0f0;padding:4px 8px;cursor:pointer;border-radius:4px;font-size:11px;display:flex;align-items:center;gap:4px">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            Copier
          </button>
          <button onclick="this.closest('.debug-qa-panel').remove()" style="background:#f00;color:#fff;border:none;padding:2px 8px;cursor:pointer;border-radius:4px;font-weight:bold">X</button>
        </div>
      </div>
      <div style="padding:12px;overflow-y:auto;flex:1">
        ${qaRows}
      </div>
    `;

    // Ajouter l'event listener pour le bouton copier
    const copyBtn = qaPanel.querySelector('.debug-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText((window as any)[copyId]);
          (copyBtn as HTMLElement).style.background = '#0f0';
          (copyBtn as HTMLElement).style.color = '#000';
          copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Copie!
          `;
          setTimeout(() => {
            (copyBtn as HTMLElement).style.background = '#1a1a2e';
            (copyBtn as HTMLElement).style.color = '#0f0';
            copyBtn.innerHTML = `
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              Copier
            `;
          }, 1500);
        } catch (err) {
          console.error('Erreur copie:', err);
        }
      });
    }

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
          <td style="text-align:right;padding:2px">${c.poids ?? '-'}</td>
          <td style="text-align:right;padding:2px">${c.poids_question ?? '-'}</td>
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
        <div><span style="color:#888">Typologie acheteur: </span>${debug.coeff_type_frns ?? 'N/A'}</div>
      </div>
      <div style="color:#fff;font-weight:bold;margin:6px 0 4px;border-bottom:1px solid #333;padding-bottom:2px">
        Caracteristiques (${chars.length})
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:9px">
        <tr style="color:#888;border-bottom:1px solid #333">
          <th style="text-align:left">Id</th>
          <th style="text-align:left;padding:2px;width:35%">|Carac</th>
          <th style="text-align:right;padding:2px">|bareme</th>
          <th style="text-align:right;padding:2px">|poids</th>
          <th style="text-align:right;padding:2px">|poids_q</th>
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
  async function injectDebugInModal(modal: Element, productName: string): Promise<void> {
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

    // Calculs des scores
    const tousLesPoidsQuestion = chars.map(c => c.poids_question).filter((pq): pq is number => pq !== undefined);
    const totalPoidsQuestion = [...new Set(tousLesPoidsQuestion)].reduce((a, b) => a + b, 0);

    // Map bareme * poids par caracteristique
    const tabProduiBaremePoids: Record<number, number> = {};
    chars.forEach(c => {
      tabProduiBaremePoids[c.id_caracteristique] = (c.bareme ?? 0) * (c.poids ?? 0);
    });

    // Récupérer les données du fournisseur
    let data_fournisseur: FournisseurData | null = null;
    try {
      data_fournisseur = await getFournisseur(product.id);
    } catch (error) {
      console.warn('Impossible de recuperer les donnees fournisseur');
    }

    // Grouper les caracteristiques par poids_question
    const groupedByPoidsQuestion: Record<number, CharacteristicDebug[]> = chars.reduce((acc, c) => {
      const pq = c.poids_question ?? 0;
      if (!acc[pq]) acc[pq] = [];
      acc[pq].push(c);
      return acc;
    }, {} as Record<number, CharacteristicDebug[]>);

    // Calculer les scores par poids question
    const scoresParPoidsQuestion: Record<number, number> = {};
    const calculDetailsScoreTechnique: string[] = [];
    let sommeNumerateur = 0;
    let sommeDenominateur = 0;

    // Trier les entrees par poids question decroissant
    const sortedEntries = Object.entries(groupedByPoidsQuestion).sort((a, b) => {
      return parseFloat(b[0]) - parseFloat(a[0]);
    });

    sortedEntries.forEach(([poidsQuestion, caractList]) => {
      const sommeProduits = caractList.reduce((sum, c) => sum + (tabProduiBaremePoids[c.id_caracteristique] ?? 0), 0);
      const sommePoids = caractList.reduce((sum, c) => sum + (c.poids ?? 0), 0);
      const scoreParPQ = sommePoids !== 0 ? (sommeProduits / sommePoids) : 0;

      scoresParPoidsQuestion[parseFloat(poidsQuestion)] = scoreParPQ;

      const pq = parseFloat(poidsQuestion);
      sommeNumerateur += scoreParPQ * pq;
      sommeDenominateur += pq;

      calculDetailsScoreTechnique.push(`(${parseFloat(scoreParPQ.toFixed(2))} x ${pq})`);
    });

    const scoreTechniqueProduit = sommeDenominateur !== 0 ? (sommeNumerateur / sommeDenominateur) : 0;
    const scoreFinalProduit = scoreTechniqueProduit * (debug.coeff_geo ?? 1) * (debug.coeff_type_frns ?? 1) * (debug.coeff_etat_score ?? 1);

    // Generer les lignes du tableau avec les lignes de sous-total
    let tableRows = '';
    sortedEntries.forEach(([poidsQuestion, caractList]) => {
      // Ajouter les lignes pour chaque caracteristique
      caractList.forEach(c => {
        const charInfo = charsMap[c.id_caracteristique];
        const nom = charInfo?.nom || '?';
        const barColor = c.bareme >= 80 ? '#0f0' : c.bareme >= 50 ? '#ff0' : '#f80';
        const negativColor = 'color:#f88';
        const produiBaremePoids = tabProduiBaremePoids[c.id_caracteristique] ?? 0;
        tableRows += `
          <tr style="border-bottom:1px solid #1a1a1a">
            <td style="padding:4px;color:#0ff">${c.id_caracteristique}</td>
            <td style="padding:4px;color:#fff;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${nom}">${nom}</td>
            <td style="text-align:center;padding:4px;color:${barColor};font-weight:bold">${parseFloat((c.bareme ?? 0).toFixed(2))}</td>
            <td style="text-align:center;padding:1px;color:#fff">x</td>
            <td style="text-align:center;padding:4px">${c.poids ?? '-'}</td>
            <td style="text-align:left;padding:4px;${produiBaremePoids < 0 ? negativColor : ''}">= ${parseFloat(produiBaremePoids.toFixed(2))}</td>
            <td style="text-align:center;padding:4px">${c.poids_question ?? '-'}</td>
          </tr>
        `;
      });

      // Calculer les sommes pour ce groupe de poids_question
      const sommeProduits = caractList.reduce((sum, c) => sum + (tabProduiBaremePoids[c.id_caracteristique] ?? 0), 0);
      const sommePoids = caractList.reduce((sum, c) => sum + (c.poids ?? 0), 0);
      const resultat = scoresParPoidsQuestion[parseFloat(poidsQuestion)] ?? 0;

      // Ajouter la ligne de sous-total
      tableRows += `
        <tr style="background:#1a3a1a;border-bottom:1px solid #0f0">
          <td colspan="5" style="text-align:right;padding:6px;color:#fff;font-weight:bold">
            Score Caracteristique :
          </td>
          <td colspan="2" style="padding:6px;color:#0f0;font-weight:bold">
            ${parseFloat(sommeProduits.toFixed(2))} / ${sommePoids} = <span style="color:#ff0;font-weight:bold">${parseFloat(resultat.toFixed(2))}</span>
          </td>
        </tr>
      `;
    });

    // Préparer les informations du fournisseur pour l'affichage
    let fournisseurInfo = '';
    if (data_fournisseur) {
      console.log('Donnees fournisseur completes:', JSON.stringify(data_fournisseur, null, 2));

      // Traiter les pays
      let paysHtml = '';
      if (Array.isArray(data_fournisseur.pays) && data_fournisseur.pays.length > 0) {
        paysHtml = data_fournisseur.pays.map(p => `
          <div style="padding:4px 8px;background:#1a1a1a;border-radius:4px;margin-bottom:4px">
            <div><span style="color:#888">ID:</span> <span style="color:#0ff">${p.id_pays}</span></div>
            <div><span style="color:#888">Nom:</span> <span style="color:#0f0;font-weight:bold">${p.nom_pays}</span></div>
            <div><span style="color:#888">Couvre partiel:</span> <span style="color:${p.couvre_partiel ? '#ff0' : '#0f0'}">${p.couvre_partiel ? 'Oui' : 'Non'}</span></div>
          </div>
        `).join('');
      } else {
        paysHtml = '<div style="color:#888">Aucun pays</div>';
      }

      // Traiter les départements
      let departementsHtml = '';
      if (Array.isArray(data_fournisseur.departements) && data_fournisseur.departements.length > 0) {
        departementsHtml = data_fournisseur.departements.map(d => `
          <div style="padding:4px 8px;background:#1a1a1a;border-radius:4px;margin-bottom:4px;display:inline-block;margin-right:4px">
            <span style="color:#0ff">${d.id_dept}</span>
            ${d.nom_dept ? `<span style="color:#888"> - ${d.nom_dept}</span>` : ''}
          </div>
        `).join('');
      } else {
        departementsHtml = '<div style="color:#888">Aucun departement</div>';
      }

      fournisseurInfo = `
        <div style="color:#fff;font-weight:bold;margin-bottom:6px;margin-top:12px">Informations Fournisseur</div>
        <div style="padding:8px;background:#111;border-radius:4px;margin-bottom:12px">
          <div style="color:#888;font-weight:bold;margin-bottom:4px;border-bottom:1px solid #333;padding-bottom:2px">
            Pays (${data_fournisseur.pays?.length || 0}) :
          </div>
          <div style="margin-bottom:8px;display:grid;grid-auto-flow:column;grid-auto-columns:150px;gap:10px;overflow-x:auto;overflow-y:hidden;">
            ${paysHtml}
          </div>

          <div style="color:#888;font-weight:bold;margin-bottom:4px;border-bottom:1px solid #333;padding-bottom:2px">
            Departements (${data_fournisseur.departements?.length || 0}) :
          </div>
          <div style="display:grid;grid-auto-flow:column;grid-template-rows:repeat(2, 50px);grid-auto-columns:150px;gap:10px;overflow-x:auto;overflow-y:hidden;">
            ${departementsHtml}
          </div>

          <div style="margin-top:8px;padding-top:8px;border-top:1px solid #333">
            <details>
              <summary style="color:#888;cursor:pointer;user-select:none">JSON brut</summary>
              <pre style="color:#0ff;font-size:10px;margin-top:4px;overflow-x:auto;white-space:pre-wrap">${JSON.stringify(data_fournisseur, null, 2)}</pre>
            </details>
          </div>
        </div>
      `;
    } else {
      fournisseurInfo = `
        <div style="color:#fff;font-weight:bold;margin-bottom:6px;margin-top:12px">Informations Fournisseur</div>
        <div style="padding:8px;background:#111;border-radius:4px;margin-bottom:12px">
          <div><span style="color:#f88">Donnees fournisseur non disponibles</span></div>
        </div>
      `;
    }

    panel.innerHTML = `
      <div style="color:#fff;font-weight:bold;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:2px solid #0f0">
        DEBUG MATCHING
      </div>

      <div style="display:grid;grid-template-columns:1fr;gap:6px;margin-bottom:12px;padding:8px;background:#111;border-radius:4px">
        <table>
          <tr>
            <td><div><span style="color:#888">ID:</span> <span style="color:#0ff">${product.id}</span></div></td>
            <td><div><span style="color:#888">matchScore:</span> <span style="color:#ff0;font-weight:bold">${product.matchScore}%</span></div></td>
            <td><div><span style="color:#888">coeff_geo:</span> <span style="color:#0f0">${debug.coeff_geo ?? 'N/A'}</span></div></td>
          </tr>
          <tr>
            <td><div><span style="color:#888">Nb caracteristiques:</span> <span style="color:#0ff">${chars.length}</span></div></td>
            <td><div><span style="color:#888">Coeff Etat Score:</span> <span style="color:#0f0">${debug.coeff_etat_score ?? 'N/A'}</span></div></td>
            <td><div><span style="color:#888">Coeff_Carac:</span> <span style="color:#0f0">${debug.coeff_caracteristique?.toFixed(2) ?? 'N/A'}</span></div></td>
          </tr>
          <tr>
            <td><div><span style="color:#888">isRecommended:</span> ${product.isRecommended ? '<span style="color:#0f0">true</span>' : '<span style="color:#f88">false</span>'}</div></td>
            <td><div><span style="color:#888">Typologie acheteur:</span> <span style="color:#0f0">${debug.coeff_type_frns ?? 'N/A'}</span></div></td>
            <td></td>
          </tr>
        </table>
      </div>

      <div style="color:#fff;font-weight:bold;margin-bottom:6px">characteristics_debug (${chars.length})</div>

      <div style="max-height:400px;overflow-y:auto;background:#111;border-radius:4px">
        <table style="width:100%;border-collapse:collapse;font-size:11px">
          <thead style="position:sticky;top:0;background:#111">
            <tr style="color:#888">
              <th style="text-align:left;padding:4px;border-bottom:1px solid #333">Id</th>
              <th style="text-align:left;padding:4px;border-bottom:1px solid #333">Nom caracteristique</th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Bareme</th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333"></th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Poids</th>
              <th style="text-align:left;padding:4px;border-bottom:1px solid #333"></th>
              <th style="text-align:center;padding:4px;border-bottom:1px solid #333">Poids Question (${totalPoidsQuestion})</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows}
            <tr style="border-bottom:1px solid #1a1a1a;background:#2a2a0a">
              <td colspan="5" style="text-align:right;padding:6px;color:#fff;font-weight:bold">Score technique du produit : </td>
              <td colspan="2" style="padding:6px;color:#0f0">
                [${calculDetailsScoreTechnique.join(' + ')}] / ${sommeDenominateur} = <span style="color:#ff0;font-weight:bold">${parseFloat(scoreTechniqueProduit.toFixed(2))}</span>
              </td>
            </tr>
            <tr style="border-bottom:1px solid #1a1a1a">
              <td colspan="5" style="text-align:right;padding:6px;color:#fff;font-weight:bold">Score final du produit : </td>
              <td colspan="2" style="padding:6px;color:#0f0">
                ${parseFloat(scoreTechniqueProduit.toFixed(2))} x ${debug.coeff_geo ?? 1}(coeff_geo) x ${debug.coeff_type_frns ?? 1}(coeff_type_frns) x ${debug.coeff_etat_score ?? 1}(coeff_etat_score) = <span style="color:#ff0;font-weight:bold">${parseFloat(scoreFinalProduit.toFixed(2))}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      ${fournisseurInfo}
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
