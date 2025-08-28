from enum import Enum
from common_utils.autres.CollectionName import CollectionName

# TODO:
# modification url à notifier / à confirmer si à mettre dans .env
CollectionWebhook = {
    CollectionName.PRODUIT    : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.DEVIS      : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.CATEGORIE  : "https://webhook.site/c9e32e3d-348e-4df4-9584-f0848d23900b",
    CollectionName.ECHANGE    : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
    CollectionName.FOURNISSEUR: "https://webhook.site/c9e32e3d-348e-4df4-9584-f0848d23900b",
    CollectionName.SITEWEB    : "https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645",
  }