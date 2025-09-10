$(function () {
  // --- DÉBUT DE LA SECTION FUSIONNÉE ---

  // Variable globale pour la connexion WebSocket
  let socket = null;

  // --- FIN DE LA SECTION FUSIONNÉE ---

  // Global state
  const state = {
    searchQuery: "",
    topK: 30,
    temperature: 0.4,
    // NOUVEAU: Ajout des champs pour correspondre au schéma
    templatePrompt: $("#llmPrompt").val(),
    useReranker: true,
    rerankerModel: "BAAI/bge-reranker-v2-m3",
    selectedModel: "google/gemini-flash-1.5", // Mis à jour avec la nouvelle valeur par défaut
    isFilterOpen: true,
    isLlmEnabled: false,
    isSidebarOpen: false,
    isResultSuccess: false,
    selectedSources: {
      produits: true,
      devis: false,
      mcf: false,
      siteweb: false,
    },
    selectedCategories: [],
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

        var data_param = "";
        if (typeof data.param_data != "undefined") {
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
            config.templateResult = templateResult_with_optgroup_sans_selectall_select2;
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

    $(document).on('change', "#date-debut", function() {
        // La date de fin ne peut pas être antérieure à la date de début choisie
        if (this.value) {
            $("#date-fin").prop('min', this.value);
        }
    });

    $(document).on('change', "#date-fin", function() {
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
        bgColor: "bg-custom-vert-light",
        textColor: "text-green-800",
        icon: "trending-up",
        label: "Très pertinent",
      };
    } else if (percentage > 60) {
      config = {
        bgColor: "bg-blue-100",
        textColor: "text-blue-700",
        icon: "trending-up",
        label: "Pertinent",
      };
    } else if (percentage > 30) {
      config = {
        bgColor: "bg-amber-100",   
        textColor: "text-amber-700", 
        icon: "bar-chart-horizontal",            
        label: "Pertinence moyenne",
      };
    } else {
      config = {
        bgColor: "bg-custom-rouge-light",
        textColor: "text-red-800",
        icon: "trending-down",
        label: "Faible pertinence",
      };
    }

    return `
      <div class="flex items-center gap-2 p-2 rounded-lg ${config.bgColor} ${config.textColor}">
          <i data-lucide="${config.icon}" class="h-4 w-4"></i>
          <div class="flex flex-col">
              <span class="text-xs font-bold">${config.label}</span>
              <span class="text-xs">${percentage}% de confiance</span>
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
    const HELLOPRO_LOGO_URL = "https://static.hellopro.fr/img/hp-favicon.png";

    switch (sourceName) {
      case "siteweb":
        return `
            <span class="flex items-center gap-2 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <img src="${HELLOPRO_LOGO_URL}" class="h-4 w-4 rounded-full" alt="Logo HelloPro">
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
      default:
        return `
            <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                <i data-lucide="database" class="h-3 w-3"></i>
                <span>${sourceName}</span>
            </span>`;
    }
  }

  const lucide = { createIcons: () => window.lucide?.createIcons() };

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
    });
    elements.etatFilter.on("change", function () {
      state.selectedEtat = $(this).val() || [];
    });
    elements.affichageFilter.on("change", function () {
      state.selectedAffichage = $(this).val() || [];
    });
    elements.categorieFilter.on("change", function () {
        state.selectedCategories = $(this).val() || [];
        console.log("Catégories sélectionnées :", state.selectedCategories);
    });
    elements.fournisseurFilter.on("change", function () {
        state.selectedFournisseurs = $(this).val() || [];
        state.selectedNomFournisseurs = $(this).find('option:selected').map(function() {
            return $(this).text();
        }).get();
    });


    // Mise à jour pour correspondre aux noms de sources de `index3.html`
    ["produits", "devis", "siteweb", "echanges"].forEach((source) => {
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
    if(state.isLlmEnabled && !state.isSidebarOpen) {
      state.isSidebarOpen = true;
    } else if(!state.isLlmEnabled && state.isSidebarOpen) {
      state.isSidebarOpen = false;
    } else if(state.isLlmEnabled && state.isSidebarOpen) {
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
    const hasQuery = state.searchQuery.trim().length > 0;
    const isDisabled = state.isSearching || !hasQuery;
    elements.searchBtn
      .add(elements.searchBtnDesktop)
      .prop("disabled", isDisabled);
    elements.searchBtnText.text(
      state.isSearching ? "Recherche..." : "Rechercher"
    );
  }

  function updateUI() {
    if (state.searchResults.length > 0) {
      elements.emptyState.hide();
      elements.noResults.hide();
      elements.searchResultsContainer.show();
      elements.searchMetrics.show();
      elements.searchingState.hide();
      elements.llmAnalyzeState.hide();
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
        .addClass("bg-custom-orange text-white")
        .removeClass("border-custom-gris-blanc hover:bg-custom-clair-2");
    } else {
      elements.llmConfig.slideUp(200);
      elements.llmToggle
        .removeClass("bg-custom-orange text-white")
        .addClass("border-custom-gris-blanc hover:bg-custom-clair-2");
    }
    state.isFilterOpen
      ? elements.filterSidebar.show()
      : elements.filterSidebar.hide();
    if (state.isSidebarOpen) {
      elements.resultsSidebar
        .removeClass("hidden translate-x-full")
        .addClass("translate-x-0");
      $("#resultsToggleIcon").html(
        '<i data-lucide="panel-right-close" class="h-4 w-4"></i>'
      );
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
      if(!state.isSearching) {
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

    function handleSearchResultsPayload(payload) {
    // Met à jour les résultats de recherche dans l'état, en les adaptant
    state.searchResults = payload.results.map(adaptSearchResult);
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
    switch (result.source) {
      case "produits_3":
        title = meta.nom_produit || title;
        break;
      case "devis":
        title = meta.lead_id || title;
      case "echanges":
        title = meta.conversation_id || title;
      case "siteweb":
        title = meta.url || title;
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

    if(result.source === 'devis') {
      url = `https://bo.hellopro.fr/admin/gest_com/v2/fiche_lead.php?id_lead=${meta.lead_id}`
    } else if(result.source === 'echanges') {
      url = `https://bo.hellopro.fr/admin/service_client_lead/?page=liste_messages&id_lead=${meta.id_demande}&id_categorie=${meta.id_categorie}`;
    }

    return {
      id: meta.sku || Math.random().toString(36).substring(7), // L'UI a besoin d'un ID unique
      title: title,
      source: result.source,
      category: meta.id_categorie || 'N/A',
      supplier: meta.fournisseur || 'N/A',
      snippet: description,
      confidence: result.score * 100, // S'assure que le score existe
      url: url || '#',
      id_produit: meta.id_produit,
      chunk_info: `${meta.chunk_id}/${meta.total_chunks}`
    };
  }

  /**
   * Remplace la fonction de recherche par le système WebSocket.
   */
  async function executeSearch() {
    if (!state.searchQuery.trim() || state.isSearching) return;

    if(state.isLlmEnabled) {
      if(elements.templatePrompt.val().trim() === "") {
        $('#errorPromptNull').show(100).delay(3000).hide(100);
        document.querySelector('#errorPromptNull').scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
    }

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

    const wsUrl = "ws://34.90.162.9:8510/ws/search"; // L'URL est maintenant ici
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

      // --- DÉBUT DE LA MODIFICATION : Construction de la requête conforme au schéma ---

      // 1. Construire la liste `source` au format `List[SourcesFiltre]`
      let sourcesAvecFiltres = Object.keys(state.selectedSources)
        .filter(sourceName => state.selectedSources[sourceName])
        .map(sourceName => {
          const filtreSpecifique = {};
          // Appliquer les filtres spécifiques à chaque source en se basant sur les IDs des inputs
          switch (sourceName) {
            case 'produits':
              sourceName = 'produits_3';
              const produitsSource = $('#produitsSource').val();
              if (produitsSource.length > 0) {
                // La clé 'provenance' est une supposition logique, à confirmer avec le backend
                filtreSpecifique.source = produitsSource;
              }
              break;
            case 'devis':
              const devisNaf = $('#devisNaf').val();
              const devisNaf2 = $('#devisNaf2').val();
              const devisEffectif = $('#devisEffectif').val();

              if (devisNaf.length > 0) filtreSpecifique.naf5 = devisNaf;
              if (devisNaf2.length > 0) filtreSpecifique.naf2 = devisNaf2;
              if (devisEffectif.length > 0) filtreSpecifique.effectif = devisEffectif;

              if (state.selectedNomFournisseurs && state.selectedNomFournisseurs.length > 0) {
                filtreSpecifique.liste_frns = state.selectedNomFournisseurs;
              }

              const date_value = $("#date-general").val();
              const date_debut = $("#date-debut").val();
              const date_fin   = $("#date-fin").val();
              const operation  = $("#operation").val();

              let filter_date = {}
              let avec_filtre_date = false;
              if (date_value != "") {
                filter_date.date = dateToTimestamp(date_value)
                avec_filtre_date = true;
              } else if (date_debut != "" && date_fin != "") {
                avec_filtre_date = true;
                filter_date.start = dateToTimestamp(date_debut)
                filter_date.end   = dateToTimestamp(date_fin)
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
              const sitewebModele = $('#sitewebModele').val();
              if (sitewebModele) {
                filtreSpecifique.page_type = sitewebModele;
              }
              break;
          }
          return {
            source: sourceName,
            filtre: filtreSpecifique
          };
        });

      // Si aucune source n'est sélectionnée, utiliser la valeur par défaut du schéma
      if (sourcesAvecFiltres.length === 0) {
        sourcesAvecFiltres = [{ source: "produits_3", filtre: {} }];
      }

      // 2. Construire le filtre global (filtre principal)
      const filtreGlobal = {};
      if (state.selectedEtat && state.selectedEtat.length > 0) filtreGlobal.etat = state.selectedEtat;
      if (state.selectedAffichage && state.selectedAffichage.length > 0) filtreGlobal.affichage = state.selectedAffichage;
      if (state.selectedCategories && state.selectedCategories.length > 0) filtreGlobal.id_categorie = state.selectedCategories;
      if (state.selectedFournisseurs && state.selectedFournisseurs.length > 0) filtreGlobal.id_fournisseur = state.selectedFournisseurs;

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
        },
        options: {
          use_reranker: state.useReranker,
          reranker_model: state.rerankerModel,
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
          break;
        case 'initial_results':
          console.log("Réception des résultats initiaux (pré-reranking).");
          // On utilise notre nouvelle fonction helper pour traiter les résultats
          handleSearchResultsPayload(data.payload);
          break;
        case 'rerank_complete':
          // Met à jour les résultats de recherche dans l'état, en les adaptant
          handleSearchResultsPayload(data.payload);
          // state.searchResults = data.payload.results.map(adaptSearchResult);

          // // 1. Extraire les IDs des résultats qui sont des produits
          // const id_produits_a_chercher = state.searchResults
          //   .filter(result => result.source === 'produits' && result.id_produit)
          //   .map(result => result.id_produit);

          // console.log(`IDs de produits à chercher:`, id_produits_a_chercher);
          // // 2. Si on a des produits, on va chercher leurs infos détaillées
          // if (id_produits_a_chercher.length > 0) {
          //   get_info_produit(id_produits_a_chercher);
          // } else {
          //   // S'il n'y a aucun produit, on affiche directement les résultats
          //   updateUI();
          // }
          break;
        case 'llm_start':
          state.llmResponse = ''; // S'assure que la réponse est vide au début du streaming
          // MODIFICATION : Agrandir le sidebar, afficher le loader et cacher la zone de texte
          $('#llmResponseContainer').show();
          $('#resultsSidebar').css('width', '550px');
          $('#insightsContent').show();
          $('#llmLoadingState').show();
          // $('#llmResponseText').parent().hide(); // Cache le conteneur avec la bordure
          updateUI(); // Met à jour l'interface pour montrer que le LLM a commencé
          break;
        case 'llm_chunk':
          // MODIFICATION : Cacher le loader et afficher la zone de texte au premier chunk
          $('#llmLoadingState').hide();
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
    console.log("Rendering state:", state);
    elements.searchResultsList.empty();
    state.searchResults.forEach((result) => {
      const relevanceHtml = getRelevanceCard(result.confidence / 100);
      const sourceBadgeHtml = getSourceBadge(result.source);

      const resultCardHtml = `
        <div class="bg-white rounded-lg border border-custom-clair-2 hover:shadow-lg transition-all duration-300 hover:border-custom-bleu group p-4 flex flex-col justify-between">
          <div class="space-y-3 mb-4">
              <div class="flex items-start justify-between gap-2">
                  <h3 class="font-semibold text-base leading-tight text-custom-noir transition-colors" data-id_produit="${result.id_produit}">${result.title}</h3>
                  <a href="${result.url}" target="_blank" rel="noopener noreferrer" class="h-8 w-8 flex-shrink-0 flex items-center justify-center rounded-full hover:bg-blue-100">
                    <i data-lucide="external-link" class="h-4 w-4 text-custom-gris group-hover:text-blue-700"></i>
                  </a>
              </div>
              <div class="flex flex-wrap gap-2">
                  ${sourceBadgeHtml}
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                    <i data-lucide="tag" class="h-3 w-3"></i>
                    <span>${result.category}</span>
                  </span>
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                    <i data-lucide="building-2" class="h-3 w-3"></i>
                    <span>${result.supplier}</span>
                  </span>
                  <span class="flex items-center gap-1.5 px-2 py-1 bg-custom-clair-3 text-custom-gris text-xs rounded-full">
                    <i data-lucide="building-2" class="h-3 w-3"></i>
                    <span>Chunk : ${result.chunk_info}</span>
                  </span>
              </div>
              <div>
                <p id="snippet-${result.id}" class="text-sm text-custom-gris leading-relaxed line-clamp-3 transition-all duration-300">${result.snippet || ""}</p>
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


  // Initialisation de l'application
  initializeFormState();
  initializeSelect2();
  initializeDatePicker();
  initializeEventListeners();
  updateUI();
  lucide.createIcons();
});