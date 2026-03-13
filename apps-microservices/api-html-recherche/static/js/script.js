$(function () {
  // --- DÉBUT DE LA SECTION FUSIONNÉE ---

  // Variable globale pour la connexion WebSocket
  let socket = null;
  let websocket = null;

  // --- FIN DE LA SECTION FUSIONNÉE ---

  // NOUVEAU: Variable globale pour la connexion WebSocket de TRANSCRIPTION
  let transcriptionSocket = null;

  // Global state
  const state = {
    searchQuery: "",
    topK: 30,
    temperature: 0.4,
    // NOUVEAU: Ajout des champs pour correspondre au schéma
    templatePrompt: $("#llmPrompt").val(),
    useReranker: true,
    rerankerModel: "BAAI/bge-reranker-v2-m3",
    // selectedModel: "google/gemini-flash-1.5", // Mis à jour avec la nouvelle valeur par défaut
    selectedModel: "gemini-3.1-pro-preview", // Mis à jour avec la nouvelle valeur par défaut
    selectedThinking: "high",
    selectedProvider: "gemini",
    isFilterOpen: true,
    isLlmEnabled: false,
    isSidebarOpen: false,
    isResultSuccess: false,
    selectedSources: {
      produits: true,
      devis: false,
      mcf: false,
      siteweb: false,
      pj: false,
      prix: false,
    },
    selectedCategories: [],
    selectedIdsProduits: [],
    selectedFournisseurs: [],
    selectedNomFournisseurs: [],
    // NOUVEAU: Utilisation de .val() de select2 qui retourne un tableau
    selectedEtat: [],
    selectedAffichage: [],
    isSearching: false,
    searchResults: [],
    llmResponse: "",
    searchMetrics: { totalResults: 0, searchTime: 0, sourcesUsed: [] },
    expandedSections: { sources: true, categories: false, insights: true },
    copiedContent: "",
    selectedCategoriesRubrique: {},
    typeRecherche: 1,
    hybrid: false,
    reranking: true
  };

  // DOM elements
  const elements = {
    searchInput: $("#searchInput"),
    searchBtn: $("#searchBtn"),
    searchBtnDesktop: $("#searchBtnDesktop"),
    searchBtnText: $("#searchBtnText"),
    llmToggle: $("#llmToggle"),
    llmToggleText: $("#llmToggleText"),
    filterToggle: $("#filterToggle"),
    resultsToggle: $("#resultsToggle"),
    filterSidebar: $("#filterSidebar"),
    resultsSidebar: $("#resultsSidebar"),
    emptyState: $("#emptyState"),
    noResults: $("#noResults"),
    llmConfig: $("#llmConfig"),
    topKSlider: $("#topKSlider"),
    topKValue: $("#topKValue"),
    temperatureSlider: $("#temperatureSlider"),
    // NOUVEAU: Ajout des nouveaux éléments DOM
    templatePrompt: $("#llmPrompt"),
    useReranker: $("#useReranker"),
    rerankerModel: $("#rerankerModel"),
    llmModel: $("#llmModel"),
    etatFilter: $("#etatFilter"),
    affichageFilter: $("#affichageFilter"),
    mobileFilterBtn: $("#mobileFilterBtn"),
    mobileFilterSheet: $("#mobileFilterSheet"),
    mobileFilterContent: $("#mobileFilterContent"),
    closeMobileFilter: $("#closeMobileFilter"),
    mobileFilterOverlay: $("#mobileFilterOverlay"),
    searchResultsContainer: $("#searchResultsContainer"),
    searchResultsList: $("#searchResultsList"),
    llmResponseContainer: $("#llmResponseContainer"),
    llmResponseText: $("#llmResponseText"),
    llmEmptyState: $("#llmEmptyState"),
    llmAnalyzeState: $("#llmAnalyzeState"),
    searchMetrics: $("#searchMetrics"),
    searchingState: $("#searchingState"),
    metricsContent: $("#metricsContent"),
    mainContentWrapper: $("#mainContentWrapper"),
    categorieFilter: $("#categorieDropdown"),
    fournisseurFilter: $("#fournisseurDropdown"),
    btnTranscription: $("#btn-transcription"),
    typeRecherche: $("input[name='type-recherche']"),
    idsProduit: $(`#ids_produit`),
    avecPrix: $(`#avecPrix`),
    rechercheHybride: $(`#rechercheHybride`)
  };

  // (Le reste de vos fonctions d'initialisation comme CONFIG_SELECT2, OPTIONS_SELECT2, etc. reste ici)
  // ...
  // ... (Toutes les fonctions de `script.js` de `initializeFormState` à `renderSkeletons` sont conservées ici sans modification)
  // ...

  var CONFIG_SELECT2 = {
    groupSelected: false,
    with_ajax: true,
    action: "",
    pagination: false,
    limit: 20,
    data: data_select2, // Assurez-vous que cette variable est définie si vous l'utilisez
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
  
  var OPTIONS_SELECT2_SIMPLE = {
      width: "100%",
      closeOnSelect: true,
      dropdownCssClass: "custom-select2-filter",
      dropdownAutoWidth: true,
      allowClear: false,        // Pas de croix de suppression
      placeholder: "",           // Pas de placeholder
      minimumResultsForSearch: Infinity,  // Désactive le champ de recherche
      language: {
        lang: "fr",
        noResults: function () {
          return "Aucun résultat trouvé";
        }
      }
  };

  function GetURLParameter(sParam) {
    var sPageURL = window.location.search.substring(1);
    var sURLVariables = sPageURL.split('&');
    for (var i = 0; i < sURLVariables.length; i++) {
      var sParameterName = sURLVariables[i].split('=');
      if (sParameterName[0] == sParam) {
        return sParameterName[1];
      }
    }
  }

  function initializeFormState() {
    // Boucle sur les sources définies dans l'état initial
    for (const source in state.selectedSources) {
      const isChecked = state.selectedSources[source];
      // Correction: le nom des sources dans l'UI peut différer (ex: devis vs devis_poc)
      // Il faudra assurer la correspondance ou renommer les IDs des checkbox
      const $checkbox = $(`#${source.replace('_poc', '')}`); // tentative de correspondance
      const $subfilters = $(`#${source.replace('_poc', '')}Subfilters`);

      if (isChecked) {
        // Coche la case correspondante
        $checkbox.prop("checked", true);
        // Affiche directement les sous-filtres (sans animation)
        $subfilters.show();
      } else {
        // S'assure que les autres sous-filtres sont bien masqués
        $subfilters.hide();
      }
    }
  }

  function init_tooltip() {
    // INIT TOOLTIP
    $("[data-tooltip='tooltip']").each(function (index, element) {
      element = $(element);
      let content = element.data("content");
      let side = element.data("position");
      let interactive = element.hasClass("interactive_tooltip") ? true : false;

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
            interactive: interactive,
          });
        }
      }
    });
  }

  function generate_error_message(message) {
    if (!message) {
      message = "Une erreur a été rencontrée. Veuillez réessayer s'il vous plaît !";
    }

    return `
        <div class="flex items-center gap-4 text-xs">
            <i data-lucide="circle-x" class="h-4 w-4"></i>
            <span class="font-weight-700 font-14">${message}</span>
        </div>
    `;
  }

  function generate_succes_message(message) {
    if (!message) {
      message = "Action effectué avec succès";
    }

    return `
        <div class="flex items-center gap-4 text-xs">
            <i data-lucide="circle-check" class="h-4 w-4"></i>
            <span class="font-weight-700 font-14">${message}</span>
        </div>
    `;
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
   * Réinitialise les zones de résultats avant une nouvelle recherche.
   */
  function clearResults() {
    $("#tbody-data-content").html("");
    $("#nombre-recherches").html(
      '<img src="./assets/image/loading_action.gif" alt="">'
    );
    $(".cout-valeur").html(
      '<img src="./assets/image/loading_action.gif" alt="">'
    );
    $("#sql_req_ach").val("");
    // Cette fonction n'est plus utilisée pour le log, on utilisera console.log ou un logger dédié
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

      var param_children = "";
      if (typeof data.children != "undefined") {
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

        var data_param = "";
        if (typeof data.param_data != "undefined") {
          $.each(data.param_data, function (index, option) {
            if (Array.isArray(option)) option = option.join(option);
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
          '<label class="group-info flex gap-4 group-info" ' +
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
                $(this)
                  .closest(".select2-results__option")
                  .find(".opt-checkbox"),
                (i, item) => {
                  if (!$(item).hasClass("select-all")) {
                    remove_valeur_select2(elem, $(item).data("id"));
                  }
                }
              );
            }
          });

        let allCheckbox = groupLabel.find(
          '.select-all > input[type="checkbox"]'
        );
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
        var data_param = "";
        if (typeof data.param_data != "undefined") {
          $.each(data.param_data, function (index, option) {
            if (Array.isArray(option)) option = option.join(",");
            data_param += ` data-${index}="${option}" `;
          });
        }
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
          checkbox = $(`
          <label class="bloc-ckeck opt-checkbox' ${selected ? " checked" : " "} ${data_param}>
            <input type="checkbox" ${selected ? " checked" : " "}><span class="checkmark"><i class="bx bx-check"></i></span>${data.text}
          </label>
          `)
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

  function init_filter_select2(
    elem,
    url,
    config = Object.assign({}, CONFIG_SELECT2),
    options = Object.assign({}, OPTIONS_SELECT2)
  ) {
    if (config.with_ajax) {
      options["ajax"] = {
        url: url,
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

          var processedData = $.map(data.results, function (group) {
            if (group.children) {
              group.children = $.map(group.children, function (child) {
                // On retourne l'objet enfant tel quel. Select2 détectera la clé 'ids'
                // et créera automatiquement un attribut data-ids.
                return child;
              });
            }
            return group;
          });

          let resultats = {
            // results: data.results || data.all,
            results: processedData,
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
      if (typeof e.params != "undefined" && typeof e.params.data != "undefined" && typeof e.params.data.param_data != "undefined" && typeof e.params.data.param_data.ids != "undefined") {
        delete state.selectedCategoriesRubrique[e.params.data.id];
      }
      $(this)
        .find('option[value="' + e.params.data.id + '"]')
        .remove();
      $(this).trigger("change");
      $(this).trigger("select2:select");
    });

    $(elem).on("select2:select", function (e) {
      if (typeof e.params != "undefined" && typeof e.params.data != "undefined" && typeof e.params.data.param_data != "undefined" && typeof e.params.data.param_data.ids != "undefined") {
        state.selectedCategoriesRubrique[e.params.data.id] = e.params.data.param_data.ids;
      }
      console.log(state.selectedCategoriesRubrique)
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
        return data.text;
      }
      var $result = $("<span></span>");
      $result.text(data.text);
      if (typeof data.ids != "undefined") {
        $result.data("ids", data.ids.join(","));
      }
      return $result;
    };
  }

  function initializeSelect2() {
    // Parcourt tous les éléments qui doivent être initialisés avec Select2
    $(".init-select2-filtre").each(function (i, item) {
      const $item = $(item);
      const isAjax = $item.data("ajax") === true || $item.data("ajax") === "true";
      const url = $item.data("url");

      // Cas 1: Le Select2 doit charger ses données via AJAX
      if (isAjax && url) {
        // On crée une copie de la configuration globale
        var config = Object.assign({}, CONFIG_SELECT2);
        // On crée une copie des options globales
        var options = Object.assign({}, OPTIONS_SELECT2);

        // --- DEBUT DES CORRECTIONS ---

        // 1. LA CORRECTION CLÉ : On assigne la fonction `data_select2` à notre objet config.
        //    `init_filter_select2` pourra maintenant l'appeler via `config.data(...)`.
        config.data = data_select2;

        // 2. On récupère le payload (ex: "recup_categorie") depuis l'attribut data.
        const payloadData = $item.data("payload");

        // 3. On formate le payload en objet, car la fonction `data_select2` attend un objet.
        //    La requête AJAX enverra alors { action: "recup_categorie", term: "..." }
        config.payload = payloadData ? { action: payloadData } : {};

        // --- FIN DES CORRECTIONS ---

        // Personnalisation de la configuration et des options pour AJAX
        // config.templateResult = templateResult_with_optgroup_sans_selectall_select2;
        config.pagination = $item.data("pagination") === true;

        options.allowClear = true; // Permet de vider la sélection
        options.placeholder = "Rechercher...";
        options.minimumInputLength = 2;

        // On appelle init_filter_select2, qui n'a pas été modifiée, avec une configuration complète.
        init_filter_select2($item, url, config, options);

      } else {
        // Cas 2: Le Select2 a des options statiques dans le HTML (logique inchangée)
        var options = Object.assign({}, OPTIONS_SELECT2);
        $item.select2(options);
      }
    });

    // Gestion des selects simples (NOUVEAU)
    $(".init-select2-simple").each(function (i, item) {
      const $item = $(item);
      var options = Object.assign({}, OPTIONS_SELECT2_SIMPLE);
      $item.select2(options);
    });
  }

  function dateToTimestamp(dateString, position = 'start') {
    if (!dateString) return null; // Retourne null si le champ est vide

    // Pour la date de fin, on veut inclure toute la journée.
    const timeSuffix = (position === 'end') ? 'T23:59:59' : 'T00:00:00';

    const date = new Date(dateString + timeSuffix);

    // getTime() retourne des millisecondes, on divise par 1000 pour les secondes.
    return Math.floor(date.getTime() / 1000);
  }

  function initializeDatePicker() {
    const today = new Date().toISOString().split('T')[0];
    $(`input[type="date"]`).each(function (i, item) {
      $(item).prop('max', today);
      // let est_date_condition_general = $(item).hasClass("date-general");
    });
    function toggleDateFields() {
      const selectedOperation = $("#operation").val();

      if (selectedOperation === 'entre') {
        if (!$("#date-general-container").hasClass("hidden")) {
          $("#date-general-container").addClass('hidden');
          $("#date-general").val("");
        }
        if ($("#date-range-container").hasClass("hidden")) {
          $("#date-range-container").removeClass('hidden');
        }
      } else {
        if ($("#date-general-container").hasClass("hidden")) {
          $("#date-general-container").removeClass('hidden');
        }
        if (!$("#date-range-container").hasClass("hidden")) {
          $("#date-range-container").addClass('hidden');
          $("#date-debut").val("");
          $("#date-fin").val("");
        }
      }
    }

    $(document).on('change', "#date-debut", function () {
      // La date de fin ne peut pas être antérieure à la date de début choisie
      if (this.value) {
        $("#date-fin").prop('min', this.value);
      }
    });

    $(document).on('change', "#date-fin", function () {
      // La date de début ne peut pas être postérieure à la date de fin choisie
      if (this.value) {
        $("#date-debut").prop('max', this.value);
      }
    });

    $(document).on('change', "#operation", toggleDateFields);
    toggleDateFields();
  }

  /**
   * Génère une carte de pertinence avec un code couleur, une icône et un texte.
   * @param {number} confidence - Le score de confiance entre 0 et 1.
   * @returns {string} Le code HTML de la carte de pertinence.
   */
  function getRelevanceCard(confidence) {
    const percentage = Math.round(confidence * 100);
    let config = {};

    if (percentage > 80) {
      config = {
        bgColor: "bg-green-50",
        textColor: "text-green-600",
        icon: "trending-up",
        label: "Très pertinent",
      };
    } else if (percentage > 60) {
      config = {
        bgColor: "bg-blue-50",
        textColor: "text-blue-600",
        icon: "trending-up",
        label: "Pertinent",
      };
    } else if (percentage > 30) {
      config = {
        bgColor: "bg-amber-50",
        textColor: "text-amber-600",
        icon: "bar-chart-horizontal",
        label: "Pertinence moyenne",
      };
    } else {
      config = {
        bgColor: "bg-red-50",
        textColor: "text-red-600",
        icon: "trending-down",
        label: "Faible pertinence",
      };
    }

    return `
      <div class="flex items-center gap-2 p-2 rounded-lg ${config.bgColor} ${config.textColor}">
          <i data-lucide="${config.icon}" class="h-4 w-4"></i>
          <div class="flex flex-col">
              <span class="text-xs">${percentage}% : <span class="text-xs font-bold">${config.label}</span></span>
          </div>
      </div>
    `;
  }

  /**
   * Génère le badge HTML pour une source de données donnée.
   * @param {string} sourceName - Le nom de la source.
   * @returns {string} Le code HTML du badge.
   */
  function getSourceBadge(sourceName) {
    switch (sourceName) {
      case "siteweb":
        return `
            <span class="flex items-center gap-2 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="package" class="h-3 w-3"></i>
                <span>Site Web</span>
            </span>`;
      case "produits":
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="package" class="h-3 w-3"></i>
                <span>Produits</span>
            </span>`;
      case "devis":
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="file-signature" class="h-3 w-3"></i>
                <span>Devis</span>
            </span>`;
      case "mcf":
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="database" class="h-3 w-3"></i>
                <span>MCF & HelloPro</span>
            </span>`;
      case "prix":
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="tag" class="h-3 w-3"></i>
                <span>Prix</span>
            </span>`;
      default:
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="database" class="h-3 w-3"></i>
                <span>${sourceName}</span>
            </span>`;
    }
  }

  const lucide = { createIcons: () => window.lucide?.createIcons() };

  function show_toast(content, type) {
    let options = {
      "text": content,
      "textAlign": "center",
      "loader": false,
      "hideAfter": 5000,
      "showHideTransition": "slide",
      "allowToastClose": false,
      "position": "bottom-center"
    };

    if (type == "success") {
      options.bgColor = "#05A47A";
    } else if (type == "error") {
      options.bgColor = "#EA1F38";
    }
    $.toast(options);
    lucide.createIcons()
  }

  function initializeEventListeners() {
    elements.searchInput.on("keydown", (e) => {
      if (e.key === "Enter") executeSearch();
    });
    elements.searchBtn
      .add(elements.searchBtnDesktop)
      .on("click", executeSearch);
    elements.llmToggle.on("click", toggleLLM);
    $("#activateAI").on("click", toggleLLM);
    $("#closeLlm").on("click", () => {
      state.isLlmEnabled = false;
      updateUI();
    });
    elements.filterToggle.on("click", toggleFilters);
    $("#configureFilters").on("click", () => {
      state.isFilterOpen = true;
      updateUI();
    });
    elements.resultsToggle.on("click", toggleResults);
    $("#closeResults").on("click", () => {
      state.isSidebarOpen = false;
      updateUI();
    });
    elements.mobileFilterBtn.on("click", () => {
      elements.mobileFilterSheet.removeClass("hidden");
      setTimeout(
        () => elements.mobileFilterContent.css("transform", "translateX(0)"),
        10
      );
    });
    elements.closeMobileFilter
      .add(elements.mobileFilterOverlay)
      .on("click", closeMobileFilter);
    elements.topKSlider.on("input", function () {
      state.topK = parseInt($(this).val());
      elements.topKValue.text(state.topK);
    });
    elements.temperatureSlider.on("input", function () {
      state.temperature = parseFloat($(this).val());
      $("#temperatureValue").text(state.temperature);
    });

    elements.btnTranscription.on("click", () => {
      // On vérifie l'état via l'attribut data
      if (elements.btnTranscription.data("action") === "start") {
        startTranscription();
      } else {
        stopTranscription(true); // Arrêt manuel, donc "graceful"
      }
    });

    // NOUVEAU: Écouteurs pour les nouveaux champs
    elements.templatePrompt.on("input", function () {
      state.templatePrompt = $(this).val();
    });
    elements.useReranker.on("change", function () {
      state.useReranker = $(this).is(":checked");
    });
    elements.rerankerModel.on("input", function () {
      state.rerankerModel = $(this).val();
    });
    elements.llmModel.on("change", function () {
      state.selectedModel = $(this).val();
      if (typeof $(this).find('option:selected').data("thinking") !== "undefined") {
        state.selectedThinking = $(this).find('option:selected').data("thinking");
        state.selectedModel = state.selectedModel.replace(`-${state.selectedThinking}`, "");
        state.selectedProvider = "gemini";
      } else {
        state.selectedThinking = "";
        state.selectedProvider = "";
      }
    });
    elements.etatFilter.on("change", function () {
      state.selectedEtat = $(this).val() || [];
    });
    elements.affichageFilter.on("change", function () {
      state.selectedAffichage = $(this).val() || [];
    });
    elements.categorieFilter.on("change", function () {
      state.selectedCategories = $(this).val() || [];
    });
    elements.idsProduit.on('input', function () {
      state.selectedIdsProduits = $(this).val().match(/\d+/g) || [];
    });
    elements.fournisseurFilter.on("change", function () {
      state.selectedFournisseurs = $(this).val() || [];
      state.selectedNomFournisseurs = $(this).find('option:selected').map(function () {
        return $(this).text();
      }).get();
    });

    elements.avecPrix.on("change", function () {
      state.avecPrix = $(this).is(":checked");
    });
    elements.rechercheHybride.on('input', function () {
      state.rechercheHybride = $(this).is(":checked");
    });
    elements.typeRecherche.on("change", function (e) {
      e.preventDefault();
      state.typeRecherche = $(this).val();
      updateSearchButtons()
      const ClassBlocAutreChunks = "hidden"
      if(state.typeRecherche == 1) {
        $('#otherChunksBloc').removeClass(ClassBlocAutreChunks)
      } else {
        $('#otherChunksBloc').addClass(ClassBlocAutreChunks)
      }
    });


    // Mise à jour pour correspondre aux noms de sources de `index3.html`
    ["produits", "devis", "siteweb", "echanges","pj","prix"].forEach((source) => {
      $(`#${source}`).on("change", function () {
        state.selectedSources[source] = $(this).is(":checked");
        updateSubfilters(source);
      });
    });

    elements.searchResultsList.on("click", ".toggle-snippet", function () {
      const $button = $(this);
      const targetId = $button.data("target");
      const $snippet = $(targetId);
      const $buttonText = $button.find(".button-text");
      const $buttonIcon = $button.find(".button-icon");

      $snippet.toggleClass("line-clamp-3");

      if ($snippet.hasClass("line-clamp-3")) {
        $buttonText.text("Voir plus");
        $buttonIcon.attr("data-lucide", "chevron-down");
      } else {
        $buttonText.text("Voir moins");
        $buttonIcon.attr("data-lucide", "chevron-up");
      }
      lucide.createIcons();
    });

    setupIndependentCollapsible(
      "#sourcesToggle",
      "#sourcesContent",
      state.expandedSections.sources
    );
    setupIndependentCollapsible(
      "#advancedToggle",
      "#advancedContent",
      state.expandedSections.categories
    );
    setupIndependentCollapsible(
      "#insightsToggle",
      "#insightsContent",
      state.expandedSections.insights
    );
    setupMultiSelect(
      "categorieBtn",
      "categorieDropdown",
      "categorieText",
      "selectedCategories"
    );
    setupMultiSelect(
      "fournisseurBtn",
      "fournisseurDropdown",
      "fournisseurText",
      "selectedFournisseurs"
    );
    $("#clearSearch").on("click", () => {
      elements.searchInput.val("");
      state.searchQuery = "";
      state.searchResults = [];
      updateUI();
    });
    elements.searchInput.on("input", function () {
      state.searchQuery = $(this).val();
      updateSearchButtons();
    });
    $("#generateAI").on("click", executeSearch);
    $("#use-reranking").on("change", function () {
      state.reranking = $(this).is(":checked");
    });
  }

  function setupIndependentCollapsible(
    toggleSelector,
    contentSelector,
    isInitiallyOpen
  ) {
    const $toggle = $(toggleSelector);
    const $content = $(contentSelector);
    const $chevron = $toggle.find("i");
    if (!isInitiallyOpen) {
      $content.hide();
      $chevron.attr("data-lucide", "chevron-right");
    } else {
      $chevron.attr("data-lucide", "chevron-down");
    }
    $toggle.on("click", function () {
      $content.slideToggle(200);
      $chevron.attr(
        "data-lucide",
        $content.is(":visible") ? "chevron-right" : "chevron-down"
      );
      lucide.createIcons();
    });
  }

  function toggleLLM() {
    state.isLlmEnabled = !state.isLlmEnabled;
    if (state.isLlmEnabled && !state.isSidebarOpen) {
      state.isSidebarOpen = true;
    } else if (!state.isLlmEnabled && state.isSidebarOpen) {
      state.isSidebarOpen = false;
    } else if (state.isLlmEnabled && state.isSidebarOpen) {
      state.isSidebarOpen = true;
    }
    updateUI();
  }
  function toggleFilters() {
    state.isFilterOpen = !state.isFilterOpen;
    updateUI();
  }
  function toggleResults() {
    state.isSidebarOpen = !state.isSidebarOpen;
    updateUI();
  }

  function closeMobileFilter() {
    elements.mobileFilterContent.css("transform", "translateX(-100%)");
    setTimeout(() => elements.mobileFilterSheet.addClass("hidden"), 300);
  }

  function updateSubfilters(source) {
    const $subfilters = $(`#${source}Subfilters`);
    state.selectedSources[source]
      ? $subfilters.slideDown(200)
      : $subfilters.slideUp(200);
  }

  function setupMultiSelect(buttonId, dropdownId, textId, stateKey) {
    const $button = $(`#${buttonId}`);
    const $dropdown = $(`#${dropdownId}`);
    const $text = $(`#${textId}`);
    $button.on("click", (e) => {
      e.stopPropagation();
      $dropdown.toggleClass("hidden");
    });
    $(document).on("click", (e) => {
      if (!$button.is(e.target) && $button.has(e.target).length === 0) {
        $dropdown.addClass("hidden");
      }
    });
    $dropdown.find('input[type="checkbox"]').on("change", () => {
      const selected = $dropdown
        .find("input:checked")
        .map(function () {
          return $(this).next("span").text();
        })
        .get();
      if (selected.length === 0) $text.text("Sélectionner...");
      else if (selected.length === 1) $text.text(selected[0]);
      else $text.text(`${selected.length} sélectionnés`);
      state[stateKey] = selected;
    });
  }

  function updateSearchButtons() {
    if (state.typeRecherche == 1) {
      const hasQuery = state.searchQuery.trim().length > 0;
      const isDisabled = state.isSearching || !hasQuery;
      elements.searchBtn
        .add(elements.searchBtnDesktop)
        .prop("disabled", isDisabled);
      elements.searchBtnText.text(
        state.isSearching ? "Recherche..." : "Rechercher"
      );
    } else {
      const hasQuery = true;
      const isDisabled = state.isSearching || !hasQuery;
      elements.searchBtn
        .add(elements.searchBtnDesktop)
        .prop("disabled", isDisabled);
      elements.searchBtnText.text(
        state.isSearching ? "Recherche..." : "Rechercher"
      );
    }
  }

  function updateUI() {
    if (state.searchResults.length > 0) {
      elements.emptyState.hide();
      elements.noResults.hide();
      elements.searchResultsContainer.show();
      elements.searchMetrics.show();
      elements.searchingState.hide();
      elements.metricsContent.show();
      $("#totalResults").text(state.searchMetrics.totalResults);
      $("#searchTime").text(state.searchMetrics.searchTime);
      renderSearchResults();
    } else if (state.isSearching) {
      elements.emptyState.hide();
      elements.noResults.hide();
      elements.searchResultsContainer.show();
      elements.searchMetrics.show();
      elements.searchingState.show();
      elements.llmEmptyState.hide();
      elements.llmAnalyzeState.show();
      elements.metricsContent.hide();
    } else if (state.searchQuery) {
      elements.emptyState.hide();
      elements.noResults.show();
      elements.searchResultsContainer.hide();
      elements.searchMetrics.hide();
    } else {
      elements.emptyState.show();
      elements.noResults.hide();
      elements.searchResultsContainer.hide();
      elements.searchMetrics.hide();
    }
    if (state.isLlmEnabled) {
      elements.llmConfig.slideDown(200);
      elements.llmToggle
        .addClass("bg-orange-200 text-orange-800 hover:bg-orange-300")
        .removeClass("border-custom-gris-blanc hover:bg-custom-clair-2");
    } else {
      elements.llmConfig.slideUp(200);
      elements.llmToggle
        .removeClass("bg-orange-200 text-orange-800 hover:bg-orange-300")
        .addClass("border-custom-gris-blanc hover:bg-custom-clair-2");
    }
    if (state.isFilterOpen) {
      elements.filterSidebar.show()
      elements.filterToggle.addClass('bg-custom-clair-2 hover:bg-gray-400').removeClass('hover:bg-custom-clair-2');
    } else {
      elements.filterSidebar.hide();
      elements.filterToggle.addClass('hover:bg-custom-clair-2').removeClass('bg-custom-clair-2 hover:bg-gray-400');
    }
    if (state.isSidebarOpen) {
      elements.resultsSidebar
        .removeClass("hidden translate-x-full")
        .addClass("translate-x-0");
      $("#resultsToggleIcon").html(
        '<i data-lucide="panel-right-close" class="h-4 w-4"></i>'
      );
      elements.resultsToggle.addClass('bg-custom-clair-2 hover:bg-gray-400').removeClass('hover:bg-custom-clair-2');
    } else {
      elements.resultsSidebar
        .removeClass("translate-x-0")
        .addClass("translate-x-full");
      setTimeout(() => {
        if (!state.isSidebarOpen) elements.resultsSidebar.addClass("hidden");
      }, 300);
      $("#resultsToggleIcon").html(
        '<i data-lucide="panel-right-open" class="h-4 w-4"></i>'
      );
      elements.resultsToggle.addClass('hover:bg-custom-clair-2').removeClass('bg-custom-clair-2 hover:bg-gray-400');
    }

    if (state.isSidebarOpen) {
      elements.mainContentWrapper
        .removeClass("max-w-6xl")
        .addClass("max-w-4xl");
    } else {
      elements.mainContentWrapper
        .removeClass("max-w-4xl")
        .addClass("max-w-6xl");
    }
    updateSearchButtons();
    updateResultsSidebar();
    lucide.createIcons();
  }

  function updateResultsSidebar() {
    if (state.llmResponse && state.isLlmEnabled) {
      elements.llmResponseContainer.show();
      elements.llmEmptyState.hide();
      // MODIFICATION : Utilisation de marked.parse() pour convertir le Markdown en HTML
      elements.llmResponseText.html(marked.parse(state.llmResponse));
      $("#modelBadge").text(state.selectedModel || "gpt-4o");
      $("#usedTemperature").text(state.temperature);
      $("#usedSources").text(state.searchMetrics.sourcesUsed.length || 0);
      $("#estimatedTokens").text(Math.floor(state.llmResponse.length / 4));
    } else {
      elements.llmResponseContainer.hide();
      if (!state.isSearching) {
        elements.llmEmptyState.show();
      }
    }
    state.searchResults.length > 0
      ? $("#resultsBadge").show().text(state.searchResults.length)
      : $("#resultsBadge").hide();
  }

  function renderSkeletons() {
    elements.searchResultsList.empty();
    const skeletonHtml = `<div class="bg-white rounded-lg border border-custom-clair-2 p-4 space-y-3 animate-pulse"><div class="h-4 bg-custom-clair-2 rounded w-3/4"></div><div class="flex flex-wrap gap-2"><div class="h-5 bg-custom-clair-2 rounded-full w-20"></div><div class="h-5 bg-custom-clair-2 rounded-full w-24"></div></div><div class="space-y-2"><div class="h-3 bg-custom-clair-2 rounded w-full"></div><div class="h-3 bg-custom-clair-2 rounded w-5/6"></div></div></div>`;
    for (let i = 0; i < 5; i++) {
      elements.searchResultsList.append(skeletonHtml);
    }
  }

  function expandPjResults(results) {
    const expanded = [];
    const autreChunks = $('#autreChunks').val() || [];
    let isFullChunks = false 
    let isAdjacentChunks = false
    
    if (autreChunks.length > 0 && state.typeRecherche == 1) {
      if(autreChunks == "full") {
        isFullChunks = true
      } else if (autreChunks == "adjacent") {
        isAdjacentChunks = true
      }
    }

    results.forEach(item => {
        if (isAdjacentChunks) {
            if (item.metadata.context_pre && item.metadata.context_pre.trim() !== "") {
                const preItem = JSON.parse(JSON.stringify(item));
                
                preItem.metadata.entity.text = item.metadata.context_pre;
                preItem.metadata.entity.chunk_id = +preItem.metadata.entity.chunk_id - 1;
                if (preItem.id) {
                    preItem.id += '_pre';
                }
                // On peut ajouter un indicateur si besoin de styliser différemment plus tard
                preItem._isContext = 'pre'; 
                
                expanded.push(preItem);
            }

            expanded.push(item);

            if (item.metadata.context_post && item.metadata.context_post.trim() !== "") {
                const postItem = JSON.parse(JSON.stringify(item));
                
                postItem.metadata.entity.text = item.metadata.context_post;
                postItem.metadata.entity.chunk_id = +postItem.metadata.entity.chunk_id + 1;

                if (postItem.id) {
                    postItem.id += '_post';
                }
                postItem._isContext = 'post';

                expanded.push(postItem);
            }

        } else if (isFullChunks) {
            for(let i = 1;;i++) {
                const actualItem = JSON.parse(JSON.stringify(item));

                if(!item.metadata[`context_${i}`]) {
                  break
                }

                actualItem.metadata.entity.text = item.metadata[`context_${i}`];
                actualItem.metadata.entity.chunk_id = i;
                if (actualItem.id) {
                    actualItem.id = i;
                }
                
                expanded.push(actualItem);
            }
        } else {
            expanded.push(item);
        }
    });

    return expanded;
  }

  function handleSearchResultsPayload(payload) {
    const expandedResults = expandPjResults(payload.results);
    // Met à jour les résultats de recherche dans l'état, en les adaptant
    state.searchResults = expandedResults.map(adaptSearchResult);
    console.log("Mise à jour de l'état avec les résultats :", state.searchResults);

    // 1. Extraire les IDs des résultats qui sont des produits
    const id_produits_a_chercher = state.searchResults
      .filter(result => result.source === 'produits' && result.id_produit)
      .map(result => result.id_produit);

    // 2. Si on a des produits, on va chercher leurs infos détaillées
    if (id_produits_a_chercher.length > 0) {
      // La fonction `get_info_produit` mettra à jour l'UI dans son callback `complete`
      get_info_produit(id_produits_a_chercher);
    } else {
      // S'il n'y a aucun produit, on affiche directement les résultats
      updateUI();
    }
  }
  // --- DÉBUT DE LA SECTION FUSIONNÉE ---

  /**
   * Adapte le format des résultats du WebSocket à celui attendu par l'interface.
   * @param {object} result - L'objet résultat brut du WebSocket.
   * @returns {object} Un objet résultat formaté pour l'UI.
   */
  function adaptSearchResult(result) {
    const meta = result.metadata.entity;
    // Le score de confiance est le rerank_score s'il existe, sinon le score vectoriel.
    const score = result.rerank_score !== undefined ? result.rerank_score : result.score;


    let title = meta.id_produit || 'Titre non disponible';
    let categorie = meta.categorie || meta.id_categorie || 'N/A';
    let price = "";
    let price_copy = ""
    switch (result.source) {
      case "produits_3":
        title = meta.nom_produit || title;
        result.source = "Produits"
        break;
      case "produits_4":
        title = meta.nom_produit || title;
        result.source = "Produits"
        price_ht = meta.prix_ht || 'N/A';
        price_ttc = meta.prix_ttc || 'N/A';
        price += `<span class='text-sm'>Prix HT : ${price_ht}</span><span class='text-sm'>Prix TTC : ${price_ttc}</span>`;
        price_copy = `
          Prix HT : ${price_ht}
          Prix TTC : ${price_ttc}
        `;
        break;
      case "produits_5":
        title = meta.nom_produit || title;
        result.source = "Produits"
        price_ht = meta.prix_ht || 'N/A';
        price_ttc = meta.prix_ttc || 'N/A';
        price += `<span class='text-sm'>Prix HT : ${price_ht}</span><span class='text-sm'>Prix TTC : ${price_ttc}</span>`;
        price_copy = `
          Prix HT : ${price_ht}
          Prix TTC : ${price_ttc}
        `;
        break;
      case "devis":
        title = meta.lead_id || title;
        break;
      case "echanges":
        title = meta.conversation_id || title;
        break;
      case "siteweb_2":
        // case "siteweb":
        title = meta.url || title;
        result.source = "siteweb"
        break;
      case "pjechanges":
        title = meta.id_demande || title;
        result.source = "PJ"
        break;
      case "prix":
        title = meta.nom_produit || title;
        result.source = "Prix"
        if (meta.valeur_prix) {
          let prix_line = `Prix: ${meta.valeur_prix}`;
          for (const extra of [meta.devise, meta.taxe, meta.unite]) {
            if (extra) {
              prix_line += ` ${extra}`;
            }
          }
          price_copy = prix_line;
          price += `<span class='text-sm'>${prix_line}</span>`;
        }
        break;
      default:
        break;
    }
    let description = meta.text || 'Aucune description.';

    // Logique d'extraction du titre et de la description depuis le texte brut
    if (meta.text) {
      const titleMatch = meta.text.match(/nom_produit:(.*?)(?=\s*categorie:|description:|$)/);
      if (titleMatch && titleMatch[1]) {
        title = titleMatch[1].trim();
      }

      const descMatch = meta.text.match(/description:(.*)/s);
      if (descMatch && descMatch[1]) {
        description = descMatch[1].trim().replace(/^P>/, '');
      }
    }

    let url = meta.url;

    if (result.source === 'devis') {
      url = `https://bo.hellopro.fr/admin/gest_com/v2/fiche_lead.php?id_lead=${meta.lead_id}`
    } else if (result.source === 'echanges') {
      url = `https://bo.hellopro.fr/admin/service_client_lead/?page=liste_messages&id_lead=${meta.id_demande}&id_categorie=${meta.id_categorie}`;
    } else if (result.source === 'PJ') {
      url = `https://bo.hellopro.fr/${meta.fichier_source}`;
      
      if(/mon_compte/.test(meta.fichier_source)) {
        url = `https://mc.hellopro.fr/${meta.fichier_source}`;
      }
    }

    return {
      id: meta.sku || Math.random().toString(36).substring(7), // L'UI a besoin d'un ID unique
      title: title,
      source: result.source,
      category: categorie,
      supplier: meta.fournisseur || 'N/A',
      snippet: description,
      confidence: result.score * 100, // S'assure que le score existe
      url: url || '#',
      id_produit: meta.id_produit,
      chunk_info: `${meta.chunk_id}/${meta.total_chunks}`,
      is_pre_chunks: result._isContext == "pre",
      is_post_chunks: result._isContext == "post",
      price: price,
      price_copy: price_copy
    };
  }

  /**
   * Remplace la fonction de recherche par le système WebSocket.
   */
  async function executeSearch() {
    console.log(state.typeRecherche)
    if (
      state.typeRecherche == 1
      && (
        !state.searchQuery.trim()
        || state.isSearching
      )
    ) return;

    if (state.isLlmEnabled) {
      if (elements.templatePrompt.val().trim() === "") {
        if (!state.isFilterOpen) {
          state.isFilterOpen = true
          updateUI()
        }
        $('#errorPromptNull').show(100).delay(5000).hide(100);
        document.querySelector('#llmConfig').scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
    }

    document.querySelector('body').scrollIntoView({ behavior: 'smooth', block: 'start' });

    state.isSearching = true;
    state.searchResults = [];
    state.llmResponse = ""; // Réinitialiser la réponse LLM

    // MODIFICATION : Réinitialise la largeur du sidebar au début de chaque recherche
    $('#resultsSidebar').css('width', '');

    renderSkeletons();
    updateUI();

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
    
    // if (GetURLParameter("domain") == 1) {
    
    let wsUrl = "wss://api.hellopro.eu/search-service/ws/search";
    // }
    console.log(`Connexion à ${wsUrl}...`);

    try {
      socket = new WebSocket(wsUrl);
    } catch (error) {
      console.error(`Erreur de connexion WebSocket: ${error.message}`);
      state.isSearching = false;
      updateUI();
      return;
    }

    socket.onopen = () => {
      console.log('WebSocket connecté.');
      if (elements.llmResponseText.hasClass('text-custom-rouge')) {
        elements.llmResponseText.removeClass('text-custom-rouge');
      }
      // --- DÉBUT DE LA MODIFICATION : Construction de la requête conforme au schéma ---

      // 1. Construire la liste `source` au format `List[SourcesFiltre]`
      let sourcesAvecFiltres = Object.keys(state.selectedSources)
        .filter(sourceName => state.selectedSources[sourceName])
        .map(sourceName => {
          const filtreSpecifique = {};
          const autreChunks = $('#autreChunks').val() || [];

          if (autreChunks.length > 0 && state.typeRecherche == 1) {
            filtreSpecifique.autre_chunks = autreChunks;
          }
          
          let onlyProduits = true;

          $.each(state.selectedSources, function(key, value) {
              if (key === 'produits') {
                  if (value !== true) onlyProduits = false;
              }
              else {
                  if (value !== false) onlyProduits = false;
              }
          });
          state.hybrid = onlyProduits;

          // Appliquer les filtres spécifiques à chaque source en se basant sur les IDs des inputs
          switch (sourceName) {
            case 'produits':
              // sourceName = 'produits_3';
              sourceName = GetURLParameter("source") || 'produits_3';
              const produitsSource = $('#produitsSource').val();
              if (produitsSource.length > 0) {
                // La clé 'provenance' est une supposition logique, à confirmer avec le backend
                filtreSpecifique.source = produitsSource;
              }
              if (state.avecPrix) filtreSpecifique.avec_prix = state.avecPrix;
              if (state.selectedFournisseurs && state.selectedFournisseurs.length > 0) filtreSpecifique.id_fournisseur = state.selectedFournisseurs;
              if (state.selectedIdsProduits && state.selectedIdsProduits.length > 0) filtreSpecifique.id_produit = state.selectedIdsProduits;
              // console.log(state.hybrid, state.selectedSources)
              break;
            case 'devis':
              const devisNaf = $('#devisNaf').val();
              const devisNaf2 = $('#devisNaf2').val();
              const devisEffectif = $('#devisEffectif').val();

              if (devisNaf.length > 0) filtreSpecifique.naf5 = devisNaf;
              if (devisNaf2.length > 0) filtreSpecifique.naf2 = devisNaf2;
              if (devisEffectif.length > 0) filtreSpecifique.effectif = devisEffectif;

              // if (state.selectedNomFournisseurs && state.selectedNomFournisseurs.length > 0) {
              //   filtreSpecifique.liste_frns = state.selectedNomFournisseurs;
              // }

              const date_value = $("#date-general").val();
              const date_debut = $("#date-debut").val();
              const date_fin = $("#date-fin").val();
              const operation = $("#operation").val();

              let filter_date = {}
              let avec_filtre_date = false;
              if (date_value != "") {
                filter_date.date = dateToTimestamp(date_value)
                avec_filtre_date = true;
              } else if (date_debut != "" && date_fin != "") {
                avec_filtre_date = true;
                filter_date.start = dateToTimestamp(date_debut)
                filter_date.end = dateToTimestamp(date_fin)
              }

              if (avec_filtre_date) {
                filtreSpecifique.date_du_lead = {
                  "operator": operation,
                  "values": filter_date
                }
              }

              console.log("Filtres Devis appliqués:", filtreSpecifique);
              break;
            case 'siteweb':
              const sitewebModele = $('#sitewebModele').val() || [];
              if (sitewebModele.length > 0) {
                filtreSpecifique.page_type = sitewebModele;
              }
              const fournisseurDomaine = $("#fournisseurDomaine").val() || [];
              if (fournisseurDomaine.length > 0) {
                filtreSpecifique.domaine = fournisseurDomaine;
              }
              const fournisseurSiteweb = $("#fournisseurSiteweb").val() || [];
              if (fournisseurSiteweb.length > 0) {
                filtreSpecifique.id_fournisseur = fournisseurSiteweb;
              }
              sourceName = 'siteweb_2';
              break;
            case 'pj':
              const pjModele = $('#pjModele').val() || [];
              const pjAutreChunks = $('#pjAutreChunks').val() || [];

              if (pjModele.length > 0) {
                filtreSpecifique.page_type = pjModele;
              }
              if (pjAutreChunks.length > 0) {
                filtreSpecifique.autre_chunks = pjAutreChunks;
              }

              sourceName = 'pjechanges';
              break;
            case 'echanges':
              const fournisseurMcf = $("#fournisseurMcf").val() || [];
              if (fournisseurMcf.length > 0) {
                filtreSpecifique.id_fournisseur = fournisseurMcf;
              }
              break;
            case 'prix':
              const prixSource = $('#prixSource').val();
              if (prixSource && prixSource.length > 0) {
                filtreSpecifique.source = prixSource;
              }
              sourceName = 'prix';
              break;
          }
          return {
            source: sourceName,
            filtre: filtreSpecifique
          };
        });

      // Si aucune source n'est sélectionnée, utiliser la valeur par défaut du schéma
      if (sourcesAvecFiltres.length === 0) {
        // sourcesAvecFiltres = [{ source: "produits_3", filtre: {} }];
        sourcesAvecFiltres = [{ source: GetURLParameter("source") || "produits_3", filtre: {} }];
        state.hybrid = true;
      }

      // 2. Construire le filtre global (filtre principal)
      const filtreGlobal = {};
      if (state.selectedEtat && state.selectedEtat.length > 0) filtreGlobal.etat = state.selectedEtat;
      if (state.selectedAffichage && state.selectedAffichage.length > 0) filtreGlobal.affichage = state.selectedAffichage;
      if (state.selectedCategoriesRubrique && !$.isEmptyObject(state.selectedCategoriesRubrique)) {
        $.each(state.selectedCategoriesRubrique, (_, val) => {
          $.each(val, (j, id_feuille) => {
            state.selectedCategories.push(id_feuille);
          });
        });
        let selectedCategorie = []
        $.each(state.selectedCategories, (_, i) => {
          if (!i.includes("r_")) {
            selectedCategorie.push(i);
          }
        });
        state.selectedCategories = [...new Set(selectedCategorie)]
      }
      if (state.selectedCategories && state.selectedCategories.length > 0) filtreGlobal.id_categorie = state.selectedCategories;
      // if (state.selectedFournisseurs && state.selectedFournisseurs.length > 0) filtreGlobal.id_fournisseur = state.selectedFournisseurs;

      // 3. Construire l'objet de requête final
      const searchRequest = {
        prompt: state.searchQuery,
        source: sourcesAvecFiltres, // Utilise la nouvelle structure
        action: state.isLlmEnabled ? 2 : 1,
        top_k: state.topK,
        filtre: filtreGlobal, // Le filtre global
        // Le champ `filtre_source` n'est plus à ce niveau, il est intégré dans `source`
        llm: {
          chat_model: state.selectedModel,
          temperature: state.temperature,
          template_prompt: $("#llmPrompt").val() || state.templatePrompt,
          provider: state.selectedProvider,
          thinking_level: state.selectedThinking,
        },
        options: {
          use_reranker: state.useReranker,
          reranker_model: state.rerankerModel,
          rrf: GetURLParameter("rrf") == 1
        },
        type: $("input[name='type-recherche']:checked").val(),
        hybrid: GetURLParameter("hybrid") == 1 ? true : false,
        hybrid_options: {
          ef: GetURLParameter("ef") || 5000,
          dense_limit_multiplier: GetURLParameter("dense_limit_multiplier") || 5,
          ranker_type: GetURLParameter("ranker_type") || "rrf",
          rrf_k: GetURLParameter("rrf_k") || 60,
          drop_ratio_search: GetURLParameter("drop_ratio_search") || 0.0,
          radius: GetURLParameter("radius") || null,
          range_filter: GetURLParameter("range_filter") || null
        }
      };

      // --- FIN DE LA MODIFICATION ---

      socket.send(JSON.stringify(searchRequest));
      console.log('Requête de recherche envoyée (conforme au schéma):', searchRequest);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("Message reçu:", data.type);

      switch (data.type) {
        case 'status':
        case 'warning':
        case 'embedding_complete':
          console.log(`[WS Status] ${data.payload}`);
          break;
        case 'error':
          console.error(`[WS Error] ${data.payload}`);
          if (!state.isSidebarOpen) {
            state.isSidebarOpen = true;
            updateUI();
          }
          // Cacher l'indicateur de chargement
          elements.llmAnalyzeState.hide();
          // Afficher le conteneur de réponse
          elements.llmResponseContainer.show();
          // Créer un élément HTML pour l'erreur et l'afficher
          const errorHtml = `<div class="llm-error">${data.payload}</div>`;
          elements.llmResponseText.html(errorHtml);
          state.llmResponse = data.payload;
          updateResultsSidebar();
          if (!elements.llmResponseText.hasClass('text-custom-rouge')) {
            elements.llmResponseText.addClass('text-custom-rouge');
          }
          show_toast(generate_error_message("Une erreur s'est produite"), "error");
          $('html, body').animate({
            scrollTop: $('body').offset().top
          }, 800);
          // La recherche est terminée à cause de l'erreur
          state.isSearching = false;
          updateUI(); // Mettre à jour les boutons, etc.
          socket.close();
          break;
        case 'initial_results':
          console.log("Réception des résultats initiaux (pré-reranking).");
          // On utilise notre nouvelle fonction helper pour traiter les résultats
          handleSearchResultsPayload(data.payload);
          break;
        case 'rerank_complete':
          // Met à jour les résultats de recherche dans l'état, en les adaptant
          handleSearchResultsPayload(data.payload);
          break;
        case 'llm_start':
          state.llmResponse = ''; // S'assure que la réponse est vide au début du streaming
          // MODIFICATION : Agrandir le sidebar, afficher le loader et cacher la zone de texte
          $('#llmResponseContainer').show();
          $('#resultsSidebar').css('width', '550px');
          $('#insightsContent').show();
          // $('#llmResponseText').parent().hide(); // Cache le conteneur avec la bordure
          updateUI(); // Met à jour l'interface pour montrer que le LLM a commencé
          break;
        case 'llm_chunk':
          // MODIFICATION : Cacher le loader et afficher la zone de texte au premier chunk
          // $('#llmResponseText').parent().show();
          state.llmResponse += data.payload;
          // Met à jour uniquement le panneau latéral pour une meilleure performance
          updateResultsSidebar();
          break;
        case 'end_of_stream':
          const timings = data.payload.timings || {};
          const sourcesUsed = Object.keys(state.selectedSources).filter(key => state.selectedSources[key]);

          state.searchMetrics = {
            totalResults: data.payload.result_count || state.searchResults.length,
            searchTime: (timings.total_process || 0).toFixed(2) + "s",
            sourcesUsed: sourcesUsed,
          };

          // La recherche est terminée
          state.isSearching = false;
          elements.llmAnalyzeState.hide();
          updateUI(); // Met à jour l'interface une dernière fois
          socket.close(); // Ferme la connexion
          break;
        default:
          console.warn(`Type de message inconnu: ${data.type}`);
      }
    };

    socket.onerror = (error) => {
      console.error(`Erreur WebSocket:`, error);
      state.isSearching = false;
      updateUI();
    };

    socket.onclose = (event) => {
      console.log(`Connexion fermée. Code: ${event.code}, Raison: ${event.reason}`);
      // S'assure que l'état de recherche est bien remis à false
      if (state.isSearching) {
        state.isSearching = false;
        updateUI();
      }
    };
  }

  // --- FIN DE LA SECTION FUSIONNÉE ---

  function get_info_produit(id_produits) {
    // Log pour vérifier que les bons IDs arrivent ici
    console.log("🚀 Lancement de get_info_produit avec les IDs :", id_produits);

    $.ajax({
      // J'ai vu que vous utilisiez une URL complète, c'est parfait pour éviter les ambiguïtés.
      url: "https://www.hellopro.fr/partenaires_externes/info_produit/get_info_produit_complet.php",
      type: "POST",

      // 1. On indique au serveur qu'on envoie du JSON.
      contentType: "application/json; charset=utf-8",

      // 2. On crée un objet JS simple { id_produits: [...] } et on le transforme ENTIÈREMENT en chaîne JSON.
      data: JSON.stringify({ id_produits: id_produits }),

      // 3. On indique qu'on s'attend à recevoir du JSON en retour.
      dataType: "json",

      success: function (nomsProduits) {
        console.log("✅ Succès AJAX, noms de produits reçus :", nomsProduits);

        state.searchResults = state.searchResults.map(result => {
          if (result.source === 'produits' && nomsProduits[result.id_produit]) {
            return {
              ...result,
              title: nomsProduits[result.id_produit]["nom_produit"],
              url: nomsProduits[result.id_produit]["url_produit"]
            };
          }
          return result;
        });
      },
      error: function (jqXHR, textStatus, errorThrown) {
        // Des logs plus détaillés pour le débogage
        console.error("❌ Erreur lors de l'appel AJAX :", textStatus, errorThrown);
        console.error("Statut de la réponse :", jqXHR.status);
        console.error("Réponse du serveur :", jqXHR.responseText);
      },
      complete: function () {
        console.log("🏁 Appel AJAX terminé. Mise à jour de l'interface.");
        console.log("Résultats finaux après mise à jour des noms de produits :", state.searchResults);
        updateUI();
      }
    });
  }

  function renderSearchResults() {
    elements.searchResultsList.empty();
    state.copiedContent = "";
    let i = 1;
    state.searchResults.forEach((result) => {
      const relevanceHtml = (state.typeRecherche == 1) ? getRelevanceCard(result.confidence / 100) : "";
      const sourceBadgeHtml = getSourceBadge(result.source);
      const class_supplier = result.source == "devis" ? "hidden" : ""
      let class_bg_other_chunks = "bg-white"
      if(result.is_pre_chunks) {
        class_bg_other_chunks = "bg-blue-50/75"
      } else if(result.is_post_chunks) {
        class_bg_other_chunks = "bg-green-50/75"
      }

      state.copiedContent += `
      --------------------------------
      Titre : ${result.title}
      Source : ${result.source}
      Fournisseur : ${result.supplier}
      Catégorie : ${result.category}
      Texte : ${result.snippet || ""}
      ${result.price_copy || ""}
      `;
      let price = result.price;
      
      const resultCardHtml = `
        <div class="${class_bg_other_chunks} rounded-lg border border-custom-clair-2 hover:shadow-lg transition-all duration-300 hover:border-custom-bleu group p-4 flex flex-col justify-between">
          <div class="space-y-3 mb-4">
              <div class="flex items-start justify-between gap-2">
                  <h3 class="font-semibold text-base leading-tight text-custom-noir transition-colors" data-id_produit="${result.id_produit}">${i}. ${result.title}</h3>
                  <a href="${result.url}" target="_blank" rel="noopener noreferrer" class="h-8 w-8 flex-shrink-0 flex items-center justify-center rounded-full hover:bg-blue-100">
                    <i data-lucide="external-link" class="h-4 w-4 text-custom-gris group-hover:text-blue-700"></i>
                  </a>
              </div>
              <div class="flex items-start gap-2 flex-col">
                  ${price}
              </div>
              <div class="flex flex-wrap gap-2">
                  ${sourceBadgeHtml}
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                    <i data-lucide="tag" class="h-3 w-3"></i>
                    <span>${result.category}</span>
                  </span>
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full ${class_supplier}">
                    <i data-lucide="building-2" class="h-3 w-3"></i>
                    <span>${result.supplier}</span>
                  </span>
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                    <i data-lucide="building-2" class="h-3 w-3"></i>
                    <span>Chunk : ${result.chunk_info}</span>
                  </span>
              </div>
              <div>
                <p id="snippet-${result.id}" class="data-texte-ws text-sm text-custom-gris leading-relaxed line-clamp-3 transition-all duration-300">${result.snippet || ""}</p>
                <button 
                  class="toggle-snippet text-sm font-semibold text-custom-bleu hover:text-custom-bleu-heavy mt-2 flex items-center gap-1 hidden" 
                  data-target="#snippet-${result.id}">
                  <span class="button-text">Voir plus</span>
                  <i data-lucide="chevron-down" class="h-4 w-4 button-icon transition-transform duration-200"></i>
                </button>
              </div>
          </div>
          <div class="mt-auto">
            ${relevanceHtml}
          </div>
        </div>`;

      elements.searchResultsList.append(resultCardHtml);
      i++;
    });

    // Vérifier après rendu si le texte est tronqué
    elements.searchResultsList.find("p[id^='snippet-']").each(function () {
      const $p = $(this);
      const $btn = $p.next("button.toggle-snippet");

      const fullHeight = this.scrollHeight;                  // hauteur réelle du contenu
      const visibleHeight = $p[0].getBoundingClientRect().height; // hauteur affichée

      if (fullHeight > visibleHeight + 1) { // on tolère 1px d'arrondi
        $btn.removeClass("hidden"); // texte tronqué → bouton affiché
      }
    });

    lucide.createIcons();
  }

  $(document).on('click', '#copier-texte', function () {
    const separator = '-------------------------------------\n';
    let formattedText = '';

    formattedText += separator.trim();
    formattedText = state.copiedContent;
    console.log("Texte qui sera copié :\n" + formattedText);
    copyTextToClipboard(formattedText);
  });

  /**
   * transcription audio via google speech to text
   */
  let transcriptionAudioContext;
  let transcriptionMediaStream;
  let transcriptionScriptProcessor;
  let transcriptionAnimationFrameId;
  let transcriptionTimeoutId;
  let transcriptionSilenceTimeoutId;

  const TRANSCRIPTION_AUTH_TOKEN = "h3ll0pro2k25-stt356";
  let TRANSCRIPTION_WEBSOCKET_URL = `wss://api.hellopro.eu/transcription-service/ws/google/transcription?token=${TRANSCRIPTION_AUTH_TOKEN}`;
  if (GetURLParameter("server") == "chatgpt") {
    TRANSCRIPTION_WEBSOCKET_URL = `wss://api.hellopro.eu/transcription-service/ws/openai/transcription?token=${TRANSCRIPTION_AUTH_TOKEN}`;
  }

  const transcriptionStartColor = { r: 51, g: 83, b: 255, a: 1 };
  const transcriptionEndColor = { r: 253, g: 187, b: 155, a: 1 };

  function transcriptionInterpolateColor(index, totalBars) {
    const ratio = totalBars > 1 ? index / (totalBars - 1) : 0;
    const r = Math.round(transcriptionStartColor.r + (transcriptionEndColor.r - transcriptionStartColor.r) * ratio);
    const g = Math.round(transcriptionStartColor.g + (transcriptionEndColor.g - transcriptionStartColor.g) * ratio);
    const b = Math.round(transcriptionStartColor.b + (transcriptionEndColor.b - transcriptionStartColor.b) * ratio);
    return `rgba(${r}, ${g}, ${b}, 1)`;
  }

  const setupTranscriptionButton = (action) => {
    if (action === "start") {
      elements.btnTranscription.data("action", "start");
      elements.btnTranscription.html(`<i data-lucide="mic" class="h-4 w-4"></i>`);
    } else {
      elements.btnTranscription.data("action", "stop");
      const totalBars = 5;
      const barsHtml = Array.from({ length: totalBars }, (_, i) => {
        const color = transcriptionInterpolateColor(i, totalBars);
        return `<div class="bar" style="height: 2px; background-color: ${color};" data-current-height="2"></div>`;
      }).join("");
      elements.btnTranscription.html(`<div class="audio-visualizer">${barsHtml}</div><i data-lucide="square" class="h-4 w-4"></i>`);
    }
    lucide.createIcons();
  };

  const startTranscription = async () => {
    elements.btnTranscription.prop("disabled", true);
    try {
      transcriptionMediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      transcriptionAudioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = transcriptionAudioContext.createMediaStreamSource(transcriptionMediaStream);
      transcriptionScriptProcessor = transcriptionAudioContext.createScriptProcessor(4096, 1, 1);
      const analyser = transcriptionAudioContext.createAnalyser();
      analyser.fftSize = 256;
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      source.connect(analyser);

      transcriptionScriptProcessor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0);
        const int16Buffer = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          int16Buffer[i] = Math.max(-1, Math.min(1, inputData[i])) * 32767;
        }
        const base64 = btoa(String.fromCharCode.apply(null, new Uint8Array(int16Buffer.buffer)));
        if (transcriptionSocket && transcriptionSocket.readyState === WebSocket.OPEN) {
          transcriptionSocket.send(JSON.stringify({ audio: base64 }));
        }
      };

      source.connect(transcriptionScriptProcessor);
      transcriptionScriptProcessor.connect(transcriptionAudioContext.destination);

      connectTranscriptionWebSocket();
      setupTranscriptionButton("stop");
      startSmoothAudioVisualizer(analyser, dataArray);

      transcriptionTimeoutId = setTimeout(() => {
        show_toast(generate_error_message("Limite de 1 minute atteinte."), "error");
        stopTranscription(true);
      }, 60000);

    } catch (err) {
      console.error("Error accessing microphone:", err);
      show_toast(generate_error_message("Erreur: Impossible d’accéder au microphone."), "error");
      setupTranscriptionButton("start");
    } finally {
      elements.btnTranscription.prop("disabled", false);
    }
  };

  const stopTranscription = (isGraceful = true) => {
    if (transcriptionAnimationFrameId) cancelAnimationFrame(transcriptionAnimationFrameId);
    if (transcriptionTimeoutId) clearTimeout(transcriptionTimeoutId);
    if (transcriptionSilenceTimeoutId) clearTimeout(transcriptionSilenceTimeoutId);
    transcriptionAnimationFrameId = null;
    transcriptionTimeoutId = null;
    transcriptionSilenceTimeoutId = null;

    const socketToClose = transcriptionSocket;

    if (!socketToClose) {
      setupTranscriptionButton('start');
      return;
    }

    if (isGraceful && socketToClose.readyState === WebSocket.OPEN) {
      socketToClose.send(JSON.stringify({ command: "end_stream" }));
    }

    if (socketToClose.readyState < 2) {
      socketToClose.close();
    }

    transcriptionSocket = null;

    if (transcriptionMediaStream) {
      transcriptionMediaStream.getTracks().forEach((track) => track.stop());
      transcriptionMediaStream = null;
    }
    if (transcriptionAudioContext && transcriptionAudioContext.state !== "closed") {
      transcriptionAudioContext.close();
      transcriptionAudioContext = null;
    }
    if (transcriptionScriptProcessor) {
      transcriptionScriptProcessor.disconnect();
      transcriptionScriptProcessor = null;
    }

    setupTranscriptionButton("start");

    // --- CORRECTION 2 (SÉCURITÉ) ---
    // S'assure que le bouton de recherche est dans le bon état à la fin
    updateSearchButtons();
  };

  const connectTranscriptionWebSocket = () => {
    transcriptionSocket = new WebSocket(TRANSCRIPTION_WEBSOCKET_URL);

    transcriptionSocket.onopen = () => {
      console.log("Transcription WebSocket connection established.");

      // --- CORRECTION 1 ---
      // Remplacement de 'websocket' par 'transcriptionSocket'
      transcriptionSocket.send(JSON.stringify({
        config: {
          sampleRate: transcriptionAudioContext.sampleRate,
          languageCode: (GetURLParameter("server") == "chatgpt") ? 'fr' : 'fr-FR',
          enablePunctuation: true,
          interimResults: true
        }
      }));
    };

    transcriptionSocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "transcript" && data.transcript) {
        elements.searchInput.val(data.transcript);

        // --- CORRECTION 2 ---
        // Mettre à jour l'état et l'UI du bouton de recherche
        state.searchQuery = data.transcript;
        updateSearchButtons();

      } else if (data.type === "error") {
        show_toast(generate_error_message(`Erreur du serveur: ${data.error}`), "error");
        stopTranscription(false);
      } else if (data.type === "end_stream") {
        show_toast(generate_succes_message(`Fin de transcription`), "success");
        stopTranscription(true);
      }
    };

    transcriptionSocket.onerror = (error) => {
      console.error("Transcription WebSocket error:", error);
      show_toast(generate_error_message("Erreur de connexion WebSocket."), "error");
    };

    transcriptionSocket.onclose = (event) => {
      // console.log(`Transcription WebSocket connection closed: ${event.code}`);
      show_toast(generate_succes_message(`Transcription terminée`), "success");
      stopTranscription(false);
    };
  };

  const startSmoothAudioVisualizer = (analyser, dataArray) => {
    const $visualizerBars = $(".audio-visualizer .bar");
    if ($visualizerBars.length === 0) return;

    const bufferLength = analyser.frequencyBinCount;
    const smoothingFactor = 0.8;
    const SILENCE_THRESHOLD = 5;
    const SILENCE_DURATION = 5000;

    function draw() {
      transcriptionAnimationFrameId = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      let volumeSum = 0;
      for (let i = 0; i < bufferLength; i++) {
        volumeSum += dataArray[i];
      }
      const averageVolume = volumeSum / bufferLength;

      if (averageVolume > SILENCE_THRESHOLD) {
        if (transcriptionSilenceTimeoutId) clearTimeout(transcriptionSilenceTimeoutId);
        transcriptionSilenceTimeoutId = null;
      } else {
        if (!transcriptionSilenceTimeoutId) {
          transcriptionSilenceTimeoutId = setTimeout(() => {
            show_toast(generate_error_message("Silence détecté, arrêt de la transcription."), "error");
            stopTranscription(true);
          }, SILENCE_DURATION);
        }
      }

      const barHeightMultiplier = 20 / 255;
      $visualizerBars.each(function (i) {
        const $bar = $(this);
        const barIndex = Math.floor(i * (bufferLength / $visualizerBars.length));
        const targetHeight = Math.max(2, dataArray[barIndex] * barHeightMultiplier);
        let currentHeight = $bar.data("current-height");
        currentHeight = currentHeight * smoothingFactor + targetHeight * (1 - smoothingFactor);
        $bar.css("height", `${currentHeight}px`);
        $bar.data("current-height", currentHeight);
      });
    }
    draw();
  };
  /**
   * fin transcription
   */


  /**
   * Fonction pour copier du texte dans le presse-papiers.
   * Tente d'utiliser l'API moderne (navigator.clipboard) et se rabat
   * sur l'ancienne méthode (document.execCommand) si nécessaire.
   * @param {string} text Le texte à copier.
   */
  function copyTextToClipboard(text) {
    // Utilise l'API moderne si elle est disponible (contexte sécurisé HTTPS ou localhost)
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        console.log('Texte copié avec succès (méthode moderne) !');
        show_toast(generate_succes_message("Copié dans le presse papier"), "success")
      }).catch(function (err) {
        console.error('Échec de la copie (méthode moderne) : ', err);
        // Si la méthode moderne échoue, on essaie l'ancienne
        fallbackCopyTextToClipboard(text);
      });
    } else {
      // Si l'API moderne n'est pas disponible, utilise la méthode de repli
      console.log("API Clipboard non disponible, utilisation de la méthode de repli.");
      fallbackCopyTextToClipboard(text);
    }
  }

  /**
   * Fonction de repli (fallback) utilisant la méthode dépréciée document.execCommand.
   * @param {string} text Le texte à copier.
   */
  function fallbackCopyTextToClipboard(text) {
    var textArea = document.createElement("textarea");
    textArea.value = text;

    // Rendre l'élément invisible et éviter de faire défiler la page
    textArea.style.position = "fixed";
    textArea.style.top = 0;
    textArea.style.left = 0;
    textArea.style.opacity = 0;

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
      var successful = document.execCommand('copy');
      if (successful) {
        console.log('Texte copié avec succès (méthode de repli).');
        show_toast(generate_succes_message("Copié dans le presse papier"), "success")
        // Affichez un message de succès à l'utilisateur ici
      } else {
        console.error('Échec de la copie (méthode de repli).');
        show_toast(generate_error_message("Erreur de copie dans le presse papier"), "error")
        // Affichez un message d'erreur à l'utilisateur ici
      }
    } catch (err) {
      console.error('Erreur lors de la copie (méthode de repli): ', err);
      show_toast(generate_error_message("Erreur de copie dans le presse papier"), "error")
    }

    document.body.removeChild(textArea);
  }

  // Initialisation de l'application
  initializeFormState();
  initializeSelect2();
  initializeDatePicker();
  initializeEventListeners();
  updateUI();
  setupTranscriptionButton("start");
  lucide.createIcons();
});