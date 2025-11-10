import { useState } from "react"
import { Clipboard, ClipboardCheck } from "lucide-react"
import { toast } from "sonner"
import { cls } from "./utils"
import { Button } from "@/components/ui/button"

export default function Message({ role, children, rawContent }) {
  const isUser = role === "user"
  const [isCopied, setIsCopied] = useState(false)

  const handleCopy = async () => {
    const textToCopy = rawContent || children
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(textToCopy)
      } else {
        const textarea = document.createElement("textarea")
        textarea.value = textToCopy
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
      }
      setIsCopied(true)
      toast.success("Copied to clipboard!")
      setTimeout(() => setIsCopied(false), 2000)
    } catch (err) {
      toast.error("Failed to copy to clipboard.")
    }
  }

  return (
    <div className={cls("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-zinc-900 text-[10px] font-bold text-white dark:bg-white dark:text-zinc-900">
          AI
        </div>
      )}
      <div
        className={cls(
          "max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm",
          isUser
            ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
            : "bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800",
        )}
      >
        {children}
      </div>
      {isUser && (
        <div className="mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-zinc-900 text-[10px] font-bold text-white dark:bg-white dark:text-zinc-900">
          HP
        </div>
      )}
      {!isUser && (
        <div className="flex items-center">
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="h-8 w-8"
          >
            {isCopied ? (
              <ClipboardCheck className="h-4 w-4" />
            ) : (
              <Clipboard className="h-4 w-4" />
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
