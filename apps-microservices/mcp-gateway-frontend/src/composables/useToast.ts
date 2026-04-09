import { useToast as usePrimeToast } from 'primevue/usetoast'

export function useToast() {
  const toast = usePrimeToast()

  function success(message: string) {
    toast.add({ severity: 'success', summary: 'Succès', detail: message, life: 3000 })
  }

  function error(message: string) {
    toast.add({ severity: 'error', summary: 'Erreur', detail: message, life: 5000 })
  }

  function info(message: string) {
    toast.add({ severity: 'info', summary: 'Info', detail: message, life: 3000 })
  }

  return { success, error, info }
}
