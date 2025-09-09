var host = window.location.protocol + "//" + window.location.hostname;
var AJAX_COUT_TOTAL;
var base_url = "/admin/repertoire_test/moulinettes_interne/process_prospects/rag_prod";
var socket = null;

var CONFIG_SELECT2 = {
  groupSelected: false,
  with_ajax: true,
  action: "",
  pagination: false,
  limit: 20,
  data: data_select2,
  payload: {},
  with_templateResult: true,
  templateResult: templateResult_with_optgroup_select2,
  templateSelection: templateDropdown_selection,
  unique: false,
};

var OPTIONS_SELECT2 = {
  // language: "fr",
  width: "100%",
  formatNoMatches: "Aucune",
  closeOnSelect: true,
  dropdownCssClass: "custom-select2-filter",
  dropdownAutoWidth: true,
  allowClear: true,
  placeholder: "Rechercher",
  language: {
    // French translations
    lang: "fr",
    noResults: function () {
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'>Aucun résultat trouvé</span>"
      );
    },
    searching: function () {
      return `Recherche en cours…`;
    },
    inputTooShort: function (args) {
      var remainingChars = args.minimum - args.input.length;
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'>Saisissez au moins " +
          remainingChars +
          " caractère" +
          (remainingChars > 1 ? "s" : "") +
          " ou plus</span>"
      );
    },
    errorLoading: function () {
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'>Les résultats n'ont pas pu être chargés</span>"
      );
    },
    loadingMore: function () {
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'>Chargement des résultats supplémentaires…</span>"
      );
    },
  },
  minimumInputLength: 0,
};

var host = window.location.protocol + "//" + window.location.hostname;

/**
 * Affiche un message dans la zone de statut/chargement.
 * @param {string} message - Le message à afficher.
 * @param {string} type - Le type de message (info, success, warn, error).
 */
function logStatus(message, type = 'info') {
    // On réutilise le conteneur de chargement existant pour afficher les statuts.
    const loadingContainer = $("#loading-table-content");
    const statusMessage = `[${new Date().toLocaleTimeString()}] ${message}`;
    
    // Pour la simplicité, on affiche le dernier statut. On pourrait aussi créer une liste.
    loadingContainer.html(`<span>${statusMessage}</span>`).show();
    console.log(`[WebSocket Status - ${type}]`, message); // On log aussi en console pour le débogage
}

/**
 * Affiche les résultats de recherche dans le tableau principal.
 * @param {Array} results - La liste des documents/résultats reçus.
 */
function displaySearchResults(results) {
    const tbody = $('#tbody-data-content');
    tbody.html(''); // Vider les anciens résultats

    if (!results || results.length === 0) {
        const colspan = ORDRE_COLONNE.length + 2; // +2 pour checkbox et colonne de gestion
        tbody.html(`<tr><td colspan="${colspan}" class="text-center">Aucun résultat trouvé.</td></tr>`);
        return;
    }

    results.forEach(result => {
        const meta = result.metadata.entity || {};
        const row = $('<tr></tr>').attr('data-id', meta.id_produit || '');

        // 1. Colonne de la case à cocher
        row.append('<td class="table-default-vue"><input class="check-box-recherche" type="checkbox"></td>');

        // 2. Colonnes de données dynamiques
        Object.keys(list_header).forEach(champs => {
            if (typeof list_header[champs].est_filtre === 'undefined') {
                let cell_data = meta[champs] || '';
                
                // Formatage spécifique par champ
                if (champs === 'pertinence') {
                    const score = result.rerank_score !== undefined ? result.rerank_score : result.score;
                    cell_data = score ? Math.round(result.score * 100) + " %" : 'N/A';
                } else if (champs === 'source') {
                    cell_data = result.source;
                } else if (champs === 'url' && meta.url) {
                    cell_data = `<a href="${meta.url}" target="_blank" rel="noopener noreferrer" title="${meta.url}">Lien</a>`;
                }
                
                const td = $(`<td data-champs="${champs}" class='${list_header[champs].class || ''}'></td>`).html(cell_data);
                row.append(td);
            }
        });
        
        // 3. Colonne "Gérer" (vide, pour l'alignement avec l'en-tête)
        row.append(`<td class="table-default-vue"><i class='bx bx-info-circle font-24 c-pointer'  ></i> </td>`);
        
        tbody.append(row);
    });

    // Appliquer l'ordre et la visibilité des colonnes définis par l'utilisateur
    charger_ordre_colonne(ORDRE_COLONNE);
}

/**
 * Affiche le résumé des performances.
 * @param {object} summary - L'objet contenant les métriques de performance.
 */
function displaySummary(summary) {
    if (!summary) return;

    // Mettre à jour le nombre total de résultats
    const resultCount = summary.result_count || 0;
    $("#nombre-recherches").text(resultCount);

    // Mettre à jour le "coût" avec le temps total de traitement
    const totalTime = summary.timings?.total_process || 0;
    $(".cout-valeur").text(`${totalTime}s`);
}


/**
 * Fonction principale qui initie la recherche via WebSocket.
 */
function startWebSocketSearch() {
    clearResults();

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    }

    // TODO: L'URL du WebSocket est en dur. À adapter si nécessaire.
    const wsUrl = "ws://34.90.162.9:8510/ws/search";
    logStatus(`Connexion à ${wsUrl}...`);

    try {
        socket = new WebSocket(wsUrl);
    } catch (error) {
        logStatus(`Erreur de connexion WebSocket: ${error.message}`, 'error');
        return;
    }

    socket.onopen = () => {
        logStatus('WebSocket connecté.', 'success');
        $("#send_filter").prop('disabled', true).text('En cours...');

        // Récupération des filtres depuis l'interface existante
        const filtresActifs = recup_filtre_visualisation().filtre;
        const formattedFilters = {};
        for (const key in filtresActifs) {
            formattedFilters[key] = filtresActifs[key].values;
        }

        // Construction de la requête
        const searchRequest = {
            prompt: $('#search-prompt').val(),
            source: formattedFilters.source || ["produits"], // Source par défaut
            nombre_resultat: (parseInt($("#top_k").val(), 10) || 10).toString(),
            // action: 2, // 1 pour recherche simple, 2 pour recherche + LLM
            
            // Paramètres LLM (valeurs par défaut car non présents dans l'UI originale)
            // temperature: 0.4,
            // template_prompt: "En te basant sur les informations suivantes :\n\n{chunks}\n\nRéponds à la question : \"{recherche}\"",
            // chat_model: "gpt-4o",
            // use_reranker: true,

            // // Filtres dynamiques
            // categorie: formattedFilters.categorie || {},
            // fournisseur: formattedFilters.fournisseur || {},
            // etat_societe: formattedFilters.etat_societe || [],
            // affichage: formattedFilters.affichage || [],
            // params: {} // Pour une utilisation future
        };

        socket.send(JSON.stringify(searchRequest));
        logStatus('Requête de recherche envoyée.');
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        switch (data.type) {
            case 'status': logStatus(data.payload, 'info'); break;
            case 'warning': logStatus(data.payload, 'warn'); break;
            case 'error': logStatus(data.payload, 'error'); break;
            case 'rerank_complete':
                logStatus(`Reranking terminé en ${data.payload.duration}s.`, 'success');
                displaySearchResults(data.payload.results);
                break;
            case 'llm_start':
                // On pourrait afficher une section spécifique pour la réponse LLM si l'HTML était modifié
                logStatus('Le LLM commence à générer la réponse...', 'info');
                // Exemple: $('#llm-response-container').show();
                break;
            case 'llm_chunk':
                // Afficher le chunk LLM dans une zone dédiée
                // Exemple: $('#llm-response-container').append(data.payload);
                console.log("LLM Chunk:", data.payload); // Pour l'instant, on log en console
                break;
            case 'end_of_stream':
                logStatus('Flux terminé.', 'success');
                displaySummary(data.payload);
                socket.close();
                break;
            default: logStatus(`Message inconnu reçu: ${data.type}`, 'warn');
        }
    };

    const reEnableButtons = () => {
        $("#send_filter").prop('disabled', false).text('Lancer la recherche');
    };

    socket.onerror = (error) => {
        logStatus(`Erreur WebSocket: ${error.message || 'Une erreur est survenue.'}`, 'error');
        reEnableButtons();
    };

    socket.onclose = (event) => {
        if (event.wasClean) {
            logStatus(`Connexion fermée proprement.`, 'info');
        } else {
            logStatus('La connexion a été interrompue.', 'warn');
        }
        reEnableButtons();
    };
}



