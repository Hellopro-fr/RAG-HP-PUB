"use client"

import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight } from "lucide-react"

interface PaginationProps {
  currentPage: number
  totalItems: number
  itemsPerPage: number
  onPageChange: (page: number) => void
}

export default function Pagination({ currentPage, totalItems, itemsPerPage, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(totalItems / itemsPerPage)
  const hasPrevious = currentPage > 1
  const hasNext = currentPage < totalPages

  return (
    <div className="flex justify-center items-center gap-6">
      <Button
        variant="outline"
        disabled={!hasPrevious}
        onClick={() => onPageChange(currentPage - 1)}
        style={hasPrevious ? { borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" } : {}}
      >
        <ChevronLeft className="w-4 h-4 mr-2" />
        Previous
      </Button>

      <div className="text-sm text-gris-primary font-medium px-4 py-2">
        Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
      </div>

      <Button
        variant="outline"
        disabled={!hasNext}
        onClick={() => onPageChange(currentPage + 1)}
        style={hasNext ? { borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" } : {}}
      >
        Next
        <ChevronRight className="w-4 h-4 ml-2" />
      </Button>
    </div>
  )
}
