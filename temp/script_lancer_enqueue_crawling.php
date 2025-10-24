<?php
/**
 * @author Hosana
 * @date   09/01/2025
 * @todo   launcher des crawler et scraper
 */

// Définition de l'encodage par défaut
header('Content-Type: text/html; charset=UTF-8');

require_once($_SERVER['DOCUMENT_ROOT'] . '/include/connexion.php');
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "include/functions.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_hellopro.php');
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_generales.php');
require_once($_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');

/**Les differents valeurs du statuts
 * statut_scraper_eci : 
* 0 => non commencé
* 1 => en cours
* 2 => terminé 
* 3 => n'as pas de traitement scraper 
* 4 => erreur
* 
* statut_crawler_eci : 
* 0 => non commencé
* 1 => en cours
* 2 => terminé 
* 3 => partiellement términé
* 4 => erreur
 * 
 */

ini_set('memory_limit', '-1');
ini_set('max_execution_time',0); 
$id_script = 2298;
if(!isset($_GET["launcher"]) || empty(trim($_GET["launcher"])))
{
	debut_script($id_script);
}


function getNbRetry($id)
{
    $sql_retry = "SELECT
                    nb_retry_eci
                FROM enqueue_crawling_ia ECI
                WHERE id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id)."'
    ";
    $res_retry = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_retry) or die(hellopro_mysql_error($sql_retry, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $nb_retry = mysqli_fetch_assoc($res_retry);
   
    return $nb_retry['nb_retry_eci'];
}

function hasPending($type , $id = "")
{
    $where = $type == "scraper" ? "statut_scraper_eci" : "statut_crawler_eci";
    $where_id = !empty($id) ? " AND ECI.id_domaine_scrapping_produit_ia = " . $id : "";
    $sql_pending = "SELECT
        ECI.id_enqueue_crawling_ia,
            ECI.id_domaine_scrapping_produit_ia,
            " . $where . "
        FROM 
            enqueue_crawling_ia ECI
        INNER JOIN domaine_scrapping_produit_ia DSPI ON DSPI.id_domaine_scrapping_produit_ia = ECI.id_domaine_scrapping_produit_ia
        WHERE " . $where . " = 1 " . $where_id . "
    ";
    $res_pending = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_pending) or die(hellopro_mysql_error($sql_pending, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $nb_pending = mysqli_num_rows($res_pending);
   
    return $nb_pending;
}

$retour = "";
$crawlerLaunched = $scraperLaunced = 0;
$domaineScraper = "";
$pendingCrawler = hasPending("crawler");
$pendigScraper = hasPending("scraper");
$type = $_GET['type'];

/**
 * verification des pid crawler encours 
 * - Si pid n'esiste plus , et le domaine est encours de crawling, on met à jour le statut du domaine et de l'enqueue en erreur
 * - Si pid n'esiste plus , on supprime le fichier pid
 */

$processFiles = glob($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/processus/' . '*.txt'); // Trouve tous les fichiers JSON dans le répertoire

$domaine_retry = [];

foreach($processFiles as $processFile)
{
    $pid_content = file_get_contents($processFile);
    $tab_pid = explode("##", $pid_content);
    $pid = trim(explode(":",$tab_pid[0])[1]);
    $domain_pid = trim(explode(":",$tab_pid[1])[1]);
    $verif_pid =  shell_exec("ps -p $pid");
    if(!empty($verif_pid) && !stripos($verif_pid  , $pid ) && hasPending("crawler" , $domain_pid) > 0)
    {
        $data_maj =[ 
            "statut_crawler_eci" => 4,
            "date_continuation_eci" => "NULL"
        ];

        $retry = getNbRetry($domain_pid);
        if($retry == 0 || in_array($retry , [1 , 2 ]) )
        {
            $data_maj["date_continuation_eci"] = date('Y-m-d H:i');
            $data_maj["nb_retry_eci"] = $retry + 1;
            $domaine_retry[] = $domain_pid;
        }
        elseif($retry >= 3)
        {
            $mail_admin = getMailUserScraping($domain_pid);
            $mail_admin = !empty($mail_admin) ? "," . $mail_admin : "";
            $nom_domaine_pid = getDomaine($domain_pid);
            
            $server_name_bo = $GLOBALS['protocol_http_host_bo'] . "bo.hellopro.fr"; // PROD
	        $server_name_script = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
	
	        $scraping_tool_base_link = $server_name_bo . "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/index_V2.php";
	        $shell_crawling_base_link = $server_name_script . "/script/chatgpt/script_relaunch_crawling.php";

            $objet = "[ERREUR][SCRAPPING] - Crawling de domaine arrêté : Nombre maximum de relance atteint";
            $message = 'Bonjour,';
            $message .= "<br><br> Le script de crawling des urls du domaine <b><a href='{$scraping_tool_base_link}?domaine_dspi=contient|{$nom_domaine_pid}'>{$domain_pid} - {$nom_domaine_pid}</a></b> a échoué après 4 tentatives de crawling.";
            $message .= '<br><br>Cordialement';    
            
            envoyer_mail_scripts($objet, "", "script@hellopro.fr" . $mail_admin , $message, 1); //PROD
        }
        
        //maj statut enqueue => erreur
        sql_update_info(
            $data_maj,
            "enqueue_crawling_ia",
            [
                "id_domaine_scrapping_produit_ia" => $domain_pid
            ]
        );
        //maj statut domaine => erreur
        sql_update_info(
            [
                "statut_dspi" => 9
            ],
            "domaine_scrapping_produit_ia",
            [
                "id_domaine_scrapping_produit_ia" => $domain_pid
            ]
        );
        $pendingCrawler = hasPending("crawler");
        echo "erreur node";
    }
    
    if(!empty($verif_pid) && !stripos($verif_pid  , $pid )){
        unlink($processFile);
    }

}



/**
 * verification des pid scraper encours 
 * - Si pid n'esiste plus , et le domaine est encours de scraper, on met à jour le statut du domaine et de l'enqueue scraper en erreur
 * - Si pid n'esiste plus , on supprime le fichier pid
 */
$processFilesScraper = glob($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/processus/pid_fpnfp_' . '*.txt'); // Trouve tous les fichiers JSON dans le répertoire

foreach($processFilesScraper as $processScraper )
{
    $pid_content = file_get_contents($processScraper);
    $tab_pid = explode("##", $pid_content);
    $pid = trim(explode(":",$tab_pid[0])[1]);
    $domain_pid = trim(explode(":",$tab_pid[1])[1]);
    $verif_pid =  shell_exec("ps -p $pid");


    if(!empty($verif_pid) && !stripos($verif_pid  , $pid ))
    {
        if(hasPending("scraper" , $domain_pid) > 0)
        {
            //maj statut enqueue => erreur
            sql_update_info(
                [ 
                    "statut_scraper_eci" => 4
                ],
                "enqueue_crawling_ia",
                [
                    "id_domaine_scrapping_produit_ia" => $domain_pid
                ]
            );

            //maj statut domaine => erreur
            sql_update_info(
                [
                    "statut_dspi" => 9
                ],
                "domaine_scrapping_produit_ia",
                [
                    "id_domaine_scrapping_produit_ia" => $domain_pid
                ]
            );

            $objet = "[ERREUR][SCRAPPING] - Erreur de scraping des urls fiches produits et non produits";
            $message = 'Bonjour,';
            $message .= "<br><br> Une erreur est survénu lors du scraping des urls fiches produits et non produits du domaine {$domain_pid} - {$nom_domaine_pid}  .";
            $message .= '<br><br>Cordialement';    
            
            envoyer_mail_scripts($objet, "", "script@hellopro.fr" , $message, 1); //PROD
        }
        
        unlink($processScraper);
    }
}

$server_name = $GLOBALS['protocol_http_host_bo'] . "bo.hellopro.fr"; // PROD
// $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-bo.hellopro.fr"; // DEV

/**
 * Verification des scraper en cours de scrapping fp et nfp
 */

$sql_fpnfp = "SELECT
	id_domaine_scrapping_produit_ia, domaine_dspi , info_processus_dspi
FROM domaine_scrapping_produit_ia DSPI
WHERE statut_dspi = 11  AND info_processus_dspi IS NOT NULL";
$res_fpnfp = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_fpnfp) or die(hellopro_mysql_error($sql_fpnfp, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

while($lig_fpnfp = mysqli_fetch_assoc($res_fpnfp))
{
    $domaine = $lig_fpnfp['domaine_dspi'];
    $id_domaine = $lig_fpnfp['id_domaine_scrapping_produit_ia'];

    $fileFP = $_SERVER['DOCUMENT_ROOT'] ."script/fichiers/chatgpt/scrapping_produit/InfoFPDomaine/InfoFP-" . $id_domaine . ".json";

    $info_processus = json_decode($lig_fpnfp['info_processus_dspi'], true);

    //si le fichier existe 
    if(file_exists($fileFP) && !empty($info_processus) && !empty($info_processus["pid_detect_fp_manuel"]) )
    {
        $pid = $info_processus["pid_detect_fp_manuel"];
        $relance_detect_fp = $info_processus["relance_detect_fp"] ?? 0;
 
        $verif_pid =  shell_exec("ps -p $pid");
        
        if(!empty($verif_pid) && !stripos($verif_pid  , $pid ))
        {
            
            $relance_detect_fp++;
            $info_processus = [ "relance_detect_fp" => $relance_detect_fp];
            $data_maj_dfp = [];
            

            //maximum de relance 3
            if($relance_detect_fp <= 3)
            {
                $pendigScraper++;

                $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_process_detect_fiche_produit' . date('Ymdhis') . '.log';
                $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/script/chatgpt/script_process_detect_fiche_produit.php?id_domaine=" . $id_domaine . "&origine=detectMethod' -a '" . $test_temp . "'";
                $retour_shell = shell_exec($command);

                // Récupération du PID du processus lancé
                if (preg_match('/pid (\d+)/', $retour_shell, $matches)) {
                    $pid = $matches[1];                   
                    $info_processus["pid_detect_fp_manuel"] = $pid;
                }

                $objet = "[SCRIPT][SCRAPPING] - RELANCE de la détection manuelle des fiches produits";
                $message = 'Bonjour,';
                $message .= "<br><br> La relance du script de détection manuelle des fiches produits du domaine {$id_domaine} - {$nom_domaine_pid}  est en cours.";
                $message .= "<br><br>Nombre de relance : {$relance_detect_fp} fois.";
                $message .= '<br><br>Cordialement';                    
                envoyer_mail_scripts($objet, "", "script@hellopro.fr" , $message, 1); //PROD
            }
            else
            {  
                $info_processus["pid_detect_fp_manuel"] = "";   
                $data_maj_dfp["statut_dspi"] = 8; // statut erreur

                 //maj statut enqueue => erreur
                sql_update_info(
                    [ 
                        "statut_scraper_eci" => 4
                    ],
                    "enqueue_crawling_ia",
                    [
                        "id_domaine_scrapping_produit_ia" => $id_domaine
                    ]
                );

                $objet = "[ERREUR][SCRAPPING] - Maximum de relance atteint pour la détection manuelle des fiches produits";
                $message = 'Bonjour,';
                $message .= "<br><br> Le script de détection manuelle des fiches produits du domaine {$id_domaine} - {$nom_domaine_pid}  a échoué après 4 tentatives de relance.";
                $message .= '<br><br>Cordialement';                    
                envoyer_mail_scripts($objet, "", "script@hellopro.fr" , $message, 1); //PROD
            }  

            $data_maj_dfp["info_processus_dspi"] = json_encode($info_processus, JSON_UNESCAPED_UNICODE);

            sql_update_info(
                $data_maj_dfp,
                "domaine_scrapping_produit_ia",
                [
                    "id_domaine_scrapping_produit_ia" => $id_domaine
                ]
            );
        }
    }
    
}



//recuperation maximum par crawl
$sql_param = 
    "SELECT
        variable_crawler_pci,
        valeur_pci
    FROM parametre_crawler_ia PCI
    WHERE variable_crawler_pci IN('parallelecrawl' , 'parallelescraper') 
";

$res_param = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_param) or die(hellopro_mysql_error($sql_param, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

$max_crawl = 1;
$max_scraper = 5;
while($lig_param = mysqli_fetch_assoc($res_param))
{
    if($lig_param['variable_crawler_pci'] == 'parallelecrawl')
    {
        $max_crawl = !empty($lig_param['valeur_pci']) ? $lig_param['valeur_pci'] : 1;
    }
    if($lig_param['variable_crawler_pci'] == 'parallelescraper')
    {
        $max_scraper = !empty($lig_param['valeur_pci']) ? $lig_param['valeur_pci'] : 5;
    }

}

if($type == 'crawler')
{
    $scraperLaunced = $max_scraper + 20;
}
if($type == 'scraper')
{
    $crawlerLaunched = $max_crawl + 20;
}


if($pendigScraper >= $max_scraper && $type == 'scraper')
{
    exit;
}
if($pendingCrawler >= $max_crawl && $type == 'crawler')
{
    exit;
}
if($pendigScraper >= $max_scraper  && $pendingCrawler  >= $max_crawl )
{
    exit;
}

$crawlerLaunched = $pendingCrawler;
$scraperLaunced = $pendigScraper;
$repertoire_pid_domaine = $_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/processus/';


##TRAITEMENT DOUBLON DOMAINE
$doublon_nok = $id_domaine_to_delete = [];
$sql_doublon_domaine = "SELECT domaine_dspi, COUNT(*) AS nb_occurences
                    FROM domaine_scrapping_produit_ia 
                    GROUP BY domaine_dspi
                    HAVING COUNT(*) > 1;";
$res_doublon_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_doublon_domaine) or die(hellopro_mysql_error($sql_doublon_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
while ($lig_doublon_domaine = mysqli_fetch_assoc($res_doublon_domaine)) {
    $domaine = $lig_doublon_domaine['domaine_dspi'];
    $nb_occurences = $lig_doublon_domaine['nb_occurences'];

    if ($nb_occurences > 1) {
        //supprimer les doublons et laisser un seul
        $sql_doublon = "SELECT id_domaine_scrapping_produit_ia , statut_dspi
                        FROM domaine_scrapping_produit_ia 
                        WHERE domaine_dspi = '" . hellopro_traitement_donnee_annuaire_bo($domaine) . "'                         
                        ORDER BY id_domaine_scrapping_produit_ia ASC";
        $res_doublon = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_doublon) or die(hellopro_mysql_error($sql_doublon, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $first_domaine = $first_domaine_statut = "";
        while ($lig_doublon = mysqli_fetch_assoc($res_doublon)) {
            if(empty($first_domaine)) {
                $first_domaine = $lig_doublon['id_domaine_scrapping_produit_ia'];
                $first_domaine_statut = $lig_doublon['statut_dspi'];
            } else {
                if($lig_doublon['statut_dspi'] == 1) {
                    $id_domaine_to_delete[$lig_doublon['id_domaine_scrapping_produit_ia']] = $domaine;                   
                } else if($first_domaine_statut == 1) {
                    $id_domaine_to_delete[$first_domaine] = $domaine;  
                    $first_domaine = $lig_doublon['id_domaine_scrapping_produit_ia'];
                    $first_domaine_statut = $lig_doublon['statut_dspi'];
                } else {
                    $doublon_nok[$domaine][] = $lig_doublon['id_domaine_scrapping_produit_ia'];
                    $doublon_nok[$domaine][] = $first_domaine;
                }
                
            }
        }
    }
}

if(!empty($id_domaine_to_delete) || !empty($doublon_nok))
{
    $message_doublon = "";
    foreach ($id_domaine_to_delete as $id_domaine_dbln => $domaine_dbln) {
        $sql_delete_dbln = "DELETE 
                        FROM domaine_scrapping_produit_ia 
                        WHERE 
                            id_domaine_scrapping_produit_ia = '" .  hellopro_traitement_donnee_annuaire_bo($id_domaine_dbln) . "'  ";
        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_delete_dbln) or die(hellopro_mysql_error($sql_delete_dbln, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $message_doublon .= "Domaine doublon supprimé : " . $id_domaine_dbln . " - " . $domaine_dbln . "<br>";
    }

    $message_doublon = count($doublon_nok) > 0 ? $message_doublon . "<br>Liste des domaines doublons non supprimés : <br>" : $message_doublon;
    foreach ($doublon_nok as $domaine_dbln => $ids_domaine_dbln) {
        $ids_domaine_dbln = array_unique($ids_domaine_dbln);
        $message_doublon .= "Domaine doublon non supprimé : " . $domaine_dbln . " - " . implode(", ", $ids_domaine_dbln) . "<br>";
    }
    

    $objet = "[SCRIPT][SCRAPPING] - Doublon de domaine supprimé";
    $message = 'Bonjour,';
    $message .= "<br><br> Le script de suppression des doublons de domaine a été exécuté avec succès.";
    $message .= "<br><br>Liste des domaines doublons supprimés : <br>" . $message_doublon;
    $message .= '<br><br>Cordialement';
    envoyer_mail_scripts($objet, "", "haingatiana@hellopro.fr,randrianjanaka@hellopro.fr,tandriatsiferantsoa@hellopro.fr" , $message, 1); //PROD
}

$sql_enqueue = "SELECT
        ECI.id_enqueue_crawling_ia,
        ECI.id_domaine_scrapping_produit_ia,
        ECI.statut_crawler_eci,
        ECI.statut_scraper_eci,
        DSPI.data_crawling_dspi,
        DSPI.domaine_dspi,
        ECI.method_detect_eci,
        ECI.date_continuation_eci,
        ECI.nb_retry_eci,
        DSPI.id_upload_scrapping_produit_ia
    FROM 
        enqueue_crawling_ia ECI
LEFT JOIN domaine_scrapping_produit_ia DSPI ON DSPI.id_domaine_scrapping_produit_ia = ECI.id_domaine_scrapping_produit_ia
    WHERE 
    ( statut_crawler_eci = 0 OR statut_scraper_eci = 0 or ( statut_crawler_eci = 3 AND date_continuation_eci <= NOW()) 
    or ( statut_crawler_eci = 4 AND nb_retry_eci IN(1,2) ) ) AND ( DSPI.id_upload_dspi NOT IN (25,26,27,28,29,30,31,32) OR DSPI.id_upload_dspi IS NULL )
    ORDER BY  id_enqueue_crawling_ia ASC
";

$res_enqueue = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_enqueue) or die(hellopro_mysql_error($sql_enqueue, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
while($lig_enqueue = mysqli_fetch_assoc($res_enqueue)){
    $id_domaine         = $lig_enqueue['id_domaine_scrapping_produit_ia'];
    $id_eci             = $lig_enqueue['id_enqueue_crawling_ia'];
    $domaine            = $lig_enqueue['domaine_dspi'];
    $method             = $lig_enqueue['method_detect_eci'];
    $statut_crawler_eci = $lig_enqueue['statut_crawler_eci'];
    $statut_scraper_eci = $lig_enqueue['statut_scraper_eci'];
    $date_continuation  = $lig_enqueue['date_continuation_eci'];
    $nb_retry           = $lig_enqueue['nb_retry_eci'];
    $data               = json_decode($lig_enqueue['data_crawling_dspi'] , true);
    $homepage           = !empty($data['homepage']) ? $data['homepage'] : "https://".$domaine; 
    $id_upload_scrapping_produit_ia = $lig_enqueue['id_upload_scrapping_produit_ia'];

    if($scraperLaunced >= $max_scraper && $crawlerLaunched  >= $max_crawl)
    {
        break;
    }

     /**
     * condition scraper:
     * - si le scraper est en attente (0)
     * - si les scraper en cours sont inferieur au max par crawl
     * - si un scraper n'est pas déjà lancé
     * - si les urls fiches produits et non produits sont renseignées     * 
     */
    if( $statut_scraper_eci == 0  && $scraperLaunced < $max_scraper && !empty($data['url_produit']) && !empty($data['url_non_produit']))
    { 

        //TODO lancement shell_exec scrapping fp & nfp
        $data_fpnfp = [
            "id" => $id_domaine,
            "domain" => $domaine,
            "typescraping" => "fpnfp",        
            // "fp" => implode( "," , $data['url_produit']),
            // "nfp" => implode( "," , $data['url_non_produit'])
        ];
        $param_scrapping = [];
        foreach ($data_fpnfp as $key => $value) {
            $param_scrapping[] = $key . "=" . $value;
        }

        $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/shell_scrapping_fpnfp_' . $id_domaine . '_' . date('Ymdhis') . '.log';
        $command_2 = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/shell.php?" . implode( "&" , $param_scrapping) . "' -a '" . $test_temp . "'";
        $b = shell_exec($command_2);

        $retour .= "\n Scraper lancé pour le domaine : " .$id_domaine . " - " . $domaine;
        $scraperLaunced++;
        $domaineScraper = $id_domaine;
        //maj statut enqueue => en cours
        sql_update_info(
            [
                "statut_scraper_eci" => 1
            ],
            "enqueue_crawling_ia",
            [
                "id_domaine_scrapping_produit_ia" => $id_domaine
            ]
        );

    }

    //skipper le crawling si le statut crawl est 3 (partiel terminé) ou 4 (erreur) et date continuation est vide
    if(in_array($statut_crawler_eci , [3,4]) && (empty($date_continuation) || $date_continuation == "0000-00-00 00:00:00"))
    {
        continue;
    }

    //skipper  le crawling si le statut crawl est 4 (erreur) et le nombre de retry n'est pas 1 , 2 
    if($statut_crawler_eci == 4 && !in_array($nb_retry , [1,2]))
    {
        continue;
    }

    /**
     * condition crawler:
     * - si le crawler est en attente (0) ou partiellement terminé (3)
     * - si les rawlers en cours sont inferieur au max par crawl
     * - si le scraper est terminé (2) ou n'en as pas (3) || si le domaine est en cours de scrapping
     * - si le crawler n'y a pas encore de crawler lancé
     */
    //
    if( in_array($statut_crawler_eci , [0 , 3 , 4])  && $crawlerLaunched < $max_crawl && ( in_array($statut_scraper_eci , [2,3])  || $domaineScraper == $id_domaine ) )
    {
        if($method != "auto" && $statut_scraper_eci != "2" && $domaineScraper != $id_domaine )
        {
            continue;
        }

        //verification si fichier pid du domaine 
        $file_pid_domaine = $repertoire_pid_domaine . 'pid_' . $domaine . '.txt';
        if(file_exists($file_pid_domaine))
        {
            continue; //si le fichier pid existe, on skip le domaine
        }
        //verification si le domaine n'est pas déjà en cours de crawling
        if (hasPending("crawler" , $id_domaine) > 0)
        {
            continue; //si le domaine est déjà en cours de crawling, on skip le domaine
        }

        //TODO lancement shell_exec crawling domaine
        $data_crawling = [
            "id" => $id_domaine,
            // "domain" => $domaine,
            // "site" => $homepage,
            "typecrawling" => "link",
            "method" => $method
        ];


        $data_maj_dspi = [];

        //parametre pour drop dataset et requestEnqueue et pour skipper les liens avec un ? et #
        $parametersMap = [
            'dropData' => 'dropdata',
            'skipQuestionMark' => 'skipquestionmark',
            'skipDiez' => 'skipdiez',
            'bypassQuestionMark' => 'bypassquestionmark',
            'bypassDiez' => 'bypassdiez',
            'breakLimit' => 'breaklimit',
            'toKeep' => 'tokeep',
            'toRemove' => 'toremove',
        ];
        
        $paramUnset = ['dropData'];
        
        // Traitement de chaque paramètre
        foreach ($parametersMap as $sourceKey => $targetKey) {
            if (isset($data[$sourceKey]) && !empty($data[$sourceKey])) {
                $data_crawling[$targetKey] = $data[$sourceKey] == 1 ? 1 : $data[$sourceKey];

                if (in_array($sourceKey, $paramUnset)) {
                    unset($data[$sourceKey]);
                }
                
                $data_maj_dspi['data_crawling_dspi'] = json_encode($data, JSON_UNESCAPED_UNICODE);
            }
        }
        
        
        $param_crawling = [];
        foreach ($data_crawling as $key => $value) {
            $param_crawling[] = $key . "=" . $value;
        }

        $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/shell_lancement_crawling_' . $id_domaine . '_' . date('Ymdhis') . '.log';
        $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/shell.php?" . implode( "&" , $param_crawling) . "' -a '" . $test_temp . "'";
        $a = shell_exec($command);

        $retour .= "\n Crawler lancé pour le domaine : " .$id_domaine . " - " . $domaine;

        $crawlerLaunched++;

        //maj statut enqueue => en cours
        $data_maj_eci = [ "statut_crawler_eci" => 1 ];
        if($statut_crawler_eci == 4 && !in_array($id_domaine , $domaine_retry))
        {
            $retry = getNbRetry($id_domaine);
            $data_maj_eci["nb_retry_eci"] = $retry + 1;
        }
        sql_update_info(
            $data_maj_eci,
            "enqueue_crawling_ia",
            [
                "id_domaine_scrapping_produit_ia" => $id_domaine
            ]
        );

        //maj statut domaine => en cours
        if($statut_crawler_eci == 4 )
        {
            $data_maj_dspi["statut_dspi"] = 1;
        }

        if(!empty($data_maj_dspi))
        {
            sql_update_info(
                $data_maj_dspi,
                "domaine_scrapping_produit_ia",
                [
                    "id_domaine_scrapping_produit_ia" => $id_domaine
                ]
            );
        }
    }
    
}


if(!isset($_GET["launcher"]) || empty(trim($_GET["launcher"])))
{
	fin_script($id_script,$retour);
}