/**
 * Réinitialise les zones de résultats avant une nouvelle recherche.
 */
function clearResults() {
    $("#tbody-data-content").html('');
    $("#nombre-recherches").html('<img src="./assets/image/loading_action.gif" alt="">');
    $(".cout-valeur").html('<img src="./assets/image/loading_action.gif" alt="">');
    $("#sql_req_ach").val('');
    logStatus("En attente d'une nouvelle recherche...", 'info');
}

function init_tooltip() {
  // INIT TOOLTIP
  $("[data-tooltip='tooltip']").each(function (index, element) {
      element = $(element);
      let content = element.data("content");
      let side = element.data("position");
      let interactive = (element.hasClass('interactive_tooltip')) ? true : false;

      if (content) {
          content = content.trim();
          if (element.tooltipster) {
          element.tooltipster({
              content,
              side,
              contentAsHTML: true,
              theme: "hellopro-tooltip",
              animation: "grow",
              debug: false,
              interactive: interactive
          });
          }
      }
  });
}

function decodeEntities(array) {
  for (let i in array) {
    var decoded = $("<div/>").html(array[i]["text"]).text();
    array[i]["text"] = decoded;
  }
  return array;
}

function templateDropdown_selection(state) {
  if (!state.id) {
    return state.text;
  }

  var $state = $(
    '<div class="d-flex gp-8 align-items-center font-color-bleu font-weight-500"><span class="font-12 lh-20"></span></div>'
  );
  $state.find("span").text(state.text);

  return $state;
}

function templateResult_unique(elem, config = CONFIG_SELECT2) {
  return function (data) {
    return data;
  };
}

function templateResult_with_optgroup_select2(elem, config = CONFIG_SELECT2) {
  return function (data) {
    if (data.loading) {
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'><img style='height: 24px;' src='" +
          window.location.protocol +
          "//" +
          window.location.host +
          "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/assets/image/loading-ps.svg'>  " +
          data.text +
          "</span>"
      );
    }

    if (data.children) {
      let allSelected = true;
      $.each(data.children, function (index, option) {
        if (
          !$(elem)
            .find('option[value="' + option.id + '"]')
            .is(":selected")
        ) {
          allSelected = false;
          return false;
        }
      });

      data_param = "";
      if (data.param_data != "undefined") {
        $.each(data.param_data, function (index, option) {
          data_param += ` data-${index}="${option}" `;
        });
      }

      let checkbox =
        '<label class="bloc-ckeck opt-checkbox select-all' +
        (allSelected ? " checked" : " ") +
        '"><input type="checkbox" ' +
        (allSelected ? " checked" : " ") +
        '><span class="checkmark"><i class="bx bx-check"></i></span> Tous sélectionner</label>';
      let groupLabel = $(
        '<label class="d-flex justify-content-space-between group-info" ' +
          data_param +
          ' ><span class="group-titre">' +
          data.text +
          "</span>" +
          checkbox +
          "</label>"
      );

      groupLabel
        .find('.select-all > input[type="checkbox"]')
        .on("change", function () {
          let isChecked = $(this).prop("checked");
          $(this)
            .closest(".select2-results__group")
            .find('input[type="checkbox"]')
            .prop("checked", isChecked);
          $(this)
            .closest(".select2-results__group")
            .find(".opt-checkbox")
            .toggleClass("checked");

          $(this)
            .closest(".select2-results__group")
            .next(".select2-results__options")
            .find('input[type="checkbox"]')
            .prop("checked", isChecked);
          $(this)
            .closest(".select2-results__group")
            .next(".select2-results__options")
            .find(".opt-checkbox")
            .toggleClass("checked");

          if (isChecked) {
            $.each(
              $(this).closest(".select2-results__option").find(".checked"),
              (i, item) => {
                if (!$(item).hasClass("select-all")) {
                  assign_valeur_select2(
                    elem,
                    new Option(
                      $.trim($(item).text()),
                      $(item).data("id"),
                      true,
                      true
                    ),
                    data
                  );
                }
              }
            );
          } else {
            $.each(
              $(this).closest(".select2-results__option").find(".opt-checkbox"),
              (i, item) => {
                if (!$(item).hasClass("select-all")) {
                  remove_valeur_select2(elem, $(item).data("id"));
                }
              }
            );
          }
        });

      let allCheckbox = groupLabel.find('.select-all > input[type="checkbox"]');
      let childCheckboxes = groupLabel.find(
        '.opt-checkbox input[type="checkbox"]'
      );

      // Check/uncheck "Select All" based on child checkboxes
      childCheckboxes.on("change", function () {
        let isChecked = true;
        childCheckboxes.each(function () {
          if (!$(this).prop("checked")) {
            isChecked = false;
            return false; // Exit loop early
          }
        });
        allCheckbox.prop("checked", isChecked);
      });

      // Toggle all child checkboxes when "Select All" is changed
      allCheckbox.on("change", function () {
        let isChecked = $(this).prop("checked");
        childCheckboxes.prop("checked", isChecked);
      });

      return groupLabel;
    } else {
      // Render regular option
      let selected = $(elem)
        .find('option[value="' + data.id + '"]')
        .is(":selected");
      let checkbox = "";
      if (config.unique) {
        checkbox = $(
          '<label class="bloc-ckeck opt-checkbox' +
            (selected ? " checked" : " ") +
            "\" data-id='" +
            data.id +
            "' > " +
            data.text +
            "</label>"
        );
      } else {
        checkbox = $(
          '<label class="bloc-ckeck opt-checkbox' +
            (selected ? " checked" : " ") +
            "\" data-id='" +
            data.id +
            '\' ><input type="checkbox" ' +
            (selected ? " checked" : " ") +
            '><span class="checkmark"><i class="bx bx-check"></i></span> ' +
            data.text +
            "</label>"
        );
      }
      return checkbox;
    }
  };
}

