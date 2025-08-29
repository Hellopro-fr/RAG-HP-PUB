from enum import Enum
from common_utils.autres.CollectionName import CollectionName

# TODO:
# modification url à notifier / à confirmer si à mettre dans .env
CollectionWebhook = {
    CollectionName.PRODUIT    : "https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482",
    CollectionName.DEVIS      : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.CATEGORIE  : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.ECHANGE    : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.FOURNISSEUR: "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.SITEWEB    : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
  }