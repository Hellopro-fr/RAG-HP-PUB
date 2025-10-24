<?php
header('Content-Type: text/html; charset=UTF-8');
require_once($_SERVER['DOCUMENT_ROOT'] . "/admin/secure/check_session.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/include/connexion.php');
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_hellopro.php');
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_generales.php');
require_once($_SERVER['DOCUMENT_ROOT'] . "design_system/fonctions/fonctions_composants.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');

function getWhereCms($first_url , $where_sql = true)
{
    global $info_cms;
    if(!empty($info_cms)) {
        return $where_sql ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : $info_cms;
    }
    $hostname = parse_url($first_url)['host'];

    $repertoire_cmseek = $_SERVER['DOCUMENT_ROOT']  . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/cmseek/";
    $path = $repertoire_cmseek . 'Result/'.$hostname.'/cms.json'; 
    //TODO : ONLY DEV
    // if(file_exists($path)) {
    //     $info_cms = file_get_contents($path);
    //     return $where_sql ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : $info_cms;
    // }    

    shell_exec('cd '. $repertoire_cmseek .' && yes | python3 cmseek.py -u '.$first_url );
    $path = $repertoire_cmseek . 'Result/'.$hostname.'/cms.json';            
    $info_cms = file_get_contents($path);
    return $where_sql ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : $info_cms;
    
}

function insertCrawling($domaine , $data , $info_cms = "" )
{
    $sql_select_dspi = "
        SELECT 
            id_domaine_scrapping_produit_ia,cms_dspi            
        FROM 
            domaine_scrapping_produit_ia DSPI
        WHERE 
            DSPI.domaine_dspi = '" . hellopro_traitement_donnee_annuaire_bo($domaine) . "'
    ";

    $res_dspi = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_select_dspi)  or die(hellopro_mysql_error($sql_select_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $where_cms = "";
    $first_url = $data['homepage'];
    if(mysqli_num_rows($res_dspi) > 0) 
    {
        $lig = mysqli_fetch_assoc($res_dspi);
        $id_dspi = $lig["id_domaine_scrapping_produit_ia"];
        $cms_dspi = $lig["cms_dspi"];
        
        if(empty($cms_dspi))
        {            
            $where_cms = !empty($info_cms) ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : getWhereCms($first_url);
        }

        $sql_insert_dspi = "
            UPDATE 
                domaine_scrapping_produit_ia
            SET                 
                statut_dspi = '1',
                utilisateur_dspi = '{$_SESSION['user_bo']}',
                data_crawling_dspi = '". hellopro_traitement_donnee_annuaire_bo(json_encode($data , JSON_UNESCAPED_UNICODE))."'
                " . $where_cms . "
            where 
                id_domaine_scrapping_produit_ia = '".$id_dspi."'
        ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_dspi) or die(hellopro_mysql_error($sql_insert_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    }
    else
    {
        //insertion d'un societe si le domaine n'est pas passé par l'identification prospect
        $sql_societe = "INSERT INTO 
                            societe
                        SET
                            etat_societe = '3',
                            id_type_societe_contrat = '5',
                            date_creation_societe = NOW()   ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_societe) or die(hellopro_mysql_error($sql_societe, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $id_soc = mysqli_insert_id($GLOBALS['LINK_MYSQLI_HELLOPRO_IA']);

        $sql_soc_url = "INSERT INTO 
                            societe_url
                        SET
                            id_societe_su = '" . hellopro_traitement_donnee_annuaire_bo($id_soc) . "',
                            url_su = '" . hellopro_traitement_donnee_annuaire_bo($data['homepage']) . "',
                            type_url_su = '0' ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_soc_url) or die(hellopro_mysql_error($sql_soc_url, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
                        

        $where_cms = !empty($info_cms) ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : getWhereCms($first_url);
        $sql_insert_dspi = "
            INSERT INTO 
                domaine_scrapping_produit_ia
            SET 
                domaine_dspi = '" . hellopro_traitement_donnee_annuaire_bo($domaine) . "',
                date_creation_dspi = NOW(),
                statut_dspi = '1',
                utilisateur_dspi = '{$_SESSION['user_bo']}',
                id_societe_dspi = '" . hellopro_traitement_donnee_annuaire_bo($id_soc) . "',
                data_crawling_dspi = '". hellopro_traitement_donnee_annuaire_bo(json_encode($data , JSON_UNESCAPED_UNICODE))."'
                " . $where_cms . "
        ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_dspi) or die(hellopro_mysql_error($sql_insert_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $id_dspi = mysqli_insert_id($GLOBALS['LINK_MYSQLI_HELLOPRO_IA']);

        
    }


    $sql_enqueue = "INSERT INTO 
            enqueue_crawling_ia
        SET
            id_domaine_scrapping_produit_ia =  '" . hellopro_traitement_donnee_annuaire_bo($id_dspi) . "',
            statut_crawler_eci = '0',
            statut_scraper_eci = '3',
            method_detect_eci = 'auto'
        ON DUPLICATE KEY UPDATE 
        id_domaine_scrapping_produit_ia =  '" . hellopro_traitement_donnee_annuaire_bo($id_dspi) . "'
            ";
    mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_enqueue) or die(hellopro_mysql_error($sql_enqueue, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));


    return  [
        "id_domaine" => $id_dspi ,
        "id_societe" => $id_soc
    ];
}

function verifHttp($url)
{
    if (!preg_match("/^(http:\/\/|https:\/\/|ftp:\/\/)/", $url))
    {
        $url = "https://" .ltrim($url , ':/');
    }
    return $url;
}

function detailsDomaine($domaine_strict , $domaine_non_strict)
{
    $tab_domaine = [
        1 => $domaine_strict,
        2 => $domaine_non_strict
    ];

    $lig = [];
    foreach($tab_domaine as $key => $value)
    {
        
        if(empty($lig["scrapping_produit"]))
        {
            //recherche si c'est déja crawler
            $sql_select_dspi = "
                SELECT 
                    DSPI.id_domaine_scrapping_produit_ia AS id,
                    DSPI.statut_dspi, 
                    DSPI.domaine_dspi        
                FROM 
                    domaine_scrapping_produit_ia DSPI
                WHERE 
                    DSPI.domaine_dspi = '" . hellopro_traitement_donnee_annuaire_bo($value) . "'
            ";

            $res_dspi = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_select_dspi)  or die(hellopro_mysql_error($sql_select_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            if(mysqli_num_rows($res_dspi) > 0)
            {
                $lig["scrapping_produit"] = mysqli_fetch_assoc($res_dspi);
            }
        
        }
        if(empty($lig["identification_prospects"]))
        {
            //recherche si ce domaine est déja passé sur identification prospect
            $sql_domaine_ip = "SELECT
                            id_domaine_identification_prospects AS id,
                            eligibilite_dip,
                            domaine_dip,
                            AIP.etat_aip
                        FROM
                            domaine_identification_prospects DIP
                            INNER JOIN action_identification_prospects AIP ON AIP.id_action_identification_prospects = DIP.id_aip_dip
                            WHERE domaine_dip = '" . hellopro_traitement_donnee_annuaire_bo($value) . "' ";
            $res_domaine_ip = mysqli_query($GLOBALS["LINK_MYSQLI_HELLOPRO_IA"], $sql_domaine_ip) or die(hellopro_mysql_error($sql_domaine_ip, $GLOBALS["LINK_MYSQLI_HELLOPRO_IA"]));
            if (mysqli_num_rows($res_domaine_ip) > 0)
            {
                $lig["identification_prospects"] = mysqli_fetch_assoc($res_domaine_ip);
            }
        }
    }

    return $lig;
}

$res = [
    "success" => false,
    "message" => "Donnée du crawling vide"
];

//patterns cms gérer 
$cms_gerer = [
    "PrestaShop",
    "WIX Website Builder",
    "TYPO3 CMS",
    "Shopify",
    "Magento",
    "Drupal",
    "WordPress",
];

$pattern_cms = "/(" . preg_replace("/\s+/", "\s*", implode("|", $cms_gerer)) . ")/i";

if (!empty($_POST['data']) )
{
    $data = $_POST['data'];
    $data['homepage'] = trim($data['homepage']);
    $domaine = !empty($data['domaine']) ? $data['domaine'] : recupere_domaine($data['homepage']);
    if(empty($data['domaine'])) {
        unset($data['domaine']);
    }

    $data['homepage'] = verifHttp($data['homepage']);


    $info_cms = $data['info_cms'];
    unset($data['info_cms']);    
    
    $tab_dspi = insertCrawling($domaine , $data , $info_cms );
    
    //lancer crawler suivant
    launchEnqueueCrawler();

    //lancer qualification ia
    launchQualificationIa([ "id_societe" => $tab_dspi['id_societe'] ]);

    $res = [
        "success" => true,
        "message" => "",
    ];
    
    
}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'get_cms')
{
    $first_url = $_POST['first_url'];
    if(!empty($first_url))
    {
        $info_cms = getWhereCms($first_url , false);
        $data_cms =  json_decode($info_cms , true);
        
        if(!empty($data_cms['cms_name']))
        {
            $data_cms['cms_name'] = (preg_match($pattern_cms , $data_cms['cms_name'])) ? 
                $data_cms['cms_name'] . ' <span class="font-color-vert"> (CMS géré) </span>' :
                $data_cms['cms_name'] . ' <span class="font-color-orange"> (CMS non géré) </span>';
        }

        $res = [
            "success" => true,
            "cms" => $data_cms['cms_name'],
            "info_cms" => $info_cms
        ];        
    }
}
elseif(isset($_FILES['csvFile']) && $_FILES['csvFile']['error'] == UPLOAD_ERR_OK  && $_POST['action'] == 'verif_upload')
{
    $fileTmpPath = $_FILES['csvFile']['tmp_name'];
    $fileName = $_FILES['csvFile']['name'];
    $fileSize = $_FILES['csvFile']['size'];
    $fileType = $_FILES['csvFile']['type'];

    $extension = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
    if($extension != 'csv') {
        $res = [
            "success" => false,
            "message" => "Fichier uploadé n'est pas un csv"
        ];
    }
    else
    {
        if (($handle = fopen($fileTmpPath, 'r')) !== false) {
            $data = $all_cms_G = $all_cms_NG = [];
            $total = $url_ok = $url_nok = $cms_G = $cms_NG = $sans_cms = $non_eligible = 0;

            while (($ligne = fgetcsv($handle, 1000000, ";")) !== false) {  
                $total++;
                $erreur = [];
                $homepage = trim($ligne[0]);
                $domaine = $spec_domaine = trim($ligne[1]);

                //verification du homepage 
                $homepage = verifHttp($homepage);
                
                if(!isFonctionalUrl($homepage))
                {
                    $erreur[] = "Le homepage n'est pas un url valide";
                }
                
                //verification du domaine spécifique
                if(!empty($domaine))
                {
                    if(!stripos($homepage, $domaine))
                    {
                        $erreur[] = "Le domaine spécifique n'est pas présent dans le homepage";
                        $domaine = recupere_domaine($homepage);
                    }
                }
                else
                {
                    $domaine = recupere_domaine($homepage);
                }

                //verification etat domaine
                $domaine_non_strict = recupere_domaine_n_strict($homepage);

                if(empty($domaine))
                {
                    $erreur[] = "Erreur de réécuperation de domaine sur la page d'acceuil";
                }

                $is_non_eligible = false;
                $info_domaine = detailsDomaine($domaine , $domaine_non_strict);
                if(!empty($info_domaine["scrapping_produit"]['id']))
                {
                    $erreur[] = "Ce domaine est déjà crawler";
                }
                else if(!empty($info_domaine["identification_prospects"]['id']))
                {
                    $etat_aip    = $info_domaine["identification_prospects"]["etat_aip"];
                    $eligibilite = $info_domaine["identification_prospects"]["eligibilite_dip"];
                    if($etat_aip == 2)
                    {
                        if($eligibilite == 1)
                        {
                            $erreur[] = "Ce domaine est déjà tésté par l'identification, et est déjà éligible. La récuperation des fiches produits est déjà en cours";
                        }
                        else
                        {
                            $is_non_eligible = true;
                        }
                    }
                    else
                    {
                        $erreur[] = "Ce domaine est déjà en cours d'identification prospects.";
                    }
                    
                }

                $list_soc = est_deja_existe_bo($homepage);
                if(!empty($list_soc))
                {
                    $erreur[] = "Ce domaine est déjà existant dans la base BO";
                }

                //verification cms 
                $info_cms = "";               

                if(empty($erreur)){
                    $info_cms =  getWhereCms($homepage, false);
                    $data_cms =  json_decode($info_cms , true);

                    $url_ok++;
                    $index_data = "";
                    if($is_non_eligible)
                    {
                        $non_eligible++;
                        $index_data = "non_eligible";
                    }
                    else if(empty($data_cms['cms_name']))
                    {
                        $sans_cms++;
                        $index_data = "sans_cms";
                    }
                    else if(preg_match($pattern_cms , $data_cms['cms_name']))
                    {
                        $cms_G++;
                        $all_cms_G[] = $data_cms['cms_name'];
                        $index_data = "cms_gerer";
                    }
                    else{
                        $cms_NG++;
                        $all_cms_NG[] = $data_cms['cms_name'];
                        $index_data = "cms_non_gerer";
                    }

                    $data[$index_data][$data_cms['cms_name']][] = [
                        'homepage' => $homepage,
                        'domaine' => !empty($spec_domaine) ? $spec_domaine : $domaine,
                        // 'robots' => $robots,
                        // 'url_produit' => $url_produit,
                        // 'url_non_produit' => $url_non_produit,
                        "info_cms" => $info_cms,
                        "cms" => $data_cms['cms_name'],
                        'erreur' => $erreur
                    ];

                    

                }
                else{
                    $url_nok++;

                    $erreur = array_unique($erreur);
                    $data['erreur'][] = [
                        "site" => $homepage,
                        'erreur' => $erreur,
                        'ligne' => $total
                    ];
                }                
                
            }

            //affichage des retours
            $data["all_cms_G"] = $all_cms_G;
            $data["all_cms_NG"] = $all_cms_NG;

            $occurence_cms_G =  array_count_values($all_cms_G); 
            $html_cms_gerer = [];
            foreach ($occurence_cms_G as $cms => $nb)
            {
                $html_cms_gerer[] = <<<HTML_CONTENT
                                        <span class="badge badge-primary  cms-check checked">    
                                            <input type="checkbox" name="cms-gerer" class="cms-gerer" value="{$cms}" checked>                                                
                                            {$cms}
                                            <span class="number bg-color-bleu border-radius-8 font-color-white">{$nb}</span>
                                        </span>
                HTML_CONTENT;
            }

            $html_cms_gerer = implode('' , $html_cms_gerer);

            $html_cms_non_gerer = implode(", " , array_unique($all_cms_NG));


            $aff_erreur = " d-none ";            
            $html_cms_erreur = [];
            if(!empty($data['erreur']))
            {
                $aff_erreur = "";
                foreach ($data['erreur'] as $info_erreur)
                {
                    $html_erreur = [];
                    foreach ($info_erreur['erreur'] as $str_erreur)
                    {
                        $html_erreur[] = <<<HTML_CONTENT
                                                <span class="font-color-rouge">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; → {$str_erreur}</span>
                        HTML_CONTENT;
                    }
                    $html_erreur = implode('' , $html_erreur);

                    $data_html["title"] = 'Site : <a target="_blank" href="' . $info_erreur['site'] . '" class="font-color-bleu">' . $info_erreur['site'] . '</a>' . ', <span class="font-color-gris"> dans la ligne <strong>' . $info_erreur['ligne'] . '</strong></span>';
                    $data_html["html_content"] = <<<HTML_CONTENT
                            <div class="d-flex justify-content-center gp-4 flex-d-column w-100">
                                {$html_erreur}
                            </div>
                    HTML_CONTENT;
                    ob_start();
                    dropdown_v1($data_html, false, ["border-radius-8", "bigger-chevron", "font-16"], "div", ["font-16", "font-color-noir" ]);  
                    $html_cms_erreur[] = ob_get_contents() ;
                    ob_end_clean();
                    
                }

            }
            $html_cms_erreur = implode('' , $html_cms_erreur);


            //création du détail des site ok
            $html_details_ok = [];
            foreach ($data["cms_gerer"] as $cms_name => $list_ok)
            {
                $html_list_ok = [];
                foreach ($list_ok as $site_ok)
                {                    
                    $html_list_ok[] = <<<HTML_CONTENT
                            <a target="_blank" href="{$site_ok['homepage']}" class="font-color-bleu ml-24  w-fit-content">- {$site_ok['homepage']}</a>
                    HTML_CONTENT;                        
                                            
                }     
                $html_list_ok = implode('' , $html_list_ok);

                $data_html["title"] = $cms_name;
                $data_html["html_content"] = <<<HTML_CONTENT
                        <div class="d-flex justify-content-center gp-4 flex-d-column w-100">
                            {$html_list_ok}
                        </div>
                HTML_CONTENT;
                ob_start();
                dropdown_v1($data_html, false, ["border-radius-8", "bigger-chevron", "font-16"], "div", ["font-16", "font-color-noir" ]);  
                $html_details_ok[] = ob_get_contents() ;
                ob_end_clean();                 
            } 
            foreach (["non_eligible" , "sans_cms" , "cms_non_gerer"] as $index_ok)
            {
                if(empty($data[$index_ok])) continue;
                $html_list_ok = [];
                foreach ($data[$index_ok] as $cms_name => $list_ok)
                {               
                    if(!empty($cms_name)){
                        $html_list_ok[] = '<span class="font-color-noir font-weight-600 ml-8 mt-8">'.$cms_name.'</span>';
                    }     
                    foreach ($list_ok as $site_ok)
                    {                    
                        $html_list_ok[] = <<<HTML_CONTENT
                                <a target="_blank" href="{$site_ok['homepage']}" class="font-color-bleu ml-24  w-fit-content">- {$site_ok['homepage']}</a>
                        HTML_CONTENT;                        
                                            
                    }   
                }  
                $html_list_ok = implode('' , $html_list_ok);

                $data_html["title"] = $index_ok == "non_eligible" ? "Domaine déjà tésté par l'identification prospects IA et n'est pas éligible" : ( $index_ok == "sans_cms" ? "Sans CMS" : "Autre CMS" ) ;
                $data_html["html_content"] = <<<HTML_CONTENT
                        <div class="d-flex justify-content-center gp-4 flex-d-column w-100">
                            {$html_list_ok}
                        </div>
                HTML_CONTENT;
                ob_start();
                dropdown_v1($data_html, false, ["border-radius-8", "bigger-chevron", "font-16"], "div", ["font-16", "font-color-noir" ]);  
                $html_details_ok[] = ob_get_contents() ;
                ob_end_clean();                 
                                
            }
                
            $html_details_ok = implode('' , $html_details_ok);

            //si n'as pas d'url ok , sans cms , autres cms
            $hide_bloc_ok = $url_ok == 0 ? " d-none " : "";
            $hide_sans_cms = $sans_cms == 0 ? " d-none " : "";
            $hide_cms_NG = $cms_NG == 0 ? " d-none " : "";
            $hide_cms_G = $cms_G == 0 ? " d-none " : "";
            $hide_non_eligible = $non_eligible == 0 ? " d-none " : "";

            //bloc btn lancer scrapping
            $html_btn_valide = "";
            if($url_ok > 0)
            {
                $html_btn_valide = <<<HTML_CONTENT
                        <div class="btn btn-primary ml-auto mr-auto mt-16 " id="lancer-crawling-csv">
                            Débuter le crawling des sites
                        </div>
                HTML_CONTENT;
            }

            
            $html_retour = <<<HTML_CONTENT
                        <div id="recap_upload" class="d-flex flex-d-column gp-16 p-relative px-24 py-16">
                            <div class="font-color-noir font-weight-600 w-100">
                                Votre upload: <span class="nom-upload font-color-gris">{$fileName}</span>
                            </div>                              
                            <div class="d-flex flex-d-column gp-12">
                                <span class="font-color-noir font-weight-600">Récapitulation :</span>
                                <div class="stat-upload d-flex gp-12 f-wrap">
                                    <span class="badge badge-primary">
                                        <span class="number bg-color-bleu border-radius-8 font-color-white">{$total}</span>
                                        Site identifié
                                    </span>
                                    <span class="badge badge-success">
                                        <span class="number bg-color-vert border-radius-8 font-color-white">{$url_ok}</span>
                                        Site ok
                                    </span>
                                    <span class="badge badge-danger">
                                        <span class="number bg-color-rouge border-radius-8 font-color-white">{$url_nok}</span>
                                        Site avec erreur
                                    </span>
                                </div>
                                <div class="border-1 border-color-vert border-radius-8 d-flex flex-d-column gp-12 p-8 stat-cms-upload p-relative {$hide_bloc_ok} ">
                                    <i class="bx bxs-up-arrow"></i>
                                    <div class="align-items-end d-flex f-wrap gp-12">  
                                        <div class="d-flex flex-d-column">
                                            <span class="badge badge-success align-self-center  mb-12">
                                                <span class="number bg-color-vert border-radius-8 font-color-white">{$cms_G}</span>
                                                CMS géré
                                            </span>
                                            <div class=" stat-cms-gerer border-1 border-color-gris-blanc border-radius-8 d-flex f-wrap gp-8 p-6 p-relative {$hide_cms_G}  ">
                                                <i class="bx bxs-up-arrow"></i>
                                                
                                                {$html_cms_gerer}
                                                                                            
                                            </div>
                                        </div>                                        
                                        <span class="badge badge-warning mb-12 cms-check {$hide_cms_NG}" title = "{$html_cms_non_gerer}">
                                            <input type="checkbox" id="autres-cms" name="autres-cms" class="autres-cms">                                            
                                            Autre CMS
                                            <span class="number bg-color-orange border-radius-8 font-color-white">{$cms_NG}</span>
                                        </span>
                                        <span class="badge badge-danger mb-12 cms-check {$hide_sans_cms}">   
                                            <input type="checkbox" id="sans-cms" name="sans-cms" class="sans-cms">                                            
                                            Sans CMS
                                            <span class="number bg-color-rouge border-radius-8 font-color-white">{$sans_cms}</span>
                                        </span>
                                        <span class="badge badge-warning mb-12 cms-check {$hide_non_eligible}">
                                            <input type="checkbox" id="non-eligible" name="non-eligible" class="non-eligible">                                            
                                            Domaine tésté par l'identification prospects IA et n'est pas éligible
                                            <span class="number bg-color-orange border-radius-8 font-color-white">{$non_eligible}</span>
                                        </span>
                                    </div>
                                    <div class="d-flex flex-d-column">
                                        <span class="badge badge-primary border-radius-8 c-pointer instruction-lib"><i class="bx bxs-info-circle"></i> Cliquez pour voir les détails des sites OK</span>
                                        <div class="instruction">
                                            {$html_details_ok}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="d-flex flex-d-column gp-12 mt-12 {$aff_erreur}">
                                <span class="font-color-rouge font-weight-600">Voici la liste des erreurs :</span>
                                {$html_cms_erreur}
                            </div>
                        </div>
                        {$html_btn_valide}
            HTML_CONTENT;

            $res = [
                "success" => true,
                "data" => $data,
                "html" => $html_retour
            ];
        }
        else{
            $res = [
                "success" => false,
                "message" => "Impossible de lire le fichier"
            ];
        }
    }
}
elseif(isset($_FILES['csvFile']) && $_FILES['csvFile']['error'] == UPLOAD_ERR_OK  && $_POST['action'] == 'crawl_csv')
{

    $a_crawler = $_POST['crawler'];
    $a_crawler = json_decode($a_crawler, true);

    $fileTmpPath = $_FILES['csvFile']['tmp_name'];
    $fileName = $_FILES['csvFile']['name'];
    $fileSize = $_FILES['csvFile']['size'];
    $fileType = $_FILES['csvFile']['type'];
    $extension = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
    if($extension != 'csv') {
        $res = [
            "success" => false,
            "message" => "Fichier uploadé n'est pas un csv"
        ];
    }
    else
    {
        $annee = date("Y");
        $mois = date("m");
        $jour = date("d");
        $repertoire = "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fichiers/{$annee}/{$mois}/{$jour}/";
        if (!is_dir($_SERVER['DOCUMENT_ROOT'] . $repertoire)) {
            if (!mkdir($_SERVER['DOCUMENT_ROOT'] . $repertoire, 0777, true)) {
                return false;
            }
        }
        $name = date("Y-m-d-H-i-s") . "-{$_SESSION['user_bo']}-{$fileName}";
        if (move_uploaded_file($fileTmpPath, $_SERVER["DOCUMENT_ROOT"] . $repertoire . $name)) {
            $sql_insert_uspi = "
                    INSERT INTO 
                        upload_scrapping_produit_ia
                    SET 
                        chemin_csv_uspi = '{$repertoire}{$name}',
                        id_utilisateur_uspi = '{$_SESSION['user_bo']}',
                        date_upload_uspi = NOW(),
                        etat_uspi = '1'
            ";
            mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_uspi) or die(hellopro_mysql_error($sql_insert_uspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            $id_uspi = mysqli_insert_id($GLOBALS['LINK_MYSQLI_HELLOPRO_IA']);

            if (($handle = fopen($_SERVER["DOCUMENT_ROOT"] . $repertoire . $name, 'r')) !== false) {     
                
                $data = $list_id = $list_id_societe = [];
                $url_ok = 0;
                while (($ligne = fgetcsv($handle, 1000000, ";")) !== false) 
                {  
                    
                    $erreur = [];
                    $homepage = trim($ligne[0]);
                    $domaine = $spec_domaine = trim($ligne[1]);
                    
    
                    //verification du homepage 
                    $homepage = verifHttp($homepage);

                    if(!isFonctionalUrl($homepage))
                    {
                        $erreur[] = "Le homepage n'est pas un url valide";
                    }
                    
                    //verification du domaine spécifique
                    if(!empty($domaine))
                    {
                        if(!stripos($homepage, $domaine))
                        {
                            $erreur[] = "Le domaine spécifique n'est pas présent dans le homepage";
                            $domaine = recupere_domaine($homepage);
                        }
                    }
                    else
                    {
                        $domaine = recupere_domaine($homepage);
                    }
    
                    //verification etat domaine
                    $domaine_non_strict = recupere_domaine_n_strict($homepage);

                    if(empty($domaine))
                    {
                        $erreur[] = "Erreur de réécuperation de domaine sur la page d'acceuil";
                    }

                    $is_non_eligible = false;
                    $info_domaine = detailsDomaine($domaine , $domaine_non_strict);
                    if(!empty($info_domaine["scrapping_produit"]['id']))
                    {
                        $erreur[] = "Ce domaine est déjà crawler";
                    }
                    else if(!empty($info_domaine["identification_prospects"]['id']))
                    {
                        $etat_aip    = $info_domaine["identification_prospects"]["etat_aip"];
                        $eligibilite = $info_domaine["identification_prospects"]["eligibilite_dip"];
                        if($etat_aip == 2)
                        {
                            if($eligibilite == 1)
                            {
                                $erreur[] = "Ce domaine est déjà tésté par l'identification, et est déjà éligible. La récuperation des fiches produits est déjà en cours";
                            }
                            else
                            {
                                $is_non_eligible = true;
                            }
                        }
                        else
                        {
                            $erreur[] = "Ce domaine est déjà en cours d'identification prospects.";
                        }
                        
                    }

                    $list_soc = est_deja_existe_bo($homepage);
                    if(!empty($list_soc))
                    {
                        $erreur[] = "Ce domaine est déjà existant dans la base BO";
                    }
                    
        
                    //verification cms 
                    $info_cms = "";
                    
                    if(empty($erreur)){

                        $info_cms =  getWhereCms($homepage, false);
                        $data_cms =  json_decode($info_cms , true);
                        
                        $url_ok++;
                        $index_data = "";
                        if($is_non_eligible)
                        {
                            $index_data = "non_eligible";
                        }
                        else if(empty($data_cms['cms_name']))
                        {
                            $index_data = "sans_cms";
                        }
                        else if(preg_match($pattern_cms , $data_cms['cms_name']))
                        {
                            $index_data = $data_cms['cms_name'];
                        }
                        else{
                            $index_data = "cms_non_gerer";
                        }

                        //crawler seulement ceux cocher
                        if(in_array($index_data , $a_crawler))
                        {
                            $data = [
                                'homepage' => $homepage,
                                // 'robots' => $robots,
                                // 'url_produit' => $url_produit,
                                // 'url_non_produit' => $url_non_produit,
                                'upload' => $id_uspi
                            ];
                            if(!empty($spec_domaine))
                            {
                                $data['domaine'] = $spec_domaine;
                            }
                            $data_dspi =  insertCrawling($domaine , $data , $info_cms);
                            $list_id[] = $data_dspi;
                            $list_id_societe[] = $data_dspi['id_societe'];
                        }
    
                    }  
                }
            }
        }     

        //lancer crawler suivant
        launchEnqueueCrawler();

        //lancer quaification ia
        launchQualificationIa([ "id_societe" => $list_id_societe ]);

        $res = [
            "success" => true,
            "list_id" => $list_id
        ];
    }
}
elseif(isset($_FILES['csvFile']) && $_FILES['csvFile']['error'] == UPLOAD_ERR_OK  && $_POST['action'] == 'script_crawl_csv')
{

    $a_crawler = $_POST['crawler'];
    $a_crawler = json_decode($a_crawler, true);

    $scope_crawl = $_POST['scope_crawl'];

    $fileTmpPath = $_FILES['csvFile']['tmp_name'];
    $fileName = $_FILES['csvFile']['name'];
    $fileSize = $_FILES['csvFile']['size'];
    $fileType = $_FILES['csvFile']['type'];
    $extension = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
    if($extension != 'csv') {
        $res = [
            "success" => false,
            "message" => "Fichier uploadé n'est pas un csv"
        ];
    }
    else
    {
        $res = [
            "success" => false,
            "message" => "Erreur d'upload du csv"
        ];

        $annee = date("Y");
        $mois = date("m");
        $jour = date("d");
        $repertoire = "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fichiers/{$annee}/{$mois}/{$jour}/";
        if (!is_dir($_SERVER['DOCUMENT_ROOT'] . $repertoire)) {
            if (!mkdir($_SERVER['DOCUMENT_ROOT'] . $repertoire, 0777, true)) {
                return false;
            }
        }
        $name = date("Y-m-d-H-i-s") . "-{$_SESSION['user_bo']}-{$fileName}";
        if (move_uploaded_file($fileTmpPath, $_SERVER["DOCUMENT_ROOT"] . $repertoire . $name)) {
            $sql_insert_uspi = "
                    INSERT INTO 
                        upload_scrapping_produit_ia
                    SET 
                        chemin_csv_uspi = '{$repertoire}{$name}',
                        id_utilisateur_uspi = '{$_SESSION['user_bo']}',
                        date_upload_uspi = NOW(),
                        etat_uspi = '1'
            ";
            mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_uspi) or die(hellopro_mysql_error($sql_insert_uspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            $id_uspi = mysqli_insert_id($GLOBALS['LINK_MYSQLI_HELLOPRO_IA']);

            $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
            
            
        
            $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_launch_crawl_csv' . date('Ymdhis') . '.log';
            $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 3 '" . $server_name . "/script/chatgpt/script_launch_crawl_csv.php?id_upload=" . $id_uspi . "&scope_crawl=" . $scope_crawl . "&a_crawler=". implode(";" , $a_crawler )."' -a '" . $test_temp . "'";
            $a = shell_exec($command);
            
            $res = [
                "success" => true,
                "message" => "Lancement du crawling du fichier csv en cours"
            ];
        }
    }

    
}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'get_param_crawler')
{
    $tab_param_exclu = ["nb_variante","nb_domaine_par_serp"];

    $sql_param = "SELECT
        id_parametre_crawler_ia, nom_pci , valeur_pci, variable_crawler_pci , min_valeur_pci
    FROM parametre_crawler_ia";
    $res_param = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_param) or die(hellopro_mysql_error($sql_param, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $html_param = [];
    while ($ligne = mysqli_fetch_assoc($res_param)) {

        if(in_array($ligne["variable_crawler_pci"],$tab_param_exclu)) {
            continue;
        }

        $text_supp = $ligne['min_valeur_pci'] == 0 ? " (0 si pas de limite)" : "";
        $html_param[] = <<<HTML_CONTENT
                                <div class="form-group  w-100"> 
                                    <label class="label">{$ligne['nom_pci']} <i class="font-color-orange">*{$text_supp}</i></label>
                                    <input type="number" name="param-{$ligne['variable_crawler_pci']}" class="parametre-crawler" data-variable="{$ligne['variable_crawler_pci']}" value="{$ligne['valeur_pci']}" min="{$ligne['min_valeur_pci']}" placeholder="Entrer la valeur"> 
                                    <span class="badge badge-danger d-none"><i class="bx bxs-x-circle"></i> Ce champ doit être renseigné</span>
                                </div>
                HTML_CONTENT;
    }

    $html_param = implode('' , $html_param);
    $res = <<<HTML_CONTENT
            <div class="d-flex justify-content-center align-items-center flex-d-column">
                {$html_param}
            </div>
            <div class="d-flex align-items-center gp-24">
                <div class="btn bg-color-bleu border-0 d-flex justify-content-center align-items-center gp-8 enrg-param-crawler">
                    Enregistrer
                </div>
                <div class="btn bg-color-rouge border-0 annuler-restaurer d-flex justify-content-center align-items-center gp-8"  data-modal="hide" data-target="modal_param_crawler">
                    Annuler
                </div>
            </div>
    HTML_CONTENT;

    echo $res;
    exit;
}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'set_param_crawler')
{
    $maxPerCrawl = $_POST['maxPerCrawl'];
    $maxPerMinute = $_POST['maxPerMinute'];

    $dataParams = $_POST['dataParams'];

    if(count($dataParams) > 0)
    {
        $where_update = "";
        foreach ($dataParams as $key => $value) {
            $where_update .= " WHEN variable_crawler_pci = '{$key}' THEN '" . hellopro_traitement_donnee_annuaire_bo($value) . "' ";
        }
        $sql_update = "
            UPDATE parametre_crawler_ia
            SET valeur_pci = CASE
                " . $where_update. "
            END
        ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update) or die(hellopro_mysql_error($sql_update, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $res = [
            "success" => true,
            "message" => "Paramètre enregistré"
        ];
    }
    else{
        $res = [
            "success" => false,
            "message" => "Paramètre manquant"
        ];
    }

}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'maj_domaine')
{
    $id                 = $_POST['id'];
    $url_produit        = $_POST['url_prod'];
    $url_non_produit    = $_POST['url_non_prod'];

    if(empty($url_produit) || empty($url_non_produit))
    {
        $res = [
            "success" => false,
            "message" => "Les urls fiches produits et non fiches produits sont obligatoires"
        ];
        echo json_encode($res);
        exit;
    }
    

    $sql_select_dspi = "
        SELECT 
            id_domaine_scrapping_produit_ia,cms_dspi  , data_crawling_dspi          
        FROM 
            domaine_scrapping_produit_ia DSPI
        WHERE 
            DSPI.id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id) . "'
    ";

    $res_dspi = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_select_dspi)  or die(hellopro_mysql_error($sql_select_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $where_cms = "";
    
    if(mysqli_num_rows($res_dspi) > 0) 
    {
        $lig = mysqli_fetch_assoc($res_dspi);
        $id_dspi = $lig["id_domaine_scrapping_produit_ia"];
        $data = json_decode($lig["data_crawling_dspi"] , true);
        $data['url_produit'] = $url_produit;
        $data['url_non_produit'] = $url_non_produit;

        $first_url = $url_produit[0];
        //mettre à jour l'information du cms
        if(empty($cms_dspi))
        {            
            $where_cms = !empty($info_cms) ? ", cms_dspi = '".hellopro_traitement_donnee_annuaire_bo($info_cms)."'" : getWhereCms($first_url);
        }


        $sql_insert_dspi = "
            UPDATE 
                domaine_scrapping_produit_ia
            SET                 
                statut_dspi = '11',
                utilisateur_dspi = '{$_SESSION['user_bo']}',
                data_crawling_dspi = '". hellopro_traitement_donnee_annuaire_bo(json_encode($data , JSON_UNESCAPED_UNICODE))."'
                " . $where_cms . "
            where 
                id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_dspi) . "'
        ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_dspi) or die(hellopro_mysql_error($sql_insert_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));


        //mettre à jours la fille d'attente
        $sql_upadate_eci = "
            UPDATE
                enqueue_crawling_ia
            SET
                statut_scraper_eci = '0',
                method_detect_eci = 'manuelle'
            WHERE
                id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_dspi) . "'
        ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_upadate_eci) or die(hellopro_mysql_error($sql_upadate_eci, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

        //lancer crawler suivant
        launchEnqueueCrawler("scraper");

        $res = [
            "success" => true,
            "message" => "Mise à jour réussi"
        ];
        //$action = "[Erreur identification fiches produits] - Action renseigner 5 url fiche produits et 5 urls non fiche produits";
        $action = 2;
        historique_action_utilisateur($_SESSION['user_bo'], $id_dspi, "", $action);
        maj_utilisateur_dspi($id_dspi, $_SESSION['user_bo']);
    }
    else{
        $res = [
            "success" => false,
            "message" => "Domaine non trouvé",
        
        ];
    }
    
    
}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'relaunch_crawl')
{

    $id_domaine         = $_POST['id_domaine'];
    $homepage           = $_POST['homepage'];
    $dropData           = $_POST['reset'];
    $skipQuestionMark   = $_POST['skipQuestionMark'];
    $skipDiez           = $_POST['skipDiez'];
    $bypassquestionmark = $_POST['bypassquestionmark'];
    $bypassdiez         = $_POST['bypassdiez'];
    $breaklimit         = $_POST['breaklimit'];
    $toKeep             = $_POST['toKeep'];
    $toRemove           = $_POST['toRemove'];
    
    if(empty($id_domaine) || empty($homepage))
    {
        $res = [
            "success" => false,
            "message" => "Domaine ou homepage non renseigné"
        ];
        echo json_encode($res);
        exit;
    }

    if (!empty(trim($toKeep)) && !empty(trim($toRemove))) {
        $res = [
            "success" => false,
            "message" => "Vous ne pouvez pas renseigner à la fois des paramètres à garder et des paramètres à supprimer"
        ];
        echo json_encode($res);
        exit;
    }

    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD

    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_relaunch_crawl_' . date('Ymdhis') . '.log';
    $params_query = http_build_query([
        'id'                 => $id_domaine,
        'homepage'           => $homepage,
        'dropData'           => $dropData,
        'skipQuestionMark'   => $skipQuestionMark,
        'skipDiez'           => $skipDiez,
        'bypassquestionmark' => $bypassquestionmark,
        'bypassdiez'         => $bypassdiez,
        'breaklimit'         => $breaklimit,
        'toKeep'             => $toKeep,
        'toRemove'           => $toRemove
    ]);
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -O - '" . $server_name . "/script/chatgpt/script_relaunch_crawling.php?{$params_query}' 2>> '" . $test_temp . "'";
    $a = shell_exec($command);
    //$action = "Action relancer le crawl";
    $action = 1;
    historique_action_utilisateur($_SESSION['user_bo'], $id_domaine, "", $action);
    maj_utilisateur_dspi($id_domaine, $_SESSION['user_bo']);


    if (!empty($a)) {
        $aJson = json_decode($a, true);

        if (json_last_error() !== JSON_ERROR_NONE) {
            $res = [
                "success" => false,
                "message" => "Erreur lors de la relance du crawl"
            ];
            echo json_encode($res);
            exit;
        }

        if ($aJson['success'] == 'error') {
            $res = [
                "success" => false,
                "message" => $aJson['message']
            ];
            echo json_encode($res);
            exit;
        } else {
            $res = [
                "success" => true,
                "message" => $aJson['message']
            ];
        }
    }
}
elseif(!empty($_POST['action'])  && $_POST['action'] == 'stop_crawl')
{

    $id_domaine = $_POST['id_domaine'];
    
    if(empty($id_domaine))
    {
        $res = [
            "success" => false,
            "message" => "Domaine non renseigné"
        ];
        echo json_encode($res);
        exit;
    }   
    
    $sql_domaine = "
        SELECT
            id_domaine_scrapping_produit_ia, domaine_dspi, systeme_dspi
        FROM
            domaine_scrapping_produit_ia DSPI
        WHERE
            DSPI.id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
    ";
    $res_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_domaine) or die(hellopro_mysql_error($sql_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    
    if($ligne_domaine = mysqli_fetch_assoc($res_domaine) )
    {
        if ((int)$ligne_domaine['systeme_dspi'] === SYSTEM_API) {
            // New API System
            $api_service = get_crawler_api_service();
            $api_response = $api_service->stopCrawl($id_domaine);

            if (isset($api_response['crawl_id'])) {
                $res = [
                    "success" => true,
                    "message" => "Signal d'arrêt envoyé au service de crawl.",
                ];
            } else {
                $res = [
                    "success" => false,
                    "message" => $api_response['message'] ?? "Erreur lors de l'arrêt du crawl via l'API."
                ];
            }
        } else {
            // Legacy System
            $domaine = $ligne_domaine['domaine_dspi'];
            $file = $_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/stopper/' . $domaine . '.txt';       

            if (file_exists($file)) {
                unlink($file);
            }   

            file_put_contents($file, "stop");

            $res = [
                "success" => true,
                "message" => "Arrêt du crawl (legacy) réussi",
            ];
        }
    }
    else{
        $res = [
            "success" => false,
            "message" => "Domaine non trouvé"
        ];       
    
    }

} 
elseif (!empty($_POST['action'])  && $_POST['action'] == 'config_crawl') {


    $id_domaine        = $_POST['id_domaine'];
    $sql_select_dspi = "
        SELECT 
            id_domaine_scrapping_produit_ia,cms_dspi  , data_crawling_dspi          
        FROM 
            domaine_scrapping_produit_ia DSPI
        WHERE 
            DSPI.id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
    ";

    $res_dspi = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_select_dspi)  or die(hellopro_mysql_error($sql_select_dspi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $data_crawling = [];
    if ($lig = mysqli_fetch_assoc($res_dspi)) {
        $id_dspi = $lig["id_domaine_scrapping_produit_ia"];
        $data = json_decode($lig["data_crawling_dspi"], true);
        $data_available = [
            'homepage'           => "Page d'accueil",
            'dropData'           => "Réinitialiser le crawl",
            'skipQuestionMark'   => "Ne pas garder les ?",
            'skipDiez'           => "Ne pas garder les #",
            'bypassquestionmark' => "Garder les ?",
            'bypassdiez'         => "Garder les #",
            'breaklimit'         => "Ignorer la limite nombre d'urls à crawler",
            'toKeep'             => "Paramètres à conserver",
            'toRemove'           => "Paramètres à supprimer",
            'url_produit'        => "URL fiches produits",
            'url_non_produit'    => "URL non fiches produits",
        ];
        //verifier si les données sont présentes
        foreach ($data_available as $key => $labelle) {
            if (isset($data[$key])) {

                $info_data = $data[$key];
                if ($data[$key] === 1) {
                    $info_data = "OUI";
                }
                if ($data[$key] === 0) {
                    $info_data = "NON";
                }
                if (is_array($data[$key])) {                   
                    $info_data = implode('<br> ', $data[$key]);
                }
                $data_crawling[] = "<div class='badge'><span class='font-16 font-weight-600'>" . $labelle . " : </span> <span class='font-14'>" . $info_data . "</span> </div>";
            }
        }
    }
    $html_data = implode('', $data_crawling);

    $html = <<<HTML_CONTENT
                <div class="d-flex flex-d-column gp-8">
                    ${html_data}
                </div>
    HTML_CONTENT;
    $res = [
        "success" => true,
        "html" => $html,
    ];
} 
elseif (!empty($_POST['action'])  && $_POST['action'] == 'relaunch_upload_csv') {
    $id_upload = $_POST['id_upload'];
    $scope_crawl = $_POST['scope_crawl'];
    if (empty($id_upload)) {
        $res = [
            "success" => false,
            "message" => "Identifiant de l'upload manquant"
        ];
        echo json_encode($res);
        exit;
    }

    $a_crawler = ["cms_gerer", "sans_cms", "cms_non_gerer"];

    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
    // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV


    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_launch_crawl_csv' . date('Ymdhis') . '.log';
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 3 '" . $server_name . "/script/chatgpt/script_launch_crawl_csv.php?id_upload=" . $id_upload . "&scope_crawl=" . $scope_crawl . "&a_crawler=" . implode(";", $a_crawler) . "' -a '" . $test_temp . "'";
    $a = shell_exec($command);

    $res = [
        "success" => true,
        "message" => "Relancement du crawling du fichier csv en cours"
    ];
} 
elseif (!empty($_POST['action'])  && $_POST['action'] == 'finish_upload_csv') {
    $id_upload = $_POST['id_upload'];

    if (empty($id_upload)) {
        $res = [
            "success" => false,
            "message" => "Identifiant de l'upload manquant"
        ];
        echo json_encode($res);
        exit;
    }

    sql_update_info(
        [
            "etat_uspi" => 2
        ],
        "upload_scrapping_produit_ia",
        [
            "id_upload_scrapping_produit_ia" => $id_upload
        ]
    );

    $res = [
        "success" => true,
        "message" => "Maj status Upload en terminé avec succès"
    ];
}


echo json_encode($res);