function assign_valeur_select2(elem, option, data) {
  if (!$(elem).find(`option[value="${data.id}"]`).is(":selected")) {
    $(elem).append(option).trigger("change");
    $(elem).trigger({
      type: "select2:select",
      params: {
        data: data,
      },
    });
  }
}

function remove_valeur_select2(elem, id) {
  if ($(elem).find(`option[value="${id}"]`).is(":selected")) {
    $(elem).find(`option[value="${id}"]:selected`).remove();
    $(elem).trigger("change");
    $(elem).trigger({
      type: "select2:select",
    });
  }
}

function data_select2(data = {}) {
  return function (params) {
    let option = Object.assign({}, data);

    option.term = params.term;
    option.page = params.page || 1;
    return option;
  };
}

/**
 * @author Aina Sandratra <sandrianirinaharivelo@hellopro.fr>
 * @date   23-04-2024 16:22
 * @param {jQuery} elem     → élément à instancier
 * @param {string} url      → url de la requête ajax depuis la racine
 * @param {Object} config   → configuration supplémentaire pour Select2
 * @param {Object} options  → options minimum pour Select2
 */
function init_filter_select2(
  elem,
  url,
  config = Object.assign({}, CONFIG_SELECT2),
  options = Object.assign({}, OPTIONS_SELECT2)
) {
  if (config.with_ajax) {
    options["ajax"] = {
      url: window.location.protocol + "//" + window.location.host + url,
      type: "POST",
      dataType: "json",
      delay: 250,
      data: config.data(config.payload),
      transport: function (params, success, failure) {
        var $request = $.ajax(params);

        $request.then(success);
        $request.fail(failure);

        return $request;
      },
      processResults: function (data, params) {
        var page = params.page || 1;

        let resultats = {
          results: data.results || data.all,
        };

        if (config.pagination) {
          resultats.pagination = {
            more: page * config.limit <= data.total_count,
          };
        }
        return resultats;
      },
      cache: false,
    };

    if (config.with_templateResult) {
      options["templateResult"] = config.templateResult(elem, config);
    }
    options["templateSelection"] = config.templateSelection;
  }

  elem.select2(options);

  $(elem).on("select2:unselect", function (e) {
    if ($(this).attr("id") == "societe-naf") {
      $('.naf-item[data-code_naf="' + e.params.data.id + '"]').removeClass(
        "active"
      );
      $('.naf-item[data-code_naf="' + e.params.data.id + '"] > i')
        .removeClass("bxs-check-circle")
        .addClass("bxs-plus-circle cursor-pointer");
    }
    $(this)
      .find('option[value="' + e.params.data.id + '"]')
      .remove();
    $(this).trigger("change");
    $(this).trigger("select2:select");
  });

  $(elem).on("select2:select", function (e) {
    if (typeof $(this).data("item") !== "undefined") {
      let element = `.${$(this).data("item")}-container`;
      let block = `.${$(this).data("item")}-block`;
      if ($(this).val().length > 0) {
        if ($(block).hasClass("d-none")) {
          $(block).removeClass("d-none");
        }
        let action = $(element).data("action");
        let ids = $(this).val().join(",");
      } else {
        if (!$(block).hasClass("d-none")) {
          $(block).addClass("d-none");
        }
      }
      var all_hidden = true;
      $(".list-criteres > div").each(function () {
        // Check if the current div does not have the 'd-none' class
        if (!$(this).hasClass("d-none")) {
          all_hidden = false; // Set flag to false if any div is not hidden
          return false; // Exit the loop early since not all divs are hidden
        }
      });

      if (!all_hidden) {
        if (!$(".info-critere-vide").hasClass("d-none")) {
          $(".info-critere-vide").addClass("d-none");
        }
      } else {
        if ($(".info-critere-vide").hasClass("d-none")) {
          $(".info-critere-vide").removeClass("d-none");
        }
      }

      if ($(elem).parent().find(".badge-danger").length) {
        if ($(elem).val().join(",") == "") {
          if ($(elem).parent().find(".badge-danger").hasClass("d-none")) {
            $(elem).parent().find(".badge-danger").removeClass("d-none");
          }
        } else {
          if (!$(elem).parent().find(".badge-danger").hasClass("d-none")) {
            $(elem).parent().find(".badge-danger").addClass("d-none");
          }
        }
      }
    }
  });
}

function reset_select(el) {
  if (el.data("ajax") != true) {
    el.val(el.children().first().val()).change();
  } else {
    $.each(el.val(), (i, id) => {
      remove_valeur_select2(el, id);
      el.trigger("change");
    });
  }
}

function templateResult_with_optgroup_sans_selectall_select2(
  elem,
  config = CONFIG_SELECT2
) {
  return function (data) {
    if (data.loading) {
      return $(
        "<span class='d-flex align-items-center justify-content-start gp-8'><img style='height: 24px;' src='" +
          window.location.protocol +
          "//" +
          window.location.host +
          "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/assets/image/loading-ps.svg'>  " +
          data.text +
          "</span>"
      );
    }

    if (typeof data.children != "undefined") {
      $(".select2-results__group").each(function () {
        if (data.text == $(this).text()) {
          return (data.text = "");
        }
      });
    }
    return data.text;
  };
}

function init_champs(i, data) {
  let html = "",
    old_filter = "";
  let classes = "";
  switch (data.type) {
    case 0:
    case 4:
      if (typeof data.nb_input !== "undefined") {
        html += `<div class='d-flex align-items-center justify-content-center gp-8'>`;
        for (let j = 1; j <= data.nb_input; j++) {
          classes = j == data.nb_input ? " last-input d-none" : "";
          html += `<input type="${
            type_champ_filtre[data.type].type
          }" class="input-requettage input-${i}-${j} ${classes}" id="${i}-${j}" name="${i}-${j}"  placeholder="${
            data.title
          }" ></input>`;
        }
        html += `</div>`;
      } else {
        html += `<input type="${
          type_champ_filtre[data.type].type
        }" class="input-requettage input-${i}" id="${i}" name="${i}"  placeholder="${
          data.title
        }" ></input>`;
      }
      break;
    case 1:
    case 2:
      let multiple =
        type_champ_filtre[data.type].multiple == true
          ? 'multiple="multiple"'
          : "";
      let pagination =
        data.pagination == true ? `data-pagination="${data.pagination}"` : "";
      let payload =
        typeof data.payload !== "undefined" ? `data-payload="${data.payload}"` : "";
      let url =
        typeof data.ajax !== "undefined" ? `data-url="${data.ajax}"` : "";
      let ajax =
        typeof data.value === "undefined" ? `data-ajax="true"` : "";
      html += `<select class="${i} init-select2-filtre w-100" ${multiple} ${ajax} ${payload} ${url} ${pagination}>`;
      if (typeof data.value !== "undefined") {
        $.each(data.value, (key, item) => {
          html += `<option value="${key}">${item}</option>`;
        });
      }
      html += `</select>`;
      break;
    case 3:
      html += `<div class='d-flex align-items-center justify-content-center gp-8'>`;
      html += `<input type="text" class="input-requettage date-debut input-debut w-100" id="value_${i}_debut" name="value_${i}_debut"  placeholder="Date de début" autocomplete="off" ></input>`;
      html += `<input type="text" class="input-requettage date-fin input-fin d-none" id="value_${i}_fin" name="value_${i}_fin"  placeholder="Date de fin" autocomplete="off" ></input></div>`;
      break;
  }
  return {
    html: html,
    old_values: old_filter,
  };
}

