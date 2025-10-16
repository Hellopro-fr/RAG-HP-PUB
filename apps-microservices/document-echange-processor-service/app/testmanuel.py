import asyncio
import json

from document_echange_processor_service.core.processor import process_document_data_for_templating # Importe la logique métier

# 👇 Remplace par ton JSONL "copié-collé"
jsonl_data = """
{"fournisseur":"JMF BUROTIK","id_fournisseur":"1833442","etat":"Pause","affichage":"Complet","acheteur":"WA QUAN","id_acheteur":"2222926","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2017124135058_dv0000000323_01_devis_20171204.pdf","fichier_source":"upload_file\/2017124135058_dv0000000323_01_devis_20171204.pdf","source":"MCF"}
{"etat":"Pause","affichage":"Complet","acheteur":"BREMOND Michelle","id_acheteur":"2223853","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2017124141742_doc_et_tarif_poubelles_10-2017_qte.pdf","fichier_source":"upload_file\/2017124141742_doc_et_tarif_poubelles_10-2017_qte.pdf","source":"MCF"}
{"etat":"Pause","affichage":"D&eacute;couverte","acheteur":"CMSE","id_acheteur":"2250809","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/20180312162147_devis_aps210.pdf","fichier_source":"upload_file\/20180312162147_devis_aps210.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/20180528152954_devis_n_11753.pdf","fichier_source":"upload_file\/20180528152954_devis_n_11753.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2025106160519_tarif_12_2024_fabrique_d_aliments.pdf","fichier_source":"upload_file\/2025106160519_tarif_12_2024_fabrique_d_aliments.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2025103163450_flyer_a5_jbe_consulting_pack_caisse_e_monnayeur-1.pdf","fichier_source":"upload_file\/2025103163450_flyer_a5_jbe_consulting_pack_caisse_e_monnayeur-1.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/20250926095421_tarif_materiel_07_2025.pdf","fichier_source":"upload_file\/20250926095421_tarif_materiel_07_2025.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2016097164205_ace_solutions_-_proposition_commerciale_peristal.pdf","fichier_source":"upload_file\/2016097164205_ace_solutions_-_proposition_commerciale_peristal.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/sm32500354-m-razabadraibe-p0020570-04931.%20razabadraibe%20-%20p0020570.pdf","fichier_source":"upload_file\/sm32500354-m-razabadraibe-p0020570-04931.%20razabadraibe%20-%20p0020570.pdf","source":"MCF"}
{"acheteur":"Particulier","id_acheteur":"2274807","document":"https:\/\/www.hellopro.fr\/fichiers_communs_bo_front\/rag\/pj\/mon_compte\/upload_file\/2025107154249_brochure_radioguide%CC%81es_jardieuro.pdf","fichier_source":"upload_file\/2025107154249_brochure_radioguide%CC%81es_jardieuro.pdf","source":"MCF"}
"""

async def main():
    for line in jsonl_data.strip().splitlines():
        document = json.loads(line)
        result = await process_document_data_for_templating(document)
        print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
