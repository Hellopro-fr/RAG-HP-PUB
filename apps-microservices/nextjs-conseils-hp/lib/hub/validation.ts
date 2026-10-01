/**
 * Validations minimales des formulaires HUB, côté client.
 *
 * La spec (§9) laisse la validation utilisateur entièrement au front ; le serveur
 * ne fait qu'un contrôle de dernier recours. On reste donc volontairement permissif :
 * l'objectif est de filtrer le vide et le charabia, pas de rejeter des saisies valides.
 */

/**
 * Vérif minimale d'un numéro de téléphone : au moins 6 chiffres.
 * Indicatif (`+33`, `0033`) et séparateurs (espaces, points, tirets, parenthèses)
 * sont ignorés — seuls les chiffres comptent.
 */
export function isValidPhone(value: string): boolean {
  const digits = value.match(/\d/g)?.length ?? 0;
  return digits >= 6;
}