function init_condition_champs(i, data) {
  let html = "",
    old_filter = "";
  if (data.length > 1) {
    html += `<select class="${i} init-filtre">`;
    $.each(data, (key, item) => {
      html += `<option value="${item}">${value_filtre_champs[item]}</option>`;
    });
    html += `</select>`;
    old_filter = `${data[0]}`;
  }
  return {
    html: html,
    old_values: old_filter,
  };
}
function init_filter_champs() {
  var list_champs = $(".list-champs");
  var content, supp_content, old_value, default_multi, value_multi;
  $.each(list_header, function (i, data) {
    if (typeof data.no_filter === "undefined") {
      let html = "";
      let init_champs_filter = init_champs(i, data);
      let init_condition_champs_filter = init_condition_champs(
        i,
        data.recherche
      );
      html += init_condition_champs_filter.html + init_champs_filter.html;
      if (html) {
        list_champs.append(`
                    <div id="${i}-container" class="filter-champs form-group type-${
          type_champ_filtre[data.type].type
        } ${default_multi}" data-type="${
          data.type
        }" data-champs="${i}" data-title="${data.title}" data-old-filter="${
          init_champs_filter.old_values +
          "|" +
          init_condition_champs_filter.old_values
        }">
                        <label class="bloc-check ">
                            <input type="checkbox" value="${i}" id="filter_${i}" class="check-champs">
                            <span class="checkmark">
                                <i class="bx bx-check"></i></span> ${data.title}
                        </label>
                        <div class="fliter-content">
                            ${html}
                        </div>
                    </div>
                `);
      }
    }
  });
}

function init_default_filter_value(default_filter) {
  var action_filtre = {
  };
  $.each(default_filter, function (champs, value) {
    if (champs && value) {
      let condition = value.split("|");
      $(`#${champs}-container`).find("select.init-filtre").val(condition[0]);
      let values = condition[1].split(";");
      $(`#${champs}-container`).data("old-filter", value);
      $(`#${champs}-container`).find(".check-champs").prop("checked", true);
      if (!$(`#${champs}-container`).find(".bloc-check").hasClass("checked")) {
        $(`#${champs}-container`).find(".bloc-check").addClass("checked");
      }
      $(`#${champs}-container`).find(".fliter-content").show();
      switch ($(`#${champs}-container`).data("type")) {
        case 0:
        case 4:
          $(`#${champs}-container`).find(".input-requettage").val(condition[1]);
          break;
        case 1:
        case 2:
          if (
            $(`#${champs}-container`)
              .find(".init-select2-filtre")
              .data("ajax") != "true"
          ) {
            $(`#${champs}-container`)
              .find("select:not(.init-filtre)")
              .val(values)
              .trigger("change", ["noGestion"]);
          } else {
            let url = $(`#${champs}-container`)
              .find(".init-select2-filtre")
              .data("url");
            if (url !== "undefined") {
              let action = action_filtre[champs];
              let ids = values.join(",");
              $.ajax({
                url:
                  window.location.protocol +
                  "//" +
                  window.location.hostname +
                  url,
                type: "POST",
                dataType: "JSON",
                data: {
                  action,
                  ids,
                },
                success: function (r) {
                  if (r.results) {
                    $.each(r.results, (i, data) => {
                      if (data.children) {
                        $.each(data.children, (_, val) => {
                          $(`#${champs}-container`)
                            .find(".init-select2-filtre")
                            .append(new Option(val.text, val.id, true, true));
                        });
                      } else {
                        $(`#${champs}-container`)
                          .find(".init-select2-filtre")
                          .append(new Option(data.text, data.id, true, true));
                      }
                    });
                  } else {
                    $.each(r, (i, val) => {
                      $(`#${champs}-container`)
                        .find(".init-select2-filtre")
                        .append(new Option(val, i, true, true));
                    });
                  }
                },
              });
            }
          }
          break;
        case 3:
          let dates = condition[1].split(";");
          $(`#${champs}-container`)
            .find("select.init-filtre")
            .trigger("change");
          $(`#${champs}-container`).find(".date-debut").val(dates[0]);
          if (dates[1]) {
            $(`#${champs}-container`).find(".date-fin").val(dates[1]);
          }
          break;
      }
    }
  });
}
function gestion_btn_send_filter(type_btn = "filtre") {
  var old_value, new_value, tab_value;
  var changed_filter = (is_filter_champs = false);
  $(".send-filter-container").removeClass("changed-filter not-sticky");

  var is_reset = type_btn == "reset" ? true : false;
  if (is_reset) {
    $(".check-champs:checked").prop("checked", false).trigger("change");
  } else if ($(".check-champs:checked").length) {
    changed_filter = true;
    $(".send-filter-container").addClass("changed-filter");
    return;
  }

  $("[data-old-filter]").each(function (i, e) {
    old_value = $(this).data("old-filter");
    if (is_reset) {
      let new_old_value = "";
      if ($(this).find(".init-filtre").length > 0) {
        new_old_value += $(this).find(".init-filtre").val() + "|";
      }
      new_old_value += $(this)
        .find(".input-requettage, select:not(.init-filtre)")
        .map((_, el) => $(el).val())
        .get()
        .filter((val) => val !== "")
        .join(";");
      switch ($(this).data("type")) {
        case 0:
        case 4:
          $.each($(this).find(".input-requettage"), (_, el) => $(el).val(""));
          break;
        case 1:
        case 2:
          reset_select($(this).find("select:not(.init-filtre)"));
          break;
        case 3:
          $(".date-debut, .date-fin").val("");
          break;
      }
      $(this)
        .find(".init-filtre")
        .val($(this).find(".init-filtre").children().first().val())
        .change();
      if (old_value != new_old_value) {
        $(this).data("old-filter", new_old_value);
        changed_filter = true;
        $(".send-filter-container").addClass("changed-filter");
        if (!is_reset) return false;
      }
    }
  });
}

