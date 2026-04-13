import { useToast } from './useToast'

function fallbackCopy(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let success = false
  try {
    success = document.execCommand('copy')
  } catch {
    success = false
  }
  document.body.removeChild(textarea)
  return success
}

export function useClipboard() {
  const toast = useToast()

  async function copy(text: string, label = 'Texte') {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        const ok = fallbackCopy(text)
        if (!ok) throw new Error('execCommand failed')
      }
      toast.success(`${label} copié dans le presse-papiers`)
    } catch {
      toast.error('Impossible de copier dans le presse-papiers')
    }
  }

  return { copy }
}