function recup_filtre_visualisation(type_btn = "filtrer") {
  var new_url =
    host +
    "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/index.php";
  var filtre = {};
  var ordre = {};
  var arg_url = "";

  filtre = $.map($(".list-champs input[type='checkbox']:checked"), (item) => ({
    [$(item).val()]: {
      champs: $(item).val(),
      condition:
        $(item).closest(".filter-champs").find("select.init-filtre").val() ||
        "in",
      values: $(item)
        .closest(".filter-champs")
        .find(".input-requettage, select:not(.init-filtre)")
        .map((_, el) => $(el).val())
        .get()
        .filter((val) => val !== ""),
      old_filter: $(item).closest(".filter-champs").data("old_filter"),
      new_value: $(item)
        .closest(".filter-champs")
        .find(".input-requettage, select:not(.init-filtre)")
        .map((_, el) => $(el).val())
        .get()
        .filter((val) => val !== "")
        .join(";"),
    },
  })).reduce((acc, obj) => ({ ...acc, ...obj }), {});

  $.each(filtre, function (champs, { new_value, condition, values }) {
    new_value &&
      new_value !== ";" &&
      values.length > 0 &&
      (arg_url += `${
        arg_url.length == 0 ? "?" : "&"
      }${champs}=${condition}|${new_value}`);
  });

  if (type_btn != "reset") new_url += arg_url;

  var val_ordre;
  $(".table-container-recherche thead th[data-order]").each(function (i, e) {
    val_ordre = $(this).data("order");
    if (val_ordre) ordre[$(this).data("champs")] = val_ordre;
  });

  return {
    filtre: filtre,
    ordre: ordre,
    new_url: new_url,
  };
}

function update_selected_row_colors() {
  $(".check-box-recherche").each(function (index) {
    var isChecked = $(this).prop("checked");
    // Ajouter ou supprimer la classe "selected" en fonction de l'état de la case à cocher
    $(this).closest("tr").toggleClass("selected", isChecked);
    $(this)
      .parent()
      .css("background-color", isChecked ? "#F9FAFB" : "#ffffff");
  });
}

function gestion_selection_recherche() {
  //changement du bouton exporter
  if ($(".check-box-recherche:checked").length) {
    $("#exporter_recherche")
      .html(
        "<i class='bx bxs-download font-16 mr-4'></i> Exporter la sélection"
      )
      .data("selection", "select");
    if ($("#search_prospect option:selected").val()) {
      $(".header-search-prospect").addClass("d-none");
      $(".header-selected-prospect").removeClass("d-none");
    } else {
      $(".header-selected-prospect").addClass("d-none");
      $(".header-search-prospect").removeClass("d-none");
    }
  } else {
    $("#exporter_recherche")
      .html("<i class='bx bxs-download font-16 mr-4'></i> Exporter")
      .data("selection", "all");
    $(".header-selected-prospect").addClass("d-none");
    $(".header-search-prospect").removeClass("d-none");
  }
}

function init_dropdown_order_table() {
  var bx_menu, champs, th_title, asc, desc;
  var value_number = ["id_recherche_conversation_lp_ia"];
  $(".table-container-recherche thead th").each(function (i, e) {
    bx_menu = $(this).find(".bx-menu");
    if (bx_menu.length) {
      champs = $(this).data("champs");
      asc = "Asc";
      desc = "Desc";
      if ($.inArray(champs, value_number) !== -1) {
        asc = "0-9";
        desc = "9-0";
      }
      th_title = $(this).find(".table-th-title");
      th_title.attr("data-title", th_title.html().trim());
      bx_menu.addClass("dropdown-toggle").attr("data-toggle", "dropdown");
      $(this).attr("data-order", "")
        .append(`<ul class="dropdown-menu" aria-labelledby="${$(this).data(
        "id"
      )}">
                                    <li class="order-table-asc"><i class='bx bx-up-arrow-alt'></i> ${asc}</li>
                                    <li class="order-table-desc"><i class='bx bx-down-arrow-alt' ></i> ${desc}</li>
                                    <li class="order-table-none" style="display:none"><i class='bx bx-x'></i> Pas de tri</li>
                                </ul>`);
    }
  });
}

function refresh_hover_colonne() {
  $(
    ".modal-body #modal-content-gerer-colonne ul#sotable_list_thead .checkbox-div"
  ).hover(
    function () {
      $(this).find(".for-icone-move").replaceWith(`
                <div class="for-icone-move mr-24">
                    <i class="move-checkbox bx bx-sort-alt-2 bx-sm font-color-gris"></i>
                </div>`);
    },
    function () {
      $(this)
        .find(".for-icone-move")
        .replaceWith(`<div class="for-icone-move mr-40"></div>`);
    }
  );
}

function get_ordre_champs() {
  $.ajax({
    type: "POST",
    url:
      window.location.protocol +
      "//" +
      window.location.hostname +
      "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/ajax/ajax_filtre_recherche_chatgpt.php",
    data: { action: "get_ordre_champs" },
    success: function (res) {
      var array_ordre_colonne;
      if (!res) {
        array_ordre_colonne = ORDRE_COLONNE;
      } else {
        array_ordre_colonne = res.split(",");
      }

      if (array_ordre_colonne.length == 0) {
        array_ordre_colonne = ORDRE_COLONNE;
      }
      ORDRE_COLONNE = array_ordre_colonne;
    },
  });
}

function charger_ordre_colonne(ordre_colonne) {
  console.log(ordre_colonne);
  ordre_colonne.reverse();

  $(".table-container-recherche thead tr").each(function (i, e) {
    var this_tr = $(this);
    this_tr.find("th[data-champs]").removeClass("table-default-vue");
    //traitement ordre
    $.each(ordre_colonne, function (id, label) {
      this_tr
        .find("th[data-champs=" + label + "]")
        .addClass("table-default-vue");
      this_tr
        .find(" th:eq(1)")
        .after(this_tr.find("th[data-champs=" + label + "]"));
    });
  });

  $(".table-container-recherche tbody tr").each(function (i, e) {
    var this_tr = $(this);
    this_tr.find("td[data-champs]").removeClass("table-default-vue");
    //traitement ordre
    $.each(ordre_colonne, function (id, label) {
      this_tr
        .find("td[data-champs=" + label + "]")
        .addClass("table-default-vue");
      this_tr
        .find(" td:eq(1)")
        .after(this_tr.find("td[data-champs=" + label + "]"));
    });
  });
  ordre_colonne.reverse();

  update_fixed_scroll();
  checkOverflowMessage();
}

function checkOverflowMessage() {
  $(".recherche-message").each(function () {
    var recherche_message = $(this);
    var voir_plus_button = recherche_message.next(".voir-plus");

    if (recherche_message[0].scrollHeight > recherche_message.innerHeight()) {
      voir_plus_button.show();
    } else {
      voir_plus_button.hide();
    }
  });
}

function update_fixed_scroll() {
  $("#fixed-scrollbar")
    .show()
    .width($(".table-container-recherche").outerWidth(!0));
  $("#fixed-scrollbar")
    .find("div")
    .width($(".table-container-recherche table:eq(0)").get(0).scrollWidth);
}

function reset_trie() {
  $("th[data-order]").each(function (i, e) {
    var order = $(this).data("order");
    if (order != "") {
      $(this).data("order", "");
      var th_title = $(this).find(".table-th-title");
      th_title.html(th_title.data("title"));
      $(this)
        .find(".dropdown-menu li.order-table-none")
        .hide()
        .siblings()
        .show();
    }
  });
}

var AJAX_CHARGER_rechercheS;

$.fn.isInViewport = function () {
  var elementTop = $(this).offset().top;
  var elementBottom = elementTop + $(this).outerHeight();

  var viewportTop = $(window).scrollTop();
  var viewportBottom = viewportTop + $(window).height();

  return (
    elementBottom > viewportTop &&
    elementTop < viewportBottom - $(this).height()
  );
};

$(function () {
  get_ordre_champs();
  init_dropdown_order_table();
  init_filter_champs();
  // $(".date-debut").datepicker({ language: "fr" });
  // $(".date-fin").datepicker({ language: "fr" });
  init_default_filter_value(default_filter);

   $("body").on("click", "#send_filter", function () {
      startWebSocketSearch();
  });

  $("body").on("click", ".no-filter", function () {
    $(this).addClass("d-none");
    $(".list-filter").removeClass("d-none");
    update_fixed_scroll();
  });

  $("body").on("click", ".hide-filter", function () {
    $(this).parent().addClass("d-none");
    $(".no-filter").removeClass("d-none");
    update_fixed_scroll();
  });

  $("body").on("change", ".check-champs", function () {
    var content = $(this).closest(".filter-champs").find(".fliter-content");
    gestion_btn_send_filter();
    if ($(this).is(":checked")) {
      content.show(300);
    } else {
      content.hide(300);
    }
  });

  //initialisation du order de la table
  $("body").on("click", "li.order-table-asc", function () {
    reset_trie();
    $(this).hide(200).siblings().show(200);
    var parent_th = $(this).closest("th");
    var th_title = parent_th.find(".table-th-title");
    parent_th.data("order", "asc");
    th_title.html(th_title.data("title") + "*");
    $("#current_page").val(1);
    charger_donnees_recherche();
  });
  $("body").on("click", "li.order-table-desc", function () {
    reset_trie();
    $(this).hide(200).siblings().show(200);
    var parent_th = $(this).closest("th");
    var th_title = parent_th.find(".table-th-title");
    parent_th.data("order", "desc");
    th_title.html(th_title.data("title") + "*");
    $("#current_page").val(1);
    charger_donnees_recherche();
  });
  $("body").on("click", "li.order-table-none", function () {
    $(this).hide(200).siblings().show(200);
    var parent_th = $(this).closest("th");
    var th_title = parent_th.find(".table-th-title");
    parent_th.data("order", "");
    th_title.html(th_title.data("title"));
    $("#current_page").val(1);
    charger_donnees_recherche();
  });
  $("body").on(
    "click",
    '.dropdown-toggle[data-toggle="dropdown"]',
    function () {
      var left = $(this).offset().left;
      $(this).parent().find(".dropdown-menu").css("left", left);
    }
  );
  $("body").on("change", "#nb-recherche-choice", function () {
    $("#current_page").val(1);
    charger_donnees_recherche();
  });

  $(".date-debut")
    .closest(".fliter-content")
    .find(".init-filtre")
    .on("change", function (e) {
      var $filterContent = $(this).closest(".fliter-content");

      if ($(this).val() == "entre") {
        if ($filterContent.find(".date-fin").hasClass("d-none")) {
          $filterContent.find(".date-fin").removeClass("d-none");
          $filterContent.find(".date-debut").removeClass("w-100");
        }
        if ($filterContent.find(".date-debut").hasClass("w-100")) {
          $filterContent.find(".date-debut").removeClass("w-100");
        }
      } else {
        if (!$filterContent.find(".date-fin").hasClass("d-none")) {
          $filterContent.find(".date-fin").addClass("d-none");
          $filterContent.find(".date-fin").val("");
        }
        if (!$filterContent.find(".date-debut").hasClass("w-100")) {
          $filterContent.find(".date-debut").addClass("w-100");
        }
      }
    });

  $(".init-filtre").on("change", function (e) {
    if (
      $.inArray($.trim($(this).val()), ["est_vide", "n_est_pas_vide"]) === -1
    ) {
      $.each(
        $(this)
          .closest(".filter-champs")
          .find(".input-requettage,select:not(.init-filtre)"),
        (_, el) => {
          if (!$(el).hasClass("date-debut") && !$(el).hasClass("date-fin")) {
            if (
              $.inArray($.trim($(this).val()), ["entre", "n_est_pas_entre"]) !==
              -1
            ) {
              if ($(el).hasClass("last-input")) {
                if ($(el).hasClass("d-none")) {
                  $(el).removeClass("d-none");
                }
              } else {
                $(el).removeClass("d-none");
              }
            } else {
              if ($(el).hasClass("last-input")) {
                if (!$(el).hasClass("d-none")) {
                  $(el).hasClass("input-requettage")
                    ? $(el).val("")
                    : reset_select($(el));
                  $(el).addClass("d-none");
                }
              } else {
                $(el).removeClass("d-none");
              }
            }
          }
        }
      );
    } else {
      $.each(
        $(this)
          .closest(".filter-champs")
          .find(".input-requettage,select:not(.init-filtre)"),
        (_, el) => {
          if (!$(el).hasClass("date-debut") && !$(el).hasClass("date-fin")) {
            if (!$(el).hasClass("d-none")) {
              $(el).hasClass("input-requettage")
                ? $(el).val("")
                : reset_select($(el));
              $(el).addClass("d-none");
            }
          }
        }
      );
    }
  });

  get_ordre_champs();
  // charger_donnees_recherche(default_filter);
  //initialisation des filtres dans url
  //initialisation d'id prospect si renseigné par defaut

  //initialisation gestion bouton send filter
  $("body").on(
    "change",
    "#date_debut , #date_fin , .filter-champs select.type-requettage ",
    function (event, extraParam) {
      if (!(extraParam && extraParam == "noGestion")) {
        gestion_btn_send_filter();
      }
    }
  );
  $("body").on(
    "keyup",
    "#name_recherche , .filter-champs input.input-requettage",
    function (event, extraParam) {
      if (!(extraParam && extraParam == "noGestion")) {
        gestion_btn_send_filter();
      }
    }
  );
  var observer_send_filter = new IntersectionObserver(function (
    entries,
    observer
  ) {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        $(".send-filter-container.changed-filter").addClass("not-sticky");
      } else {
        $(".send-filter-container.changed-filter").removeClass("not-sticky");
      }
    });
  });

  var send_filter_observer = document.querySelector("#send-filter-observer");
  observer_send_filter.observe(send_filter_observer);

  $("body").on("keyup", "#search_champs", function (event) {
    var filtre = $(this).val().toLowerCase();
    var filtre_2 = filtre.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    var title, title_2;
    if (filtre) {
      $(".filter-champs").each(function (i, e) {
        title = $(this).data("title").toLowerCase();
        title_2 = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (title.indexOf(filtre) !== -1 || title_2.indexOf(filtre_2) !== -1) {
          $(this).show();
        } else {
          $(this).hide();
        }
      });
    } else {
      $(".filter-champs").show();
    }
  });
  $("body").on("click", ".search-champs-container .bx", function () {
    $("#search_champs").val("");
    $(".filter-champs").show();
  });

  $("body").on("click", "#send_filter", function () {
    startWebSocketSearch();
  });

  $("body").on("click", "#reset_filter", function () {
    gestion_btn_send_filter("reset");
    clearResults();
    logStatus("Filtres réinitialisés. Prêt pour une nouvelle recherche.", 'info');
  });

  var top_lr = $(".table-container-recherche").offset().top;
  $(".list-filter").css("min-height", "calc( 100vh - " + top_lr + "px )");

  top_lr = $(".lefter-righter-list").offset().top;
  $(".lefter-righter-list").css(
    "min-height",
    "calc( 100vh - " + top_lr + "px )"
  );

  /*TABLEAU LIST recherche*/
  $("body")
    .on("mouseenter", ".righter-list-head tbody tr", function () {
      // Survol de la ligne du tableau
      $(this).find(".recherche-actions").css("background-color", "#F9FAFB");
      $(this)
        .find(".recherche-actions .bx.bx-plus.prospect-selected")
        .css("display", "inline-block");
    })
    .on("mouseleave", ".righter-list-head tbody tr", function () {
      // Quitter la ligne du tableau
      $(this).find(".recherche-actions").css("background-color", "#ffffff");
      $(this).find(".recherche-actions .bx.bx-plus").css("display", "none");
    });

  var update_selected_count = function () {
    // Mettre à jour le total des éléments sélectionnés
    var selected_count = $(".check-box-recherche:checked").length;

    // console.log(selected_count);
    $("#nombre-recherches").hide();
    if (selected_count == 1)
      $("#nb-selected-recherche").text(
        selected_count + " recherche sélectionné"
      );
    if (selected_count > 1)
      $("#nb-selected-recherche").text(
        selected_count + " recherches sélectionnés"
      );
    $("#selected-recherches").css("display", "inline-block");
    if (selected_count == 0) {
      $("#nombre-recherches").show();
      $("#selected-recherches").css("display", "none");
    }
  };

  $("body").on("change", "#select-all-checkbox", function () {
    // Mettre à jour toutes les cases à cocher dans le tableau
    $(".check-box-recherche").prop("checked", $(this).prop("checked"));
    update_selected_row_colors();
    update_selected_count();

    gestion_selection_recherche();
  });

  // Écouter l'événement de changement sur les cases à cocher du tbody
  $("body").on("change", ".check-box-recherche", function () {
    // Mettre à jour la case à cocher du thead en conséquence
    $("#select-all-checkbox").prop(
      "checked",
      $(".check-box-recherche:checked").length ===
        $(".check-box-recherche").length
    );
    update_selected_row_colors();
    update_selected_count();

    gestion_selection_recherche();
  });

  $("body").on("click", "#clear-selected-recherche", function () {
    $("#select-all-checkbox").prop("checked", false);
    $(".check-box-recherche").prop("checked", false);
    // Enlever la classe 'selected' des lignes
    $(".righter-list-head tbody tr.selected").removeClass("selected");
    // Mettre à jour le total des éléments sélectionnés
    update_selected_count();

    gestion_selection_recherche();
  });

  $("body").on("click", ".gerer-colonne-recherche", function () {
    var text_with_class = {};
    var text_without_class = {};
    $(".table-container-recherche thead th").each(function (i, e) {
      if (i == 0 || i === $(".table-container-recherche thead th").length - 1)
        return;
      var avec_class_vue = $(this)
        .contents()
        .filter(function () {
          return this.nodeType === 3;
        })
        .text()
        .trim();
      if (!avec_class_vue) {
        avec_class_vue = $(this).contents(".table-th-title").data("title");
      }

      var data_champs = $(this).data("champs");

      if ($(this).hasClass("table-default-vue")) {
        // Ajoute le texte au tableau pour les th avec la classe 'table-default-vue'
        text_with_class[data_champs] = avec_class_vue;
      } else {
        // Ajoute le texte au tableau pour les th sans la classe 'table-default-vue'
        text_without_class[data_champs] = avec_class_vue;
      }
    });
    var html_text_with_class = ``;
    $.each(text_with_class, function (data_champs, label) {
      html_text_with_class =
        html_text_with_class +
        `<li class="checkbox-div" data-champs="` +
        data_champs +
        `">
                <div class="for-icone-move mr-40"></div>                        
                <div>
                    <input type="checkbox" id="fields_` +
        data_champs +
        `"  class="filter-colonne-champs" checked>
                    <label class="font-14 ml-8 font-weight-400 font-color-gris" for="fields_` +
        data_champs +
        `">` +
        label +
        `</label>
                </div>            
            </li> `;
    });

    var html_text_without_class = ``;
    $.each(text_without_class, function (data_champs, label) {
      html_text_without_class =
        html_text_without_class +
        `<li class="checkbox-div" data-champs="` +
        data_champs +
        `">
                <div class="for-icone-move mr-40"></div>     
                <div>
                    <input type="checkbox" id="fields_` +
        data_champs +
        `" class="filter-colonne-champs">
                    <label class="font-14 ml-8 font-weight-400 font-color-gris" for="fields_` +
        data_champs +
        `">` +
        label +
        `</label> 
                </div>              
            </li>`;
    });

    var HTML_modal_content =
      "<ul id='sotable_list_thead'>" +
      html_text_with_class +
      "</ul><ul id='other_list_thead'>" +
      html_text_without_class +
      "</ul>";

    $("#loading-colonne-recherche").remove();
    $("#modal-content-gerer-colonne").html(HTML_modal_content);
    $("#sotable_list_thead").sortable();

    refresh_hover_colonne();
  });

  $("body").on("keyup", "#filtrer_colonne", function (event) {
    var filtre = $(this).val().toLowerCase();
    var filtre_2 = filtre.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    var title, title_2;
    if (filtre) {
      $(".filter-colonne-champs").each(function (i, e) {
        var labelText = $(this).next("label").text().toLowerCase();
        title = labelText;
        title_2 = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (title.indexOf(filtre) !== -1 || title_2.indexOf(filtre_2) !== -1) {
          $(this).closest("li").show();
        } else {
          $(this).closest("li").hide();
        }
      });
    } else {
      $(".filter-colonne-champs").closest("li").show();
    }
  });

  $("body").on("change", ".checkbox-div input[type=checkbox]", function () {
    var parent = $(this).closest(".checkbox-div");
    if ($(this).is(":checked")) {
      $("#sotable_list_thead").append(parent);
    } else {
      $("#other_list_thead").prepend(parent);
    }
    refresh_hover_colonne();
  });

  $("body").on("click", "#enregistrer_order_colonne", function () {
    $("#gerer-colonne-modal").modal("hide");

    var ordre_affiche = [];
    $("#sotable_list_thead li").each(function (i, e) {
      ordre_affiche.push($(this).data("champs"));
    });

    ORDRE_COLONNE = ordre_affiche;
    charger_ordre_colonne(ordre_affiche);

    $.ajax({
      type: "POST",
      url:
        window.location.protocol +
        "//" +
        window.location.hostname +
        "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/ajax/ajax_filtre_recherche_chatgpt.php",
      data: { action: "insert_ordre_colonne", ordre_to_base: ordre_affiche },
      success: function (res) {
        //    console.log(res);
      },
    });
  });

  /**voir les détails du critères */
  $("body").on("click", ".voir_critere_recherche", function () {
    $("#modalDetails").text("Critères de la demande");
    $("#loading-detail-content").show();
    $("#modal-detail-content").hide();

    var id_recherche = $(this).attr("id");
    $.ajax({
      type: "POST",
      url:
        window.location.protocol +
        "//" +
        window.location.hostname +
        "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/ajax/ajax_filtre_recherche_chatgpt.php",
      data: { action: "afficher_critere", id_recherche: id_recherche },
      success: function (res) {
        $("#loading-detail-content").hide();
        $("#modal-detail-content").html(res);
        $("#modal-detail-content").show();
      },
    });
  });

  /**voir les détails du message recherche */
  $("body").on("click", ".message", function () {
    $("#modalDetails").text("Message");
    $("#loading-detail-content").show();
    var contenu_div = $(this).prev("div").html();
    $("#loading-detail-content").hide();
    $("#modal-detail-content").html(contenu_div);
  });

  /**voir les détails du message qualifiquation */
  $("body").on("click", ".message_qualification", function () {
    $("#modalDetails").text("Message qualification");
    $("#loading-detail-content").show();
    var contenu_div = $(this).prev("div").html();
    $("#loading-detail-content").hide();
    $("#modal-detail-content").html(contenu_div);
  });
  /* FIN TABLEAU LIST recherche*/

  //extraction des recherches
  $("body").on("click", "#exporter_recherche", function () {
    var _this = $(this);
    var selection = _this.data("selection");
    var tab_filtre = recup_filtre_visualisation();
    var filtre = tab_filtre["filtre"];
    var ordre = tab_filtre["ordre"];
    var new_url = tab_filtre["new_url"];
    var list_id = [];
    var content = _this.html();
    if (selection == "select") {
      $(".check-box-recherche:checked").each(function (i, e) {
        list_id.push($(e).closest("tr").data("id"));
      });
    }
    var nb = $("#nombre-recherches").text();
    var list_champ = ORDRE_COLONNE;
    if ($("#sotable_list_thead > li").length) {
      list_champ = [];
      $("#sotable_list_thead > li").each(function (i, el) {
        list_champ.push($(e).data("champs"));
      });
    }

    $.ajax({
      type: "POST",
      url:
        host +
        "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/ajax/ajax_filtre_recherche_chatgpt.php",
      data: {
        action: "export_recherche",
        selection: selection,
        filtre: filtre,
        list_champ,
        list_id: list_id,
        ordre,
        new_url,
      },
      xhrFields: {
        responseType: "blob",
      },
      beforeSend: function () {
        $("#nombre-recherches").html(
          '<img src="' +
            host +
            '/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/assets/image/loading_action.gif" alt=”” >'
        );
        _this.html(
          '<i class="bx bx-loader-circle bx-spin bx-rotate-180 mr-4 font-14" style="position: relative;top: 2px;""></i> Exportation en cours'
        );
      },
      success: function (response, status, xhr) {
        _this.html(content);
        $("#nombre-recherches").text(nb);
        $("#zone-extraction").html(response);

        var disposition = xhr.getResponseHeader("Content-Disposition");
        var filenameFromServer = "";
        if (disposition && disposition.indexOf("attachment") !== -1) {
          var matches = /"([^"]+)"/.exec(disposition);
          if (matches && matches[1]) {
            filenameFromServer = matches[1];
          }
        }

        var finalFilename = filenameFromServer || "export-recherche.csv";
        var downloadLink = $("<a></a>");
        var url = window.URL.createObjectURL(response);
        downloadLink.attr("href", url);
        downloadLink.attr("download", finalFilename);

        $("body").append(downloadLink);
        downloadLink[0].click();
        window.URL.revokeObjectURL(url);
        downloadLink.remove();
      },
    });
  });

  $("#fixed-scrollbar").scroll(function () {
    $(".table-container-recherche").scrollLeft($(this).scrollLeft());
  });

  $(".table-container-recherche").scroll(function () {
    var i_scroll = $(this).scrollLeft();
    if (i_scroll >= 10) {
      $(this).find("th:nth-child(3)").addClass("has-shadow-right");
      $(this).find("td:nth-child(3)").addClass("has-shadow-right");
    } else {
      $(this).find("th.has-shadow-right").removeClass("has-shadow-right");
      $(this).find("td.has-shadow-right").removeClass("has-shadow-right");
    }
  });

  $(window).on("resize", function () {
    update_fixed_scroll();
    checkOverflowMessage();
  });

  $.each($(".init-select2-filtre"), function (i, item) {
    if (typeof $(item).data("ajax") !== "undefined" && $(item).data("ajax") == "true") {
      var config = Object.assign({}, CONFIG_SELECT2);
      config.templateResult =
        templateResult_with_optgroup_sans_selectall_select2;
      config.with_ajax = $(item).data("ajax") == true;
      var option = Object.assign({}, OPTIONS_SELECT2);
      option.allowClear = false;
      if (typeof $(item).data("payload") != "undefined") {
        config.payload = $(item).data("payload");
      }
      if (typeof $(item).data("pagination") != "undefined") {
        config.pagination = $(item).data("pagination") == true;
      }
      option.placeholder =
        "Rechercher " +
        $(item)
          .closest(".form-group")
          .find("span")
          .contents()
          .filter(function () {
            return this.nodeType === 3;
          })
          .text()
          .replace("*", "")
          .trim()
          .toLowerCase();
      option.minimumInputLength = 2;
      if ($(item).data("url") !== "undefined") {
        init_filter_select2($(item), $(item).data("url"), config, option);
      }
    } else if ($(item).hasClass("id_process_hec") || $(item).hasClass("type_ia_hec")) {
      var option = Object.assign({}, OPTIONS_SELECT2);
      $(item).select2(option);
    }
  });

  $(document).on("click", ".get-info-recherche", function (e) {
    e.preventDefault();
    $.ajax({
      type: "POST",
      url:
        window.location.protocol +
        "//" +
        window.location.hostname +
        "/admin/repertoire_test/moulinettes_interne/recherche_chatgpt/ajax/ajax_filtre_recherche_chatgpt.php",
      dataType: "JSON",
      data: {
        action: "get_info_recherche",
        id: $(this).data("id"),
      },
      beforeSend: function () {
        $(".info-reponse").html(`
                    <div id="loading-detail-content" class="loading-content">
                        <img style="height: 24px;" src="${host}/admin/repertoire_test/moulinettes_interne/landing_page_chagpt/assets/image/loading-ps.svg">
                    </div>
                `);
      },
      success: function (res) {
        $(".info-reponse").html(`${typeof res.content !== "undefined" ? res.content : ""}`);
      },
    });
  });
});
